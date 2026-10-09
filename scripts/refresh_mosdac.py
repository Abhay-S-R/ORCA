"""Refresh the MOSDAC products ORCA reads: INSAT-3DR daily SST, EOS-06 analysed
chlorophyll, EOS-06 scatterometer wind (contract §3.2 / §3.3).

MOSDAC *does* have a plain REST API — `download_api/gettoken` +
`apios/datasets.json` + `download_api/download` — which the official `mdapi.py`
client (https://www.mosdac.gov.in/software/mdapi.zip) drives from a config.json.
This script calls the same three endpoints directly instead of vendoring 778
lines of interactive prompts, because the only things ORCA needs are "what is
new" and "fetch it".

Credentials — free registration at https://www.mosdac.gov.in/ (SAC approves by
hand, so a new account can take days). Put them in the project `.env`:

    MOSDAC_USERNAME=...
    MOSDAC_PASSWORD=...

Files are written under their MOSDAC identifiers, unchanged:
`orca.data.freshness.content_date_from_name()` reads the date straight out of
`3RIMG_17SEP2026_...` and `E06SCTL4AW_2026259_...`, so renaming them would make
ORCA's freshness reporting lie.

Rate limits are the provider's, not ours: 5,000 files/day per user, plus a
per-minute cap. Repeated auth failures lock the account, which is why a 401 here
stops rather than retries.

Usage: python scripts/refresh_mosdac.py [--days N]
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data" / "tier3" / "mosdac"

TOKEN_URL = "https://mosdac.gov.in/download_api/gettoken"
SEARCH_URL = "https://mosdac.gov.in/apios/datasets.json"
DOWNLOAD_URL = "https://mosdac.gov.in/download_api/download"
REFRESH_URL = "https://mosdac.gov.in/download_api/refresh-token"
LOGOUT_URL = "https://mosdac.gov.in/download_api/logout"

# (datasetId, destination directory, what it is)
#
# The ids are not guessable from the filenames and are not published as a list —
# they were found by probing the search endpoint. `E06SCTL4AW_*.nc` comes from
# `E06SCT_L4_AWV`, not `E06SCT_L4_AW`; `E06OCML4AC_*.nc` from `E06OCM_L4_AC`.
# If MOSDAC renames one, probe candidates against SEARCH_URL — a wrong id
# answers 500 "Data unavailable for given parameters", a right one answers 200.
PRODUCTS: tuple[tuple[str, str, str], ...] = (
    ("3RIMG_L3B_SST_DLY", "Sea surface temp", "INSAT-3DR daily SST"),
    ("E06OCM_L4_AC", "chlorophyll", "EOS-06 analysed chlorophyll"),
    # 25 km: the 12 km files on disk came from a stream MOSDAC no longer serves
    # under this id. `geospatial.wind_vectors()` reads lat/lon out of the file,
    # so the coarser grid loads unchanged — only the vector field is sparser.
    ("E06SCT_L4_AWV", "Wind", "EOS-06 scatterometer wind"),
)


def _login(user: str, pw: str) -> tuple[str, str]:
    r = requests.post(TOKEN_URL, json={"username": user, "password": pw}, timeout=60)
    if r.status_code in (400, 401):
        raise SystemExit(f"[ERROR] MOSDAC rejected the login: {r.json().get('error', r.text[:200])}")
    r.raise_for_status()
    body = r.json()
    return body["access_token"], body["refresh_token"]


def _search(dataset_id: str, start: date, end: date) -> list[dict]:
    r = requests.get(SEARCH_URL, params={
        "datasetId": dataset_id,
        "startTime": start.isoformat(),
        "endTime": end.isoformat(),
    }, timeout=90)
    if r.status_code != 200:
        # 500 "Data unavailable for given parameters" is MOSDAC's answer both to a
        # wrong id and to a window it has nothing in — the caller cannot tell them
        # apart, so report the id and move on rather than aborting the whole run.
        print(f"    [WARN] search returned {r.status_code}: {r.json().get('message', [''])[0]}")
        return []
    return r.json().get("entries", [])


def _download(token: str, record_id: str, dest: Path) -> str:
    """Returns "ok", "skip", "expired", or a failure reason.

    Resumes a partial `.part` with a Range request. MOSDAC does not advertise
    `Accept-Ranges`, but it honours `Range` and answers 206 — without resuming,
    the 54 MB scatterometer granules never complete, because the connection drops
    every time and each retry restarts from byte zero.
    """
    if dest.exists():
        return "skip"
    tmp = dest.with_suffix(dest.suffix + ".part")
    have = tmp.stat().st_size if tmp.exists() else 0
    headers = {"Authorization": f"Bearer {token}"}
    if have:
        headers["Range"] = f"bytes={have}-"
    r = requests.get(DOWNLOAD_URL, headers=headers,
                     params={"id": record_id}, stream=True, timeout=120)
    if r.status_code == 401:
        return "expired"
    if r.status_code == 429:
        body = r.json()
        if body.get("type") == "daily_limit":
            raise SystemExit(f"[STOP] {body.get('message')} — resume tomorrow.")
        print(f"    [WAIT] {body.get('message')}")
        time.sleep(20)
        return _download(token, record_id, dest)
    if r.status_code == 416:
        # We already hold as many bytes as the server has; treat the .part as done.
        tmp.replace(dest)
        return "ok"
    if r.status_code not in (200, 206):
        return f"HTTP {r.status_code}"
    if "filename=" not in (r.headers.get("Content-Disposition") or ""):
        return "not on server"
    if r.status_code == 200:
        have = 0  # server ignored the Range and restarted; so must we

    # Write to .part and only rename once the byte count matches the full size.
    # A truncated file renamed into place would be indexed as a fresh granule
    # and then fail to parse.
    total = int(r.headers.get("Content-Length", 0)) + have
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = have
    try:
        with tmp.open("ab" if have else "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 16):
                written += fh.write(chunk)
    except requests.exceptions.RequestException as exc:
        # Keep the .part: the next attempt resumes from here instead of from zero.
        return f"transfer broke at {written}/{total or '?'} ({type(exc).__name__})"
    if total and written != total:
        return f"truncated ({written}/{total} bytes)"
    tmp.replace(dest)
    return "ok"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=7,
                    help="trailing window to fetch (default 7 — MOSDAC publishes L3/L4 in NRT, "
                         "so today alone is often still empty)")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")
    user = os.environ.get("MOSDAC_USERNAME", "").strip()
    pw = os.environ.get("MOSDAC_PASSWORD", "").strip()
    if not (user and pw):
        print("[ERROR] Add MOSDAC_USERNAME and MOSDAC_PASSWORD to .env "
              "(register at https://www.mosdac.gov.in/ — approval is manual).")
        return 1

    access, refresh = _login(user, pw)
    end = datetime.now(UTC).date()
    start = end - timedelta(days=args.days)
    print(f"window {start} -> {end}")

    totals = {"ok": 0, "skip": 0, "fail": 0}
    try:
        for dataset_id, subdir, label in PRODUCTS:
            dest_dir = DATA_ROOT / subdir
            entries = _search(dataset_id, start, end)
            print(f"[*] {label} ({dataset_id}): {len(entries)} granule(s) in window")
            for e in entries:
                dest = dest_dir / e["identifier"]
                # Eight attempts, because a dropped transfer is the normal case
                # here rather than the exceptional one — each one resumes from the
                # .part, so a 54 MB granule crawls forward instead of restarting.
                for attempt in range(8):
                    result = _download(access, e["id"], dest)
                    if result == "expired":
                        body = requests.post(REFRESH_URL, json={"refresh_token": refresh},
                                             timeout=60).json()
                        access, refresh = body["access_token"], body["refresh_token"]
                        continue
                    if result in ("ok", "skip") or result == "not on server":
                        break
                    if attempt < 7:
                        print(f"    [RETRY] {e['identifier']}: {result}")
                        time.sleep(5)
                if result == "ok":
                    totals["ok"] += 1
                    print(f"    + {e['identifier']}")
                elif result == "skip":
                    totals["skip"] += 1
                else:
                    totals["fail"] += 1
                    print(f"    [FAIL] {e['identifier']}: {result}")
    finally:
        requests.post(LOGOUT_URL, json={"username": user}, timeout=30)

    print(f"\n{totals['ok']} downloaded, {totals['skip']} already present, {totals['fail']} failed")
    return 1 if totals["ok"] == 0 and totals["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
