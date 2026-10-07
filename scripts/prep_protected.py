#!/usr/bin/env python3
"""Prepare marine protected areas (MPAs) for sea-route planning.

Reads UNEP-WCMC WDPA marine protected areas from data/tier1/boundaries/india_marine_mpas.geojson
(or data/raw/protected_areas.geojson) and writes to data/sea_route/protected_areas.geojson.

USAGE
  python scripts/prep_protected.py [--output data/sea_route/protected_areas.geojson]
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from shapely.geometry import box, shape
from shapely import to_geojson

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("prep_protected")

BBOX_W, BBOX_E, BBOX_S, BBOX_N = 66.0, 95.0, 5.0, 24.0
DEFAULT_OUTPUT = Path("data/sea_route/protected_areas.geojson")


def build_protected(output_path: Path) -> int:
    clip_box = box(BBOX_W, BBOX_S, BBOX_E, BBOX_N)

    candidate_files = [
        Path("data/raw/protected_areas.geojson"),
        Path("data/tier1/boundaries/india_marine_mpas.geojson"),
    ]

    source_path = None
    for p in candidate_files:
        if p.exists():
            source_path = p
            break

    features = []
    if source_path:
        log.info("Reading MPAs from %s", source_path)
        data = json.loads(source_path.read_text(encoding="utf-8"))
        for feat in data.get("features", []):
            try:
                g = shape(feat["geometry"])
                if not g.intersects(clip_box):
                    continue
                props = feat.get("properties", {})
                name = props.get("name") or props.get("NAME") or "Marine Protected Area"
                wdpaid = str(props.get("site_id") or props.get("WDPAID") or len(features) + 1)
                designation = props.get("designation") or "MPA"

                # Core sanctuaries can be set to "warn" by default, or "block" if strict no-take
                mode = "warn"
                if props.get("no_take") == "All":
                    mode = "warn"

                features.append({
                    "type": "Feature",
                    "geometry": json.loads(to_geojson(g)),
                    "properties": {
                        "WDPAID": wdpaid,
                        "NAME": name,
                        "designation": designation,
                        "mode": mode,
                        "source": "WDPA / UNEP-WCMC",
                    },
                })
            except Exception as exc:
                log.warning("Skipping bad feature: %s", exc)
    else:
        log.warning("No MPA sources found. Writing empty collection.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, separators=(",", ":"))

    log.info("Written %d protected area features to %s", len(features), output_path)
    return len(features)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = ap.parse_args()

    build_protected(args.output)


if __name__ == "__main__":
    main()
