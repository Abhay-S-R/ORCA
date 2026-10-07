"""Dataset loaders for the sea-route engine.

All loaders are @lru_cache(maxsize=1) — read once at first use, held in
memory for the lifetime of the process.  Reload by restarting the server
(or calling <fn>.cache_clear() in tests).

File locations are configurable via module-level constants so the Natural
Earth 10m or GSHHG coastline can be swapped in without code changes — only
the file at SEA_ROUTE_LAND_FILE needs to change.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

log = logging.getLogger("orca.sea_route.datasets")

# ── File locations (overridable via environment) ──────────────────────────────
_DATA_ROOT = Path(__file__).resolve().parents[3] / "data" / "sea_route"

LAND_FILE = Path(os.getenv("SEA_ROUTE_LAND_FILE", str(_DATA_ROOT / "land_india.geojson")))
PORTS_FILE = Path(os.getenv("SEA_ROUTE_PORTS_FILE", str(_DATA_ROOT / "ports.geojson")))
EEZ_FILE = Path(os.getenv("SEA_ROUTE_EEZ_FILE", str(_DATA_ROOT / "india_eez.geojson")))
RESTRICTED_FILE = Path(os.getenv("SEA_ROUTE_RESTRICTED_FILE", str(_DATA_ROOT / "restricted_areas.geojson")))
PROTECTED_FILE = Path(os.getenv("SEA_ROUTE_PROTECTED_FILE", str(_DATA_ROOT / "protected_areas.geojson")))
ZONES_FILE = Path(os.getenv("SEA_ROUTE_ZONES_FILE", str(_DATA_ROOT / "fishing_zones.geojson")))


# ── Domain types ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Port:
    id: str
    name: str
    code: str
    type: str          # "major" | "minor" | "fishing_harbour"
    state: str
    lat: float
    lng: float


@dataclass(frozen=True)
class FishingZone:
    id: str
    name: str
    geometry: BaseGeometry
    entry_lat: float | None
    entry_lng: float | None
    properties: dict[str, Any]


@dataclass(frozen=True)
class RestrictedArea:
    id: str
    name: str
    geometry: BaseGeometry
    mode: str          # "block" | "warn"
    note: str


# ── Loaders ───────────────────────────────────────────────────────────────────

def _load_geojson(path: Path) -> dict:
    if not path.exists():
        log.warning("sea_route: %s not found — run scripts/prep_all.py", path)
        return {"type": "FeatureCollection", "features": []}
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def load_land_polygons() -> tuple[BaseGeometry, ...]:
    """Land polygons clipped to India bbox.  Tuple for immutability."""
    data = _load_geojson(LAND_FILE)
    geoms: list[BaseGeometry] = []
    for feat in data.get("features", []):
        try:
            geoms.append(shape(feat["geometry"]))
        except Exception as exc:
            log.warning("sea_route: skipping bad land feature: %s", exc)
    log.info("sea_route: loaded %d land polygons from %s", len(geoms), LAND_FILE.name)
    return tuple(geoms)


@lru_cache(maxsize=1)
def load_ports() -> tuple[Port, ...]:
    data = _load_geojson(PORTS_FILE)
    ports: list[Port] = []
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        try:
            coords = feat["geometry"]["coordinates"]
            ports.append(Port(
                id=p.get("id", ""),
                name=p.get("name", ""),
                code=p.get("code", ""),
                type=p.get("type", "minor"),
                state=p.get("state", ""),
                lat=float(coords[1]),
                lng=float(coords[0]),
            ))
        except Exception as exc:
            log.warning("sea_route: skipping bad port feature: %s", exc)
    log.info("sea_route: loaded %d ports", len(ports))
    return tuple(ports)


@lru_cache(maxsize=1)
def load_eez_polygon() -> BaseGeometry | None:
    data = _load_geojson(EEZ_FILE)
    feats = data.get("features", [])
    if not feats:
        return None
    from shapely.ops import unary_union
    geoms = [shape(f["geometry"]) for f in feats if f.get("geometry")]
    return unary_union(geoms) if geoms else None


@lru_cache(maxsize=1)
def load_restricted_areas() -> tuple[RestrictedArea, ...]:
    """Maritime boundary lines buffered to 2 nm restricted polygons.

    PLACEHOLDER — replace source geometry with official IMBL data.
    Currently derived from Marine Regions VLIZ boundaries.
    """
    data = _load_geojson(RESTRICTED_FILE)
    areas: list[RestrictedArea] = []
    for i, feat in enumerate(data.get("features", [])):
        p = feat.get("properties", {})
        try:
            areas.append(RestrictedArea(
                id=p.get("id", str(i)),
                name=p.get("name", f"Restricted area {i}"),
                geometry=shape(feat["geometry"]),
                mode=p.get("mode", "block"),
                note=p.get("note", "PLACEHOLDER — replace with official IMBL data"),
            ))
        except Exception as exc:
            log.warning("sea_route: skipping bad restricted area: %s", exc)
    log.info("sea_route: loaded %d restricted areas", len(areas))
    return tuple(areas)


@lru_cache(maxsize=1)
def load_protected_areas() -> tuple[RestrictedArea, ...]:
    """WDPA marine protected areas for India (ISO3=IND, marine)."""
    data = _load_geojson(PROTECTED_FILE)
    areas: list[RestrictedArea] = []
    for i, feat in enumerate(data.get("features", [])):
        p = feat.get("properties", {})
        try:
            areas.append(RestrictedArea(
                id=p.get("WDPAID", str(i)),
                name=p.get("NAME", f"Protected area {i}"),
                geometry=shape(feat["geometry"]),
                mode=p.get("mode", "warn"),  # default warn; set "block" per area to block routing
                note="Protected Planet WDPA marine protected area (IND)",
            ))
        except Exception as exc:
            log.warning("sea_route: skipping bad protected area: %s", exc)
    log.info("sea_route: loaded %d protected areas", len(areas))
    return tuple(areas)


@lru_cache(maxsize=1)
def load_fishing_zones() -> tuple[FishingZone, ...]:
    data = _load_geojson(ZONES_FILE)
    zones: list[FishingZone] = []
    for feat in data.get("features", []):
        p = feat.get("properties", {})
        try:
            zones.append(FishingZone(
                id=p.get("id", ""),
                name=p.get("name", ""),
                geometry=shape(feat["geometry"]),
                entry_lat=p.get("entry_lat") or None,
                entry_lng=p.get("entry_lng") or None,
                properties=p,
            ))
        except Exception as exc:
            log.warning("sea_route: skipping bad zone: %s", exc)
    log.info("sea_route: loaded %d fishing zones", len(zones))
    return tuple(zones)
