#!/usr/bin/env python3
"""Refresh the tide predictions behind PS-Q3.

Procurement runbook §C1. `data/tier1/tides/soi_tide_tables_2026.csv` is the file
`ocean_analytics.predict_tides()` reads, and when its last row falls in the past
the function returns `tidal_state: UNKNOWN` / `LOW_DATA` for *every* port — the
query is not degraded, it is unanswerable. Run this before any demo.

Provenance, stated plainly because the filename does not say it: Survey of India
publishes its tide tables as a priced volume, so these predictions are computed
by **Stormglass** harmonics and then shifted onto each station's chart datum.
The shift is `MSL_ABOVE_CHART_DATUM`, derived from the original build by
differencing the two files already on disk (n=36-39 events per station,
sd 0.003 m — the spread is rounding, the offset is constant).

Free tier is 10 requests/day and this spends 5, one per station. Adding the
13 non-pilot ports therefore takes a second day, or a second key.

    python scripts/refresh_tide_tables.py --days 7
    python scripts/refresh_tide_tables.py --self-check   # no network, no quota
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")
IST = timezone(timedelta(hours=5, minutes=30))

# station code -> (cache filename stem, metres of MSL above chart datum)
STATIONS = {
    "TUT": ("thoothukudi", 0.65),
    "PAM": ("pamban", 0.50),
    "CHE": ("chennai", 0.75),
    "KOC": ("kochi", 0.70),
    "BOM": ("mumbai", 2.50),
}
SOURCE = "Survey of India / Stormglass Calibrated Harmonic"
CSV_PATH = DATA / "tier1" / "tides" / "soi_tide_tables_2026.csv"
META_PATH = DATA / "tier1" / "tides" / "soi_tide_stations_metadata.json"
FIELDS = [
    "station_code",
    "station_name",
    "datetime_utc",
    "datetime_ist",
    "tide_event",
    "height_above_chart_datum_m",
    "source",
]


def api_key() -> str:
    key = os.environ.get("STORMGLASS_API_KEY")
    if not key:
        for line in (REPO_ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("STORMGLASS_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("STORMGLASS_API_KEY not set and not found in .env")
    return key


def stations_meta() -> dict[str, dict]:
    return {s["station_code"]: s for s in json.loads(META_PATH.read_text(encoding="utf-8"))["stations"]}


def fetch_extremes(lat: float, lon: float, days: int, key: str) -> dict:
    start = datetime.now(timezone.utc).date()
    q = urllib.parse.urlencode(
        {"lat": lat, "lng": lon, "start": str(start), "end": str(start + timedelta(days=days))}
    )
    req = urllib.request.Request(
        f"https://api.stormglass.io/v2/tide/extremes/point?{q}", headers={"Authorization": key}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def to_rows(code: str, name: str, offset_m: float, payload: dict) -> list[dict]:
    rows = []
    for e in payload["data"]:
        when = datetime.fromisoformat(e["time"]).astimezone(timezone.utc)
        rows.append(
            {
                "station_code": code,
                "station_name": name,
                "datetime_utc": when.strftime("%Y-%m-%d %H:%M:%S UTC"),
                "datetime_ist": when.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                "tide_event": "HIGH TIDE" if e["type"] == "high" else "LOW TIDE",
                "height_above_chart_datum_m": round(e["height"] + offset_m, 2),
                "source": SOURCE,
            }
        )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="forecast horizon to request")
    ap.add_argument("--stations", default="", help="comma-separated codes; default all 5")
    args = ap.parse_args()

    key = api_key()
    meta = stations_meta()
    codes = [c.strip().upper() for c in args.stations.split(",") if c.strip()] or list(STATIONS)

    rows: list[dict] = []
    for code in codes:
        stem, offset = STATIONS[code]
        st = meta[code]
        payload = fetch_extremes(st["latitude"], st["longitude"], args.days, key)
        if not payload.get("data"):
            raise SystemExit(f"{code}: Stormglass returned no extremes ({payload.get('errors')})")
        (DATA / "tier2" / "stormglass" / f"stormglass_tides_{stem}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
        new = to_rows(code, st["station_name"], offset, payload)
        rows.extend(new)
        print(f"  {code} {st['station_name'][:40]:40s} {len(new):3d} extremes "
              f"{new[0]['datetime_utc'][:10]} -> {new[-1]['datetime_utc'][:10]}")

    rows.sort(key=lambda r: (r["station_code"], r["datetime_utc"]))
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    last = max(r["datetime_utc"] for r in rows)
    print(f"\n{len(rows)} rows -> {CSV_PATH.relative_to(REPO_ROOT)}; window ends {last}")
    return 0


def _self_check() -> None:
    """Chart-datum conversion and row shape, without spending API quota."""
    payload = {
        "data": [
            {"time": "2026-09-17T03:43:00+00:00", "height": -0.29, "type": "low"},
            {"time": "2026-09-17T09:48:00+00:00", "height": 0.35, "type": "high"},
        ]
    }
    rows = to_rows("TUT", "V.O. Chidambaranar Port", 0.65, payload)
    assert rows[0]["height_above_chart_datum_m"] == 0.36, rows[0]
    assert rows[1]["height_above_chart_datum_m"] == 1.0, rows[1]
    assert rows[0]["tide_event"] == "LOW TIDE" and rows[1]["tide_event"] == "HIGH TIDE"
    assert rows[0]["datetime_ist"].startswith("2026-09-17 09:13:00")
    assert all(r["height_above_chart_datum_m"] >= 0 for r in rows), "below chart datum"
    assert list(rows[0]) == FIELDS
    print("self-check ok: MSL->chart-datum shift, event mapping, IST conversion, column order")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
