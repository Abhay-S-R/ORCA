"""Refresh the Open-Meteo offline caches for every place in the gazetteer.

Procurement runbook §A1. Three files per location — marine, weather, lightning —
written where `loaders.cached_*_path()` looks for them, so a network failure
during judging outside Tamil Nadu still answers instead of degrading.

The place list is `loaders._GAZETTEER` itself, not a second hand-kept table:
aliases that share a coordinate ("kochi" / "cochin" / "ernakulam") are fetched
once under one canonical name, because `loaders.port_coordinates()` picks a
cache by nearest coordinate, not by string match.

These caches have a 7-day validity window (coverage guide §8). Re-run before
any demo.

    python scripts/refresh_openmeteo_caches.py            # all locations
    python scripts/refresh_openmeteo_caches.py --limit 3  # smoke test
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from orca.data import loaders

MARINE = (
    "https://marine-api.open-meteo.com/v1/marine",
    (
        "wave_height,wave_direction,wave_period,swell_wave_height,swell_wave_period,"
        "wind_wave_height,ocean_current_velocity,ocean_current_direction"
    ),
)
WEATHER = (
    "https://api.open-meteo.com/v1/forecast",
    (
        "wind_speed_10m,wind_direction_10m,wind_gusts_10m,temperature_2m,"
        "precipitation,visibility"
    ),
)
LIGHTNING = ("https://api.open-meteo.com/v1/forecast", "lightning_potential,cape")


def canonical_places() -> dict[str, tuple[float, float]]:
    """One name per coordinate — the shortest alias, which is the one a cache
    file should be named after."""
    by_coord: dict[tuple[float, float], list[str]] = {}
    for name, coord in loaders._GAZETTEER.items():
        by_coord.setdefault(coord, []).append(name)
    places = {min(names, key=lambda n: (len(n), n)): c for c, names in by_coord.items()}
    # The pilot caches (chennai, kochi, mumbai, visakhapatnam) predate the
    # gazetteer and sit at their own coordinates, so they are not reachable by
    # any gazetteer name. Left out, the six ports the demo actually names are
    # the only ones that stay stale.
    for port, coord in loaders.port_coordinates().items():
        places.setdefault(port, coord)
    return places


def fetch(base: str, hourly: str, lat: float, lon: float) -> dict:
    q = urllib.parse.urlencode(
        {"latitude": lat, "longitude": lon, "hourly": hourly, "timezone": "Asia/Kolkata"}
    )
    with urllib.request.urlopen(f"{base}?{q}", timeout=60) as r:
        return json.loads(r.read())


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def refresh(place: str, lat: float, lon: float) -> None:
    for (base, hourly), path in (
        (MARINE, loaders.cached_marine_path(place)),
        (WEATHER, loaders.cached_weather_path(place)),
        (LIGHTNING, loaders.cached_lightning_path(place)),
    ):
        payload = fetch(base, hourly, lat, lon)
        if not payload.get("hourly", {}).get("time"):
            raise RuntimeError(f"{place}: {base} returned no hourly series")
        write(path, payload)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="fetch only the first N places")
    ap.add_argument("--only", default="", help="comma-separated place names, instead of all")
    ap.add_argument("--sleep", type=float, default=0.3, help="seconds between places")
    args = ap.parse_args()

    places = canonical_places()
    names = [n.strip().lower() for n in args.only.split(",") if n.strip()] or sorted(places)
    names = names[: args.limit or None]
    print(f"{len(loaders._GAZETTEER)} gazetteer entries -> {len(places)} coordinates; "
          f"fetching {len(names)}")

    done, failed = [], []
    for i, name in enumerate(names, 1):
        lat, lon = places[name]
        try:
            refresh(name, lat, lon)
            done.append(name)
            print(f"  [{i}/{len(names)}] {name} ({lat}, {lon})")
        except Exception as exc:  # keep going — one dead place is not a failed run
            failed.append((name, exc))
            print(f"  [{i}/{len(names)}] {name} FAILED: {exc}")
        time.sleep(args.sleep)

    print(f"\n{len(done)} cached, {len(failed)} failed")
    if failed:
        for name, exc in failed:
            print(f"  ! {name}: {exc}")
    print("\nPaste into backend/orca/data/loaders.py:\n")
    print("CACHED_WEATHER_PORTS = (")
    for n in done:
        print(f'    "{n}",')
    print(")")
    print("CACHED_MARINE_PORTS = CACHED_WEATHER_PORTS  # same fetch, same coverage")
    return 1 if failed else 0


def _self_check() -> None:
    """Every gazetteer name maps to exactly one canonical cache file, and each
    canonical name is itself a gazetteer entry."""
    places = canonical_places()
    assert len(set(places.values())) == len(places), "two canonical names share a coordinate"
    assert set(loaders.CACHED_WEATHER_PORTS) <= set(places), "a cached port would never be refreshed"
    gaz = {n for n in places if n in loaders._GAZETTEER}
    assert len(gaz) <= len(loaders._GAZETTEER)
    print(f"self-check ok: {len(loaders._GAZETTEER)} gazetteer names + "
          f"{len(places) - len(gaz)} pilot caches -> {len(places)} cache files")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
    else:
        raise SystemExit(main())
