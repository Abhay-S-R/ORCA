"""Agent 6 (Geospatial) — plan §4 S5.

In-memory Shapely + STRtree, not a database (plan §4 S5 Day 3: "five boundary
files and a 720x720 bathymetry grid load in under a second"). This uses
Shapely + pyproj directly rather than the full GeoPandas stack — STRtree and
geodesic distance don't need a DataFrame layer on top of them, and the
backend already has no GeoPandas dependency to reuse.

Every containment/proximity/zone query honours `orca_geofence_usable` (plan
§4 S5 Day 3): the centroid/MultiPoint-only MPA records (Gulf of Mannar,
Sunderban, Ashtamudi, Point Calimere — defect C-1 in the data audit) are
loaded for display but never treated as a boundary to contain or measure
against.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import xarray as xr
from pyproj import Geod
from shapely import to_geojson
from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
BOUNDARIES_DIR = DATA_ROOT / "tier1" / "boundaries"
BATHYMETRY_FILE = DATA_ROOT / "tier1" / "bathymetry" / "gebco_2026_n10.5_s7.5_w77.5_e80.5.nc"

_GEOD = Geod(ellps="WGS84")
NM_PER_METER = 1.0 / 1852.0

# Geodesic nautical-mile bands for the proximity alert level (plan §4 S5 Day 4).
_PROXIMITY_BANDS: tuple[tuple[float, str], ...] = ((1.0, "DANGER"), (5.0, "CAUTION"))

# Static per pilot region for Phase 1; a per-vessel-draft threshold is Phase 2 scope.
SHALLOW_HAZARD_THRESHOLD_M = 10.0

# Pilot bbox (matches the GEBCO extract's own extent) + a margin so a boundary
# just outside the strict box — e.g. the Sri Lanka EEZ line near Rameswaram —
# still clips in with context rather than getting cut off at the viewport edge.
_MAP_CLIP_MARGIN_DEG = 1.5
_MAP_CLIP_BOX = box(77.5 - _MAP_CLIP_MARGIN_DEG, 7.5 - _MAP_CLIP_MARGIN_DEG,
                     80.5 + _MAP_CLIP_MARGIN_DEG, 10.5 + _MAP_CLIP_MARGIN_DEG)
# (west, south, east, north) — the one pilot-region extent every map layer
# (Agent 6's own and Agent 8's, plan §5.9) should cite as `bounds` rather
# than each recomputing/hardcoding the same four numbers.
PILOT_BBOX_WSEN: tuple[float, float, float, float] = _MAP_CLIP_BOX.bounds

# Douglas-Peucker tolerance for map DISPLAY only (plan §4.7) — ~100m, well
# past what a Leaflet pixel can resolve at any zoom this app uses. This never
# touches the geometry check_boundary_proximity/point_in_polygon measure
# against — those always use the full-precision load_boundaries() output.
_MAP_SIMPLIFY_TOLERANCE_DEG = 0.001


@dataclass(frozen=True)
class BoundaryFeature:
    name: str
    designation: str
    source_file: str
    geofence_usable: bool
    geometry: BaseGeometry


@dataclass(frozen=True)
class ProximityResult:
    boundary_name: str
    distance_nm: float
    alert_level: str  # "INSIDE" | "DANGER" | "CAUTION" | "CLEAR"
    nearest_point: tuple[float, float]  # (lon, lat)


@dataclass(frozen=True)
class DepthResult:
    depth_m: float | None  # positive magnitude below sea level; None if on_land
    on_land: bool
    shallow_hazard: bool


def _load_geojson_features(path: Path, source_label: str) -> list[BoundaryFeature]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[BoundaryFeature] = []
    for feat in data["features"]:
        props = feat.get("properties", {})
        # EEZ files carry no orca_geofence_usable flag (single authoritative
        # polygon each) — default usable=True; only the MPA file's audited
        # centroid records are explicitly flagged False.
        usable = bool(props.get("orca_geofence_usable", True))
        name = props.get("name") or props.get("geoname") or source_label
        out.append(
            BoundaryFeature(
                name=name,
                designation=props.get("designation", source_label),
                source_file=path.name,
                geofence_usable=usable,
                geometry=shape(feat["geometry"]),
            )
        )
    return out


@lru_cache(maxsize=1)
def boundary_data_vintage() -> str:
    """When the boundary set was acquired, read from the files themselves.

    Static reference data still has an acquisition timestamp — the VLIZ WFS
    response carries its own `timeStamp`, and the audited MPA set carries
    `generated_at`. Exit criterion 4 ("every number on screen carries dataset
    + timestamp") applies to the IMBL distance too, so this is what that
    number cites. The OLDEST of the sources wins: a boundary set is only as
    fresh as its stalest member.
    """
    stamps: list[str] = []
    for name, key in (
        ("india_eez_polygon.geojson", "timeStamp"),
        ("srilanka_eez_polygon.geojson", "timeStamp"),
        ("mpa_geofence_provenance.json", "generated_at"),
    ):
        path = BOUNDARIES_DIR / name
        if not path.exists():
            continue
        value = json.loads(path.read_text(encoding="utf-8")).get(key)
        if value:
            stamps.append(str(value))
    if not stamps:
        return ""
    # ISO-8601 UTC sorts lexicographically; normalise the millisecond form so
    # "…15.288Z" and "…27Z" compare on the same axis.
    return min(stamps, key=lambda t: t.replace("Z", "").split(".")[0])


@lru_cache(maxsize=1)
def load_boundaries() -> tuple[BoundaryFeature, ...]:
    features: list[BoundaryFeature] = []
    features += _load_geojson_features(BOUNDARIES_DIR / "india_eez_polygon.geojson", "India EEZ")
    features += _load_geojson_features(BOUNDARIES_DIR / "srilanka_eez_polygon.geojson", "Sri Lanka EEZ")
    features += _load_geojson_features(BOUNDARIES_DIR / "india_marine_mpas.geojson", "Marine Protected Area")
    return tuple(features)


@lru_cache(maxsize=1)
def _usable_index() -> tuple[STRtree, list[BoundaryFeature]]:
    usable = [f for f in load_boundaries() if f.geofence_usable]
    tree = STRtree([f.geometry for f in usable])
    return tree, usable


def point_in_polygon(lat: float, lon: float) -> list[BoundaryFeature]:
    """Every geofence-usable boundary whose polygon contains (lat, lon).

    Queried as `predicate="within"` (point within polygon), not "contains"
    (polygon contains point) — mathematically the same relation, but
    GEOS's STRtree query returns empty for "contains" against these
    MultiPolygon boundaries even where `geometry.contains(point)` is True
    directly. "within" gives the correct, verified-against-direct-contains
    result, so tree-indexed and unindexed checks agree.
    """
    tree, usable = _usable_index()
    hits = tree.query(Point(lon, lat), predicate="within")
    return [usable[i] for i in hits]


def _alert_level(distance_nm: float, inside: bool) -> str:
    if inside:
        return "INSIDE"
    for threshold, level in _PROXIMITY_BANDS:
        if distance_nm <= threshold:
            return level
    return "CLEAR"


def check_boundary_proximity(lat: float, lon: float, boundary_name: str) -> ProximityResult:
    """Geodesic nautical-mile distance from (lat, lon) to the named
    boundary's nearest edge, via pyproj's WGS84 geodesic — planar/Euclidean
    distance is wrong by kilometers at this latitude for anything beyond a
    few hundred meters.

    The India EEZ boundary IS the India-Sri Lanka Maritime Boundary Line
    (IMBL) along the Palk Bay / Gulf of Mannar stretch — the pilot data has
    no separate IMBL line dataset, so `boundary_name="Indian Exclusive
    Economic Zone"` is how the IMBL-distance exit criterion (plan §4 S5) is
    answered: nearest point on the EEZ polygon's edge.
    """
    matches = [f for f in load_boundaries() if f.name == boundary_name and f.geofence_usable]
    if not matches:
        raise ValueError(f"No geofence-usable boundary named {boundary_name!r}")
    boundary = matches[0]

    pt = Point(lon, lat)
    inside = boundary.geometry.contains(pt)
    edge = boundary.geometry.boundary  # Polygon -> LinearRing(s); MultiPolygon -> MultiLineString
    nearest = edge.interpolate(edge.project(pt))
    _, _, distance_m = _GEOD.inv(lon, lat, nearest.x, nearest.y)
    distance_nm = round(abs(distance_m) * NM_PER_METER, 3)

    return ProximityResult(
        boundary_name=boundary.name,
        distance_nm=distance_nm,
        alert_level=_alert_level(distance_nm, inside),
        nearest_point=(round(nearest.x, 6), round(nearest.y, 6)),
    )


def bearing_and_distance(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> tuple[float, float]:
    """(true_bearing_degrees, distance_nm) from one point to another, geodesic."""
    azimuth, _, distance_m = _GEOD.inv(from_lon, from_lat, to_lon, to_lat)
    return round(azimuth % 360.0, 1), round(distance_m * NM_PER_METER, 3)


# ---- Bathymetry (Day 5) -----------------------------------------------------

@lru_cache(maxsize=1)
def _bathymetry() -> xr.Dataset:
    return xr.open_dataset(BATHYMETRY_FILE)


def depth_at_point(lat: float, lon: float) -> DepthResult:
    """GEBCO 2026 nearest-cell depth. GEBCO elevation is signed relative to
    sea level: positive is land, negative is below sea level. Nearest-cell
    (not interpolated) matches the grid's own stated resolution (~15 arcsec)
    and keeps this consistent with `bearing_and_distance`'s "cite the point
    you actually used" provenance requirement.
    """
    elevation = float(_bathymetry()["elevation"].sel(lat=lat, lon=lon, method="nearest").item())
    if elevation >= 0:
        return DepthResult(depth_m=None, on_land=True, shallow_hazard=False)
    depth = -elevation
    return DepthResult(
        depth_m=round(depth, 1), on_land=False, shallow_hazard=depth < SHALLOW_HAZARD_THRESHOLD_M
    )


def bathymetry_heatmap_points(stride: int = 16) -> list[dict[str, float]]:
    """Downsampled GEBCO depth points for Agent 8's Heatmap map layer
    (Architecture §11.1: "SST grid, chlorophyll concentration, wave
    height" — bathymetry is the one gridded field already loaded here).
    Every `stride`-th grid cell, land cells (elevation >= 0) skipped since
    a heatmap over depth has nothing to say about dry land.

    ponytail: stride=16 on the 720x720 pilot grid is ~1-2k real GEBCO
    points, comfortably under the §4.7 feature-count budget without
    resampling to a raster — the tile pyramid (Pillow, next checkpoint) is
    the real fix for a denser view; this is deliberately the coarse one.
    """
    ds = _bathymetry()
    lats = ds["lat"].values[::stride]
    lons = ds["lon"].values[::stride]
    elevation = ds["elevation"].values[::stride, ::stride]
    points: list[dict[str, float]] = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            el = float(elevation[i, j])
            if el >= 0:
                continue  # land — not a depth point
            points.append({"lat": float(lat), "lon": float(lon), "depth_m": round(-el, 1)})
    return points


# ---- Map layers (Day 6) -----------------------------------------------------

def generate_map_layers(user_lat: float | None = None, user_lon: float | None = None) -> dict[str, Any]:
    """Named GeoJSON FeatureCollections for the Leaflet shell. Only
    geofence-usable boundaries render as polygons — a non-usable centroid
    record has no shape worth drawing as one.

    Clipped to the pilot region and simplified before serialization (plan
    §4.7: "Never ship [full-precision geometry] to the client"). Before this,
    generate_map_layers sent India's and Sri Lanka's ENTIRE EEZ boundaries —
    71,782 and 56,019 coordinate points respectively, ~3.3MB uncompressed for
    one response — which is enough to hang Leaflet's GeoJSON renderer on a
    normal machine long past the point it looks like the map failed to load
    at all. Clipping to the pilot bbox also correctly drops boundaries that
    have nothing to do with this region at all (Chilika Lake, Thane Creek,
    the Sundarbans — all loaded from a national MPA file, not filtered by
    region until now).
    """
    boundary_features = []
    for f in load_boundaries():
        if not f.geofence_usable:
            continue
        clipped = f.geometry.intersection(_MAP_CLIP_BOX)
        if clipped.is_empty:
            continue  # outside the pilot region entirely — not this map's business
        simplified = clipped.simplify(_MAP_SIMPLIFY_TOLERANCE_DEG, preserve_topology=True)
        boundary_features.append({
            "type": "Feature",
            "geometry": json.loads(to_geojson(simplified)),
            "properties": {"name": f.name, "designation": f.designation, "source_file": f.source_file},
        })
    layers: dict[str, Any] = {
        "boundaries": {"type": "FeatureCollection", "features": boundary_features}
    }
    if user_lat is not None and user_lon is not None:
        layers["user_position"] = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [user_lon, user_lat]},
                    "properties": {"label": "You"},
                }
            ],
        }
    return layers


# ---- Zone queries (Day 7) ---------------------------------------------------

def spatial_query_zones(lat: float, lon: float, radius_nm: float) -> list[BoundaryFeature]:
    """Every geofence-usable boundary within `radius_nm` of (lat, lon):
    containing it outright, or with an edge closer than `radius_nm`.
    """
    pt = Point(lon, lat)
    # 1 deg latitude ~= 60 nm; a coarse bbox pre-filter, narrowed below by
    # the actual geodesic distance so the 1.5x pad costs nothing but a few
    # extra candidates to check exactly.
    tree, usable = _usable_index()
    candidate_idx = tree.query(pt.buffer((radius_nm / 60.0) * 1.5))

    results: list[BoundaryFeature] = []
    for i in candidate_idx:
        feature = usable[i]
        if feature.geometry.contains(pt):
            results.append(feature)
            continue
        edge = feature.geometry.boundary
        nearest = edge.interpolate(edge.project(pt))
        _, _, distance_m = _GEOD.inv(lon, lat, nearest.x, nearest.y)
        if distance_m * NM_PER_METER <= radius_nm:
            results.append(feature)
    return results


if __name__ == "__main__":
    # Gulf of Mannar, offshore Thoothukudi — confirmed inside the India EEZ
    # polygon and shallow. Cross-checks the Day 3-7 chain end to end.
    lat, lon = 8.70, 78.50

    boundaries = load_boundaries()
    assert len(boundaries) >= 15, len(boundaries)
    non_usable = [f.name for f in boundaries if not f.geofence_usable]
    assert "Gulf of Mannar" in non_usable, non_usable  # defect C-1 must stay excluded

    inside = point_in_polygon(lat, lon)
    assert any(f.name == "Indian Exclusive Economic Zone" for f in inside), [f.name for f in inside]
    assert not any(f.name == "Gulf of Mannar" for f in inside)  # never via a centroid

    imbl = check_boundary_proximity(lat, lon, "Indian Exclusive Economic Zone")
    assert imbl.alert_level == "INSIDE"
    assert imbl.distance_nm >= 0

    bearing, distance = bearing_and_distance(lat, lon, 9.29, 79.31)
    assert 0 <= bearing < 360 and distance > 0

    depth = depth_at_point(lat, lon)
    assert depth.on_land is False
    assert depth.depth_m is not None and depth.depth_m >= 0

    layers = generate_map_layers(user_lat=lat, user_lon=lon)
    assert layers["boundaries"]["features"]
    assert layers["user_position"]["features"][0]["geometry"]["coordinates"] == [lon, lat]

    zones = spatial_query_zones(lat, lon, radius_nm=50)
    assert any(f.name == "Indian Exclusive Economic Zone" for f in zones)

    print("geospatial self-check ok:", imbl, depth)
