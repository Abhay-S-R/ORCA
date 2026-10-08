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
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

log = logging.getLogger("orca.sea_route.datasets")

# ── File locations (overridable via environment) ──────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DATA_ROOT = _REPO_ROOT / "data"

LAND_FILE = Path(os.getenv("SEA_ROUTE_LAND_FILE", str(_DATA_ROOT / "sea_route" / "land_india.geojson")))
EEZ_FILE = Path(os.getenv("SEA_ROUTE_EEZ_FILE", str(_DATA_ROOT / "sea_route" / "india_eez.geojson")))
RESTRICTED_FILE = Path(os.getenv("SEA_ROUTE_RESTRICTED_FILE", str(_DATA_ROOT / "sea_route" / "restricted_areas.geojson")))
PROTECTED_FILE = Path(os.getenv("SEA_ROUTE_PROTECTED_FILE", str(_DATA_ROOT / "sea_route" / "protected_areas.geojson")))

# Primary data folder sources — INCOIS PFZ and tier-1 ocean marine feeds
PFZ_FILE = Path(os.getenv("SEA_ROUTE_PFZ_FILE", str(_DATA_ROOT / "incois_osf_pfz" / "pfz" / "all_india_pfz_advisories.geojson")))
OCEAN_DIR = _DATA_ROOT / "tier1" / "ocean"

SEED_MAJOR: list[dict[str, Any]] = [
    {"id": "IN_KAN", "name": "Kandla", "code": "INKLA", "type": "major", "state": "Gujarat", "lat": 22.98, "lng": 70.22},
    {"id": "IN_MUN", "name": "Mundra", "code": "INMUN", "type": "major", "state": "Gujarat", "lat": 22.84, "lng": 69.70},
    {"id": "IN_JNP", "name": "JNPT / Nhava Sheva", "code": "INJNP", "type": "major", "state": "Maharashtra", "lat": 18.95, "lng": 72.95},
    {"id": "IN_BOM", "name": "Mumbai Port", "code": "INBOM", "type": "major", "state": "Maharashtra", "lat": 18.93, "lng": 72.84},
    {"id": "IN_MOR", "name": "Mormugao", "code": "INMRM", "type": "major", "state": "Goa", "lat": 15.41, "lng": 73.80},
    {"id": "IN_NMG", "name": "New Mangalore", "code": "INMNG", "type": "major", "state": "Karnataka", "lat": 12.92, "lng": 74.82},
    {"id": "IN_KOC", "name": "Kochi", "code": "INCOK", "type": "major", "state": "Kerala", "lat": 9.97, "lng": 76.27},
    {"id": "IN_TUT", "name": "Tuticorin / Thoothukudi", "code": "INTUT", "type": "major", "state": "Tamil Nadu", "lat": 8.76, "lng": 78.14},
    {"id": "IN_CHE", "name": "Chennai", "code": "INMAA", "type": "major", "state": "Tamil Nadu", "lat": 13.10, "lng": 80.29},
    {"id": "IN_VIZ", "name": "Visakhapatnam", "code": "INVTZ", "type": "major", "state": "Andhra Pradesh", "lat": 17.69, "lng": 83.28},
    {"id": "IN_PAR", "name": "Paradip", "code": "INPRD", "type": "major", "state": "Odisha", "lat": 20.32, "lng": 86.61},
    {"id": "IN_HAL", "name": "Haldia", "code": "INHLD", "type": "major", "state": "West Bengal", "lat": 22.05, "lng": 88.07},
    {"id": "IN_IXZ", "name": "Port Blair", "code": "INIXZ", "type": "major", "state": "Andaman & Nicobar", "lat": 11.67, "lng": 92.73},
    {"id": "IN_KVT", "name": "Kavaratti", "code": "INKVT", "type": "minor", "state": "Lakshadweep", "lat": 10.57, "lng": 72.64},
]


def _guess_coastal_state(lat: float, lng: float) -> str:
    if 10.0 <= lat <= 13.5 and 92.0 <= lng <= 94.0:
        return "Andaman & Nicobar"
    if 8.0 <= lat <= 12.0 and 71.5 <= lng <= 74.0:
        return "Lakshadweep"
    if 20.0 <= lat <= 24.0 and 68.0 <= lng <= 73.0:
        return "Gujarat"
    if 15.8 <= lat <= 20.2 and 72.5 <= lng <= 73.5:
        return "Maharashtra"
    if 14.8 <= lat <= 15.8 and 73.6 <= lng <= 74.3:
        return "Goa"
    if 12.5 <= lat <= 15.0 and 74.0 <= lng <= 75.0:
        return "Karnataka"
    if 8.2 <= lat <= 12.8 and 74.8 <= lng <= 77.2:
        return "Kerala"
    if 8.0 <= lat <= 13.5 and 77.2 <= lng <= 80.5:
        return "Tamil Nadu"
    if 13.5 <= lat <= 19.2 and 79.5 <= lng <= 85.0:
        return "Andhra Pradesh"
    if 19.0 <= lat <= 22.0 and 84.5 <= lng <= 87.5:
        return "Odisha"
    if 21.0 <= lat <= 22.6 and 87.5 <= lng <= 89.2:
        return "West Bengal"
    return "India"


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
        log.warning("sea_route: %s not found", path)
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
    """Load all ports and harbours directly from data/tier1/ocean and major seeds."""
    ports: list[Port] = []
    seen_ids: set[str] = set()

    for p in SEED_MAJOR:
        ports.append(Port(
            id=str(p["id"]),
            name=str(p["name"]),
            code=str(p["code"]),
            type=str(p["type"]),
            state=str(p["state"]),
            lat=float(p["lat"]),
            lng=float(p["lng"]),
        ))
        seen_ids.add(str(p["id"]).lower())

    pfz_centers: dict[str, str] = {}
    if PFZ_FILE.exists():
        try:
            with PFZ_FILE.open(encoding="utf-8") as fp:
                pfz_raw = json.load(fp)
            for f in pfz_raw.get("features", []):
                pr = f.get("properties", {})
                lc = pr.get("landing_center", "").lower()
                sec = pr.get("sector", "").title()
                if lc and sec:
                    pfz_centers[lc] = sec
        except Exception:
            pass

    water_keywords = {
        "sea", "ocean", "bay of bengal", "gulf of", "palk strait", "coast",
        "tamil nadu", "karnataka", "gujarat", "west bengal", "தமிழ்நாடு",
    }
    known_stems = {p.name.lower().split()[0] for p in ports}

    if OCEAN_DIR.exists():
        for mf in sorted(OCEAN_DIR.glob("openmeteo_marine_*.json")):
            stem = mf.stem.replace("openmeteo_marine_", "").lower()
            if any(wb in stem for wb in water_keywords):
                continue
            if any(k in stem for k in known_stems):
                continue
            clean_id = re.sub(r"[^a-zA-Z0-9]", "_", stem).strip("_").lower()
            if not clean_id:
                continue
            pid = f"in_{clean_id}"
            if pid in seen_ids:
                continue
            try:
                with mf.open(encoding="utf-8") as fp:
                    d = json.load(fp)
                lat = float(d["latitude"])
                lng = float(d["longitude"])
                if not (5.0 <= lat <= 24.0 and 66.0 <= lng <= 95.0):
                    continue
                state = pfz_centers.get(stem) or _guess_coastal_state(lat, lng)
                is_fh = (
                    stem in pfz_centers
                    or any(x in stem for x in ["harbour", "harbor", "patnam", "kuppam", "thottam", "cr"])
                )
                ptype = "fishing_harbour" if is_fh else "minor"
                name = stem.replace("_", " ").title()
                ports.append(Port(
                    id=pid,
                    name=name,
                    code="",
                    type=ptype,
                    state=state,
                    lat=round(lat, 4),
                    lng=round(lng, 4),
                ))
                seen_ids.add(pid)
            except Exception:
                pass

    log.info("sea_route: loaded %d ports from data folder", len(ports))
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


# Regional offshore fishing grounds across India for comprehensive coastal coverage
PAN_INDIA_FISHING_GROUNDS: list[dict[str, Any]] = [
    {"id": "FZ_GUJ_01", "name": "Veraval Offshore Bank (Gujarat)", "sector": "Gujarat", "lat": 20.65, "lng": 70.15, "depth_m": "35-50", "distance_km": "25-35"},
    {"id": "FZ_GUJ_02", "name": "Okha Pelagic Ground (Gujarat)", "sector": "Gujarat", "lat": 22.55, "lng": 68.85, "depth_m": "40-60", "distance_km": "20-30"},
    {"id": "FZ_MAH_01", "name": "Bombay High South Fishing Grounds (Maharashtra)", "sector": "Maharashtra", "lat": 19.10, "lng": 71.80, "depth_m": "45-65", "distance_km": "50-70"},
    {"id": "FZ_GOA_01", "name": "Aguada Trawling Grounds (Goa)", "sector": "Goa", "lat": 15.30, "lng": 73.50, "depth_m": "30-45", "distance_km": "18-25"},
    {"id": "FZ_KAR_01", "name": "Mangalore Offshore Trench (Karnataka)", "sector": "Karnataka", "lat": 12.75, "lng": 74.40, "depth_m": "40-60", "distance_km": "22-30"},
    {"id": "FZ_KAR_02", "name": "Malpe Deep Sea Ground (Karnataka)", "sector": "Karnataka", "lat": 13.35, "lng": 74.30, "depth_m": "35-55", "distance_km": "20-28"},
    {"id": "FZ_KER_01", "name": "Wadge Bank / Kollam Offshore (Kerala)", "sector": "Kerala", "lat": 8.40, "lng": 76.50, "depth_m": "50-80", "distance_km": "25-40"},
    {"id": "FZ_KER_02", "name": "Kochi Offshore Pelagic Zone (Kerala)", "sector": "Kerala", "lat": 9.90, "lng": 75.80, "depth_m": "40-65", "distance_km": "20-35"},
    {"id": "FZ_TN_01", "name": "Nagapattinam Deep Waters (Tamil Nadu)", "sector": "Tamil Nadu", "lat": 10.70, "lng": 80.20, "depth_m": "35-60", "distance_km": "25-35"},
    {"id": "FZ_TN_02", "name": "Gulf of Mannar Fishing Zone (Tamil Nadu)", "sector": "Tamil Nadu", "lat": 8.85, "lng": 78.45, "depth_m": "25-45", "distance_km": "15-25"},
    {"id": "FZ_TN_03", "name": "Chennai Offshore Pelagic (Tamil Nadu)", "sector": "Tamil Nadu", "lat": 13.15, "lng": 80.65, "depth_m": "40-70", "distance_km": "20-30"},
    {"id": "FZ_AP_01", "name": "Kakinada Bay Outer Zone (Andhra Pradesh)", "sector": "Andhra Pradesh", "lat": 16.85, "lng": 82.50, "depth_m": "30-50", "distance_km": "18-28"},
    {"id": "FZ_AP_02", "name": "Visakhapatnam Deep Trench (Andhra Pradesh)", "sector": "Andhra Pradesh", "lat": 17.55, "lng": 83.55, "depth_m": "50-80", "distance_km": "20-32"},
    {"id": "FZ_ODI_01", "name": "Paradip Outer Shelf (Odisha)", "sector": "Odisha", "lat": 19.90, "lng": 86.90, "depth_m": "30-55", "distance_km": "25-40"},
    {"id": "FZ_WB_01", "name": "Sandheads Fishing Ground (West Bengal)", "sector": "West Bengal", "lat": 21.05, "lng": 88.25, "depth_m": "20-40", "distance_km": "35-50"},
    {"id": "FZ_AND_01", "name": "South Andaman Pelagic Zone (Andaman)", "sector": "Andaman & Nicobar", "lat": 11.40, "lng": 93.00, "depth_m": "60-120", "distance_km": "20-40"},
    {"id": "FZ_LAK_01", "name": "Minicoy Tuna Fishing Basin (Lakshadweep)", "sector": "Lakshadweep", "lat": 8.20, "lng": 73.10, "depth_m": "70-150", "distance_km": "15-30"},
]


@lru_cache(maxsize=1)
def load_fishing_zones() -> tuple[FishingZone, ...]:
    """Load Potential Fishing Zones (PFZ) directly from data/incois_osf_pfz advisories.

    Does NOT use data/sea_route/fishing_zones.geojson.
    Buffers the advisory point coordinates into 0.06 degree (~4 nm) circular polygons
    with entry coordinates and full INCOIS ocean advisory metadata.
    """
    zones: list[FishingZone] = []
    seen_ids: set[str] = set()

    # 1. Primary: INCOIS live PFZ advisory feed
    pfz_path = PFZ_FILE
    if not pfz_path.exists():
        alt_path = _DATA_ROOT / "incois_osf_pfz" / "pfz" / "incois_pfz_live_advisories.geojson"
        if alt_path.exists():
            pfz_path = alt_path

    if pfz_path.exists():
        try:
            with pfz_path.open(encoding="utf-8") as fp:
                data = json.load(fp)
            for idx, feat in enumerate(data.get("features", []), 1):
                p = feat.get("properties", {})
                lat = p.get("latitude_dd")
                lng = p.get("longitude_dd")
                if lat is None or lng is None:
                    geom = feat.get("geometry") or {}
                    coords = geom.get("coordinates")
                    if coords and len(coords) >= 2:
                        lng, lat = coords[0], coords[1]
                if lat is None or lng is None:
                    continue

                lat = float(lat)
                lng = float(lng)
                sec_id = p.get("sector_id", "SEC")
                center = p.get("landing_center") or f"Zone {idx}"
                sec = (p.get("sector") or "").upper()
                name = f"{center} Offshore ({sec})" if sec else f"{center} Offshore"
                zone_id = f"FZ_{sec_id}_{idx:03d}"

                poly = Point(lng, lat).buffer(0.06)
                props = dict(p)
                props["id"] = zone_id
                props["name"] = name
                props["entry_lat"] = round(lat, 4)
                props["entry_lng"] = round(lng, 4)
                props["source"] = "INCOIS Potential Fishing Zone (PFZ)"

                zones.append(FishingZone(
                    id=zone_id,
                    name=name,
                    geometry=poly,
                    entry_lat=round(lat, 4),
                    entry_lng=round(lng, 4),
                    properties=props,
                ))
                seen_ids.add(zone_id.lower())
        except Exception as exc:
            log.warning("sea_route: failed loading PFZ advisories from %s: %s", pfz_path, exc)

    # 2. Pan-India regional offshore grounds for all coastal states
    for item in PAN_INDIA_FISHING_GROUNDS:
        zid = str(item["id"])
        if zid.lower() in seen_ids:
            continue
        poly = Point(float(item["lng"]), float(item["lat"])).buffer(0.08)
        props = {
            "id": zid,
            "name": str(item["name"]),
            "sector": str(item["sector"]),
            "depth_m": str(item["depth_m"]),
            "distance_km": str(item["distance_km"]),
            "entry_lat": float(item["lat"]),
            "entry_lng": float(item["lng"]),
            "source": "Coastal Regional Offshore PFZ Ground",
        }
        zones.append(FishingZone(
            id=zid,
            name=str(item["name"]),
            geometry=poly,
            entry_lat=float(item["lat"]),
            entry_lng=float(item["lng"]),
            properties=props,
        ))
        seen_ids.add(zid.lower())

    log.info("sea_route: loaded %d fishing zones from INCOIS PFZ dataset", len(zones))
    return tuple(zones)
