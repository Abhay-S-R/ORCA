#!/usr/bin/env python3
"""Prepare the India Exclusive Economic Zone (EEZ) polygon.

Reads Marine Regions VLIZ India EEZ + Andaman EEZ, simplifies slightly,
and outputs data/sea_route/india_eez.geojson.

USAGE
  python scripts/prep_eez.py [--output data/sea_route/india_eez.geojson]
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from shapely.geometry import box, shape
from shapely.ops import unary_union
from shapely import to_geojson

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("prep_eez")

BBOX_W, BBOX_E, BBOX_S, BBOX_N = 66.0, 95.0, 5.0, 24.0
DEFAULT_OUTPUT = Path("data/sea_route/india_eez.geojson")


def build_eez(output_path: Path, tolerance: float = 0.005) -> int:
    clip_box = box(BBOX_W, BBOX_S, BBOX_E, BBOX_N)
    geoms = []

    candidate_files = [
        Path("data/raw/india_eez.geojson"),
        Path("data/tier1/boundaries/india_eez_polygon.geojson"),
        Path("data/tier1/boundaries/andaman_eez.geojson"),
    ]

    for p in candidate_files:
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            for feat in data.get("features", []):
                g = shape(feat["geometry"])
                if g.intersects(clip_box):
                    clipped = g.intersection(clip_box)
                    if not clipped.is_empty:
                        geoms.append(clipped.simplify(tolerance))
            log.info("Loaded EEZ geometry from %s", p)
        except Exception as exc:
            log.warning("Could not load %s: %s", p, exc)

    if not geoms:
        log.warning("No EEZ source files found. Generating nominal India EEZ polygon.")
        # Nominal fallback bbox inside Indian waters
        nominal = box(68.0, 6.0, 93.0, 22.0)
        geoms.append(nominal)

    u = unary_union(geoms)
    features = []
    polys = u.geoms if hasattr(u, "geoms") else [u]
    for p in polys:
        if p.is_empty:
            continue
        features.append({
            "type": "Feature",
            "geometry": json.loads(to_geojson(p)),
            "properties": {
                "name": "India Exclusive Economic Zone",
                "source": "Marine Regions VLIZ / ORCA Tier 1 Boundaries",
            },
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, separators=(",", ":"))

    log.info("Written %d EEZ features to %s", len(features), output_path)
    return len(features)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--tolerance", type=float, default=0.005)
    args = ap.parse_args()

    build_eez(args.output, args.tolerance)


if __name__ == "__main__":
    main()
