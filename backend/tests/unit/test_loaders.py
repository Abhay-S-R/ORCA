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
    assert p is not None and p.name == "kochi" and p.source in ("port_fixture", "gazetteer")


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


# Hand-checked offshore bounding boxes, (lat_min, lat_max, lon_min, lon_max),
# deliberately non-overlapping so "resolved inside its own state" is a real
# assertion and not one box quietly containing another state's answer.
_STATE_BOXES = {
    "Gujarat": (20.0, 24.0, 68.0, 73.0),
    "Kerala": (8.0, 13.0, 74.0, 77.5),
    "Andhra Pradesh": (13.5, 19.5, 79.5, 83.4),
    "Odisha": (18.5, 22.0, 83.5, 87.0),
    "West Bengal": (21.0, 22.5, 87.1, 89.0),
}

# Phase 1 exit gate, P1.1 (`R-INDIA-1`): ten coastal places across five states.
_TEN_PLACES = [
    ("is it safe near Veraval", "veraval", "Gujarat"),
    ("conditions at Porbandar", "porbandar", "Gujarat"),
    ("waves off Kozhikode", "kozhikode", "Kerala"),
    ("tide at Kollam", "kollam", "Kerala"),
    ("fishing near Kakinada", "kakinada", "Andhra Pradesh"),
    ("sea state at Machilipatnam", "machilipatnam", "Andhra Pradesh"),
    ("tide at Paradip", "paradip", "Odisha"),
    ("conditions off Gopalpur", "gopalpur", "Odisha"),
    ("is it safe at Digha", "digha", "West Bengal"),
    ("waves near Haldia", "haldia", "West Bengal"),
]


def test_ten_coastal_places_across_five_states_each_resolve_within_their_own_state():
    """P1.1 / the Phase 1 exit gate itself. The failure this guards is the
    highest-harm one in the product: a Gujarat question answered with Tamil
    Nadu numbers because the name resolved to nothing and fell through to
    DEFAULT_LAT/LON."""
    assert len({state for _, _, state in _TEN_PLACES}) == 5
    for text, name, state in _TEN_PLACES:
        p = resolve_place_from_text(text)
        assert p is not None, f"{text!r} resolved to nothing — it would be answered at the regional default"
        assert p.name == name, (text, p.name)
        lat0, lat1, lon0, lon1 = _STATE_BOXES[state]
        assert lat0 <= p.lat <= lat1 and lon0 <= p.lon <= lon1, (text, state, p)
        # And emphatically not the Gulf of Mannar default every one of these
        # used to land on.
        assert abs(p.lat - DEFAULT_LAT) + abs(p.lon - DEFAULT_LON) > 1.0, (text, p)


def test_cmems_picks_the_current_file_even_if_a_stale_one_was_written_last():
    """`docs/data/ORCA_Stale_Data_Cleanup.md` §6.2. `_cmems_newest` used to sort by
    mtime, which records when the bytes landed on this machine rather than the
    date the data describes. Restoring a backup, or re-copying `data/`,
    reorders the directory and would hand the SST fallback rung an August
    extract while the freshness badge above it — which grades the same files
    by their filename dates — still read green.

    The two must not be able to disagree, so both now read the date out of the
    name. The undated rolling NRT file is the current one by construction.
    """
    import os
    import time

    from orca.data.satellite_loaders import CMEMS_DIR, _cmems_newest

    current = _cmems_newest("thetao")
    if current is None:
        import pytest

        pytest.skip("no CMEMS thetao files on disk")
    assert current.name == "cmems_thetao_india_nrt.nc", current.name

    stale = [
        p
        for p in CMEMS_DIR.glob("cmems_*.nc")
        if "thetao" in p.name and p.name != current.name
    ]
    if not stale:
        return
    victim = stale[0]
    saved = (os.path.getatime(victim), os.path.getmtime(victim))
    try:
        os.utime(victim, (time.time(), time.time()))
        assert _cmems_newest("thetao").name == current.name, (
            "mtime still decides — a restored backup would serve superseded data as current"
        )
    finally:
        os.utime(victim, saved)
