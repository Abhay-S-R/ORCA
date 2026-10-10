
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
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import xarray as xr
from pyproj import Geod
from shapely import to_geojson
from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points
from shapely.strtree import STRtree

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
BOUNDARIES_DIR = DATA_ROOT / "tier1" / "boundaries"
GEBCO_ALL_FILE = DATA_ROOT / "tier1" / "bathymetry" / "gebco_2026_n26.0_s4.0_w60.0_e100.0.nc"
GEBCO_PILOT_FILE = DATA_ROOT / "tier1" / "bathymetry" / "gebco_2026_n10.5_s7.5_w77.5_e80.5.nc"
# scripts/download_gebco_bathymetry.py fetches the national subset; the pilot
# box stays the fallback so a fresh clone without it still answers.
ETOPO_ALL_FILE = DATA_ROOT / "tier1" / "bathymetry" / "etopo_all_india_bathymetry.nc"
ETOPO_PILOT_FILE = DATA_ROOT / "tier1" / "bathymetry" / "etopo_south_india_bathymetry.nc"

_GEOD = Geod(ellps="WGS84")
NM_PER_METER = 1.0 / 1852.0

# Geodesic nautical-mile bands for the proximity alert level (plan §4 S5 Day 4; G3: 3.0 NM matches risk_assessment's CAUTION threshold).
_PROXIMITY_BANDS: tuple[tuple[float, str], ...] = ((1.0, "DANGER"), (3.0, "CAUTION"))

# Static per pilot region for Phase 1; a per-vessel-draft threshold is Phase 2 scope.
SHALLOW_HAZARD_THRESHOLD_M = 10.0

# Pan-India maritime bounds covering Arabian Sea, Indian Ocean, and Bay of Bengal.
# No longer artificially clips the Indian EEZ into a small rectangle around Thoothukudi.
# East edge is 96 E and the south edge 3.5 N so the Andaman & Nicobar EEZ
# (88.8-95.7 E, 3.8-15.7 N) and the treaty boundary lines that meet it are
# inside the frame rather than sliced in half by the old 95 E / 4 N corner.
_MAP_CLIP_BOX = box(65.0, 3.5, 96.0, 26.0)
PAN_INDIA_BBOX_WSEN: tuple[float, float, float, float] = (65.0, 4.0, 95.0, 26.0)
PILOT_BBOX_WSEN: tuple[float, float, float, float] = (76.0, 6.0, 82.0, 12.0)

# Douglas-Peucker tolerance for map DISPLAY only (plan §4.7/§5.10 Day 10) —
# never touches the geometry check_boundary_proximity/point_in_polygon
# measures against — those always use the full-precision load_boundaries()
# output. Per-zoom, not one fixed value: z<=7 is a whole-basin view where
# ~1km of coastline wobble is invisible, z8-10 a regional view (~200m), and
# z>=11 is close enough to a vessel's own position that only full precision
# reads as correct.
_SIMPLIFY_TOLERANCE_BY_ZOOM: tuple[tuple[int, float], ...] = (
    (7, 0.01), (10, 0.002),
)  # (max_zoom_inclusive, tolerance_deg); above the last bucket -> full precision (0.0)


def _simplify_tolerance_for_zoom(zoom: int) -> float:
    for max_zoom, tolerance in _SIMPLIFY_TOLERANCE_BY_ZOOM:
        if zoom <= max_zoom:
            return tolerance
    return 0.0  # z >= 11 — full precision, no simplify() call at all


@dataclass(frozen=True)
class BoundaryFeature:
    name: str
    designation: str
    source_file: str
    geofence_usable: bool
    geometry: BaseGeometry
    # P5.26: HIGH / MEDIUM / CENTROID_ONLY, as scripts/build_mpa_geofence.py
    # grades each MPA record from its WDPA geometry type. EEZ/line files carry
    # no such tag — they are the authoritative government polygon for their
    # region, so they default to HIGH rather than reading as ungraded.
    orca_precision: str = "HIGH"


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
        # P5.26: usability is re-derived from the precision grade here too,
        # not only trusted from the upstream flag — a CENTROID_ONLY record can
        # never be geofence-usable even if a hand-edited file forgot to also
        # flip orca_geofence_usable.
        precision = props.get("orca_precision", "HIGH")
        usable = bool(props.get("orca_geofence_usable", True)) and precision != "CENTROID_ONLY"
        name = props.get("name") or props.get("geoname") or source_label
        out.append(
            BoundaryFeature(
                name=name,
                designation=props.get("designation", source_label),
                source_file=path.name,
                geofence_usable=usable,
                geometry=shape(feat["geometry"]),
                orca_precision=precision,
            )
        )
    return out


@lru_cache(maxsize=1)
def boundary_line_vintage() -> str:
    """The acquisition timestamp of the 32 delimited maritime boundary treaty lines.

    Read directly from `india_maritime_boundary_lines.geojson`'s WFS `timeStamp`.
    This is the dataset that `nearest_boundary_line` queries for the IMBL distance.
    """
    path = BOUNDARIES_DIR / "india_maritime_boundary_lines.geojson"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get("timeStamp")
        return str(value) if value else ""
    except Exception:
        return ""


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
        ("india_maritime_boundary_lines.geojson", "timeStamp"),
        ("andaman_eez.geojson", "timeStamp"),
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
    # The A&N EEZ is a separate VLIZ record, not part of the mainland polygon:
    # without it every Andaman position sits outside every geofence ORCA
    # holds, and point_in_polygon answers "high seas" for Port Blair.
    andaman = BOUNDARIES_DIR / "andaman_eez.geojson"
    if andaman.exists():
        features += _load_geojson_features(andaman, "India EEZ (Andaman & Nicobar)")
    return tuple(features)


@lru_cache(maxsize=1)
def load_boundary_lines() -> tuple[tuple[Any, dict[str, Any]], ...]:
    """The 32 delimitation LINES from the VLIZ IMBL dataset, with their treaty
    metadata, as (geometry, properties) pairs.

    Deliberately NOT part of load_boundaries(): these are MultiLineStrings,
    a line can never contain a point, and feeding them to the polygon
    geofence index would put a zero-area geometry in the STRtree that
    point_in_polygon queries. They carry what the EEZ polygon's edge cannot
    — which treaty drew this line, between whom, and when. Three lines share
    the name "Indonesia - Andaman and Nicobar (India)" under two different
    agreements, so properties travel with the geometry rather than being
    looked up by name afterwards.
    """
    path = BOUNDARIES_DIR / "india_maritime_boundary_lines.geojson"
    if not path.exists():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple((shape(f["geometry"]), f.get("properties", {})) for f in data["features"])


def geojson_geometry(geom: BaseGeometry) -> dict[str, Any]:
    """A shapely geometry as a parsed GeoJSON geometry dict.

    `shapely.to_geojson` is typed as returning None when handed a null
    geometry, so every `json.loads(to_geojson(...))` at a call site reads as
    passing `str | None` to `json.loads`. Ours are never null — but saying so
    once here beats a cast at each of the three call sites, and if shapely
    ever does hand back nothing we raise instead of writing `null` into a
    feature's `geometry` and shipping a silently empty shape to the chart.
    """
    encoded = to_geojson(geom)
    if encoded is None:
        raise ValueError(f"shapely produced no GeoJSON for a {type(geom).__name__}")
    return json.loads(encoded)


DISTRICTS_FILE = BOUNDARIES_DIR / "2011_Dist.shp"


@lru_cache(maxsize=1)
def _district_index() -> tuple[STRtree, list[dict[str, Any]]] | None:
    """Census 2011 district polygons, indexed. None if the shapefile is absent."""
    if not DISTRICTS_FILE.exists():
        return None
    import shapefile  # pyshp: pure-python .shp/.dbf reader, no GDAL

    reader = shapefile.Reader(str(DISTRICTS_FILE))
    rows: list[dict[str, Any]] = []
    for sr in reader.shapeRecords():
        # pyshp types both halves as optional and it is right to: a .shp whose
        # .dbf partner is truncated yields records without shapes. A row missing
        # either half cannot place a position in a district, so it is skipped
        # rather than crashing the whole index on one bad row.
        record, geom = sr.record, sr.shape
        if record is None or geom is None:
            continue
        rows.append({
            "district": record["DISTRICT"],
            "state": record["ST_NM"],
            "censuscode": record["censuscode"],
            "geometry": shape(dict(geom.__geo_interface__)),
        })
    return STRtree([r["geometry"] for r in rows]), rows


def district_at_point(lat: float, lon: float) -> dict[str, Any] | None:
    """The Census-2011 district a position falls in, or None at sea.

    Catch statistics are published per district, so a lat/lon only reaches
    the landings archive through this. Offshore positions are genuinely
    outside every district polygon — that is a real None, not a lookup
    failure, and callers say so rather than guessing the nearest coast.
    """
    index = _district_index()
    if index is None:
        return None
    tree, rows = index
    pt = Point(lon, lat)
    for i in tree.query(pt, predicate="within"):
        row = rows[i]
        return {"district": row["district"], "state": row["state"],
                "censuscode": row["censuscode"],
                "dataset": "Census of India 2011 district boundaries",
                "source_file": DISTRICTS_FILE.name}
    return None


def nearest_boundary_line(lat: float, lon: float) -> dict[str, Any] | None:
    """Closest delimited maritime boundary line, geodesically.

    check_boundary_proximity answers "how far to the EEZ edge", which along
    the Palk Bay IS the IMBL but elsewhere is the 200 NM limit — a different
    thing legally. This names the actual treaty line and the agreement that
    drew it, which is what an arrest across it turns on.

    Only lines BETWEEN India and another state count here. 8 of the 32
    features in the file are not that: 6 "Straight baseline" + 2 "200 NM"
    lines are India's own coastline/limit markers, `territory2: null` in the
    source data — nothing to cross into. Counting them made the pilot default
    position read 0.7 nm from a "boundary" (was 47.6 nm before the Phase 5
    merge added this filter's absence) and made an ordinary Thoothukudi
    question NO_GO (found 2026-09-25, `docs/logs/DLC_implementation_log.md`).
    `load_boundary_lines()` itself still returns all 32 — `map_layers`
    (`orca/api/geospatial_routes.py`) draws every line, baselines included,
    for context; only a verdict-relevant nearest line excludes them.
    """
    lines = [(g, p) for g, p in load_boundary_lines() if p.get("territory2")]
    if not lines:
        return None
    pt = Point(lon, lat)
    best: tuple[float, dict[str, Any], Point] | None = None
    for geometry, props in lines:
        nearest = geometry.interpolate(geometry.project(pt))
        azimuth, _, metres = _GEOD.inv(lon, lat, nearest.x, nearest.y)
        if best is None or abs(metres) < best[0]:
            best = (abs(metres), {**props, "bearing_deg": round(azimuth % 360.0, 1)}, nearest)
    metres, props, nearest = best  # type: ignore[misc]
    distance_nm = round(metres * NM_PER_METER, 3)
    return {
        "line_name": props.get("line_name"),
        "line_type": props.get("line_type"),
        "between": [props.get("territory1"), props.get("territory2")],
        "distance_nm": distance_nm,
        "bearing_deg": props["bearing_deg"],
        "alert_level": _alert_level(distance_nm, inside=False),
        "nearest_point": (round(nearest.x, 6), round(nearest.y, 6)),
        "treaty": props.get("source1"),
        "treaty_url": props.get("url1"),
        "treaty_date": props.get("doc_date"),
        "length_km": props.get("length_km"),
        "source_file": "india_maritime_boundary_lines.geojson",
        "vintage": boundary_line_vintage(),
        "acquisition_timestamp": boundary_line_vintage(),
    }


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

# Which grid is on disk is decided on first use, NOT at import: the national
# GEBCO subset is a 100 MB download that routinely finishes AFTER the server is
# already up. A path pinned at import time left a running process on the 7.5-10.5 N
# / 77.5-80.5 E pilot box forever, so every click outside it silently fell through
# to ETOPO's 60" grid — which is too coarse to contain a small island at all, and
# answered "22 m of water" for a point on dry land.
@lru_cache(maxsize=1)
def _bathymetry() -> xr.Dataset:
    return xr.open_dataset(GEBCO_ALL_FILE if GEBCO_ALL_FILE.exists() else GEBCO_PILOT_FILE)


@lru_cache(maxsize=1)
def _etopo_bathymetry() -> xr.Dataset | None:
    for path in (ETOPO_ALL_FILE, ETOPO_PILOT_FILE):
        if path.exists():
            return xr.open_dataset(path)
    return None


def depth_at_point(lat: float, lon: float) -> DepthResult:
    """Bathymetry depth reading with GEBCO 2026 pilot priority and Pan-India ETOPO fallback.

    1. GEBCO 2026 extract (15" grid, 4-26 N / 60-100 E nationally, or the
       7.5-10.5 N / 77.5-80.5 E pilot box if the national file is absent).
    2. NOAA ETOPO grid (5.0-22.0 N, 70.0-92.0 E) covering all of South and Peninsular
       India (Kerala, Karnataka, Goa, Maharashtra, Tamil Nadu, Andhra Pradesh, Bay of Bengal).
    """
    gebco = _bathymetry()
    lat_min, lat_max = float(gebco.lat.min()), float(gebco.lat.max())
    lon_min, lon_max = float(gebco.lon.min()), float(gebco.lon.max())
    if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
        elevation = float(gebco["elevation"].sel(lat=lat, lon=lon, method="nearest").item())
        if elevation >= 0:
            return DepthResult(depth_m=None, on_land=True, shallow_hazard=False)
        depth = -elevation
        return DepthResult(
            depth_m=round(depth, 1), on_land=False, shallow_hazard=depth < SHALLOW_HAZARD_THRESHOLD_M
        )

    etopo = _etopo_bathymetry()
    if etopo is not None:
        e_lat_min, e_lat_max = float(etopo.latitude.min()), float(etopo.latitude.max())
        e_lon_min, e_lon_max = float(etopo.longitude.min()), float(etopo.longitude.max())
        if e_lat_min <= lat <= e_lat_max and e_lon_min <= lon <= e_lon_max:
            alt = float(etopo["altitude"].sel(latitude=lat, longitude=lon, method="nearest").item())
            if alt >= 0:
                return DepthResult(depth_m=None, on_land=True, shallow_hazard=False)
            depth = -alt
            return DepthResult(
                depth_m=round(depth, 1), on_land=False, shallow_hazard=depth < SHALLOW_HAZARD_THRESHOLD_M
            )

    return DepthResult(depth_m=None, on_land=False, shallow_hazard=False)


def bathymetry_heatmap_points(stride: int | None = None) -> list[dict[str, float]]:
    """Downsampled GEBCO depth points for Agent 8's Heatmap map layer
    (Architecture §11.1: "SST grid, chlorophyll concentration, wave
    height" — bathymetry is the one gridded field already loaded here).
    Every `stride`-th grid cell, land cells (elevation >= 0) skipped since
    a heatmap over depth has nothing to say about dry land.

    ponytail: the default stride is derived from the grid so the point
    count stays ~1-2k whatever is loaded — the same stride=16 that gives
    45x45 on the 720x720 pilot grid would give 200k features on the
    9600x5280 national one. Comfortably under the §4.7 feature-count
    budget without resampling to a raster — the tile pyramid
    (orca/tiles.py, Rasterio + cmocean + Pillow) is the real fix for a
    denser view; this is deliberately the coarse one, kept as a light
    fallback/complement.
    """
    ds = _bathymetry()
    if stride is None:
        stride = max(1, round(max(ds.sizes["lat"], ds.sizes["lon"]) / 45))
    lats = ds["lat"].values[::stride]
    lons = ds["lon"].values[::stride]
    # Stride before .values: the other order read the whole national grid
    # (~190 MB) to keep 1 cell in `stride`², enough alone to OOM a 512 MB host.
    elevation = ds["elevation"][::stride, ::stride].values
    points: list[dict[str, float]] = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            el = float(elevation[i, j])
            if el >= 0:
                continue  # land — not a depth point
            points.append({"lat": float(lat), "lon": float(lon), "depth_m": round(-el, 1)})
    return points


# ---- Surface currents (D3 particle layer) -----------------------------------

HYCOM_DIR = DATA_ROOT / "incois_osf_pfz" / "osf_hycom"


@lru_cache(maxsize=1)
def _hycom() -> xr.Dataset:
    """Newest HYCOM current forecast on disk. Globbed, not pinned to a date:
    `scripts/refresh_osf_forecasts.py` writes a new RSMC_hycom_<date>.nc every
    run, and a hardcoded filename means the map keeps drawing the old one."""
    files = sorted(HYCOM_DIR.glob("RSMC_hycom_*.nc"))
    if not files:
        raise FileNotFoundError(f"no RSMC_hycom_*.nc in {HYCOM_DIR} — run scripts/refresh_osf_forecasts.py")
    return xr.open_dataset(files[-1], decode_times=False)


def _hycom_times(ds: xr.Dataset) -> list[datetime]:
    """HYCOM's TIME axis as UTC datetimes. The file is opened with
    decode_times=False, so the "hours since <epoch>" units are applied here."""
    epoch = datetime.fromisoformat(ds["TIME"].attrs["units"].split("since", 1)[1].strip()).replace(tzinfo=UTC)
    return [epoch + timedelta(hours=float(h)) for h in ds["TIME"].values]


def hycom_nearest_step(when: datetime | None = None) -> tuple[int, str]:
    """(index, ISO valid time) of the HYCOM step nearest `when` (default now)."""
    times = _hycom_times(_hycom())
    when = when or datetime.now(UTC)
    i = min(range(len(times)), key=lambda k: abs(times[k] - when))
    return i, times[i].isoformat().replace("+00:00", "Z")


def current_vectors(
    bbox: tuple[float, float, float, float] = PILOT_BBOX_WSEN,
    stride: int = 4,
    step: int | None = None,
) -> list[dict[str, float]]:
    """Real HYCOM surface (DEPTH=0) current vectors at one forecast step
    (default: the step nearest now — `hycom_nearest_step`), cropped to the
    bbox and downsampled. It used to take the *last* step, up to five days
    ahead, while the map drew it as today's flow; the step's valid time now
    travels with the points (P4.15). U/V are eastward/northward m/s;
    `direction_deg` is the compass bearing the current flows TOWARD
    (oceanographic convention — the opposite sense of a meteorological wind
    direction).
    """
    ds = _hycom()
    if step is None:
        step = hycom_nearest_step()[0]
    west, south, east, north = bbox
    u = ds["UVEL"].isel(TIME=step, DEPTH=0).sel(LON=slice(west, east), LAT=slice(south, north))
    v = ds["VVEL"].isel(TIME=step, DEPTH=0).sel(LON=slice(west, east), LAT=slice(south, north))
    lats = u["LAT"].values[::stride]
    lons = u["LON"].values[::stride]
    u_vals = u.values[::stride, ::stride]
    v_vals = v.values[::stride, ::stride]

    points: list[dict[str, float]] = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            uu, vv = float(u_vals[i, j]), float(v_vals[i, j])
            if not (math.isfinite(uu) and math.isfinite(vv)):
                continue  # land / masked cell
            speed = math.hypot(uu, vv)
            direction = math.degrees(math.atan2(uu, vv)) % 360.0
            points.append({
                "lat": round(float(lat), 3),
                "lon": round(float(lon), 3),
                "speed_ms": round(speed, 3),
                "direction_deg": round(direction, 1) % 360.0,  # 359.96 must not round to 360.0
                "u": round(uu, 3),
                "v": round(vv, 3),
            })
    return points


# ---- Wind vectors (D3 flow-field overlay — archived, not live) --------------

WIND_DIR = DATA_ROOT / "tier3" / "mosdac" / "Wind"


def _latest_wind_file() -> Path:
    # Filenames encode "day of year 2026" (E06SCTL4AW_2026239_...) — lexicographic
    # sort is correct chronological sort here, same trick as the WW3 filename dates.
    files = sorted(WIND_DIR.glob("E06SCTL4AW_*.nc"))
    if not files:
        raise FileNotFoundError(f"No ScatSat wind files in {WIND_DIR}")
    return files[-1]


def wind_vectors(
    bbox: tuple[float, float, float, float] = PILOT_BBOX_WSEN,
    stride: int = 4,
) -> dict[str, Any]:
    """Archived EOS-06 Scatterometer (ScatSat) 10m wind, most recent daily
    snapshot on disk, cropped to the specified bbox (defaults to pilot bbox).
    U/V m/s -> speed_ms/direction_deg, meteorological convention — the
    direction the wind blows FROM.
    """
    path = _latest_wind_file()
    ds = xr.open_dataset(path)
    west, south, east, north = bbox
    u = ds["U"].isel(time=0, lev=0).sel(lat=slice(south, north), lon=slice(west, east))
    v = ds["V"].isel(time=0, lev=0).sel(lat=slice(south, north), lon=slice(west, east))
    lats = u["lat"].values[::stride]
    lons = u["lon"].values[::stride]
    u_vals = u.values[::stride, ::stride]
    v_vals = v.values[::stride, ::stride]

    points: list[dict[str, float]] = []
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            uu, vv = float(u_vals[i, j]), float(v_vals[i, j])
            if not (math.isfinite(uu) and math.isfinite(vv)):
                continue  # land / masked cell
            speed = math.hypot(uu, vv)
            # Meteorological convention: direction the wind blows FROM.
            direction = math.degrees(math.atan2(-uu, -vv)) % 360.0
            points.append({
                "lat": round(float(lat), 3),
                "lon": round(float(lon), 3),
                "speed_ms": round(speed, 3),
                "direction_deg": round(direction, 1) % 360.0,  # 359.96 must not round to 360.0
                "u": round(uu, 3),
                "v": round(vv, 3),
            })
    acquisition_date = str(ds["time"].values[0])[:10]
    return {
        "points": points,
        "bounds": list(bbox),
        "acquisition_date": acquisition_date,
        # A daily L4 composite, stamped at 12:00 UTC of its day: the time
        # slider treats it as one frame with a 24-hour step (P4.15).
        "valid_time": str(ds["time"].values[0])[:19] + "Z",
        "step_hours": 24,
        "source_file": path.name,
    }


# ---- Map layers (Day 6) -----------------------------------------------------

def generate_map_layers(
    user_lat: float | None = None, user_lon: float | None = None, *, zoom: int = 11
) -> dict[str, Any]:
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

    `zoom` selects the Douglas-Peucker tolerance bucket (plan §5.10 Day 10) —
    the caller's current MapLibre zoom, defaulting to 11 (full precision) for
    any caller that doesn't track zoom itself.
    """
    tolerance = _simplify_tolerance_for_zoom(zoom)
    boundary_features = []
    for f in load_boundaries():
        if not f.geofence_usable:
            continue
        clipped = f.geometry.intersection(_MAP_CLIP_BOX)
        if clipped.is_empty:
            continue  # outside the pilot region entirely — not this map's business
        # Annotated because `BaseGeometry.intersection` is typed as possibly
        # returning None, which makes `to_geojson(...)` below read as `str | None`
        # and `json.loads` reject it. The `is_empty` check above already rules
        # None out — an empty intersection is a geometry, not a missing one.
        simplified: BaseGeometry = clipped.simplify(tolerance, preserve_topology=True) if tolerance else clipped
        boundary_features.append({
            "type": "Feature",
            "geometry": geojson_geometry(simplified),
            "properties": {"name": f.name, "designation": f.designation, "source_file": f.source_file},
        })
    # Delimitation lines ride as their own layer, not mixed into "boundaries":
    # they are drawn as lines, they carry a treaty rather than a designation,
    # and nothing may geofence against them.
    line_features = []
    for geometry, props in load_boundary_lines():
        clipped = geometry.intersection(_MAP_CLIP_BOX)
        if clipped.is_empty:
            continue
        simplified = clipped.simplify(tolerance, preserve_topology=True) if tolerance else clipped
        line_features.append({
            "type": "Feature",
            "geometry": geojson_geometry(simplified),
            "properties": {
                "name": props.get("line_name"),
                "line_type": props.get("line_type"),
                "between": [props.get("territory1"), props.get("territory2")],
                "treaty": props.get("source1"),
                "treaty_date": props.get("doc_date"),
                "source_file": "india_maritime_boundary_lines.geojson",
            },
        })

    layers: dict[str, Any] = {
        "boundaries": {"type": "FeatureCollection", "features": boundary_features},
        "maritime_boundary_lines": {"type": "FeatureCollection", "features": line_features},
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


# ---- Seasonal fishing ban (runbook C4, PS-C8) -------------------------------

# The ban windows and the 12 NM carve-out live with the order they were
# transcribed from, so the dates and the rule that reads them cannot drift.
_BAN_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "refresh_fishing_ban_order.py"

# MRCC region -> the coast the DoF ban order puts it on. Andaman & Nicobar is
# an east-coast entry in the order despite being its own MRCC, and the
# Lakshadweep stations sit under MRCC Mumbai, which is the west coast — so
# the roster's own hierarchy answers this without a second geography table.
_MRCC_COAST = {
    "MRCC Mumbai": "west",
    "MRCC Chennai": "east",
    "MRCC Sri Vijaya Puram": "east",
}


def coast_of(lat: float, lon: float) -> str | None:
    """"east" or "west" for a position, via the nearest ICG rescue station.

    A longitude threshold cannot do this — the peninsula's dividing meridian
    moves with latitude, and Kanyakumari round to the Gulf of Mannar is
    west-coast water under the ban order while sitting east of Kochi. The
    39-station roster is already on disk with each station's parent MRCC, and
    that hierarchy is exactly the east/west split the order uses.
    """
    from orca.agents.distress import nearest_sar_station

    nearest = nearest_sar_station(lat, lon)
    return _MRCC_COAST.get(nearest["coordinating_mrcc"]) if nearest else None


def distance_to_shore_nm(lat: float, lon: float) -> float | None:
    """Geodesic distance in nautical miles to the Indian coastline or territorial baseline.

    G2 fix: Formerly, `fishing_ban_status` used `check_boundary_proximity(lat, lon,
    "Indian Exclusive Economic Zone")` as a proxy for distance from shore. That
    measured distance to the nearest EEZ-polygon edge. Near international maritime
    borders (such as the IMBL with Sri Lanka in Palk Bay / Gulf of Mannar), the nearest
    EEZ polygon edge is the treaty line with Sri Lanka (3-12 NM away), NOT the Indian
    coastline (20-35+ NM away). This caused offshore vessels in the EEZ to be falsely
    classified as inside the 12 NM territorial-waters carve-out, silently suppressing
    the central fishing ban disclosure.

    Here we measure geodesic distance to:
    1. The Indian land boundary from Census 2011 district polygons (_district_index).
    2. The declared Indian straight baselines from india_maritime_boundary_lines.geojson.
    If the district index is unavailable, falls back to the EEZ polygon edge.
    """
    pt = Point(lon, lat)
    min_m = float("inf")
    idx = _district_index()
    if idx is not None:
        tree, rows = idx
        nearest_indices = tree.query_nearest(pt)
        for i in nearest_indices:
            geom = rows[i]["geometry"]
            if geom.intersects(pt):
                return 0.0
            _, p2 = nearest_points(pt, geom)
            _, _, m = _GEOD.inv(pt.x, pt.y, p2.x, p2.y)
            min_m = min(min_m, m)

    # Also check declared Indian Straight Baselines
    for geom, props in load_boundary_lines():
        if props.get("line_type") == "Straight baseline":
            nearest = geom.interpolate(geom.project(pt))
            _, _, m = _GEOD.inv(pt.x, pt.y, nearest.x, nearest.y)
            min_m = min(min_m, m)

    if min_m < float("inf"):
        return round(min_m * NM_PER_METER, 3)

    try:
        return check_boundary_proximity(lat, lon, "Indian Exclusive Economic Zone").distance_nm
    except ValueError:
        return None


def fishing_ban_status(lat: float, lon: float, when: date | None = None) -> dict[str, Any]:
    """Is the uniform seasonal fishing ban in force at this position today?

    A regulatory answer, not a safety one: it never becomes a NO_GO by
    itself, and it never becomes a GO either. PS-C8 lists fishing-ban waters
    beside MPAs and ORCA had nothing to say about them.

    G2: Distance from shore is measured to the Indian coastline/baseline via
    `distance_to_shore_nm`, rather than the distance to the nearest EEZ edge
    (which near maritime borders like Sri Lanka is the IMBL, not the coast).
    """
    coast = coast_of(lat, lon)
    if coast is None:
        return {"available": False,
                "note": "no ICG station roster on disk — cannot tell which coast this is "
                        "(run scripts/scrape_icg_sar_stations.py)"}

    ban = _load_ban_rules()
    if ban is None:
        return {"available": False,
                "note": "no fishing-ban order on disk (run scripts/refresh_fishing_ban_order.py)"}

    shore_nm = distance_to_shore_nm(lat, lon)

    status = ban["ban_status"](coast, when or datetime.now(tz=UTC).date(), shore_nm, ban["windows"])
    return {
        "available": True,
        "distance_from_shore_nm": shore_nm,
        "distance_to_nearest_eez_edge_nm": shore_nm,
        "order": ban["order"],
        **status,
    }


@lru_cache(maxsize=1)
def _load_ban_rules() -> dict[str, Any] | None:
    """The ban dates and the date rule, loaded from the procurement script.

    Importing the script rather than re-implementing its window arithmetic:
    the edges are inclusive and the two coasts are offset by six weeks, and
    that logic already has a self-check behind it.
    """
    import importlib.util

    payload_path = DATA_ROOT / "tier1" / "fisheries" / "seasonal_fishing_ban.json"
    if not payload_path.exists() or not _BAN_SCRIPT.exists():
        return None
    spec = importlib.util.spec_from_file_location("orca_fishing_ban", _BAN_SCRIPT)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with open(payload_path, encoding="utf-8") as f:
        payload = json.load(f)
    return {"ban_status": module.ban_status, "windows": payload["windows"], "order": payload["order"]}


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

    wind = wind_vectors()
    assert wind["points"], "no wind points in pilot bbox"
    assert wind["acquisition_date"] < "2026-09-03"  # archived, never "now"
    assert all(0 <= p["direction_deg"] < 360 for p in wind["points"])

    # Andaman EEZ: an A&N position must land inside a geofence, and inside
    # the A&N record specifically, not the mainland polygon.
    andaman_hits = [f.name for f in point_in_polygon(10.5, 93.5)]
    assert andaman_hits == ["Indian Exclusive Economic Zone (Andaman & Nicobar)"] or         "Andaman" in " ".join(andaman_hits), andaman_hits

    # Treaty lines: 32 of them, drawn as their own layer, and never in the
    # polygon geofence index (a line contains nothing).
    assert len(load_boundary_lines()) == 32, len(load_boundary_lines())
    assert len(layers["maritime_boundary_lines"]["features"]) == 32
    assert all(f.geofence_usable is False or "LineString" not in f.geometry.geom_type
               for f in load_boundaries())
    line = nearest_boundary_line(lat, lon)
    assert line and line["distance_nm"] > 0 and line["treaty"], line
    # Regression, found 2026-09-25: this pilot point used to come back 0.7 nm
    # from "India Straight Baseline" — India's own coastline, not a boundary —
    # which read as an imminent breach on an ordinary question. It must always
    # be a line between India and another state, and far enough to be CLEAR.
    assert None not in line["between"], line
    assert line["distance_nm"] > 10 and line["alert_level"] == "CLEAR", line

    # District lookup: onshore resolves, offshore is honestly None.
    onshore = district_at_point(8.80, 78.14)
    assert onshore and onshore["state"] == "Tamil Nadu", onshore
    assert district_at_point(5.0, 72.0) is None  # mid Arabian Sea

    print("geospatial self-check ok:", imbl, depth, "wind@" + wind["acquisition_date"],
          f"| A&N geofence, {len(load_boundary_lines())} treaty lines, district={onshore['district']}")
