"""Loaders over data/ — JSON, CSV, GeoJSON, NetCDF (plan §5 repo layout, S3
Day 3). Every loader here is a thin read; normalization happens in
normalize.py, not in here — a loader's job is "get bytes into memory", not
"fix axis order".
"""
from __future__ import annotations

import json
import os
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
# nearest-cached-port fallback and resolve_port_from_text() below.
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


# Alternate spellings people actually type, mapped onto a CACHED_WEATHER_PORTS
# name. Not an exhaustive gazetteer — just the ones a real query is likely to use.
_PORT_ALIASES = {"cochin": "kochi", "vizag": "visakhapatnam", "bombay": "mumbai"}


def resolve_port_from_text(text: str) -> tuple[str, float, float] | None:
    """First known pilot-region port (or alias) named in free text ->
    (port, lat, lon), or None if no port is mentioned. Plain case-insensitive
    substring match over the same 6 ports Agent 4 already falls back to —
    this decides which coordinates a query is *about*, not a safety verdict,
    so it stays deterministic text matching rather than an LLM/NLP call.

    ponytail: first match wins if a query names more than one port (e.g.
    "compare Chennai and Pamban") — good enough for a single-location query,
    revisit with real multi-location handling if that becomes a real query shape.
    """
    lowered = text.lower()
    coords = port_coordinates()
    for alias, port in _PORT_ALIASES.items():
        if alias in lowered and port in coords:
            lat, lon = coords[port]
            return port, lat, lon
    for port, (lat, lon) in coords.items():
        if port in lowered:
            return port, lat, lon
    return None
