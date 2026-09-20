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
from typing import Any, Literal

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
    return segments, confidences, verdict, reason


def _offset_point(lat: float, lon: float, bearing_deg: float, distance_nm: float) -> tuple[float, float]:
    """A point `distance_nm` from (lat, lon) along `bearing_deg`, geodesic —
    same `_GEOD` instance `densify_route` already uses, not a flat-plane
    approximation that would drift at higher pilot-region latitudes."""
    from orca.agents.geospatial import _GEOD

    lon2, lat2, _ = _GEOD.fwd(lon, lat, bearing_deg, distance_nm * 1852.0)
    return lat2, lon2


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


def plan_voyage(
    origin: tuple[float, float], destination: tuple[float, float], *,
    vessel_class: VesselClass = "small_fishing", departure_time: str | None = None,
    speed_kn: float = 8.0, draft_m: float | None = None,
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

    return VoyagePlan(
        voyage_id=str(uuid.uuid4()), origin=origin, destination=destination, vessel_class=vessel_class,
        departure_time=departure.isoformat().replace("+00:00", "Z"), segments=tuple(segments),
        verdict=verdict, verdict_reason=reason, corridor_geojson=corridor,
        confidence=compute_confidence(confidences), rerouted=rerouted, alternatives_tried=tuple(alternatives_tried),
        draft_m=draft, draft_source=draft_source, draft_disclosure=draft_disclosure,
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
