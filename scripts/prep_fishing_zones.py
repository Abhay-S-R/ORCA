#!/usr/bin/env python3
"""Prepare fishing zones dataset.

Reads either data/raw/fishing_zones.geojson or transforms INCOIS PFZ advisories
from data/incois_osf_pfz/pfz/all_india_pfz_advisories.geojson into navigable
fishing zone polygons.

Output: data/sea_route/fishing_zones.geojson

USAGE
  python scripts/prep_fishing_zones.py [--output data/sea_route/fishing_zones.geojson]
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from shapely.geometry import Point, box, shape
from shapely import to_geojson

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("prep_fishing_zones")

BBOX_W, BBOX_E, BBOX_S, BBOX_N = 66.0, 95.0, 5.0, 24.0
DEFAULT_OUTPUT = Path("data/sea_route/fishing_zones.geojson")


def build_fishing_zones(output_path: Path) -> int:
    clip_box = box(BBOX_W, BBOX_S, BBOX_E, BBOX_N)

    raw_zones = Path("data/raw/fishing_zones.geojson")
    pfz_file = Path("data/incois_osf_pfz/pfz/all_india_pfz_advisories.geojson")

    features = []

    if raw_zones.exists():
        log.info("Reading raw fishing zones from %s", raw_zones)
        data = json.loads(raw_zones.read_text(encoding="utf-8"))
        for i, feat in enumerate(data.get("features", [])):
            try:
                g = shape(feat["geometry"])
                if not g.intersects(clip_box):
                    continue
                p = feat.get("properties", {})
                zid = str(p.get("id") or f"ZONE_{i+1:03d}")
                name = str(p.get("name") or f"Fishing Zone {i+1}")
                features.append({
                    "type": "Feature",
                    "geometry": json.loads(to_geojson(g)),
                    "properties": {
                        "id": zid,
                        "name": name,
                        "entry_lat": p.get("entry_lat"),
                        "entry_lng": p.get("entry_lng"),
                        **p,
                    },
                })
            except Exception as exc:
                log.warning("Skipping bad feature: %s", exc)
    elif pfz_file.exists():
        log.info("Transforming INCOIS PFZ advisories from %s into fishing zones", pfz_file)
        data = json.loads(pfz_file.read_text(encoding="utf-8"))
        seen_centers = set()
        for i, feat in enumerate(data.get("features", [])):
            props = feat.get("properties", {})
            lat = props.get("latitude_dd")
            lng = props.get("longitude_dd")
            if lat is None or lng is None:
                continue
            if not (BBOX_S <= lat <= BBOX_N and BBOX_W <= lng <= BBOX_E):
                continue

            center_name = props.get("landing_center") or f"Zone {i+1}"
            sector = props.get("sector") or "India"
            zone_id = f"FZ_{props.get('sector_id', 'IN')}_{i+1:03d}"
            name = f"{center_name} Offshore ({sector})"

            # Build a circular polygon ~6-8 nm (approx 0.1 deg) around the PFZ center
            pt = Point(lng, lat)
            poly = pt.buffer(0.08)

            features.append({
                "type": "Feature",
                "geometry": json.loads(to_geojson(poly)),
                "properties": {
                    "id": zone_id,
                    "name": name,
                    "sector": sector,
                    "landing_center": center_name,
                    "depth_m": props.get("depth_m", "30-50"),
                    "source": "INCOIS Potential Fishing Zone (PFZ)",
                    "entry_lat": round(lat, 4),
                    "entry_lng": round(lng, 4),
                },
            })
    else:
        log.warning("No fishing zone sources found. Generating nominal fishing zones.")
        # Provide curated seed zones in Indian waters
        seed_zones = [
            ("FZ_GUJ_01", "Veraval Offshore Bank", 20.65, 70.15, 0.12),
            ("FZ_MAH_01", "Bombay High South Fishing Grounds", 19.10, 71.80, 0.15),
            ("FZ_GOA_01", "Aguada Trawling Grounds", 15.30, 73.50, 0.10),
            ("FZ_KAR_01", "Mangalore Offshore Trench", 12.75, 74.40, 0.12),
            ("FZ_KER_01", "Wadge Bank / Kollam Offshore", 8.40, 76.50, 0.15),
            ("FZ_TN_01", "Nagapattinam Deep Waters", 10.70, 80.20, 0.12),
            ("FZ_AP_01", "Kakinada Bay Outer Zone", 16.85, 82.50, 0.12),
            ("FZ_ODI_01", "Paradip Outer Shelf", 19.90, 86.90, 0.15),
            ("FZ_WB_01", "Sandheads Fishing Ground", 21.05, 88.25, 0.15),
            ("FZ_AND_01", "South Andaman Pelagic Zone", 11.40, 93.00, 0.15),
            ("FZ_LAK_01", "Minicoy Tuna Fishing Basin", 8.20, 73.10, 0.12),
        ]
        for zid, name, lat, lng, radius in seed_zones:
            poly = Point(lng, lat).buffer(radius)
            features.append({
                "type": "Feature",
                "geometry": json.loads(to_geojson(poly)),
                "properties": {
                    "id": zid,
                    "name": name,
                    "entry_lat": lat,
                    "entry_lng": lng,
                    "source": "ORCA Seed Fishing Zones",
                },
            })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, separators=(",", ":"))

    log.info("Written %d fishing zones to %s", len(features), output_path)
    return len(features)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    build_fishing_zones(args.output)


if __name__ == "__main__":
    main()
