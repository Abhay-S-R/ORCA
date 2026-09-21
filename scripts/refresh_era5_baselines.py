"""Fetch the ERA5 reference period behind PS-Q7's word "anomaly", for every
port that has a cached forecast.

`ocean_analytics.wind_anomaly()` compares the peak wind in a port's cached
forecast against a 30-day ERA5 reanalysis baseline read from
`tier1/weather/era5_historical_<port>_30d.json`. Until 2026-09-19 exactly one
such file existed — Thoothukudi — so at all 100-odd other cached ports the
anomaly leg declined with `LOW_DATA`. It declined *honestly* (ORCA will not
compare a forecast against a climatology it does not have), but "no answer" at
every port outside the pilot is still no answer.

Same provider and same units as the forecast it will be compared against:
Open-Meteo's archive API serves ERA5, in km/h, exactly as the forecast endpoint
does. That is deliberate and load-bearing — `wind_anomaly()` does no unit
conversion at all, because a like-for-like comparison is the only kind worth
making. Fetching the baseline from a different provider would put a systematic
offset straight into the z-score.

The window ends `--lag` days back (default 6): ERA5 is a reanalysis and the
last few days are not final. No API key, no account.

    python scripts/refresh_era5_baselines.py               # every cached port
    python scripts/refresh_era5_baselines.py --only kandla,veraval
    python scripts/refresh_era5_baselines.py --self-check  # no network
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from orca.data import loaders

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
# The five daily variables the existing Thoothukudi baseline carries.
# `load_era5_baseline()` reduces whatever is here to mean/std per variable, so
# adding one is free — but wind_speed_10m_max is the one wind_anomaly reads.
DAILY = "wind_speed_10m_max,wind_gusts_10m_max,precipitation_sum,temperature_2m_max,temperature_2m_min"
DAYS = 30


def baseline_path(port: str) -> Path:
    return loaders.DATA_DIR / "tier1" / "weather" / f"era5_historical_{port}_30d.json"


def window(lag_days: int, days: int = DAYS) -> tuple[date, date]:
    end = date.today() - timedelta(days=lag_days)
    return end - timedelta(days=days - 1), end


def fetch(lat: float, lon: float, start: date, end: date) -> dict:
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon,
        "start_date": str(start), "end_date": str(end),
        "daily": DAILY, "timezone": "Asia/Kolkata",
    })
    with urllib.request.urlopen(f"{ARCHIVE}?{q}", timeout=60) as r:
        return json.loads(r.read())


def usable(payload: dict) -> bool:
    """A baseline needs a spread, not just rows: `detect_anomaly` divides by
    sigma, and a constant series would make every forecast look normal."""
    daily = payload.get("daily") or {}
    winds = [v for v in (daily.get("wind_speed_10m_max") or []) if v is not None]
    return len(winds) >= DAYS // 2 and max(winds) > min(winds)


def covers(port: str, start: date) -> bool:
    """True when the file on disk already starts at or after `start` — the
    baseline is a 30-day window, so refetching it daily is pointless."""
    path = baseline_path(port)
    if not path.exists():
        return False
    try:
        dates = json.loads(path.read_text(encoding="utf-8"))["daily"]["time"]
        return date.fromisoformat(dates[0]) >= start
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated port names, instead of all cached ports")
    ap.add_argument("--limit", type=int, default=0, help="fetch only the first N ports")
    ap.add_argument("--lag", type=int, default=6, help="days to stay behind today (ERA5 is not final at the edge)")
    ap.add_argument("--sleep", type=float, default=0.3, help="seconds between ports")
    ap.add_argument("--force", action="store_true", help="refetch even when the window on disk is current")
    args = ap.parse_args()

    coords = loaders.port_coordinates()
    names = [n.strip().lower() for n in args.only.split(",") if n.strip()] or sorted(coords)
    unknown = [n for n in names if n not in coords]
    if unknown:
        raise SystemExit(f"no cached weather fixture for: {', '.join(unknown)}")
    names = names[: args.limit or None]

    start, end = window(args.lag)
    print(f"ERA5 {start} -> {end} ({DAYS} days) for {len(names)} of {len(coords)} cached ports")

    done, skipped, failed = [], [], []
    for i, port in enumerate(names, 1):
        if not args.force and covers(port, start):
            skipped.append(port)
            continue
        lat, lon = coords[port]
        try:
            payload = fetch(lat, lon, start, end)
            if not usable(payload):
                raise RuntimeError("no usable wind series (too few days, or zero variance)")
            baseline_path(port).write_text(json.dumps(payload), encoding="utf-8")
            done.append(port)
            print(f"  [{i}/{len(names)}] {port} ({lat}, {lon})")
        except Exception as exc:  # one dead port is not a failed run
            failed.append((port, exc))
            print(f"  [{i}/{len(names)}] {port} FAILED: {exc}")
        time.sleep(args.sleep)

    print(f"\n{len(done)} written, {len(skipped)} already current, {len(failed)} failed")
    for port, exc in failed:
        print(f"  ! {port}: {exc}")
    return 1 if failed else 0


def _self_check() -> None:
    """Window arithmetic and the usability rule, without network."""
    start, end = window(6)
    assert (end - start).days == DAYS - 1, (start, end)
    assert (date.today() - end).days == 6

    good = {"daily": {"wind_speed_10m_max": [20.0 + (i % 7) for i in range(DAYS)]}}
    assert usable(good)
    # A flat series has no sigma, so every forecast would score z=0 and look
    # normal — that is worse than having no baseline, which at least says so.
    assert not usable({"daily": {"wind_speed_10m_max": [25.0] * DAYS}})
    assert not usable({"daily": {"wind_speed_10m_max": [25.0, 30.0]}})
    assert not usable({})
    assert baseline_path("veraval").name == "era5_historical_veraval_30d.json"
    print(f"self-check ok: {DAYS}-day window ending {end}, variance and length rules")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
