"""Voyage-corridor computation (D3, plan §5.1/§6). Not a LangGraph node —
voyage planning is an on-demand product surface like /map-layers or
/current-vectors, not a query-driven agent hand-off. Reuses Agent 6's
full-precision spatial functions and Agent 7's safety thresholds rather than
reinventing either: this module's own job is only the thing neither of them
does — walking a route and classifying it leg by leg, each leg evaluated at
the time the vessel would actually be there.
"""
from __future__ import annotations

import heapq
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Literal

import xarray as xr
from pyproj import Proj, Transformer
from shapely.geometry import LineString
from shapely.ops import transform

from orca.agents.geospatial import (
    DATA_ROOT,
    bearing_and_distance,
    depth_at_point,
    geojson_geometry,
    point_in_polygon,
)
from orca.agents.risk_assessment import _VESSEL_DELTAS, VesselClass, compute_confidence
from orca.contracts import Confidence, RouteSegment, SourceProvenance, VoyagePlan

WW3_DIR = DATA_ROOT / "incois_osf_pfz" / "osf_ww3"
_IMBL_PROXY_BOUNDARY = "Sri Lankan Exclusive Economic Zone"  # same stand-in graph.py uses — no dedicated IMBL line in the pilot data
_MPA_SOURCE_FILE = "india_marine_mpas.geojson"  # any geofence-usable hit loaded from this file is an MPA, regardless of which park

# P1.2 (`R-NEW-8`) — what to assume when the caller supplies no draft.
#
# These are the DEEPEST draft in each class, not a typical one, and that is
# the whole point. A draft is only ever used here to subtract from a sounding:
# assume too little and a route reads CLEAR over water the vessel would ground
# in. The old table held typical values (1.2 m for small_fishing) and applied
# them SILENTLY, so a 1.8 m-draft trawler-tender got a clearance answer
# computed for a boat 0.6 m shallower and was never told.
#
# They are assumptions, labelled as assumptions everywhere they reach a user
# (`VoyagePlan.draft_source`, `draft_disclosure`), and one supplied `draft_m`
# replaces them entirely. They are NOT measurements of anyone's vessel and
# must never be presented as one.
_ASSUMED_DRAFT_M: dict[VesselClass, float] = {
    "small_fishing": 1.8,
    "mechanized_trawler": 3.5,
    "cargo_vessel": 9.0,
}
# When the class itself is unknown, assume the most conservative class rather
# than the most common one — same direction, one level up.
_MOST_CONSERVATIVE_CLASS: VesselClass = "cargo_vessel"
_DRAFT_SAFETY_MARGIN_M = 2.0  # under-keel clearance a route must keep, not just "afloat"
CORRIDOR_BUFFER_NM = 2.0
STEP_NM = 2.0  # densification spacing — coarse enough to keep segment count sane over a multi-day route, fine enough a hazard can't hide between points
# Lightning has no multi-day forecast anywhere in this codebase (Agent 4's
# nowcast is "right now" only) — checking it for a leg the vessel won't
# reach for days would be fabricating a forecast that doesn't exist, so it
# is only ever checked for legs due soon (Ground Rule 3).
_LIGHTNING_NOWCAST_HORIZON_HOURS = 3.0


# The extracted point series covers the pilot ports only, so it is a fallback
# for "the grid is not on this machine", not a general substitute for it.
_OSF_POINT_MAX_KM = 60.0


@lru_cache(maxsize=1)
def _ww3() -> xr.Dataset | None:
    """The WW3 grid, or None when it is not on this machine.

    None rather than FileNotFoundError: the 6.5 GB NetCDF is gitignored data,
    so a fresh checkout genuinely does not have it, and a voyage plan that
    crashes outright there is worse than one that falls back to the extracted
    point series and says it did."""
    files = sorted(WW3_DIR.glob("rsmc_combined_ww3_*.nc"))
    if not files:
        return None
    # decode_times=False sidesteps a real bug, not a shortcut: the file's
    # "hours since 0001-01-01" units overflow pandas' datetime64[ns], and
    # xarray's fallback needs the cftime package, which is otherwise
    # unneeded in this codebase. Times are decoded by hand in wave_height_at.
    return xr.open_dataset(files[-1], decode_times=False)


def _ww3_hours_since_epoch(when: datetime) -> float:
    """`when` on WW3's own time axis ("hours since 0001-01-01", calendar
    "standard").

    The +48 h is not a fudge: that epoch is a Julian date, and Python's
    proleptic-Gregorian datetime(1, 1, 1) is two days later than it. Without the
    shift every lookup lands two days from the requested time — inside the file's
    range, so it returns a real wave height for the wrong day."""
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    return (when - epoch).total_seconds() / 3600.0 + 48.0


def wave_height_at(lat: float, lon: float, when: datetime) -> float | None:
    """Significant wave height (m) at the WW3 cell nearest (lat, lon), at the
    forecast step nearest `when` — not the first/latest step, the one the
    vessel will actually be sailing through. None outside the file's
    ~7-day/whole-basin coverage, never 0.0 as a stand-in for "unknown"
    (Ground Rule 3 / §5.7 — a missing measurement must not read as calm seas)."""
    ds = _ww3()
    if ds is None:
        return _ww3_point_fallback(lat, lon)
    hours = ds["TIME"].values
    target = _ww3_hours_since_epoch(when)
    if target < hours.min() - 1.5 or target > hours.max() + 1.5:
        return None
    lon_min, lon_max = float(ds["IOXAXIS"].min()), float(ds["IOXAXIS"].max())
    lat_min, lat_max = float(ds["IOYAXIS"].min()), float(ds["IOYAXIS"].max())
    if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
        return None
    idx = int(abs(hours - target).argmin())
    hs = ds["HS"].isel(TIME=idx).sel(IOXAXIS=lon, IOYAXIS=lat, method="nearest").item()
    return float(hs) if math.isfinite(hs) else None


# P5.23 — a leg's cross-track current "set" beyond this fraction of cruise
# speed is a real steering/drift concern (a small craft correcting for a
# strong beam current burns fuel and time it did not plan for); below it,
# the vessel's own heading correction absorbs the drift without comment. A
# disclosed, fixed cut — not a measured constant — same style as P5.8's day
# -trip distance and P5.21's CAP-alert proxy radius.
_SET_DRIFT_FRACTION = 0.20


def current_at(lat: float, lon: float, when: datetime) -> tuple[float, float] | None:
    """(speed_ms, direction_deg the current flows TOWARD) at the HYCOM cell
    nearest (lat, lon), at the forecast step nearest `when`. None when the
    grid is absent or the point falls outside its coverage — never 0.0 as a
    stand-in for "no current" (the same Ground Rule 3 `wave_height_at` and
    `depth_at_point` already hold to)."""
    from orca.agents import geospatial

    try:
        ds = geospatial._hycom()
    except FileNotFoundError:
        return None
    lon_min, lon_max = float(ds["LON"].min()), float(ds["LON"].max())
    lat_min, lat_max = float(ds["LAT"].min()), float(ds["LAT"].max())
    if not (lon_min <= lon <= lon_max and lat_min <= lat <= lat_max):
        return None
    step, _ = geospatial.hycom_nearest_step(when)
    u = ds["UVEL"].isel(TIME=step, DEPTH=0).sel(LON=lon, LAT=lat, method="nearest").item()
    v = ds["VVEL"].isel(TIME=step, DEPTH=0).sel(LON=lon, LAT=lat, method="nearest").item()
    if not (math.isfinite(u) and math.isfinite(v)):
        return None
    speed = math.hypot(u, v)
    direction = math.degrees(math.atan2(u, v)) % 360.0
    return speed, direction


def _cross_track_set(leg_bearing_deg: float, current_speed_ms: float, current_direction_deg: float) -> float:
    """The component of the current perpendicular to the leg's own course —
    the part that pushes a vessel off its intended line rather than along
    or against it (that part only changes ETA, not track)."""
    return abs(current_speed_ms * math.sin(math.radians(current_direction_deg - leg_bearing_deg)))


def _ww3_point_fallback(lat: float, lon: float) -> float | None:
    """Hs from `scripts/extract_osf_pilot.py`'s pre-extracted WW3 points when
    the source grid is absent. A single snapshot, so it carries no time
    dimension — the caller's `when` cannot be honoured and the value is the
    extraction's own forecast step, not the vessel's ETA. Returns None outside
    the extracted set rather than reaching for the nearest point at any range.
    """
    from orca.agents.geospatial import bearing_and_distance
    from orca.data.analytics_loaders import load_osf_point_forecasts

    points = [p for p in load_osf_point_forecasts("ww3") if p.get("significant_wave_height_m") is not None]
    if not points:
        return None
    nearest = min(points, key=lambda p: bearing_and_distance(lat, lon, p["lat"], p["lon"])[1])
    _, nm = bearing_and_distance(lat, lon, nearest["lat"], nearest["lon"])
    if nm * 1.852 > _OSF_POINT_MAX_KM:
        return None
    hs = float(nearest["significant_wave_height_m"])
    return hs if math.isfinite(hs) else None


def _corridor_polygon(points_lonlat: list[tuple[float, float]], buffer_nm: float) -> dict:
    """Buffers the route in a local azimuthal-equidistant projection (meters
    are actually meters there) rather than buffering degrees directly, which
    would distort east-west vs. north-south by latitude — same
    full-precision standard the rest of Agent 6's geometry holds to."""
    line = LineString(points_lonlat)
    lon0, lat0 = points_lonlat[len(points_lonlat) // 2]
    local = Proj(proj="aeqd", lat_0=lat0, lon_0=lon0, ellps="WGS84")
    to_local = Transformer.from_proj(Proj("epsg:4326"), local, always_xy=True).transform
    to_wgs84 = Transformer.from_proj(local, Proj("epsg:4326"), always_xy=True).transform
    buffered = transform(to_local, line).buffer(buffer_nm * 1852.0)
    return geojson_geometry(transform(to_wgs84, buffered))


def densify_route(
    origin: tuple[float, float], destination: tuple[float, float], *, step_nm: float = STEP_NM
) -> list[tuple[float, float]]:
    """Geodesic waypoints from origin to destination (lat, lon), roughly
    `step_nm` apart — pyproj.Geod.npts, not a straight lerp on the map
    projection, same geodesy `bearing_and_distance` already uses."""
    from orca.agents.geospatial import (
        _GEOD,  # module-private geodesic instance, reused rather than duplicated
    )

    (lat1, lon1), (lat2, lon2) = origin, destination
    _, total_nm = bearing_and_distance(lat1, lon1, lat2, lon2)
    n_points = max(int(total_nm // step_nm) - 1, 0)
    if n_points <= 0:
        return [origin, destination]
    intermediate = _GEOD.npts(lon1, lat1, lon2, lat2, n_points)
    return [origin] + [(lat, lon) for lon, lat in intermediate] + [destination]


def _classify_segment(
    segment_id: str, start: tuple[float, float], end: tuple[float, float],
    distance_nm: float, eta: datetime, vessel_class: VesselClass, draft_m: float,
    now: datetime, speed_kn: float = 8.0,
) -> tuple[RouteSegment, Confidence]:
    """Worst-first cascade over the same leg, evaluated at its midpoint: hard
    constraints (depth, MPA, boundary) always outrank soft ones (sea state,
    lightning), and BLOCKED always outranks CAUTION — Ground Rule 4, applied
    to one leg instead of one whole-query composite."""
    mid_lat = (start[0] + end[0]) / 2
    mid_lon = (start[1] + end[1]) / 2
    provenance: list[SourceProvenance] = []
    confidences: list[Confidence] = []

    depth = depth_at_point(mid_lat, mid_lon)
    provenance.append(SourceProvenance(dataset="GEBCO 2026 bathymetry", acquisition_timestamp="", freshness_minutes=0))
    if depth.on_land or (depth.depth_m is not None and depth.depth_m < draft_m + _DRAFT_SAFETY_MARGIN_M):
        detail = "On land" if depth.on_land else f"Depth {depth.depth_m}m at draft {draft_m}m + {_DRAFT_SAFETY_MARGIN_M}m clearance"
        return _segment(segment_id, start, end, distance_nm, eta, "SHALLOW", "BLOCKED", detail, provenance, depth_m=depth.depth_m), Confidence("HIGH", "Bathymetry grid, exact cell")

    mpa_hits = [f for f in point_in_polygon(mid_lat, mid_lon) if f.source_file == _MPA_SOURCE_FILE]
    if mpa_hits:
        provenance.append(SourceProvenance(dataset="Audited MPA geofence set", acquisition_timestamp="", freshness_minutes=0))
        detail = f"Inside {mpa_hits[0].name}"
        return _segment(segment_id, start, end, distance_nm, eta, "MPA", "BLOCKED", detail, provenance, depth_m=depth.depth_m), Confidence("HIGH", "MPA polygon containment")

    # P5.23 — a REGULATORY constraint, not a safety one, but still hard: a
    # leg the vessel would sail during an active, applicable seasonal ban is
    # not a route ORCA offers, regardless of sea state (same rule P5.5 wires
    # into the on-demand query path — the ban never becomes a NO_GO *there*
    # by itself, but a voyage LEG through it is exactly the case where
    # "you'd be breaking the ban to sail this" has to block the leg).
    from orca.agents.geospatial import fishing_ban_status

    ban = fishing_ban_status(mid_lat, mid_lon, eta.date())
    if ban.get("available") and ban.get("in_ban_period") and ban.get("applies_here"):
        provenance.append(SourceProvenance(dataset="Department of Fisheries seasonal ban order", acquisition_timestamp="", freshness_minutes=0))
        order = ban.get("order") or {}
        detail = f"Uniform seasonal fishing ban in force on the {ban.get('coast')} coast at ETA ({order.get('file_number', '')})".strip()
        return _segment(segment_id, start, end, distance_nm, eta, "REGULATORY", "BLOCKED", detail, provenance, depth_m=depth.depth_m), Confidence("HIGH", "Fishing-ban order, date-checked at ETA")

    try:
        from orca.agents.geospatial import check_boundary_proximity
        imbl = check_boundary_proximity(mid_lat, mid_lon, _IMBL_PROXY_BOUNDARY)
        provenance.append(SourceProvenance(dataset="Sri Lanka EEZ boundary (IMBL proxy)", acquisition_timestamp="", freshness_minutes=0))
        if imbl.distance_nm <= 1.0:
            return _segment(segment_id, start, end, distance_nm, eta, "BOUNDARY", "BLOCKED", f"{imbl.distance_nm}nm from IMBL", provenance, depth_m=depth.depth_m), Confidence("HIGH", "Geodesic boundary distance")
    except ValueError:
        imbl = None  # boundary not usable here — not fatal to the rest of the classification

    if (eta - now).total_seconds() / 3600.0 <= _LIGHTNING_NOWCAST_HORIZON_HOURS:
        from orca.agents import weather_intelligence as wia
        lightning = wia.get_lightning_nowcast(mid_lat, mid_lon, radius_km=25.0)
        provenance.append(SourceProvenance(dataset="Lightning nowcast (WIA)", acquisition_timestamp="", freshness_minutes=0))
        if lightning["lightning_active"]:
            return _segment(segment_id, start, end, distance_nm, eta, "LIGHTNING", "BLOCKED", "Active lightning nowcast near this leg", provenance, depth_m=depth.depth_m), Confidence("MEDIUM", "Nowcast only, not a forecast")

    _wind_delta_kmh, hs_delta = _VESSEL_DELTAS[vessel_class]
    danger_hs, caution_hs = 3.5 + hs_delta, 2.0 + hs_delta
    hs = wave_height_at(mid_lat, mid_lon, eta)
    if hs is not None:
        provenance.append(SourceProvenance(dataset="INCOIS RSMC WW3 wave forecast", acquisition_timestamp="", freshness_minutes=0))
        if hs >= danger_hs:
            return _segment(segment_id, start, end, distance_nm, eta, "ROUGH_SEA", "BLOCKED", f"Hs {hs}m at ETA", provenance, depth_m=depth.depth_m, wave_height_m=hs), Confidence("HIGH", "WW3 forecast at ETA")
    else:
        confidences.append(Confidence("LOW_DATA", "ETA outside WW3 7-day forecast window or basin extent"))

    if depth.depth_m is not None and depth.depth_m < draft_m + _DRAFT_SAFETY_MARGIN_M * 2:
        return _segment(segment_id, start, end, distance_nm, eta, "SHALLOW", "CAUTION", f"Depth {depth.depth_m}m, tight clearance at draft {draft_m}m", provenance, depth_m=depth.depth_m, wave_height_m=hs), Confidence("HIGH", "Bathymetry grid, exact cell")
    if imbl is not None and imbl.distance_nm <= 3.0:
        return _segment(segment_id, start, end, distance_nm, eta, "BOUNDARY", "CAUTION", f"{imbl.distance_nm}nm from IMBL", provenance, depth_m=depth.depth_m, wave_height_m=hs), Confidence("HIGH", "Geodesic boundary distance")
    if hs is not None and hs >= caution_hs:
        return _segment(segment_id, start, end, distance_nm, eta, "ROUGH_SEA", "CAUTION", f"Hs {hs}m at ETA", provenance, depth_m=depth.depth_m, wave_height_m=hs), Confidence("HIGH", "WW3 forecast at ETA")

    # P5.23 — surface-current cross-track set. Soft (CAUTION only): a strong
    # beam current is a steering/fuel concern the skipper corrects for, not a
    # reason the leg is impassable, which is why it sits after every BLOCKED
    # check and never promotes to one.
    current = current_at(mid_lat, mid_lon, eta)
    if current is not None:
        provenance.append(SourceProvenance(dataset="INCOIS OSF HYCOM surface currents", acquisition_timestamp="", freshness_minutes=0))
        leg_bearing, _ = bearing_and_distance(start[0], start[1], end[0], end[1])
        set_ms = _cross_track_set(leg_bearing, current[0], current[1])
        speed_ms = speed_kn * 0.514444
        if speed_ms > 0 and set_ms >= _SET_DRIFT_FRACTION * speed_ms:
            detail = f"Cross-track set {set_ms:.2f} m/s, {round(100 * set_ms / speed_ms)}% of cruise speed at ETA"
            return _segment(segment_id, start, end, distance_nm, eta, "SET_DRIFT", "CAUTION", detail, provenance, depth_m=depth.depth_m, wave_height_m=hs), Confidence("MEDIUM", "HYCOM forecast current at ETA")

    confidences.append(Confidence("HIGH", "No hazard triggered"))
    return _segment(segment_id, start, end, distance_nm, eta, "CLEAR", "CLEAR", "No hazard within checked thresholds", provenance, depth_m=depth.depth_m, wave_height_m=hs), compute_confidence(confidences)


def _segment(segment_id, start, end, distance_nm, eta, hazard_class, status, detail, provenance, depth_m=None, wave_height_m=None) -> RouteSegment:
    return RouteSegment(
        segment_id=segment_id, start=start, end=end, distance_nm=round(distance_nm, 2),
        eta=eta.isoformat().replace("+00:00", "Z"), hazard_class=hazard_class, status=status,
        detail=detail, source_provenance=tuple(provenance),
        depth_m=depth_m, wave_height_m=wave_height_m,
    )


def _classify_route(
    points: list[tuple[float, float]], departure: datetime, now: datetime,
    vessel_class: VesselClass, draft: float, speed_kn: float,
) -> tuple[list[RouteSegment], list[Confidence], Literal["GO", "CAUTION", "NO_GO"], str]:
    """The leg-by-leg walk shared by the direct route and every detour
    candidate — classifies each leg with the existing `_classify_segment`
    (unchanged) and rolls the legs up to one verdict, never averaged
    (Ground Rule 4)."""
    segments: list[RouteSegment] = []
    confidences: list[Confidence] = []
    cumulative_nm = 0.0
    for i in range(len(points) - 1):
        start, end = points[i], points[i + 1]
        _, leg_nm = bearing_and_distance(start[0], start[1], end[0], end[1])
        cumulative_nm += leg_nm
        eta = departure + timedelta(hours=cumulative_nm / speed_kn)
        segment, confidence = _classify_segment(f"seg-{i}", start, end, leg_nm, eta, vessel_class, draft, now, speed_kn)
        segments.append(segment)
        confidences.append(confidence)

    blocked = [s for s in segments if s.status == "BLOCKED"]
    caution = [s for s in segments if s.status == "CAUTION"]
    verdict: Literal["GO", "CAUTION", "NO_GO"]
    if blocked:
        verdict, reason = "NO_GO", f"{len(blocked)} segment(s) blocked: {', '.join(sorted({s.hazard_class for s in blocked}))}"
    elif caution:
        verdict, reason = "CAUTION", f"{len(caution)} segment(s) need caution: {', '.join(sorted({s.hazard_class for s in caution}))}"
    else:
        verdict, reason = "GO", "All segments clear"
    return segments, confidences, verdict, reason


def _offset_point(lat: float, lon: float, bearing_deg: float, distance_nm: float) -> tuple[float, float]:
    """A point `distance_nm` from (lat, lon) along `bearing_deg`, geodesic —
    same `_GEOD` instance `densify_route` already uses, not a flat-plane
    approximation that would drift at higher pilot-region latitudes."""
    from orca.agents.geospatial import _GEOD

    lon2, lat2, _ = _GEOD.fwd(lon, lat, bearing_deg, distance_nm * 1852.0)
    return lat2, lon2


# ---------------------------------------------------------------------------
# P5.7 — A* over a coarse grid, tried only when the offset/wait candidates
# below still fail to clear. This is the "genuinely sophisticated part":
# real constraint-checked planning around an actual obstacle (a shallow
# bank, an MPA, the boundary buffer), not just three fixed-shape guesses.
# It earns the word this point is named after — "route optimization"
# (README.md) was never true of the offset detours alone.
#
# Approach note (plan §5.7, decided 2026-09-18): a library least-cost path
# (skimage.graph.MCP_Geometric) is shorter to write but its cost surface is
# static — computed once, before the search runs. orca_final §8.2 makes wave
# height *at the ETA* load-bearing, and ETA depends on how far along the path
# a cell is, which is exactly what a static cost grid cannot express. This
# hand-written A* looks the forecast up at the arrival time the path-so-far
# implies, which is why it stays hand-written rather than reaching for the
# library. ~150 lines, per the plan's own estimate.
# ---------------------------------------------------------------------------

_ASTAR_GRID_CELLS_PER_AXIS = 22  # coarse: at most ~500 nodes, not a bathymetry-resolution grid
_ASTAR_PADDING_DEG = 0.3         # room either side of the direct line to actually route around something
# Same hard-block distance risk_assessment.evaluate_marine_safety and
# _classify_segment's own IMBL check use — one number, not a second opinion
# on how close is too close.
_ASTAR_IMBL_BUFFER_NM = 1.0
# A disclosed cost trade-off (nm of "distance" one metre of forecast wave
# height at arrival is worth to the search), not a measured constant — high
# enough that the search visibly prefers a longer flat-water leg over a
# shorter rough one, low enough that it does not detour halfway round India
# to shave off a few centimetres of chop.
_ASTAR_WAVE_PENALTY_NM_PER_M = 4.0
_ASTAR_NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = (
    (-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1),
)


@dataclass(frozen=True)
class _AstarGrid:
    lats: list[float]
    lons: list[float]
    blocked: list[list[bool]]  # [i][j] — i indexes lats, j indexes lons
    wave_height_m: list[list[float | None]]  # [i][j] — see _grid_wave_heights' own ceiling note


def _grid_depths_m(lats: list[float], lons: list[float]) -> list[list[float | None]]:
    """Depth (m, positive down) at every (lat, lon) in the grid, via ONE
    vectorized GEBCO lookup instead of `depth_at_point`'s one-call-per-point
    interface. Measured on this machine: a single `depth_at_point` call
    costs ~130ms (xarray's lazy-array I/O per `.sel()`); at even a coarse
    30x30 grid that is 900 calls, minutes instead of seconds. One batched
    `.sel()` pays that I/O cost once for the whole grid.
    None means on-land or outside the loaded grid's extent — both read as
    impassable by the caller, the same conservative direction
    `depth_at_point` already takes for "cannot confirm this is safe water"
    (no ETOPO fallback here: A*'s grid only needs to be right about *whether*
    a cell is passable, and the pilot GEBCO extract already covers the
    national bbox `PAN_INDIA_BBOX_WSEN` names).
    """
    from orca.agents import geospatial

    ds = geospatial._bathymetry()
    lat_min, lat_max = float(ds.lat.min()), float(ds.lat.max())
    lon_min, lon_max = float(ds.lon.min()), float(ds.lon.max())
    lat_idx = xr.DataArray(lats, dims="grid_lat")
    lon_idx = xr.DataArray(lons, dims="grid_lon")
    elevation = ds["elevation"].sel(lat=lat_idx, lon=lon_idx, method="nearest").values

    out: list[list[float | None]] = []
    for i, lat in enumerate(lats):
        row: list[float | None] = []
        for j, lon in enumerate(lons):
            if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                row.append(None)
                continue
            el = float(elevation[i, j])
            row.append(None if el >= 0 else -el)
        out.append(row)
    return out


def _grid_wave_heights(lats: list[float], lons: list[float], eta_estimate: datetime) -> list[list[float | None]]:
    """Forecast wave height at every grid cell, at the ONE forecast step
    nearest `eta_estimate` — a single vectorized WW3 lookup, the same
    performance reasoning as `_grid_depths_m` (measured: `wave_height_at`
    alone costs ~130ms/call).

    ponytail: this is the one real simplification against the plan's literal
    "cost looked up at arrival hour" — the true per-EDGE arrival hour (which
    grows as the search extends a candidate path) would need one WW3 access
    per edge, and at 130ms/access that is minutes per plan on a live query
    path. Using one representative ETA for the whole coarse grid keeps this
    a real forecast lookup (not a static default), just not a fresh one per
    edge. Upgrade path if this ever matters: precompute this same batched
    lookup at 2-3 forecast steps spanning the plausible trip duration and
    pick the nearest per-edge, still O(steps) WW3 accesses rather than
    O(edges). Returns all-None (no penalty applied, distance-only search)
    when the WW3 grid is not on this machine — the same fallback
    `wave_height_at` takes, propagated rather than re-decided here.
    """
    from orca.agents import geospatial

    ds = _ww3()
    if ds is None:
        return [[None] * len(lons) for _ in lats]
    hours = ds["TIME"].values
    target = _ww3_hours_since_epoch(eta_estimate)
    step = int(abs(hours - target).argmin())
    lon_min, lon_max = float(ds.IOXAXIS.min()), float(ds.IOXAXIS.max())
    lat_min, lat_max = float(ds.IOYAXIS.min()), float(ds.IOYAXIS.max())

    lat_idx = xr.DataArray(lats, dims="grid_lat")
    lon_idx = xr.DataArray(lons, dims="grid_lon")
    # .load() forces this one time-step out of the file before the vectorized
    # .sel() below: left lazy, xarray's scipy backend (this file is netCDF3 —
    # GEBCO's netCDF4 backend is unaffected) mis-resolves two same-length
    # fancy indexers passed together, returning wrong data or raising
    # IndexError — reliably for a bbox spanning ~7+ degrees of longitude
    # (west coast to east coast), coincidentally never for the short hops
    # this was tested against.
    hs = ds["HS"].isel(TIME=step).load().sel(IOXAXIS=lon_idx, IOYAXIS=lat_idx, method="nearest").values

    out: list[list[float | None]] = []
    for i, lat in enumerate(lats):
        row: list[float | None] = []
        for j, lon in enumerate(lons):
            if not (lat_min <= lat <= lat_max and lon_min <= lon <= lon_max):
                row.append(None)
                continue
            v = float(hs[i, j])
            row.append(v if math.isfinite(v) else None)
        out.append(row)
    return out


def _build_astar_grid(origin: tuple[float, float], destination: tuple[float, float], departure: datetime, speed_kn: float, draft_m: float) -> _AstarGrid:
    """Impassability mask over the bounding box of origin/destination (plus
    padding to actually have room to route around something): depth <
    draft + margin (shallow or on land), inside an MPA polygon, or within
    the IMBL buffer of the nearest treaty line — the same three hard
    constraints `_classify_segment` blocks a leg on, applied per grid cell
    instead of per densified waypoint. Depth and wave height are fetched in
    two batched lookups; only the MPA/boundary checks stay per-cell (each is
    already fast — a spatial-index query, not a lazy-array read — and only
    runs for cells depth has not already ruled out)."""
    from orca.agents.geospatial import nearest_boundary_line

    min_lat = min(origin[0], destination[0]) - _ASTAR_PADDING_DEG
    max_lat = max(origin[0], destination[0]) + _ASTAR_PADDING_DEG
    min_lon = min(origin[1], destination[1]) - _ASTAR_PADDING_DEG
    max_lon = max(origin[1], destination[1]) + _ASTAR_PADDING_DEG

    n = _ASTAR_GRID_CELLS_PER_AXIS
    lats = [min_lat + (max_lat - min_lat) * i / (n - 1) for i in range(n)]
    lons = [min_lon + (max_lon - min_lon) * j / (n - 1) for j in range(n)]

    depths = _grid_depths_m(lats, lons)
    _, direct_nm = bearing_and_distance(origin[0], origin[1], destination[0], destination[1])
    eta_estimate = departure + timedelta(hours=direct_nm / speed_kn)
    wave_heights = _grid_wave_heights(lats, lons, eta_estimate)

    blocked = [[False] * n for _ in range(n)]
    for i, lat in enumerate(lats):
        for j, lon in enumerate(lons):
            depth_m = depths[i][j]
            if depth_m is None or depth_m < draft_m + _DRAFT_SAFETY_MARGIN_M:
                blocked[i][j] = True
                continue
            if any(f.source_file == _MPA_SOURCE_FILE for f in point_in_polygon(lat, lon)):
                blocked[i][j] = True
                continue
            line = nearest_boundary_line(lat, lon)
            if line is not None and line["distance_nm"] <= _ASTAR_IMBL_BUFFER_NM:
                blocked[i][j] = True
    return _AstarGrid(lats=lats, lons=lons, blocked=blocked, wave_height_m=wave_heights)


def _nearest_grid_index(grid: _AstarGrid, lat: float, lon: float) -> tuple[int, int]:
    i = min(range(len(grid.lats)), key=lambda k: abs(grid.lats[k] - lat))
    j = min(range(len(grid.lons)), key=lambda k: abs(grid.lons[k] - lon))
    return i, j


def astar_route(
    origin: tuple[float, float], destination: tuple[float, float], departure: datetime,
    speed_kn: float, draft_m: float,
) -> list[tuple[float, float]] | None:
    """A waypoint path from `origin` to `destination` around the grid's
    impassable cells, or None when no such path exists (the origin or
    destination itself sits on an impassable cell, or they are on two
    disconnected pieces of water this coarse a grid cannot bridge — a real
    outcome, reported as one, never a straight line drawn through the
    obstacle it was supposed to avoid).

    Edge cost is geodesic distance plus a wave-height penalty (`_grid_wave_heights`'
    own docstring names the one simplification against a truly per-edge
    forecast lookup).
    """
    grid = _build_astar_grid(origin, destination, departure, speed_kn, draft_m)
    start = _nearest_grid_index(grid, *origin)
    goal = _nearest_grid_index(grid, *destination)
    if grid.blocked[start[0]][start[1]] or grid.blocked[goal[0]][goal[1]]:
        return None

    def heuristic(node: tuple[int, int]) -> float:
        lat, lon = grid.lats[node[0]], grid.lons[node[1]]
        _, nm = bearing_and_distance(lat, lon, destination[0], destination[1])
        return nm

    dist_score: dict[tuple[int, int], float] = {start: 0.0}  # real nm travelled, for ETA — never the search cost
    cost_score: dict[tuple[int, int], float] = {start: 0.0}  # A* g-value, distance + wave penalty
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    open_heap: list[tuple[float, tuple[int, int]]] = [(heuristic(start), start)]
    closed: set[tuple[int, int]] = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        closed.add(current)
        if current == goal:
            break
        ci, cj = current
        clat, clon = grid.lats[ci], grid.lons[cj]
        for di, dj in _ASTAR_NEIGHBOR_OFFSETS:
            ni, nj = ci + di, cj + dj
            if not (0 <= ni < len(grid.lats) and 0 <= nj < len(grid.lons)):
                continue
            if grid.blocked[ni][nj]:
                continue
            neighbor = (ni, nj)
            nlat, nlon = grid.lats[ni], grid.lons[nj]
            _, step_nm = bearing_and_distance(clat, clon, nlat, nlon)
            tentative_dist = dist_score[current] + step_nm
            hs = grid.wave_height_m[ni][nj]
            step_cost = step_nm + (_ASTAR_WAVE_PENALTY_NM_PER_M * hs if hs is not None else 0.0)
            tentative_cost = cost_score[current] + step_cost
            if neighbor not in cost_score or tentative_cost < cost_score[neighbor]:
                dist_score[neighbor] = tentative_dist
                cost_score[neighbor] = tentative_cost
                came_from[neighbor] = current
                heapq.heappush(open_heap, (tentative_cost + heuristic(neighbor), neighbor))

    if goal != start and goal not in came_from:
        return None  # exhausted the open set without ever reaching the goal

    path_idx = [goal]
    node = goal
    while node != start:
        node = came_from[node]
        path_idx.append(node)
    path_idx.reverse()
    interior = [(grid.lats[i], grid.lons[j]) for i, j in path_idx[1:-1]]
    return [origin, *interior, destination]


# Hazard buffer + a real margin, not a token offset — CORRIDOR_BUFFER_NM is
# the width already drawn on the map for the direct route, so a detour has
# to clear that plus room to spare or it is not meaningfully a different
# corridor.
_DETOUR_OFFSET_NM = CORRIDOR_BUFFER_NM + 2.0
_DETOUR_WAIT_HOURS = 6.0


def _detour_candidates(
    origin: tuple[float, float], destination: tuple[float, float], departure: datetime,
) -> list[tuple[str, tuple[float, float], tuple[float, float], datetime]]:
    """(strategy, candidate_origin, candidate_destination, candidate_departure)
    for each alternate worth trying when the direct route is NO_GO: the
    corridor shifted perpendicular to the original bearing, both directions,
    plus departing later so an ETA-dependent hazard (lightning nowcast,
    wave forecast) may have cleared by the time the vessel would reach it —
    checklist P0 #2's own three-candidate scope, not a full path solver."""
    bearing, _ = bearing_and_distance(origin[0], origin[1], destination[0], destination[1])
    return [
        (
            "offset_east", _offset_point(*origin, bearing + 90, _DETOUR_OFFSET_NM),
            _offset_point(*destination, bearing + 90, _DETOUR_OFFSET_NM), departure,
        ),
        (
            "offset_west", _offset_point(*origin, bearing - 90, _DETOUR_OFFSET_NM),
            _offset_point(*destination, bearing - 90, _DETOUR_OFFSET_NM), departure,
        ),
        ("wait_6h", origin, destination, departure + timedelta(hours=_DETOUR_WAIT_HOURS)),
    ]


def _nearest_safe_harbour(destination: tuple[float, float], speed_kn: float) -> dict[str, Any] | None:
    """The closest ICG rescue station to the destination — the same roster
    `distress.nearest_sar_station` already serves SOS calls from, reused
    rather than sourcing a second port gazetteer for the same coastline —
    with true bearing/distance from the destination and an ETA at the
    plan's own cruise speed (P5.24)."""
    from orca.agents.distress import nearest_sar_station

    station = nearest_sar_station(*destination)
    if station is None:
        return None
    bearing_deg, distance_nm = bearing_and_distance(destination[0], destination[1], station["latitude"], station["longitude"])
    return {
        "name": station["station"], "kind": station["kind"], "latitude": station["latitude"], "longitude": station["longitude"],
        "bearing_deg": round(bearing_deg, 1), "distance_nm": round(distance_nm, 1),
        "eta_hours": round(distance_nm / speed_kn, 1) if speed_kn > 0 else None,
    }


def plan_voyage(
    origin: tuple[float, float], destination: tuple[float, float], *,
    vessel_class: VesselClass = "small_fishing", departure_time: str | None = None,
    speed_kn: float = 8.0, draft_m: float | None = None, fuel_burn_lph: float | None = None,
) -> VoyagePlan:
    """Densifies origin->destination, classifies each leg at the time the
    vessel would actually reach it, and rolls the legs up to one verdict:
    any BLOCKED segment forces NO_GO, any CAUTION (with no BLOCKED) forces
    CAUTION, never averaged (Ground Rule 4).

    A NO_GO direct route is not the final answer: this tries the detour
    candidates above and, if one clears, returns THAT as the plan
    (`rerouted=True`) rather than a blocked line the caller has to notice
    and re-request around. Never returns a re-routed line that is itself
    NO_GO — a candidate that doesn't clear is recorded in
    `alternatives_tried` and discarded, same as the checklist asks
    ("say so honestly rather than picking the least-bad NO_GO")."""
    now = datetime.now(timezone.utc)
    departure = datetime.fromisoformat(departure_time.replace("Z", "+00:00")) if departure_time else now
    if departure.tzinfo is None:
        departure = departure.replace(tzinfo=timezone.utc)
    draft_source: Literal["supplied", "assumed_deepest_of_class"]
    if draft_m is not None:
        draft, draft_source = draft_m, "supplied"
        draft_disclosure = None
    else:
        draft = _ASSUMED_DRAFT_M.get(vessel_class) or _ASSUMED_DRAFT_M[_MOST_CONSERVATIVE_CLASS]
        draft_source = "assumed_deepest_of_class"
        draft_disclosure = (
            f"No draft was given, so this plan assumes {draft:.1f} m — the deepest draft in the "
            f"{vessel_class.replace('_', ' ')} class, not a measurement of your vessel. "
            "Enter your real draft to re-check the shallow legs against it."
        )

    points = densify_route(origin, destination)
    segments, confidences, verdict, reason = _classify_route(points, departure, now, vessel_class, draft, speed_kn)
    _, direct_nm = bearing_and_distance(origin[0], origin[1], destination[0], destination[1])

    rerouted = False
    alternatives_tried: list[dict[str, Any]] = []
    if verdict == "NO_GO":
        best: dict[str, Any] | None = None
        for name, cand_origin, cand_destination, cand_departure in _detour_candidates(origin, destination, departure):
            cand_points = densify_route(cand_origin, cand_destination)
            cand_segments, cand_confidences, cand_verdict, cand_reason = _classify_route(
                cand_points, cand_departure, now, vessel_class, draft, speed_kn,
            )
            _, cand_nm = bearing_and_distance(cand_origin[0], cand_origin[1], cand_destination[0], cand_destination[1])
            added_nm = round(max(cand_nm - direct_nm, 0.0), 1)
            alternatives_tried.append({"strategy": name, "verdict": cand_verdict, "added_nm": added_nm})
            if cand_verdict != "NO_GO" and (best is None or added_nm < best["added_nm"]):
                best = {
                    "strategy": name, "added_nm": added_nm, "origin": cand_origin, "destination": cand_destination,
                    "departure": cand_departure, "points": cand_points, "segments": cand_segments,
                    "confidences": cand_confidences, "verdict": cand_verdict, "reason": cand_reason,
                }
        if best is None:
            # P5.7 — the three fixed-shape guesses above found nothing; try
            # an actual path search around the obstacle before giving up.
            astar_points = astar_route(origin, destination, departure, speed_kn, draft)
            if astar_points is not None and len(astar_points) > 2:
                astar_segments, astar_confidences, astar_verdict, astar_reason = _classify_route(
                    astar_points, departure, now, vessel_class, draft, speed_kn,
                )
                astar_nm = sum(s.distance_nm for s in astar_segments)
                added_nm = round(max(astar_nm - direct_nm, 0.0), 1)
                alternatives_tried.append({"strategy": "astar", "verdict": astar_verdict, "added_nm": added_nm})
                if astar_verdict != "NO_GO":
                    best = {
                        "strategy": "astar", "added_nm": added_nm, "origin": origin, "destination": destination,
                        "departure": departure, "points": astar_points, "segments": astar_segments,
                        "confidences": astar_confidences, "verdict": astar_verdict, "reason": astar_reason,
                    }
        if best is not None:
            rerouted = True
            origin, destination, departure, points = best["origin"], best["destination"], best["departure"], best["points"]
            segments, confidences, verdict = best["segments"], best["confidences"], best["verdict"]
            reason = (
                f"Direct route blocked; rerouted via {best['strategy'].replace('_', ' ')} "
                f"(+{best['added_nm']:.1f} nm). {best['reason']}"
            )
        else:
            tried = ", ".join(f"{a['strategy']}: {a['verdict']}" for a in alternatives_tried)
            reason = f"{reason} — no clear detour found ({tried})"

    corridor = _corridor_polygon([(lon, lat) for lat, lon in points], CORRIDOR_BUFFER_NM)
    total_nm = sum(s.distance_nm for s in segments)
    fuel_estimate_liters = round(total_nm / speed_kn * fuel_burn_lph, 1) if fuel_burn_lph is not None and speed_kn > 0 else None

    return VoyagePlan(
        voyage_id=str(uuid.uuid4()), origin=origin, destination=destination, vessel_class=vessel_class,
        departure_time=departure.isoformat().replace("+00:00", "Z"), segments=tuple(segments),
        verdict=verdict, verdict_reason=reason, corridor_geojson=corridor,
        confidence=compute_confidence(confidences), rerouted=rerouted, alternatives_tried=tuple(alternatives_tried),
        draft_m=draft, draft_source=draft_source, draft_disclosure=draft_disclosure,
        nearest_safe_harbour=_nearest_safe_harbour(destination, speed_kn),
        fuel_burn_lph=fuel_burn_lph, fuel_estimate_liters=fuel_estimate_liters,
    )


if __name__ == "__main__":
    # Gulf of Mannar shallows sit between these two Thoothukudi-area points —
    # a straight-line route between them must classify BLOCKED/SHALLOW on at
    # least one leg, the same "genuinely sophisticated part" the plan calls out.
    shallow_plan = plan_voyage((8.75, 78.20), (9.05, 78.95), vessel_class="small_fishing", speed_kn=8.0)
    assert any(s.hazard_class == "SHALLOW" for s in shallow_plan.segments), [s.hazard_class for s in shallow_plan.segments]
    assert shallow_plan.verdict in ("CAUTION", "NO_GO")

    # A short deep-water hop off the continental shelf, far from any shore,
    # boundary or MPA, must never hard-block — real sea state on the day can
    # still legitimately trigger CAUTION, so this only rules out NO_GO.
    open_water_plan = plan_voyage((8.20, 78.60), (8.10, 78.65), vessel_class="small_fishing", speed_kn=8.0)
    assert open_water_plan.verdict != "NO_GO", (open_water_plan.verdict, [(s.hazard_class, s.status) for s in open_water_plan.segments])
    assert all(s.hazard_class in ("CLEAR", "ROUGH_SEA") for s in open_water_plan.segments)

    etas = [datetime.fromisoformat(s.eta.replace("Z", "+00:00")) for s in open_water_plan.segments]
    assert etas == sorted(etas), "ETAs must be monotonically increasing along the route"

    assert open_water_plan.corridor_geojson["type"] in ("Polygon", "MultiPolygon")

    print("voyage self-check ok:", shallow_plan.verdict, shallow_plan.verdict_reason, "|", open_water_plan.verdict)
