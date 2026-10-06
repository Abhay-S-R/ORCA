#!/usr/bin/env python3
"""Clip OSM land polygons to the India bbox and save land_india.geojson.

USAGE
  python scripts/prep_land.py [--input /path/to/land-polygons-split-4326/]
                               [--output data/sea_route/land_india.geojson]
                               [--tolerance 0.0005]

INPUTS (place in data/raw/)
  Option A (recommended): OSM land-polygons-split-4326 shapefile directory
    Download from https://osmdata.openstreetmap.de/data/land-polygons.html
    Extract inside data/raw/land-polygons-split-4326/

  Option B: Natural Earth 10m land shapefile
    Download ne_10m_land.shp from https://www.naturalearthdata.com/

  Option C: GSHHG (Global Self-consistent, Hierarchical, High-resolution Geography)
    Download from https://www.soest.hawaii.edu/pwessel/gshhg/

DESIGN NOTES
- Clipped to bbox (66–95 E, 5–24 N), NOT to India's national border, so
  neighbouring land (Sri Lanka, Pakistan, Bangladesh, Myanmar, Maldives)
  stays blocked — that is a feature, not a bug.
- Douglas-Peucker simplification at ~55 m (0.0005 deg) reduces file size
  from ~2 GB to ~10 MB while keeping every headland and inlet a ship cares about.
- The loader (datasets.py) is configurable via SEA_ROUTE_LAND_FILE env var
  so this script, Natural Earth 10m or GSHHG can be swapped without code changes.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("prep_land")

BBOX_W, BBOX_E, BBOX_S, BBOX_N = 66.0, 95.0, 5.0, 24.0

DEFAULT_INPUT = Path("data/raw/land-polygons-split-4326")
DEFAULT_OUTPUT = Path("data/sea_route/land_india.geojson")
DEFAULT_TOLERANCE = 0.0005  # degrees, ≈ 55 m at the equator


def clip_and_simplify(input_path: Path, output_path: Path, tolerance: float) -> int:
    """Return the count of features written."""
    try:
        import shapefile  # pyshp — already in backend/requirements.txt
        from shapely.geometry import box, shape
        from shapely import to_geojson
    except ImportError:
        log.error("pip install pyshp shapely")
        return 0

    clip_box = box(BBOX_W, BBOX_S, BBOX_E, BBOX_N)

    # Support both a directory (shapefile parts) and a single .shp file.
    if input_path.is_dir():
        shp_files = list(input_path.glob("*.shp"))
        if not shp_files:
            log.error("No .shp file found in %s", input_path)
            return 0
    elif input_path.suffix.lower() == ".shp":
        shp_files = [input_path]
    else:
        log.error("Expected a directory or .shp file, got: %s", input_path)
        return 0

    features: list[dict] = []
    for shp in shp_files:
        log.info("Reading %s …", shp)
        try:
            rdr = shapefile.Reader(str(shp))
        except Exception as exc:
            log.warning("Could not read %s: %s", shp, exc)
            continue
        for sr in rdr.shapeRecords():
            if sr.shape is None:
                continue
            geom = shape(sr.shape.__geo_interface__)
            if not geom.is_valid:
                geom = geom.buffer(0)
            if not geom.intersects(clip_box):
                continue
            clipped = geom.intersection(clip_box)
            if clipped.is_empty:
                continue
            if tolerance > 0:
                clipped = clipped.simplify(tolerance, preserve_topology=True)
            if clipped.is_empty:
                continue
            features.append({
                "type": "Feature",
                "geometry": json.loads(to_geojson(clipped)),
                "properties": {},
            })

    log.info("Writing %d features to %s …", len(features), output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, separators=(",", ":"))
    log.info("Done.")
    return len(features)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    args = ap.parse_args()

    if not args.input.exists():
        fallback_shp = Path("data/tier1/boundaries/2011_Dist.shp")
        if fallback_shp.exists():
            log.info("OSM data not found at %s. Using fallback: %s + Sri Lanka EEZ hole", args.input, fallback_shp)
            n = generate_fallback_land(args.output, args.tolerance)
            if n > 0:
                log.info("Successfully generated %d land features from fallback data.", n)
                return
        log.error(
            "Input not found: %s\n"
            "Place the OSM land-polygons-split-4326 directory (or a .shp file) there.",
            args.input,
        )
        sys.exit(1)

    n = clip_and_simplify(args.input, args.output, args.tolerance)
    if n == 0:
        log.error("No features written — check the input file.")
        sys.exit(1)


def generate_fallback_land(output_path: Path, tolerance: float) -> int:
    import shapefile
    from shapely.geometry import box, shape, Polygon
    from shapely.ops import unary_union
    from shapely import to_geojson

    clip_box = box(BBOX_W, BBOX_S, BBOX_E, BBOX_N)
    geoms = []

    # 1. India districts shapefile
    dist_shp = Path("data/tier1/boundaries/2011_Dist.shp")
    if dist_shp.exists():
        r = shapefile.Reader(str(dist_shp))
        for sr in r.shapeRecords():
            if sr.shape is None:
                continue
            g = shape(sr.shape.__geo_interface__)
            if g.intersects(clip_box):
                clipped = g.intersection(clip_box)
                if not clipped.is_empty:
                    geoms.append(clipped.simplify(tolerance))

    # 2. Sri Lanka land from EEZ interior hole
    sl_file = Path("data/tier1/boundaries/srilanka_eez_polygon.geojson")
    if sl_file.exists():
        with sl_file.open(encoding="utf-8") as fh:
            sl_data = json.load(fh)
        sl_eez = shape(sl_data["features"][0]["geometry"])
        parts = sl_eez.geoms if hasattr(sl_eez, "geoms") else [sl_eez]
        for p in parts:
            for h in p.interiors:
                poly = Polygon(h)
                if poly.area > 0.0001:
                    geoms.append(poly.simplify(tolerance))

    if not geoms:
        return 0

    combined = unary_union(geoms)
    features = []
    polys = combined.geoms if hasattr(combined, "geoms") else [combined]
    for p in polys:
        if p.is_empty or p.area < 1e-5:
            continue
        features.append({
            "type": "Feature",
            "geometry": json.loads(to_geojson(p)),
            "properties": {},
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, separators=(",", ":"))
    return len(features)


if __name__ == "__main__":
    main()
