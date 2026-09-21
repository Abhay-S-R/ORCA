"""Refresh the Global Fishing Watch AIS vessel sample (`gfw_ais`, WEEKLY).

API token required — free registration at
https://globalfishingwatch.org/our-apis/tokens (choose the "Vessels API" and
"4Wings API" scopes). Put it in the project `.env`:

    GFW_API_KEY=eyJhbGciOi...

(`GFW_API_TOKEN` in the real environment also works and wins, so a scheduler can
inject it without a file). `.env` is gitignored and the token is never written
anywhere else, so it cannot end up in a commit.

ORCA cites this as fleet-activity *context* — where vessels of a given gear type
generally operate — not as live tracking of a particular hull, which is why the
contract classes it WEEKLY (§3.3).

Usage: python scripts/refresh_gfw_ais.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "data" / "tier2" / "gfw" / "gfw_vessels_search_sample.json"

API = "https://gateway.api.globalfishingwatch.org/v3/vessels/search"
PARAMS = {
    "query": "INDIA",
    "datasets[0]": "public-global-vessel-identity:latest",
    "limit": 5,
    "includes[0]": "MATCH_CRITERIA",
    "includes[1]": "OWNERSHIP",
}


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
    # Two names on purpose: ORCA's `.env` uses GFW_API_KEY, while a scheduler or CI
    # job injects GFW_API_TOKEN. The real environment wins over the file.
    token = (os.environ.get("GFW_API_TOKEN") or os.environ.get("GFW_API_KEY") or "").strip()
    if not token:
        print("[ERROR] No GFW token.\n"
              "  1. Register at https://globalfishingwatch.org/our-apis/tokens\n"
              "  2. Add GFW_API_KEY=your_token_here to .env\n"
              "  3. Re-run this script.")
        return 1

    try:
        resp = requests.get(API, params=PARAMS, timeout=60,
                            headers={"Authorization": f"Bearer {token}",
                                     "User-Agent": "ORCA/1.0 (SIH26176)"})
    except requests.exceptions.RequestException as exc:
        print(f"[ERROR] GFW request failed: {exc}")
        return 1

    if resp.status_code in (401, 403):
        print(f"[ERROR] GFW rejected the token ({resp.status_code}). Check it has the "
              "Vessels API scope and has not expired.")
        return 1
    if resp.status_code != 200:
        print(f"[ERROR] GFW returned {resp.status_code}: {resp.text[:300]}")
        return 1

    payload = resp.json()
    entries = payload.get("entries", [])
    if not entries:
        # Overwriting with an empty result would erase the cited sample.
        print("[ERROR] GFW returned no entries — leaving the existing file alone.")
        return 1

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"{len(entries)} vessels (of {payload.get('total', '?')} matching) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
