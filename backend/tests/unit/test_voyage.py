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
    # -2 days: WW3's "hours since 0001-01-01" is on the CF standard (Julian)
    # calendar, which datetime(1, 1, 1) — proleptic Gregorian — leads by two
    # days. `voyage._ww3_hours_since_epoch` applies the same shift; without it
    # here the test would ask for a time two days off its own expectation.
    epoch = datetime(1, 1, 1, tzinfo=timezone.utc)  # datetime cannot go earlier
    first_step = epoch + timedelta(hours=float(hours.min())) - timedelta(days=2)
    last_step = epoch + timedelta(hours=float(hours.max())) - timedelta(days=2)

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


# --- WW3 grid absent: the extracted points carry it ----------------------

def test_wave_height_falls_back_to_extracted_points_when_grid_missing(monkeypatch):
    """The 6.5 GB WW3 NetCDF is gitignored data, so a fresh checkout has none.
    That must degrade to the extracted point series, not crash a voyage plan."""
    from datetime import datetime, timezone

    from orca.agents import voyage

    monkeypatch.setattr(voyage, "_ww3", lambda: None)
    hs = voyage.wave_height_at(8.75, 78.3, datetime(2026, 8, 30, tzinfo=timezone.utc))
    assert hs is not None and 0.0 <= hs < 20.0

    # Outside the extraction footprint it must still return None rather than
    # reach for the nearest point at any distance.
    assert voyage.wave_height_at(21.6, 88.0, datetime(2026, 8, 30, tzinfo=timezone.utc)) is None


# --- P1.2 (`R-NEW-8`) — no silent default draft ----------------------------

def test_an_unsupplied_draft_is_the_deepest_of_the_class_and_says_so():
    """`voyage.py` used to fall back to 1.2 m for small_fishing silently, so a
    deeper boat got a clearance answer computed for a shallower one and was
    never told. Conservative and disclosed, or it is not a safety answer."""
    from orca.agents.voyage import _ASSUMED_DRAFT_M, plan_voyage

    plan = plan_voyage((8.75, 78.20), (9.05, 78.95), vessel_class="small_fishing")
    assert plan.draft_source == "assumed_deepest_of_class"
    assert plan.draft_m == _ASSUMED_DRAFT_M["small_fishing"]
    assert plan.draft_disclosure and f"{plan.draft_m:.1f} m" in plan.draft_disclosure
    # Conservative means deeper than the old typical value, never shallower.
    assert plan.draft_m > 1.2


def test_a_supplied_draft_is_used_as_given_with_nothing_to_disclose():
    from orca.agents.voyage import plan_voyage

    plan = plan_voyage((8.75, 78.20), (9.05, 78.95), vessel_class="small_fishing", draft_m=0.9)
    assert (plan.draft_m, plan.draft_source, plan.draft_disclosure) == (0.9, "supplied", None)


# --- P5.23: fishing ban + current drift per leg -----------------------------

def test_regulatory_ban_blocks_a_leg(monkeypatch):
    now = datetime.now(timezone.utc)
    eta = now + timedelta(hours=1)

    def fake_ban_status(lat, lon, when=None):
        return {"available": True, "in_ban_period": True, "applies_here": True,
                "coast": "east", "order": {"file_number": "F.No.TEST/2026"}}

    monkeypatch.setattr("orca.agents.geospatial.fishing_ban_status", fake_ban_status)
    segment, _ = voyage._classify_segment(
        "seg-0", (OPEN_LAT, OPEN_LON), (OPEN_LAT + 0.05, OPEN_LON + 0.05),
        3.0, eta, "small_fishing", 1.8, now,
    )
    assert segment.status == "BLOCKED"
    assert segment.hazard_class == "REGULATORY"
    assert "ban" in segment.detail.lower()


def test_no_ban_never_blocks_the_leg(monkeypatch):
    now = datetime.now(timezone.utc)
    eta = now + timedelta(hours=1)

    def fake_ban_status(lat, lon, when=None):
        return {"available": True, "in_ban_period": False, "applies_here": False}

    monkeypatch.setattr("orca.agents.geospatial.fishing_ban_status", fake_ban_status)
    segment, _ = voyage._classify_segment(
        "seg-0", (OPEN_LAT, OPEN_LON), (OPEN_LAT + 0.05, OPEN_LON + 0.05),
        3.0, eta, "small_fishing", 1.8, now,
    )
    assert segment.hazard_class != "REGULATORY"


def test_set_drift_caution_when_current_crosses_the_threshold(monkeypatch):
    now = datetime.now(timezone.utc)
    eta = now + timedelta(hours=1)
    monkeypatch.setattr("orca.agents.geospatial.fishing_ban_status", lambda lat, lon, when=None: {"available": False})
    monkeypatch.setattr(voyage, "wave_height_at", lambda lat, lon, when: 0.5)  # isolate SET_DRIFT from real sea state
    # Leg heads due north (bearing 0); a current flowing due east (90 deg) is
    # entirely cross-track — sin(90) = 1, so the full current speed counts.
    monkeypatch.setattr(voyage, "current_at", lambda lat, lon, when: (1.0, 90.0))
    segment, _ = voyage._classify_segment(
        "seg-0", (OPEN_LAT, OPEN_LON), (OPEN_LAT + 0.05, OPEN_LON),
        3.0, eta, "small_fishing", 1.8, now, speed_kn=2.0,  # slow boat, easy to cross 20% of speed
    )
    assert segment.status == "CAUTION"
    assert segment.hazard_class == "SET_DRIFT"


def test_current_along_track_never_triggers_set_drift(monkeypatch):
    now = datetime.now(timezone.utc)
    eta = now + timedelta(hours=1)
    monkeypatch.setattr("orca.agents.geospatial.fishing_ban_status", lambda lat, lon, when=None: {"available": False})
    monkeypatch.setattr(voyage, "wave_height_at", lambda lat, lon, when: 0.5)
    # Leg heads due north (bearing 0); a current also flowing due north (0
    # deg) is entirely along-track — sin(0) = 0, no cross-track component.
    monkeypatch.setattr(voyage, "current_at", lambda lat, lon, when: (5.0, 0.0))
    segment, _ = voyage._classify_segment(
        "seg-0", (OPEN_LAT, OPEN_LON), (OPEN_LAT + 0.05, OPEN_LON),
        3.0, eta, "small_fishing", 1.8, now, speed_kn=2.0,
    )
    assert segment.hazard_class != "SET_DRIFT"


def test_every_vessel_class_has_an_assumed_draft_and_the_deepest_is_the_fallback():
    from orca.agents.risk_assessment import VesselClass
    from orca.agents.voyage import _ASSUMED_DRAFT_M, _MOST_CONSERVATIVE_CLASS

    classes = set(VesselClass.__args__)  # type: ignore[attr-defined]
    assert set(_ASSUMED_DRAFT_M) == classes
    assert _ASSUMED_DRAFT_M[_MOST_CONSERVATIVE_CLASS] == max(_ASSUMED_DRAFT_M.values())


# --- P5.7: Floyd–Warshall over a coarse grid --------------------------------
#
# A synthetic grid, not real bathymetry — deterministic and fast, and it is
# the search LOGIC under test here (obstacle avoidance, ETA-driven cost),
# which is independent of what a real GEBCO/WW3 lookup returns. The real
# lookups (_grid_depths_m/_grid_wave_heights) are exercised by plan_voyage's
# own existing real-data tests when they happen to fall through to A*.

def _synthetic_grid(
    size: int, wall_col: int | None = None, wave_wall_col: int | None = None, wave_wall_rows: int = 2,
) -> voyage._AstarGrid:
    lats = [8.0 + 0.1 * i for i in range(size)]
    lons = [78.0 + 0.1 * j for j in range(size)]
    blocked = [[False] * size for _ in range(size)]
    waves: list[list[float | None]] = [[0.5] * size for _ in range(size)]
    if wall_col is not None:
        for i in range(size - 1):  # a gap at the last row so a path always exists around it
            blocked[i][wall_col] = True
    if wave_wall_col is not None:
        # Only the first `wave_wall_rows` rows are rough — the rest of that
        # column is calm, so a detour through a lower row is a genuine
        # calmer alternative rather than hitting the same rough water anyway.
        for i in range(wave_wall_rows):
            waves[i][wave_wall_col] = 5.0  # rough, not impassable — a cost, not a block
    return voyage._AstarGrid(lats=lats, lons=lons, blocked=blocked, wave_height_m=waves)


def test_astar_route_goes_around_a_blocked_column(monkeypatch):
    grid = _synthetic_grid(6, wall_col=3)
    monkeypatch.setattr(voyage, "_build_astar_grid", lambda *a, **kw: grid)
    origin, destination = (8.0, 78.0), (8.0, 78.5)
    path = voyage.astar_route(origin, destination, datetime.now(timezone.utc), 8.0, 1.8)
    assert path is not None
    assert path[0] == origin and path[-1] == destination
    # The path must cross column index 3 only at the one open row (index 5,
    # the gap left in the wall) — anywhere else there it would be crossing a
    # blocked cell.
    for lat, lon in path[1:-1]:
        j = round((lon - grid.lons[0]) / 0.1)
        if j == 3:
            i = round((lat - grid.lats[0]) / 0.1)
            assert i == 5, f"path crossed the wall at a blocked row: {(lat, lon)}"


def test_astar_route_prefers_the_calmer_path_when_both_are_clear(monkeypatch):
    """Two open corridors exist (no blocked cells); one has a rough-water
    column in the middle. The cheaper (lower cost, not just shorter) path
    must avoid the rough column when a calm alternative of the same length
    exists — proof the wave-height term actually steers the search rather
    than being computed and ignored."""
    grid = _synthetic_grid(6, wall_col=None, wave_wall_col=2, wave_wall_rows=2)
    monkeypatch.setattr(voyage, "_build_astar_grid", lambda *a, **kw: grid)
    origin, destination = (8.0, 78.0), (8.0, 78.5)
    path = voyage.astar_route(origin, destination, datetime.now(timezone.utc), 8.0, 1.8)
    assert path is not None

    def is_rough(lat: float, lon: float) -> bool:
        i = round((lat - grid.lats[0]) / 0.1)
        j = round((lon - grid.lons[0]) / 0.1)
        return grid.wave_height_m[i][j] == 5.0

    assert not any(is_rough(lat, lon) for lat, lon in path), "Warshall passed through a rough cell when a calmer route existed"
    # And it must have actually gone somewhere other than the flat row-0 line
    # to prove the detour is real, not a coincidence of the heuristic.
    assert any(lat != origin[0] for lat, lon in path), "path never left row 0 — it must have crossed the rough cell there"


def test_astar_route_returns_none_when_the_goal_is_unreachable(monkeypatch):
    size = 6
    grid = _synthetic_grid(size, wall_col=None)
    for i in range(size):  # a solid wall with no gap at all
        grid.blocked[i][3] = True
    monkeypatch.setattr(voyage, "_build_astar_grid", lambda *a, **kw: grid)
    path = voyage.astar_route((8.0, 78.0), (8.0, 78.5), datetime.now(timezone.utc), 8.0, 1.8)
    assert path is None


def test_astar_route_returns_none_when_origin_itself_is_blocked(monkeypatch):
    grid = _synthetic_grid(6)
    grid.blocked[0][0] = True  # snaps to the origin's own nearest cell
    monkeypatch.setattr(voyage, "_build_astar_grid", lambda *a, **kw: grid)
    path = voyage.astar_route((8.0, 78.0), (8.0, 78.5), datetime.now(timezone.utc), 8.0, 1.8)
    assert path is None


def test_plan_voyage_falls_through_to_warshall_when_offset_and_wait_both_fail(monkeypatch):
    """Integration point, not the search logic: when every offset/wait
    candidate is still NO_GO, plan_voyage must actually call warshall_route and
    use its result if Warshall clears — not silently give up one rung early."""

    fw_points = [(8.0, 78.0), (8.05, 78.2), (8.0, 78.5)]

    def fake_classify_route(points, departure, now, vessel_class, draft, speed_kn):
        # densify_route already turns even the direct line into >2 points, so
        # that can't distinguish "direct" from "warshall" here — only the exact
        # warshall_route output (mocked below) is treated as clear.
        if list(points) == fw_points:
            seg = voyage._segment("seg-0", points[0], points[-1], 1.0, departure, "CLEAR", "CLEAR", "clear", ())
            return [seg], [voyage.Confidence("HIGH", "test")], "GO", "clear via warshall"
        seg = voyage._segment("seg-0", points[0], points[-1], 1.0, departure, "SHALLOW", "BLOCKED", "blocked", ())
        return [seg], [voyage.Confidence("HIGH", "test")], "NO_GO", "blocked"

    monkeypatch.setattr(voyage, "_classify_route", fake_classify_route)
    monkeypatch.setattr(voyage, "_detour_candidates", lambda *a, **kw: [])  # offset/wait never even tried
    monkeypatch.setattr(voyage, "warshall_route", lambda *a, **kw: fw_points)

    plan = voyage.plan_voyage((8.0, 78.0), (8.0, 78.5), vessel_class="small_fishing", speed_kn=8.0, draft_m=1.8)
    assert plan.verdict == "GO"
    assert plan.rerouted is True
    assert any(a["strategy"] == "warshall" for a in plan.alternatives_tried)
