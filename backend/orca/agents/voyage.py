"""Voyage-corridor computation (D3, plan §5.1/§6). Not a LangGraph node —
voyage planning is an on-demand product surface like /map-layers or
/current-vectors, not a query-driven agent hand-off. Reuses Agent 6's
full-precision spatial functions and Agent 7's safety thresholds rather than
reinventing either: this module's own job is only the thing neither of them
does — walking a route and classifying it leg by leg, each leg evaluated at
the time the vessel would actually be there.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

import xarray as xr
from pyproj import Proj, Transformer
from shapely import to_geojson
from shapely.geometry import LineString
from shapely.ops import transform

from orca.agents.geospatial import (
    DATA_ROOT,
    bearing_and_distance,
    depth_at_point,
    point_in_polygon,
)
from orca.agents.risk_assessment import VesselClass, _VESSEL_DELTAS, compute_confidence
from orca.contracts import Confidence, RouteSegment, SourceProvenance, VoyagePlan

WW3_DIR = DATA_ROOT / "incois_osf_pfz" / "osf_ww3"
_IMBL_PROXY_BOUNDARY = "Sri Lankan Exclusive Economic Zone"  # same stand-in graph.py uses — no dedicated IMBL line in the pilot data
_MPA_SOURCE_FILE = "india_marine_mpas.geojson"  # any geofence-usable hit loaded from this file is an MPA, regardless of which park

# Draft-by-vessel-class defaults (m), used only when the caller doesn't supply
# a real one — a different physical quantity from risk_assessment's wind/wave
# deltas, so its own table rather than reusing that one.
_DEFAULT_DRAFT_M: dict[VesselClass, float] = {
    "small_fishing": 1.2,
    "mechanized_trawler": 2.5,
    "cargo_vessel": 6.0,
}
_DRAFT_SAFETY_MARGIN_M = 2.0  # under-keel clearance a route must keep, not just "afloat"
CORRIDOR_BUFFER_NM = 2.0
STEP_NM = 2.0  # densification spacing — coarse enough to keep segment count sane over a multi-day route, fine enough a hazard can't hide between points
# Lightning has no multi-day forecast anywhere in this codebase (Agent 4's
# nowcast is "right now" only) — checking it for a leg the vessel won't
# reach for days would be fabricating a forecast that doesn't exist, so it
# is only ever checked for legs due soon (Ground Rule 3).
_LIGHTNING_NOWCAST_HORIZON_HOURS = 3.0


@lru_cache(maxsize=1)
def _ww3() -> xr.Dataset:
    files = sorted(WW3_DIR.glob("rsmc_combined_ww3_*.nc"))
    if not files:
        raise FileNotFoundError(f"No WW3 files in {WW3_DIR}")
    # decode_times=False sidesteps a real bug, not a shortcut: the file's
    # "hours since 0001-01-01" units overflow pandas' datetime64[ns], and
    # xarray's fallback needs the cftime package, which is otherwise
    # unneeded in this codebase. Times are decoded by hand in wave_height_at.
    return xr.open_dataset(files[-1], decode_times=False)


def _ww3_hours_since_epoch(when: datetime) -> float:
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    return (when - epoch).total_seconds() / 3600.0


def wave_height_at(lat: float, lon: float, when: datetime) -> float | None:
    """Significant wave height (m) at the WW3 cell nearest (lat, lon), at the
    forecast step nearest `when` — not the first/latest step, the one the
    vessel will actually be sailing through. None outside the file's
    ~7-day/whole-basin coverage, never 0.0 as a stand-in for "unknown"
    (Ground Rule 3 / §5.7 — a missing measurement must not read as calm seas)."""
    ds = _ww3()
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
    return json.loads(to_geojson(transform(to_wgs84, buffered)))


def densify_route(
    origin: tuple[float, float], destination: tuple[float, float], *, step_nm: float = STEP_NM
) -> list[tuple[float, float]]:
    """Geodesic waypoints from origin to destination (lat, lon), roughly
    `step_nm` apart — pyproj.Geod.npts, not a straight lerp on the map
    projection, same geodesy `bearing_and_distance` already uses."""
    from orca.agents.geospatial import _GEOD  # module-private geodesic instance, reused rather than duplicated

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
    now: datetime,
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
        return _segment(segment_id, start, end, distance_nm, eta, "SHALLOW", "BLOCKED", detail, provenance), Confidence("HIGH", "Bathymetry grid, exact cell")

    mpa_hits = [f for f in point_in_polygon(mid_lat, mid_lon) if f.source_file == _MPA_SOURCE_FILE]
    if mpa_hits:
        provenance.append(SourceProvenance(dataset="Audited MPA geofence set", acquisition_timestamp="", freshness_minutes=0))
        detail = f"Inside {mpa_hits[0].name}"
        return _segment(segment_id, start, end, distance_nm, eta, "MPA", "BLOCKED", detail, provenance), Confidence("HIGH", "MPA polygon containment")

    try:
        from orca.agents.geospatial import check_boundary_proximity
        imbl = check_boundary_proximity(mid_lat, mid_lon, _IMBL_PROXY_BOUNDARY)
        provenance.append(SourceProvenance(dataset="Sri Lanka EEZ boundary (IMBL proxy)", acquisition_timestamp="", freshness_minutes=0))
        if imbl.distance_nm <= 1.0:
            return _segment(segment_id, start, end, distance_nm, eta, "BOUNDARY", "BLOCKED", f"{imbl.distance_nm}nm from IMBL", provenance), Confidence("HIGH", "Geodesic boundary distance")
    except ValueError:
        imbl = None  # boundary not usable here — not fatal to the rest of the classification

    if (eta - now).total_seconds() / 3600.0 <= _LIGHTNING_NOWCAST_HORIZON_HOURS:
        from orca.agents import weather_intelligence as wia
        lightning = wia.get_lightning_nowcast(mid_lat, mid_lon, radius_km=25.0)
        provenance.append(SourceProvenance(dataset="Lightning nowcast (WIA)", acquisition_timestamp="", freshness_minutes=0))
        if lightning["lightning_active"]:
            return _segment(segment_id, start, end, distance_nm, eta, "LIGHTNING", "BLOCKED", "Active lightning nowcast near this leg", provenance), Confidence("MEDIUM", "Nowcast only, not a forecast")

    wind_delta_kmh, hs_delta = _VESSEL_DELTAS[vessel_class]
    danger_hs, caution_hs = 3.5 + hs_delta, 2.0 + hs_delta
    hs = wave_height_at(mid_lat, mid_lon, eta)
    if hs is not None:
        provenance.append(SourceProvenance(dataset="INCOIS RSMC WW3 wave forecast", acquisition_timestamp="", freshness_minutes=0))
        if hs >= danger_hs:
            return _segment(segment_id, start, end, distance_nm, eta, "ROUGH_SEA", "BLOCKED", f"Hs {hs}m at ETA", provenance), Confidence("HIGH", "WW3 forecast at ETA")
    else:
        confidences.append(Confidence("LOW_DATA", "ETA outside WW3 7-day forecast window or basin extent"))

    if depth.depth_m is not None and depth.depth_m < draft_m + _DRAFT_SAFETY_MARGIN_M * 2:
        return _segment(segment_id, start, end, distance_nm, eta, "SHALLOW", "CAUTION", f"Depth {depth.depth_m}m, tight clearance at draft {draft_m}m", provenance), Confidence("HIGH", "Bathymetry grid, exact cell")
    if imbl is not None and imbl.distance_nm <= 3.0:
        return _segment(segment_id, start, end, distance_nm, eta, "BOUNDARY", "CAUTION", f"{imbl.distance_nm}nm from IMBL", provenance), Confidence("HIGH", "Geodesic boundary distance")
    if hs is not None and hs >= caution_hs:
        return _segment(segment_id, start, end, distance_nm, eta, "ROUGH_SEA", "CAUTION", f"Hs {hs}m at ETA", provenance), Confidence("HIGH", "WW3 forecast at ETA")

    confidences.append(Confidence("HIGH", "No hazard triggered"))
    return _segment(segment_id, start, end, distance_nm, eta, "CLEAR", "CLEAR", "No hazard within checked thresholds", provenance), compute_confidence(confidences)


def _segment(segment_id, start, end, distance_nm, eta, hazard_class, status, detail, provenance) -> RouteSegment:
    return RouteSegment(
        segment_id=segment_id, start=start, end=end, distance_nm=round(distance_nm, 2),
        eta=eta.isoformat().replace("+00:00", "Z"), hazard_class=hazard_class, status=status,
        detail=detail, source_provenance=tuple(provenance),
    )


def plan_voyage(
    origin: tuple[float, float], destination: tuple[float, float], *,
    vessel_class: VesselClass = "small_fishing", departure_time: str | None = None,
    speed_kn: float = 8.0, draft_m: float | None = None,
) -> VoyagePlan:
    """Densifies origin->destination, classifies each leg at the time the
    vessel would actually reach it, and rolls the legs up to one verdict:
    any BLOCKED segment forces NO_GO, any CAUTION (with no BLOCKED) forces
    CAUTION, never averaged (Ground Rule 4)."""
    now = datetime.now(timezone.utc)
    departure = datetime.fromisoformat(departure_time.replace("Z", "+00:00")) if departure_time else now
    if departure.tzinfo is None:
        departure = departure.replace(tzinfo=timezone.utc)
    draft = draft_m if draft_m is not None else _DEFAULT_DRAFT_M.get(vessel_class, 1.2)

    points = densify_route(origin, destination)
    segments: list[RouteSegment] = []
    confidences: list[Confidence] = []
    cumulative_nm = 0.0
    for i in range(len(points) - 1):
        start, end = points[i], points[i + 1]
        _, leg_nm = bearing_and_distance(start[0], start[1], end[0], end[1])
        cumulative_nm += leg_nm
        eta = departure + timedelta(hours=cumulative_nm / speed_kn)
        segment, confidence = _classify_segment(f"seg-{i}", start, end, leg_nm, eta, vessel_class, draft, now)
        segments.append(segment)
        confidences.append(confidence)

    blocked = [s for s in segments if s.status == "BLOCKED"]
    caution = [s for s in segments if s.status == "CAUTION"]
    if blocked:
        verdict, reason = "NO_GO", f"{len(blocked)} segment(s) blocked: {', '.join(sorted({s.hazard_class for s in blocked}))}"
    elif caution:
        verdict, reason = "CAUTION", f"{len(caution)} segment(s) need caution: {', '.join(sorted({s.hazard_class for s in caution}))}"
    else:
        verdict, reason = "GO", "All segments clear"

    corridor = _corridor_polygon([(lon, lat) for lat, lon in points], CORRIDOR_BUFFER_NM)

    return VoyagePlan(
        voyage_id=str(uuid.uuid4()), origin=origin, destination=destination, vessel_class=vessel_class,
        departure_time=departure.isoformat().replace("+00:00", "Z"), segments=tuple(segments),
        verdict=verdict, verdict_reason=reason, corridor_geojson=corridor,
        confidence=compute_confidence(confidences),
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
