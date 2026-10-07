"""Build the ports dataset.

Merges:
  1. NGA World Port Index CSV (data/raw/UpdatedPub150.csv or UpdatedPub150.xlsx)
     — filter to country IN/IND
  2. /data/raw/fishing_harbours.csv — (name, state, lat, lng)
  3. Hardcoded seed list of 11 major ports (NGA codes, LOCODE, lat/lng)

Output: data/sea_route/ports.geojson

All ports outside the India bbox (lat 5–24, lng 66–95) are rejected with a
clear message.

USAGE
  python scripts/prep_ports.py
"""
from __future__ import annotations

import csv
import json
import logging
import uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("prep_ports")

BBOX_W, BBOX_E, BBOX_S, BBOX_N = 66.0, 95.0, 5.0, 24.0

RAW_DIR = Path("data/raw")
OUTPUT = Path("data/sea_route/ports.geojson")

# Seed: 11 required major ports.  lat/lng from IHO / NGA records.
SEED_MAJOR = [
    {"id": "IN_KAN", "name": "Kandla", "code": "INKLA", "type": "major", "state": "Gujarat",    "lat": 22.98, "lng": 70.22},
    {"id": "IN_MUN", "name": "Mundra", "code": "INMUN", "type": "major", "state": "Gujarat",    "lat": 22.84, "lng": 69.70},
    {"id": "IN_JNP", "name": "JNPT / Nhava Sheva", "code": "INJNP", "type": "major", "state": "Maharashtra", "lat": 18.95, "lng": 72.95},
    {"id": "IN_MOR", "name": "Mormugao", "code": "INMRM", "type": "major", "state": "Goa",      "lat": 15.41, "lng": 73.80},
    {"id": "IN_NMG", "name": "New Mangalore", "code": "INMNG", "type": "major", "state": "Karnataka", "lat": 12.92, "lng": 74.82},
    {"id": "IN_KOC", "name": "Kochi", "code": "INCOK", "type": "major", "state": "Kerala",      "lat": 9.97,  "lng": 76.27},
    {"id": "IN_TUT", "name": "Tuticorin", "code": "INTUT", "type": "major", "state": "Tamil Nadu", "lat": 8.76, "lng": 78.14},
    {"id": "IN_CHE", "name": "Chennai", "code": "INMAA", "type": "major", "state": "Tamil Nadu", "lat": 13.10, "lng": 80.29},
    {"id": "IN_VIZ", "name": "Visakhapatnam", "code": "INVTZ", "type": "major", "state": "Andhra Pradesh", "lat": 17.69, "lng": 83.28},
    {"id": "IN_PAR", "name": "Paradip", "code": "INPRD", "type": "major", "state": "Odisha",    "lat": 20.32, "lng": 86.61},
    {"id": "IN_HAL", "name": "Haldia", "code": "INHLD", "type": "major", "state": "West Bengal", "lat": 22.05, "lng": 88.07},
    {"id": "IN_IXZ", "name": "Port Blair", "code": "INIXZ", "type": "major", "state": "Andaman & Nicobar", "lat": 11.67, "lng": 92.73},
    {"id": "IN_KVT", "name": "Kavaratti", "code": "INKVT", "type": "minor", "state": "Lakshadweep", "lat": 10.57, "lng": 72.64},
]


def _inside_bbox(lat: float, lng: float) -> bool:
    return BBOX_S <= lat <= BBOX_N and BBOX_W <= lng <= BBOX_E


def _read_nga_csv(path: Path) -> list[dict]:
    """Read NGA World Port Index CSV.  Returns list of port dicts for India."""
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            country = (row.get("Country Code") or row.get("COUNTRY_CODE") or "").strip().upper()
            if country not in ("IN", "IND"):
                continue
            try:
                lat_str = row.get("Latitude") or row.get("LAT") or ""
                lng_str = row.get("Longitude") or row.get("LON") or ""
                lat = float(lat_str)
                lng = float(lng_str)
            except ValueError:
                continue
            if not _inside_bbox(lat, lng):
                log.warning("NGA port outside bbox, skipping: %s (%.4f, %.4f)", row.get("Main port name") or row.get("PORT_NAME"), lat, lng)
                continue
            name = (row.get("Main port name") or row.get("PORT_NAME") or "Unknown").strip()
            port_num = (row.get("World Port Index Number") or row.get("INDEX_NO") or "").strip()
            rows.append({
                "id": f"nga_{port_num}" if port_num else f"nga_{uuid.uuid4().hex[:8]}",
                "name": name,
                "code": f"IN{port_num[:5]}" if port_num else "",
                "type": "minor",
                "state": "",
                "lat": lat,
                "lng": lng,
            })
    return rows


def _read_fishing_harbours(path: Path) -> list[dict]:
    """Read fishing_harbours.csv (name, state, lat, lng)."""
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            try:
                lat = float(row["lat"])
                lng = float(row["lng"])
            except (KeyError, ValueError):
                log.warning("Bad row %d in fishing_harbours.csv", i)
                continue
            if not _inside_bbox(lat, lng):
                name = row.get("name", "?")
                log.warning("Fishing harbour outside bbox, skipping: %s (%.4f, %.4f)", name, lat, lng)
                continue
            name = row.get("name", "Unknown").strip()
            state = row.get("state", "").strip()
            rows.append({
                "id": f"fh_{i}_{name[:8].replace(' ', '_').lower()}",
                "name": name,
                "code": "",
                "type": "fishing_harbour",
                "state": state,
                "lat": lat,
                "lng": lng,
            })
    return rows


def build_ports() -> list[dict]:
    ports: list[dict] = list(SEED_MAJOR)

    # NGA World Port Index.
    for candidate in ["UpdatedPub150.csv", "pub150.csv", "WorldPorts.csv"]:
        nga_path = RAW_DIR / candidate
        if nga_path.exists():
            extra = _read_nga_csv(nga_path)
            log.info("Read %d ports from NGA CSV %s", len(extra), nga_path.name)
            ports += extra
            break
    else:
        log.warning("NGA World Port Index CSV not found in data/raw/ — using seed ports only.")

    # Fishing harbours.
    fh_path = RAW_DIR / "fishing_harbours.csv"
    if fh_path.exists():
        fh = _read_fishing_harbours(fh_path)
        log.info("Read %d fishing harbours", len(fh))
        ports += fh
    else:
        log.warning("data/raw/fishing_harbours.csv not found.")

    # Deduplicate by name+lat+lng (allow seed to win over NGA for same port).
    seen: set[str] = set()
    unique: list[dict] = []
    for p in ports:
        key = f"{p['name'].lower().strip()}_{round(p['lat'], 1)}_{round(p['lng'], 1)}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


def main() -> None:
    ports = build_ports()
    log.info("Total unique ports: %d", len(ports))

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p["lng"], p["lat"]]},
            "properties": {k: v for k, v in p.items() if k not in ("lat", "lng")},
        }
        for p in ports
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, indent=2)
    log.info("Written to %s", OUTPUT)


if __name__ == "__main__":
    main()
