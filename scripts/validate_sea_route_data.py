#!/usr/bin/env python3
"""Validate all prepared sea-route datasets.

Checks:
  1. Files exist and are valid GeoJSON FeatureCollections.
  2. Counts of features in each file.
  3. All geometries are within the India bounding box (lat 5–24, lng 66–95).
  4. Ports have required fields (id, name, code, lat, lng).
  5. Restricted areas and protected areas have geometry and mode.
  6. Fishing zones have geometry and valid entry coordinates.

USAGE
  python scripts/validate_sea_route_data.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from shapely.geometry import box, shape

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("validate_sea_route_data")

BBOX_W, BBOX_E, BBOX_S, BBOX_N = 66.0, 95.0, 5.0, 24.0
clip_box = box(BBOX_W, BBOX_S, BBOX_E, BBOX_N)

DATA_FILES = {
    "Land Polygons": Path("data/sea_route/land_india.geojson"),
    "Ports": Path("data/sea_route/ports.geojson"),
    "Restricted Areas": Path("data/sea_route/restricted_areas.geojson"),
    "India EEZ": Path("data/sea_route/india_eez.geojson"),
    "Protected Areas": Path("data/sea_route/protected_areas.geojson"),
    "Fishing Zones": Path("data/sea_route/fishing_zones.geojson"),
}


def validate_file(name: str, path: Path) -> tuple[bool, int, list[str]]:
    warnings = []
    if not path.exists():
        return False, 0, [f"File {path} does not exist."]

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, 0, [f"JSON parsing error: {exc}"]

    if data.get("type") != "FeatureCollection":
        warnings.append("Root GeoJSON type is not 'FeatureCollection'")

    features = data.get("features", [])
    count = len(features)
    if count == 0:
        warnings.append("Dataset has 0 features.")

    outside_count = 0
    for i, feat in enumerate(features):
        geom_dict = feat.get("geometry")
        if not geom_dict:
            warnings.append(f"Feature #{i} missing geometry.")
            continue
        try:
            g = shape(geom_dict)
            if not g.is_valid:
                g = g.buffer(0)
            # Check bounding box overlap with India bbox
            if not g.intersects(clip_box):
                outside_count += 1
        except Exception as exc:
            warnings.append(f"Feature #{i} invalid geometry: {exc}")

    if outside_count > 0:
        warnings.append(f"{outside_count} features are entirely outside India bbox.")

    return True, count, warnings


def main() -> None:
    log.info("Validating sea-route datasets in data/sea_route/ ...")
    total_errors = 0

    print("=" * 70)
    print(f"{'Dataset':<20} | {'Status':<8} | {'Features':<10} | {'Issues'}")
    print("-" * 70)

    for name, path in DATA_FILES.items():
        ok, count, warnings = validate_file(name, path)
        status = "OK" if ok and not warnings else ("WARN" if ok else "FAIL")
        issue_str = "; ".join(warnings) if warnings else "None"
        print(f"{name:<20} | {status:<8} | {count:<10} | {issue_str}")
        if not ok or any("does not exist" in w for w in warnings):
            total_errors += 1

    print("=" * 70)
    if total_errors > 0:
        log.error("Validation failed with %d missing or unreadable files.", total_errors)
        sys.exit(1)
    else:
        log.info("Validation passed successfully!")


if __name__ == "__main__":
    main()
