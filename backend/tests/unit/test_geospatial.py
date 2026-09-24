from orca.agents.geospatial import (
    PILOT_BBOX_WSEN,
    _simplify_tolerance_for_zoom,
    bearing_and_distance,
    check_boundary_proximity,
    current_vectors,
    depth_at_point,
    generate_map_layers,
    load_boundaries,
    load_boundary_lines,
    nearest_boundary_line,
    point_in_polygon,
    spatial_query_zones,
)
from orca.data.loaders import DEFAULT_LAT, DEFAULT_LON

# Gulf of Mannar, offshore Thoothukudi — confirmed inside the India EEZ and shallow.
INSIDE_LAT, INSIDE_LON = 8.70, 78.50


def test_nearest_boundary_line_never_answers_with_indias_own_baseline() -> None:
    """Regression, found 2026-09-25: `nearest_boundary_line` used to consider
    all 32 lines, including 6 "Straight baseline" and 2 "200 NM" features
    that are India's own coastline/limit markers (`territory2: null` in the
    source data), not a line to another state. At the pilot default position
    that read 0.7 nm to "India Straight Baseline" — an imminent-breach NO_GO
    on an ordinary question with no boundary anywhere near it. Every line
    `load_boundary_lines()` holds is still drawn on the map (context); only
    the verdict-relevant nearest line must exclude India's own markers."""
    excluded_types = {p.get("line_type") for _, p in load_boundary_lines() if not p.get("territory2")}
    assert excluded_types == {"Straight baseline", "200 NM"}

    line = nearest_boundary_line(DEFAULT_LAT, DEFAULT_LON)
    assert line is not None
    assert None not in line["between"], line
    assert line["line_type"] not in ("Straight baseline", "200 NM"), line
    assert line["distance_nm"] > 10 and line["alert_level"] == "CLEAR", line

    kochi = nearest_boundary_line(9.9667, 76.2667)
    assert kochi is not None and kochi["line_type"] not in ("Straight baseline", "200 NM"), kochi


def test_gulf_of_mannar_excluded_from_geofence_usable() -> None:
    # Defect C-1: Gulf of Mannar is a MultiPoint (centroid-only) record and
    # must never be treated as a containment-capable boundary.
    names = {f.name: f.geofence_usable for f in load_boundaries()}
    assert names["Gulf of Mannar"] is False


def test_point_in_polygon_never_returns_a_non_usable_feature() -> None:
    hits = point_in_polygon(INSIDE_LAT, INSIDE_LON)
    assert any(f.name == "Indian Exclusive Economic Zone" for f in hits)
    assert all(f.geofence_usable for f in hits)


def test_boundary_proximity_reports_inside() -> None:
    result = check_boundary_proximity(INSIDE_LAT, INSIDE_LON, "Indian Exclusive Economic Zone")
    assert result.alert_level == "INSIDE"
    assert result.distance_nm >= 0


def test_boundary_proximity_rejects_non_usable_boundary_name() -> None:
    try:
        check_boundary_proximity(INSIDE_LAT, INSIDE_LON, "Gulf of Mannar")
        raise AssertionError("expected ValueError for a non-geofence-usable boundary")
    except ValueError:
        pass


def test_bearing_and_distance_is_geodesic_not_zero_for_distinct_points() -> None:
    bearing, distance_nm = bearing_and_distance(INSIDE_LAT, INSIDE_LON, 8.80, 78.14)
    assert 0 <= bearing < 360
    assert distance_nm > 0


def test_depth_at_point_marks_shallow_hazard_below_threshold() -> None:
    deep = depth_at_point(INSIDE_LAT, INSIDE_LON)
    assert deep.on_land is False
    assert deep.depth_m is not None and deep.depth_m > 0
    # A point well inland should read as on_land.
    land = depth_at_point(9.93, 78.12)  # Madurai, ~100km inland
    assert land.on_land is True
    assert land.depth_m is None


def test_generate_map_layers_only_includes_geofence_usable_boundaries() -> None:
    layers = generate_map_layers(user_lat=INSIDE_LAT, user_lon=INSIDE_LON)
    names = {f["properties"]["name"] for f in layers["boundaries"]["features"]}
    assert "Gulf of Mannar" not in names
    assert layers["user_position"]["features"][0]["geometry"]["coordinates"] == [INSIDE_LON, INSIDE_LAT]


def test_spatial_query_zones_finds_containing_boundary() -> None:
    zones = spatial_query_zones(INSIDE_LAT, INSIDE_LON, radius_nm=50)
    assert any(f.name == "Indian Exclusive Economic Zone" for f in zones)


# ---------------------------------------------------------------------------
# Plan §5.10 Day 10: per-zoom Douglas-Peucker simplification, and the
# load-bearing carve-out that a simplified boundary must never reach a
# containment check.
# ---------------------------------------------------------------------------

def test_simplify_tolerance_is_coarser_at_low_zoom_than_high_zoom() -> None:
    assert _simplify_tolerance_for_zoom(5) > _simplify_tolerance_for_zoom(9) > _simplify_tolerance_for_zoom(11)
    assert _simplify_tolerance_for_zoom(11) == 0.0, "z>=11 must be full precision, not simplified"


def test_generate_map_layers_simplifies_more_at_low_zoom() -> None:
    coarse = generate_map_layers(user_lat=INSIDE_LAT, user_lon=INSIDE_LON, zoom=5)
    fine = generate_map_layers(user_lat=INSIDE_LAT, user_lon=INSIDE_LON, zoom=11)

    def _total_points(layers: dict) -> int:
        total = 0
        for feat in layers["boundaries"]["features"]:
            geom = feat["geometry"]
            coords = geom["coordinates"]
            # Polygon or MultiPolygon rings, either way just count leaf coordinate pairs.
            stack = [coords]
            while stack:
                item = stack.pop()
                if item and isinstance(item[0], (int, float)):
                    total += 1
                elif isinstance(item, list):
                    stack.extend(item)
        return total

    assert _total_points(coarse) < _total_points(fine), (
        "z=5 boundaries must have fewer coordinate points than z=11 (never ship "
        "full-precision geometry to a whole-basin view)"
    )


def test_containment_check_never_uses_simplified_geometry() -> None:
    """The load-bearing carve-out (plan §5.10): point_in_polygon/
    check_boundary_proximity have no `zoom` parameter at all — they can only
    ever measure against load_boundaries()'s full-precision geometry, so a
    simplified IMBL rendered on-screen can never be what a containment
    verdict was actually computed against."""
    import inspect

    assert "zoom" not in inspect.signature(check_boundary_proximity).parameters
    assert "zoom" not in inspect.signature(point_in_polygon).parameters

    eez_name = "Indian Exclusive Economic Zone"
    # Regardless of what zoom the map layer response was built at, the
    # containment measurement itself is identical — it never consulted the
    # simplified feature at all.
    result_a = check_boundary_proximity(INSIDE_LAT, INSIDE_LON, eez_name)
    generate_map_layers(user_lat=INSIDE_LAT, user_lon=INSIDE_LON, zoom=5)
    result_b = check_boundary_proximity(INSIDE_LAT, INSIDE_LON, eez_name)
    assert result_a.distance_nm == result_b.distance_nm


# ---------------------------------------------------------------------------
# FLAG-2 acceptance test: IMBL distance verification (plan §8 exit criterion 6)
#
# The India EEZ polygon's eastern edge in the Palk Bay / Gulf of Mannar
# corridor approximates the IMBL. This is a known approximation — the pilot
# data has no separate IMBL line dataset (see geospatial.py docstring).
#
# Verified 2026-09-02:
#   (8.70, 78.50) — offshore Gulf of Mannar, ~16 nm inside the EEZ.
#   (8.80, 78.14) — Thoothukudi coast, ~1 nm from EEZ edge (GEBCO reads land).
#   (9.20, 79.10) — Palk Bay, ~0.5 nm inside EEZ, near the IMBL.
#
# These values are regression baselines. If the EEZ polygon source changes,
# update the expected ranges accordingly.
# ---------------------------------------------------------------------------

def test_imbl_distance_acceptance_offshore_gulf_of_mannar() -> None:
    """Plan §8 exit criterion 6: IMBL distance at the pilot query coordinate."""
    result = check_boundary_proximity(INSIDE_LAT, INSIDE_LON, "Indian Exclusive Economic Zone")
    # 8.70°N, 78.50°E is deep inside the EEZ — expect 10-25 nm range.
    assert result.alert_level == "INSIDE"
    assert 10.0 <= result.distance_nm <= 25.0, (
        f"IMBL distance {result.distance_nm} nm outside expected 10–25 nm range at "
        f"({INSIDE_LAT}, {INSIDE_LON}) — verify against the EEZ polygon source."
    )


def test_imbl_distance_acceptance_thoothukudi_coast() -> None:
    """Thoothukudi city (8.80°N, 78.14°E) sits on the coast, very close to
    the EEZ polygon edge. GEBCO reads this as land. The EEZ distance should
    be small (< 5 nm) and in CAUTION or DANGER range."""
    result = check_boundary_proximity(8.80, 78.14, "Indian Exclusive Economic Zone")
    assert result.distance_nm < 5.0, (
        f"Thoothukudi coast should be < 5 nm from EEZ edge, got {result.distance_nm}"
    )
    assert result.alert_level in ("CAUTION", "DANGER"), result.alert_level


# ---------------------------------------------------------------------------
# D3 particle layer: real HYCOM surface current vectors
# ---------------------------------------------------------------------------

def test_current_vectors_stay_within_pilot_bbox_and_have_finite_speed() -> None:
    west, south, east, north = PILOT_BBOX_WSEN
    points = current_vectors()
    assert points, "expected at least one surface current point in the pilot bbox"
    for p in points:
        assert west <= p["lon"] <= east
        assert south <= p["lat"] <= north
        assert p["speed_ms"] >= 0
        assert 0.0 <= p["direction_deg"] < 360.0


def test_imbl_distance_acceptance_palk_bay() -> None:
    """Palk Bay (9.20°N, 79.10°E) — very close to the IMBL. Should be
    inside the EEZ but with a small distance to the edge."""
    result = check_boundary_proximity(9.20, 79.10, "Indian Exclusive Economic Zone")
    assert result.alert_level == "INSIDE"
    assert result.distance_nm < 5.0, (
        f"Palk Bay should be < 5 nm from IMBL (EEZ edge), got {result.distance_nm}"
    )


def test_depth_at_point_outside_pilot_bounds_does_not_falsely_report_land() -> None:
    """Points outside the 77.5-80.5 E, 7.5-10.5 N GEBCO extract (e.g. off Kerala coast)
    must cascade to Pan-India ETOPO and report real seafloor depth rather than false land."""
    res = depth_at_point(8.25, 76.86)
    assert not res.on_land
    assert res.depth_m is not None and 40.0 <= res.depth_m <= 70.0
    assert not res.shallow_hazard



# --- seasonal fishing ban (runbook C4) ------------------------------------

def test_fishing_ban_is_per_coast_not_national() -> None:
    """The two coasts' windows are six weeks apart; a single national window
    would tell a Gujarat crew the sea was closed while it was open."""
    from datetime import date

    from orca.agents.geospatial import fishing_ban_status

    may_east = fishing_ban_status(8.70, 78.50, date(2026, 5, 1))
    if not may_east.get("available"):
        return  # roster/order are gitignored data — absence is legitimate
    may_west = fishing_ban_status(20.90, 70.30, date(2026, 5, 1))
    assert may_east["in_ban_period"] is True
    assert may_west["in_ban_period"] is False
    assert may_east["coast"] == "east" and may_west["coast"] == "west"


def test_fishing_ban_never_asserts_the_central_order_inside_territorial_waters() -> None:
    from datetime import date

    from orca.agents.geospatial import fishing_ban_status

    inshore = fishing_ban_status(20.90, 70.30, date(2026, 7, 1))  # ~2 NM off Veraval
    if not inshore.get("available"):
        return
    assert inshore["in_ban_period"] is True
    assert inshore["applies_here"] is False, "central EEZ order does not reach inside 12 NM"
    assert "state" in inshore["note"].lower()
    # Every answer carries the order it came from — a date with no file number
    # behind it is the kind of claim the deterministic core exists to prevent.
    assert inshore["order"]["file_number"]


def test_depth_at_point_reads_land_on_a_small_island_far_from_the_pilot_box() -> None:
    """Maakurandhoo (Maldives, ~5.70 N 73.31 E) is a ~1 km island — smaller than
    one cell of the 60" ETOPO fallback, which reports ~22 m of open water there.
    Only the 15" national GEBCO grid sees it as land, so this fails if the grid
    choice ever gets pinned at import time again and a running server is left on
    the pilot box after the national download lands.
    """
    from orca.agents.geospatial import GEBCO_ALL_FILE

    if not GEBCO_ALL_FILE.exists():
        return  # national subset is a gitignored 100 MB download — absence is legitimate
    assert depth_at_point(5.7024, 73.3105).on_land is True


def test_currents_are_the_step_nearest_now_and_say_which_one() -> None:
    """P4.15: the currents layer carries the valid time of the HYCOM step it
    shows, and that step is the one nearest the requested time — not the
    last step in the file, which can be days ahead."""
    from datetime import datetime, timedelta, timezone

    from orca.agents.geospatial import _hycom, _hycom_times, hycom_nearest_step

    times = _hycom_times(_hycom())
    assert all(b - a == timedelta(hours=3) for a, b in zip(times, times[1:]))
    target = times[5] + timedelta(minutes=80)  # closer to step 5 than step 6
    i, iso = hycom_nearest_step(target)
    assert i == 5 and iso == times[5].isoformat().replace("+00:00", "Z")
    assert hycom_nearest_step(times[-1] + timedelta(days=30))[0] == len(times) - 1
    assert hycom_nearest_step(datetime(2000, 1, 1, tzinfo=timezone.utc))[0] == 0
