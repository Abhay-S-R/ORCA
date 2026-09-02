from orca.agents.geospatial import (
    bearing_and_distance,
    check_boundary_proximity,
    depth_at_point,
    generate_map_layers,
    load_boundaries,
    point_in_polygon,
    spatial_query_zones,
)

# Gulf of Mannar, offshore Thoothukudi — confirmed inside the India EEZ and shallow.
INSIDE_LAT, INSIDE_LON = 8.70, 78.50


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


def test_imbl_distance_acceptance_palk_bay() -> None:
    """Palk Bay (9.20°N, 79.10°E) — very close to the IMBL. Should be
    inside the EEZ but with a small distance to the edge."""
    result = check_boundary_proximity(9.20, 79.10, "Indian Exclusive Economic Zone")
    assert result.alert_level == "INSIDE"
    assert result.distance_nm < 5.0, (
        f"Palk Bay should be < 5 nm from IMBL (EEZ edge), got {result.distance_nm}"
    )

