"""Refresh the tide predictions behind PS-Q3, for every major Indian port.

Procurement runbook §C1. `data/tier1/tides/soi_tide_tables_2026.csv` is the file
`ocean_analytics.predict_tides()` reads, and when its last row falls in the past
the function returns `tidal_state: UNKNOWN` / `LOW_DATA` for *every* port — the
query is not degraded, it is unanswerable. Run this before any demo.

Provenance, stated plainly because the filename does not say it: Survey of India
publishes its tide tables as a priced volume, so these predictions are computed
by **Stormglass** harmonics and then shifted onto each station's chart datum.
The shift is `msl_above_chart_datum_m`, derived from the original build by
differencing the two files already on disk (n=36-39 events per station,
sd 0.003 m — the spread is rounding, the offset is constant).

**Only the five pilot ports have that shift.** For the nine ports added on
2026-09-19 nobody has published a chart-datum offset we can cite, so none is
invented: those stations get the Stormglass cache and nothing else, and
`predict_tides()` serves them through its declared rung-2 fallback, which labels
the heights **mean sea level** and drops confidence to MEDIUM. Times and the
high/low ordering are right at all fourteen ports; the *height* at the nine is
on a different datum and says so all the way out to the API response. A tide
height quoted on the wrong datum is a grounding, so it is better to be a metre
vague out loud than a metre wrong in silence.

This script also writes `soi_tide_stations_metadata.json`, which used to exist
only as a hand-maintained file inside gitignored `data/` — meaning a fresh clone
had no tide stations at all, and `loaders.tide_station_coordinates()` (the place
resolver) silently lost every port's aliases.

Stormglass's free tier is 10 requests/day and there are 14 stations, so a
station is refetched only when its cache no longer reaches `--min-horizon` days
ahead (default 3). A daily cron therefore spends 0-3 requests on a normal
morning, and a cold start fills itself over two days.

    python scripts/refresh_tide_tables.py --days 7
    python scripts/refresh_tide_tables.py --stations KAN,OKH --force
    python scripts/refresh_tide_tables.py --self-check   # no network, no quota
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")
IST = timezone(timedelta(hours=5, minutes=30))

# The station roster. `msl_above_chart_datum_m` is the metres of MSL above
# chart datum used to put Stormglass's MSL heights onto the SOI table's datum;
# `None` means no published offset exists for that port, so it gets no row in
# the chart-datum CSV and is answered from the MSL cache instead.
#
# Everything else here is the station metadata file's content: coordinates are
# the port's own position, and the spring/neap/MHWS figures are the published
# tidal planes for the five pilot ports. The nine ports added on 2026-09-19
# carry no such figures, so `spring_neap` comes back UNKNOWN for them rather
# than being classified off a guessed range.
STATIONS: dict[str, dict] = {
    "TUT": {
        "station_name": "V.O. Chidambaranar Port (Thoothukudi / Tuticorin)",
        "state": "Tamil Nadu", "latitude": 8.75, "longitude": 78.1833,
        "datum": "Chart Datum (Lowest Astronomical Tide)",
        "stormglass_stem": "thoothukudi", "msl_above_chart_datum_m": 0.65,
        "spring_range_m": 0.82, "neap_range_m": 0.35,
        "mhws_m": 1.15, "mhwn_m": 0.85, "mlwn_m": 0.5, "mlws_m": 0.2,
        "tide_type": "Semi-diurnal with diurnal inequality",
    },
    "PAM": {
        "station_name": "Pamban Pass / Rameswaram",
        "state": "Tamil Nadu", "latitude": 9.2833, "longitude": 79.2,
        "datum": "Chart Datum (LAT)",
        "stormglass_stem": "pamban", "msl_above_chart_datum_m": 0.50,
        "spring_range_m": 0.7, "neap_range_m": 0.25,
        "mhws_m": 0.95, "mhwn_m": 0.7, "mlwn_m": 0.45, "mlws_m": 0.15,
        "tide_type": "Semi-diurnal (Complex shallow water harmonics)",
    },
    "CHE": {
        "station_name": "Chennai Port",
        "state": "Tamil Nadu", "latitude": 13.0833, "longitude": 80.3,
        "datum": "Chart Datum (LAT)",
        "stormglass_stem": "chennai", "msl_above_chart_datum_m": 0.75,
        "spring_range_m": 1.1, "neap_range_m": 0.55,
        "mhws_m": 1.35, "mhwn_m": 1.05, "mlwn_m": 0.55, "mlws_m": 0.25,
        "tide_type": "Semi-diurnal",
    },
    "KOC": {
        "station_name": "Cochin Port (Kochi)",
        "state": "Kerala", "latitude": 9.9667, "longitude": 76.2667,
        "datum": "Chart Datum (LAT)",
        "stormglass_stem": "kochi", "msl_above_chart_datum_m": 0.70,
        "spring_range_m": 0.9, "neap_range_m": 0.4,
        "mhws_m": 1.2, "mhwn_m": 0.95, "mlwn_m": 0.55, "mlws_m": 0.3,
        "tide_type": "Mixed Semi-diurnal",
    },
    "BOM": {
        "station_name": "Mumbai (Apollo Bunder / JNPT)",
        "state": "Maharashtra", "latitude": 18.9167, "longitude": 72.8333,
        "datum": "Chart Datum (LAT)",
        "stormglass_stem": "mumbai", "msl_above_chart_datum_m": 2.50,
        "spring_range_m": 4.4, "neap_range_m": 2.1,
        "mhws_m": 4.9, "mhwn_m": 3.7, "mlwn_m": 1.6, "mlws_m": 0.5,
        "tide_type": "Semi-diurnal (Large macrotidal range)",
    },
    # --- added 2026-09-19, all-India coverage (DLC R-INDIA-*) ---------------
    "KAN": {
        "station_name": "Deendayal Port (Kandla)",
        "state": "Gujarat", "latitude": 22.98, "longitude": 70.22,
        "stormglass_stem": "kandla",
    },
    "OKH": {
        "station_name": "Okha Port",
        "state": "Gujarat", "latitude": 22.47, "longitude": 69.07,
        "stormglass_stem": "okha",
    },
    "VER": {
        "station_name": "Veraval Fishing Harbour",
        "state": "Gujarat", "latitude": 20.9, "longitude": 70.36,
        "stormglass_stem": "veraval",
    },
    "MRM": {
        "station_name": "Mormugao Port (Vasco da Gama)",
        "state": "Goa", "latitude": 15.4, "longitude": 73.8,
        "stormglass_stem": "mormugao",
    },
    "NMP": {
        "station_name": "New Mangalore Port (Panambur)",
        "state": "Karnataka", "latitude": 12.92, "longitude": 74.8,
        "stormglass_stem": "mangalore",
    },
    "VIZ": {
        "station_name": "Visakhapatnam Port",
        "state": "Andhra Pradesh", "latitude": 17.6833, "longitude": 83.2833,
        "stormglass_stem": "visakhapatnam",
    },
    "PRD": {
        "station_name": "Paradip Port",
        "state": "Odisha", "latitude": 20.26, "longitude": 86.68,
        "stormglass_stem": "paradip",
    },
    "HDA": {
        "station_name": "Haldia Dock Complex",
        "state": "West Bengal", "latitude": 22.03, "longitude": 88.09,
        "stormglass_stem": "haldia",
    },
    "PBL": {
        "station_name": "Port Blair (Chatham)",
        "state": "Andaman & Nicobar Islands", "latitude": 11.68, "longitude": 92.75,
        "stormglass_stem": "portblair",
    },
}
# What a station without a published chart-datum offset gets instead. Kept as a
# sentence rather than a code, because it is read by a person deciding whether
# to trust a number.
MSL_ONLY_DATUM = (
    "Mean sea level (Stormglass harmonic prediction; no published chart-datum "
    "offset for this port, so heights are NOT comparable with the chart-datum ports)"
)
SOURCE = "Survey of India / Stormglass Calibrated Harmonic"
CSV_PATH = DATA / "tier1" / "tides" / "soi_tide_tables_2026.csv"
META_PATH = DATA / "tier1" / "tides" / "soi_tide_stations_metadata.json"
CACHE_DIR = DATA / "tier2" / "stormglass"
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


def station_metadata() -> dict:
    """The metadata file's content, derived from STATIONS rather than kept as a
    separate hand-edited artefact inside gitignored `data/`."""
    stations = []
    for code, st in STATIONS.items():
        row = {"station_code": code, **st}
        row.setdefault("datum", MSL_ONLY_DATUM)
        row.setdefault("msl_above_chart_datum_m", None)
        stations.append(row)
    return {"stations": stations}


def write_metadata() -> None:
    META_PATH.parent.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(station_metadata(), indent=2), encoding="utf-8")


def cache_path(code: str) -> Path:
    return CACHE_DIR / f"stormglass_tides_{STATIONS[code]['stormglass_stem']}.json"


def cache_horizon_days(code: str, now: datetime) -> float:
    """How many days ahead the station's cached extremes still reach. Negative
    (or absent) means the cache is spent and the station must be refetched —
    this is the whole quota strategy: 14 ports, 10 requests a day."""
    path = cache_path(code)
    if not path.exists():
        return -1.0
    try:
        data = json.loads(path.read_text(encoding="utf-8")).get("data") or []
        last = max(datetime.fromisoformat(e["time"]) for e in data)
    except (ValueError, KeyError, json.JSONDecodeError):
        return -1.0
    return (last.astimezone(UTC) - now).total_seconds() / 86400


def fetch_extremes(lat: float, lon: float, days: int, key: str) -> dict:
    start = datetime.now(UTC).date()
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
        when = datetime.fromisoformat(e["time"]).astimezone(UTC)
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


def read_existing_rows() -> list[dict]:
    if not CSV_PATH.exists():
        return []
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r.get("station_code") in STATIONS]


def write_csv(rows: list[dict]) -> None:
    rows.sort(key=lambda r: (r["station_code"], r["datetime_utc"]))
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7, help="forecast horizon to request")
    ap.add_argument("--stations", default="", help="comma-separated codes; default all")
    ap.add_argument("--min-horizon", type=float, default=3.0,
                    help="refetch a station only when its cache reaches less than this many days ahead")
    ap.add_argument("--force", action="store_true", help="refetch even if the cache is still good")
    args = ap.parse_args()

    key = api_key()
    now = datetime.now(UTC)
    write_metadata()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    codes = [c.strip().upper() for c in args.stations.split(",") if c.strip()] or list(STATIONS)
    unknown = [c for c in codes if c not in STATIONS]
    if unknown:
        raise SystemExit(f"unknown station code(s): {', '.join(unknown)}")

    fresh: dict[str, list[dict]] = {}   # code -> rows fetched this run
    fetched: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for code in codes:
        st = STATIONS[code]
        horizon = cache_horizon_days(code, now)
        if not args.force and horizon >= args.min_horizon:
            skipped.append(code)
            print(f"  {code} {st['station_name'][:38]:38s} cache good for {horizon:.1f}d, skipped")
            continue
        try:
            payload = fetch_extremes(st["latitude"], st["longitude"], args.days, key)
        except urllib.error.HTTPError as exc:
            # 402/429 is the free tier's daily cap. Stop rather than burn the
            # rest of the list on the same error; what is already on disk stays.
            failed.append(code)
            print(f"  {code}: HTTP {exc.code} {exc.reason}", file=sys.stderr)
            if exc.code in (402, 429):
                print("  daily quota reached — rerun tomorrow, nothing is lost", file=sys.stderr)
                break
            continue
        if not payload.get("data"):
            failed.append(code)
            print(f"  {code}: Stormglass returned no extremes ({payload.get('errors')})", file=sys.stderr)
            continue

        cache_path(code).write_text(json.dumps(payload), encoding="utf-8")
        fetched.append(code)
        offset = st.get("msl_above_chart_datum_m")
        span = f"{payload['data'][0]['time'][:10]} -> {payload['data'][-1]['time'][:10]}"
        if offset is None:
            print(f"  {code} {st['station_name'][:38]:38s} {len(payload['data']):3d} extremes "
                  f"{span}  [MSL cache only]")
        else:
            fresh[code] = to_rows(code, st["station_name"], offset, payload)
            print(f"  {code} {st['station_name'][:38]:38s} {len(fresh[code]):3d} extremes {span}")

    # Merge rather than overwrite: a partial run (quota, one port down) must not
    # delete the rows of the ports it never reached.
    merged = [r for r in read_existing_rows() if r["station_code"] not in fresh]
    merged += [r for rs in fresh.values() for r in rs]
    if merged:
        write_csv(merged)
        last = max(r["datetime_utc"] for r in merged)
        print(f"\n{len(merged)} rows -> {CSV_PATH.relative_to(REPO_ROOT)}; window ends {last}")
    on_cd = sum(1 for s in STATIONS.values() if s.get("msl_above_chart_datum_m") is not None)
    print(f"{len(STATIONS)} stations -> {META_PATH.relative_to(REPO_ROOT)} "
          f"({on_cd} on chart datum, {len(STATIONS) - on_cd} on MSL)")
    print(f"fetched {len(fetched)}, cache still good {len(skipped)}, failed {len(failed)}")
    return 1 if failed else 0


def _self_check() -> None:
    """Chart-datum conversion, row shape and the roster's own invariants,
    without spending API quota."""
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

    meta = {s["station_code"]: s for s in station_metadata()["stations"]}
    assert len(meta) == len(STATIONS) == 14, sorted(meta)
    stems = [s["stormglass_stem"] for s in meta.values()]
    assert len(set(stems)) == len(stems), "two stations would share one cache file"
    for code, s in meta.items():
        assert 6 <= s["latitude"] <= 24 and 68 <= s["longitude"] <= 94, code
        # The point of the whole datum split: a station with no published
        # offset must never be labelled chart datum.
        if s["msl_above_chart_datum_m"] is None:
            assert s["datum"] == MSL_ONLY_DATUM, code
        else:
            assert "Chart Datum" in s["datum"], code
    print(f"self-check ok: MSL->chart-datum shift, event mapping, IST conversion, "
          f"column order, {len(meta)}-station roster")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
