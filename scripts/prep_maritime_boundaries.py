"""Prepare maritime boundary restricted areas.

Reads Marine Regions VLIZ maritime boundary lines (or uses a built-in
placeholder set), buffers each line by BUFFER_NM nautical miles, and saves
the result as data/sea_route/restricted_areas.geojson.

PLACEHOLDER — replace geometry with official IMBL data before operational use.

USAGE
  python scripts/prep_maritime_boundaries.py [--input data/raw/india_maritime_boundary_lines.geojson]
                                               [--buffer 2.0]
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger("prep_maritime_boundaries")

BBOX_W, BBOX_E, BBOX_S, BBOX_N = 66.0, 95.0, 5.0, 24.0
INPUT_DEFAULT = Path("data/raw/india_maritime_boundary_lines.geojson")
OUTPUT = Path("data/sea_route/restricted_areas.geojson")
BUFFER_NM_DEFAULT = 2.0

# Degree per nautical mile at 15°N (centre of India).
_DEG_PER_NM = 1.0 / 60.0


def nm_to_deg(nm: float) -> float:
    return nm * _DEG_PER_NM


def build_restricted(input_path: Path, buffer_nm: float) -> list[dict]:
    """Return list of GeoJSON features (Polygon) from buffered boundary lines."""
    from shapely import to_geojson
    from shapely.geometry import shape

    if not input_path.exists():
        tier1_path = Path("data/tier1/boundaries/india_maritime_boundary_lines.geojson")
        if tier1_path.exists():
            log.info("Using maritime boundary lines from %s", tier1_path)
            input_path = tier1_path
        else:
            log.warning(
                "%s not found — generating placeholder restricted area set.\n"
                "Download India maritime boundary lines from "
                "https://www.marineregions.org/ and re-run.",
                input_path,
            )
            return _placeholder_areas()

    data = json.loads(input_path.read_text(encoding="utf-8"))
    buf_deg = nm_to_deg(buffer_nm)
    features: list[dict] = []
    for i, feat in enumerate(data.get("features", [])):
        props = feat.get("properties", {})
        line_type = (props.get("line_type") or "").strip().lower()
        if line_type in ("straight baseline", "200 nm"):
            continue
        # Keep only international boundary lines between India/Andaman and another country.
        t1 = (props.get("territory1") or "").strip().lower()
        t2 = (props.get("territory2") or "").strip().lower()
        if not t1 or not t2:
            continue
        has_india = "india" in t1 or "andaman" in t1 or "india" in t2 or "andaman" in t2
        is_internal = ("india" in t1 or "andaman" in t1) and ("india" in t2 or "andaman" in t2)
        if not has_india or is_internal:
            continue
        geom = shape(feat["geometry"])
        buffered = geom.buffer(buf_deg)
        name = props.get("line_name") or props.get("geoname") or props.get("name") or f"Maritime boundary {i}"
        is_pakistan = "pakistan" in t1 or "pakistan" in t2
        is_palk_bay = "palk" in name.lower()
        mode = props.get("mode") or ("block" if (is_pakistan or is_palk_bay) else "warn")

        features.append({
            "type": "Feature",
            "geometry": json.loads(to_geojson(buffered)),
            "properties": {
                "id": f"imbl_{i}",
                "name": name,
                "mode": mode,
                "note": "PLACEHOLDER — replace with official IMBL data. Source: Marine Regions VLIZ.",
                "territory1": props.get("territory1", ""),
                "territory2": props.get("territory2", ""),
            },
        })
    log.info("Generated %d restricted area polygons (%.1f nm buffer)", len(features), buffer_nm)
    return features


def _placeholder_areas() -> list[dict]:
    """Minimal placeholder restricted areas matching the India-neighbour boundaries."""
    from shapely import to_geojson
    from shapely.geometry import LineString

    # Rough lines representing India's principal maritime boundaries.
    lines = [
        {"name": "India–Pakistan IMBL (Arabian Sea)", "coords": [(23.5, 66.5), (22.0, 68.0), (20.5, 67.5)]},
        {"name": "India–Sri Lanka IMBL (Palk Bay)", "coords": [(9.5, 80.0), (8.8, 80.3), (8.0, 80.6), (7.5, 81.5)]},
        {"name": "India–Bangladesh IMBL (Bay of Bengal)", "coords": [(21.5, 90.0), (20.0, 90.5), (18.5, 90.8)]},
        {"name": "India–Myanmar IMBL (Bay of Bengal)", "coords": [(18.5, 91.5), (17.0, 92.5), (15.0, 94.0)]},
    ]
    features = []
    buf = nm_to_deg(2.0)
    for i, line in enumerate(lines):
        geom = LineString([(lng, lat) for lat, lng in line["coords"]])
        buffered = geom.buffer(buf)
        features.append({
            "type": "Feature",
            "geometry": json.loads(to_geojson(buffered)),
            "properties": {
                "id": f"placeholder_{i}",
                "name": line["name"],
                "mode": "block",
                "note": "PLACEHOLDER — replace with official IMBL data. Source: Marine Regions VLIZ.",
            },
        })
    return features


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, default=INPUT_DEFAULT)
    ap.add_argument("--buffer", type=float, default=BUFFER_NM_DEFAULT)
    args = ap.parse_args()

    features = build_restricted(args.input, args.buffer)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features,
                   "note": "PLACEHOLDER — replace with official IMBL data."}, fh, indent=2)
    log.info("Written to %s", OUTPUT)


if __name__ == "__main__":
    main()
