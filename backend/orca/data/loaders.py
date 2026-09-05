"""Loaders over data/ — JSON, CSV, GeoJSON, NetCDF (plan §5 repo layout, S3
Day 3). Every loader here is a thin read; normalization happens in
normalize.py, not in here — a loader's job is "get bytes into memory", not
"fix axis order".
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = Path(os.environ.get("ORCA_DATA_DIR") or REPO_ROOT / "data")


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ponytail: CSV/GeoJSON/NetCDF loaders are one-liners over pandas/geopandas/
# xarray — no wrapper earns its keep until a caller needs more than "read the
# file". Reuse scripts/orca_grid_utils.py for wet-cell snapping on a NetCDF
# grid; do not re-implement it (plan §5 Day 3 note).
#
#   import pandas as pd; pd.read_csv(path)
#   import geopandas as gpd; gpd.read_file(path)
#   import xarray as xr; xr.open_dataset(path)


def cached_weather_path(port: str) -> Path:
    return DATA_DIR / "tier1" / "weather" / f"openmeteo_weather_{port}.json"


def cached_marine_path(port: str) -> Path:
    return DATA_DIR / "tier1" / "ocean" / f"openmeteo_marine_{port}.json"


def cached_lightning_path(port: str) -> Path:
    return DATA_DIR / "tier1" / "hazards" / f"lightning_nowcast_{port}.json"


def cached_ndma_cap_alerts_path() -> Path:
    return DATA_DIR / "tier1" / "hazards" / "ndma_cap_alerts.json"


# Ports with a cached fallback on disk, keyed by the filename suffix used
# throughout data/tier1/ (checked against the actual files, not assumed).
CACHED_WEATHER_PORTS = ("chennai", "kochi", "mumbai", "pamban", "thoothukudi", "visakhapatnam")
CACHED_MARINE_PORTS = ("chennai", "kochi", "mumbai", "pamban", "thoothukudi")  # visakhapatnam has
# no marine cache on disk — a real gap, not an oversight; get_marine_weather's
# fallback degrades to wind-only with a named-missing wave height if hit.

# Port name -> (lat, lon), lazily built from each port's own cached weather
# fixture rather than a second hand-maintained coordinate table — the file
# already carries its own latitude/longitude. Shared by weather_intelligence's
# nearest-cached-port fallback and resolve_place_from_text() below.
_PORT_COORDS: dict[str, tuple[float, float]] | None = None


def port_coordinates() -> dict[str, tuple[float, float]]:
    global _PORT_COORDS
    if _PORT_COORDS is None:
        coords = {}
        for port in CACHED_WEATHER_PORTS:
            path = cached_weather_path(port)
            if path.exists():
                d = load_json(path)
                coords[port] = (d["latitude"], d["longitude"])
        _PORT_COORDS = coords
    return _PORT_COORDS


# The position a query is answered at when it names no place we can resolve and
# carries no GPS fix: roughly 10 nm off Thoothukudi in the Gulf of Mannar, on
# the fishing grounds the pilot region is about.
#
# The old default (8.80, 78.14) was the *town*, which /api/depth reports as
# on_land: true — so every locationless query was answered at a point no vessel
# can occupy, with a seabed depth of null and a shallow-water hazard check that
# could never fire. This one is wet (22 m over GEBCO), clear of the Gulf of
# Mannar Marine National Park boundary, and ~45 nm inside the IMBL, so a
# default-position answer is a plausible one rather than a nonsensical one.
# It is still a *default*: main.py labels it `place_source="regional_default"`
# so nothing downstream mistakes it for the user's actual position.
DEFAULT_LAT, DEFAULT_LON = 8.80, 78.30

# Alternate spellings people actually type, mapped onto a CACHED_WEATHER_PORTS
# name. Not an exhaustive gazetteer — just the ones a real query is likely to use.
_PORT_ALIASES = {"cochin": "kochi", "vizag": "visakhapatnam", "bombay": "mumbai"}


# ---------------------------------------------------------------------------
# Pilot-region gazetteer
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResolvedPlace:
    """Where a query's coordinates came from. `source` is the point of this
    type: the caller has to be able to tell a real resolution from the
    regional default, because a wrong-but-confident position is the most
    dangerous output this system can produce — the IMBL distance at Palk Bay
    is 0.4 nm (DANGER) and at Thoothukudi is 53 nm (GO)."""

    name: str  # display name, as it should appear to a user
    lat: float
    lon: float
    source: str  # "port_fixture" | "tide_station" | "pilot_gazetteer"


def tide_station_coordinates() -> dict[str, tuple[float, float]]:
    """Station name fragments -> coordinates, read from the SoI tide-station
    metadata already on disk rather than re-typed here. The file's
    `station_name` carries the parenthesised alternates people actually use
    ("Cochin Port (Kochi)", "Pamban Pass / Rameswaram"), so splitting on the
    punctuation gives the alias list for free."""
    path = DATA_DIR / "tier1" / "tides" / "soi_tide_stations_metadata.json"
    if not path.exists():
        return {}
    out: dict[str, tuple[float, float]] = {}
    for st in load_json(path).get("stations", []):
        coords = (st["latitude"], st["longitude"])
        for fragment in re.split(r"[(),/]", st.get("station_name", "")):
            name = fragment.strip().lower()
            # "Port", "Pass" etc. on their own are not place names; require a
            # word that could plausibly identify a location.
            if len(name) >= 4 and name not in ("port", "pass", "point", "harbour"):
                out.setdefault(name, coords)
    return out


# Pilot-region places that have no fixture and no tide gauge but appear in
# real queries and in the architecture doc's own scenario table. Coordinates
# are the centroid of the named water body or the landing centre itself, to
# 4 dp — enough for a boundary-proximity answer, which is what they are for.
# This is deliberately a short, auditable, hand-checked list rather than a
# geocoder call: an LLM or a network geocoder guessing a coastline position
# is exactly the fabricated-input failure §5.7 forbids.
#
# Where a place has both a cached weather fixture and an entry here, this
# entry wins. A fixture's coordinate is an Open-Meteo *grid-cell* snap chosen
# to name a file, not a position a vessel occupies, and using one as a
# position has already produced a wrong verdict: the pamban fixture snaps to
# (9.2443, 79.2281), which falls inside this repo's MEDIUM-precision Gulf of
# Mannar Marine National Park polygon (OSM relation 415570), so every "is it
# safe near Pamban" answered NO_GO — Imminent Boundary or MPA Breach. The
# surveyed Pamban Pass position below sits 1.6 nm clear of the same polygon.
_PILOT_GAZETTEER: dict[str, tuple[float, float]] = {
    # Surveyed tide-gauge position (SoI station PAM), not the weather-grid snap.
    "pamban": (9.2833, 79.2000),
    # Harbour approach rather than the town centre: the town itself is on land
    # (GEBCO on_land: true), which makes every depth and wave reading at it
    # meaningless for a query that is really about going to sea from there.
    "thoothukudi": (8.7700, 78.2300),
    "tuticorin": (8.7700, 78.2300),
    "palk bay": (9.5000, 79.2000),
    "palk strait": (9.8000, 79.6000),
    "gulf of mannar": (8.8000, 78.7000),
    "mandapam": (9.2775, 79.1250),
    "dhanushkodi": (9.1500, 79.4167),
    "tiruchendur": (8.4958, 78.1250),
    "kanyakumari": (8.0883, 77.5385),
    "kulasekarapattinam": (8.3931, 78.0472),
    "vembar": (9.1167, 78.4333),
    "kilakarai": (9.2333, 78.7833),
    "nagapattinam": (10.7667, 79.8500),
    "cuddalore": (11.7500, 79.7833),
}


def resolve_place_from_text(text: str) -> ResolvedPlace | None:
    """First pilot-region place named in free text, or None if the text names
    no place we know. Deterministic case-insensitive substring matching over
    three tiers, most-specific first: a port with its own cached fixture, a
    tide-gauge station, then the hand-checked gazetteer above.

    Returning None is a real answer, not a failure: it means "this query
    names no location I can place", and the caller must say so rather than
    quietly answering about somewhere else.

    ponytail: first match wins if a query names more than one place (e.g.
    "compare Chennai and Pamban") — good enough for a single-location query,
    revisit with real multi-location handling if that becomes a real query shape.
    """
    lowered = text.lower()

    # Longest name first within each tier, so "gulf of mannar" wins over a bare
    # "mannar" and "palk strait" is never swallowed by "palk bay".
    for source, table in (
        ("pilot_gazetteer", _PILOT_GAZETTEER),
        ("tide_station", tide_station_coordinates()),
    ):
        for name, (lat, lon) in sorted(table.items(), key=lambda kv: -len(kv[0])):
            if name in lowered:
                return ResolvedPlace(name, lat, lon, source)

    # Weather-fixture coordinates last: they are grid-cell snaps, accurate
    # enough to pick a cache file and not much more (see _PILOT_GAZETTEER).
    coords = port_coordinates()
    for alias, port in _PORT_ALIASES.items():
        if alias in lowered and port in coords:
            lat, lon = coords[port]
            return ResolvedPlace(port, lat, lon, "port_fixture")
    for port, (lat, lon) in coords.items():
        if port in lowered:
            return ResolvedPlace(port, lat, lon, "port_fixture")
    return None
