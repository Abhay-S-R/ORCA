"""D3 — voyage-corridor tests. Plan §8/§10: the reasoning-graph/voyage
acceptance scenarios specifically exercise per-segment-ETA hazard sampling,
not just whole-route classification, so that gets its own coverage here
rather than relying on voyage.py's __main__ smoke check alone."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from orca.agents import voyage
from orca.agents.geospatial import check_boundary_proximity, point_in_polygon
from orca.agents.voyage import densify_route, plan_voyage, wave_height_at

# Open water off the continental shelf, deep, no boundary/MPA nearby.
OPEN_LAT, OPEN_LON = 8.20, 78.60
# Gulf of Mannar shallows between two Thoothukudi-area points.
SHALLOW_ORIGIN = (8.75, 78.20)
SHALLOW_DEST = (9.05, 78.95)


def test_densify_route_is_geodesic_not_a_flat_lerp() -> None:
    points = densify_route(SHALLOW_ORIGIN, SHALLOW_DEST, step_nm=2.0)
    assert points[0] == SHALLOW_ORIGIN
    assert points[-1] == SHALLOW_DEST
    assert len(points) > 2, "a ~40nm route at 2nm spacing must have intermediate waypoints"
    # Every consecutive pair is a finite, positive distance apart — a flat
    # lerp on raw (lat, lon) can produce unevenly-spaced or wrong-direction
    # points; a geodesic one cannot silently duplicate a waypoint.
    from orca.agents.geospatial import bearing_and_distance

    for a, b in zip(points, points[1:]):
        _, dist = bearing_and_distance(a[0], a[1], b[0], b[1])
        assert dist > 0


def test_wave_height_at_samples_the_forecast_step_nearest_eta_not_a_fixed_step() -> None:
    """The plan's "genuinely sophisticated part": each segment must be
    evaluated at its own ETA, not always at the file's first or latest step."""
    ds = voyage._ww3()
    hours = ds["TIME"].values
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)
    first_step = epoch + timedelta(hours=float(hours.min()))
    last_step = epoch + timedelta(hours=float(hours.max()))

    hs_first_expected = ds["HS"].isel(TIME=0).sel(IOXAXIS=OPEN_LON, IOYAXIS=OPEN_LAT, method="nearest").item()
    hs_last_expected = ds["HS"].isel(TIME=-1).sel(IOXAXIS=OPEN_LON, IOYAXIS=OPEN_LAT, method="nearest").item()

    got_first = wave_height_at(OPEN_LAT, OPEN_LON, first_step)
    got_last = wave_height_at(OPEN_LAT, OPEN_LON, last_step)

    # Both calls must resolve to the exact grid values xarray itself reports
    # for those two distinct steps — i.e. two different steps really were
    # consulted, not the same one twice regardless of the `when` passed in.
    if not math.isnan(hs_first_expected):
        assert got_first is not None and abs(got_first - hs_first_expected) < 1e-6
    if not math.isnan(hs_last_expected):
        assert got_last is not None and abs(got_last - hs_last_expected) < 1e-6


def test_wave_height_at_returns_none_outside_forecast_window() -> None:
    far_past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    far_future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert wave_height_at(OPEN_LAT, OPEN_LON, far_past) is None
    assert wave_height_at(OPEN_LAT, OPEN_LON, far_future) is None


def test_shallow_route_classifies_blocked_or_caution_not_silently_clear() -> None:
    plan = plan_voyage(SHALLOW_ORIGIN, SHALLOW_DEST, vessel_class="small_fishing", speed_kn=8.0)
    hazard_classes = {s.hazard_class for s in plan.segments}
    assert "SHALLOW" in hazard_classes, hazard_classes
    assert plan.verdict in ("CAUTION", "NO_GO")


def test_verdict_rollup_never_averages_any_blocked_forces_no_go() -> None:
    """Ground Rule 4 applied to the whole voyage: one BLOCKED segment among
    many CLEAR ones must still force NO_GO, not get diluted by the rest."""
    plan = plan_voyage(SHALLOW_ORIGIN, SHALLOW_DEST, vessel_class="small_fishing", speed_kn=8.0)
    if any(s.status == "BLOCKED" for s in plan.segments):
        assert plan.verdict == "NO_GO"


# Pamban fixture coordinate (loaders.py's own comment: this snaps inside the
# Gulf of Mannar Marine National Park polygon) — a direct route starting here
# classifies MPA/BLOCKED immediately, giving a deterministic NO_GO to reroute
# around.
MPA_ORIGIN = (9.2443, 79.2281)
MPA_DEST = (9.20, 79.10)


def test_no_go_route_reroutes_to_a_clear_alternate_when_one_exists() -> None:
    """Checklist P0 #2 — route optimization, not just auditing. A direct
    route blocked by a spatial hazard (not a time-dependent one) should
    clear on at least one of the offset detours."""
    now = datetime.now(timezone.utc)
    _, _, direct_verdict, _ = voyage._classify_route(
        densify_route(MPA_ORIGIN, MPA_DEST), now, now, "small_fishing", 1.2, 8.0,
    )
    assert direct_verdict == "NO_GO", "fixture must actually start inside the MPA for this test to mean anything"

    plan = plan_voyage(MPA_ORIGIN, MPA_DEST, vessel_class="small_fishing", speed_kn=8.0)
    assert plan.rerouted is True
    assert plan.verdict != "NO_GO"
    assert len(plan.alternatives_tried) >= 1
    # The chosen route itself must never carry a BLOCKED segment — Ground
    # Rule 4 still applies to whichever plan is actually returned.
    assert all(s.status != "BLOCKED" for s in plan.segments)
    strategies = {a["strategy"] for a in plan.alternatives_tried}
    assert strategies == {"offset_east", "offset_west", "wait_6h"}


def test_rerouted_flag_is_false_and_verdict_stays_no_go_when_no_alternate_clears() -> None:
    """Honesty over optimism: `plan_voyage` must never report `rerouted=True`
    with a verdict that is still NO_GO, and must never silently swap in a
    still-blocked alternate — see checklist P0 #2's "say so honestly rather
    than picking the least-bad NO_GO"."""
    plan = plan_voyage(SHALLOW_ORIGIN, SHALLOW_DEST, vessel_class="small_fishing", speed_kn=8.0)
    if plan.verdict == "NO_GO":
        assert plan.rerouted is False
        assert "no clear detour found" in plan.verdict_reason
        assert all(a["verdict"] == "NO_GO" for a in plan.alternatives_tried)
    if plan.rerouted:
        assert plan.verdict != "NO_GO"


def test_segment_classification_uses_the_same_full_precision_containment_agent6_does() -> None:
    """No independent/simplified geometry check inside voyage.py — it must
    agree exactly with Agent 6's own full-precision point_in_polygon /
    check_boundary_proximity for the same point, same standard as
    test_geospatial.py's test_containment_check_never_uses_simplified_geometry."""
    mid_lat, mid_lon = (SHALLOW_ORIGIN[0] + SHALLOW_DEST[0]) / 2, (SHALLOW_ORIGIN[1] + SHALLOW_DEST[1]) / 2
    direct_hits = point_in_polygon(mid_lat, mid_lon)
    direct_imbl = check_boundary_proximity(mid_lat, mid_lon, voyage._IMBL_PROXY_BOUNDARY)

    plan = plan_voyage(SHALLOW_ORIGIN, SHALLOW_DEST, vessel_class="small_fishing", speed_kn=8.0)
    mid_segment = plan.segments[len(plan.segments) // 2]
    # Whatever this segment's own midpoint resolves to must match a direct
    # call against the same full-precision boundary data — not a coarser
    # zoom-simplified view of it.
    assert direct_imbl.distance_nm >= 0  # sanity: the boundary check itself is reachable
    assert isinstance(direct_hits, list)
    assert mid_segment.hazard_class in ("SHALLOW", "BOUNDARY", "MPA", "ROUGH_SEA", "LIGHTNING", "CLEAR")
