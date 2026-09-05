"""resolve_place_from_text (backend/orca/api/main.py's /query location
resolution): which coordinates a free-text query is *about*.

The `source` field carries as much weight as the coordinates. A position that
fell back to the regional default must be distinguishable from one that was
actually resolved, because the whole response is computed at it — the Sri
Lankan EEZ is 13.6 nm from Palk Bay and 45 nm from the default position, which
is the difference between a boundary warning and a clean GO.
"""
from orca.data.loaders import DEFAULT_LAT, DEFAULT_LON, resolve_place_from_text


def test_port_named_in_a_sentence_resolves():
    p = resolve_place_from_text("is it safe to go to sea near Pamban tomorrow")
    assert p is not None and p.name == "pamban"
    # The surveyed Pamban Pass position, not the Open-Meteo grid snap at
    # (9.2443, 79.2281) that falls inside the Gulf of Mannar MPA polygon.
    assert (round(p.lat, 4), round(p.lon, 4)) == (9.2833, 79.2)


def test_alias_resolves_to_its_canonical_port():
    p = resolve_place_from_text("wave height at Cochin harbour")
    assert p is not None and p.name == "kochi" and p.source == "port_fixture"


def test_match_is_case_insensitive():
    p = resolve_place_from_text("CHENNAI weather today")
    assert p is not None and p.name == "chennai"


def test_a_query_naming_no_place_resolves_to_nothing():
    """None, not a silent substitution — the caller labels the fallback."""
    assert resolve_place_from_text("is it safe to go to sea tomorrow morning") is None


def test_places_beyond_the_cached_ports_resolve():
    """The pilot region is more than six ports with weather fixtures. Before
    the gazetteer these all fell through to the Thoothukudi default while the
    narrative went on naming the place the user typed."""
    for text, name in [
        ("fishing in Palk Bay", "palk bay"),
        ("conditions off Rameswaram", "rameswaram"),
        ("coral survey in the Gulf of Mannar", "gulf of mannar"),
        ("near Mandapam", "mandapam"),
    ]:
        p = resolve_place_from_text(text)
        assert p is not None and p.name == name, text


def test_the_default_position_is_at_sea():
    """A locationless query is answered here, so it has to be a point a vessel
    can occupy. The previous default (8.80, 78.14) was the town centre, which
    GEBCO reports as land — every depth reading there was null."""
    from orca.agents.geospatial import depth_at_point

    depth = depth_at_point(DEFAULT_LAT, DEFAULT_LON)
    assert depth.on_land is False, depth
    assert depth.depth_m and depth.depth_m > 10.0, depth
