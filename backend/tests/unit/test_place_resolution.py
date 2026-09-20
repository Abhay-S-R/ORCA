"""P1.2 (`R-NEW-1`) and P1.4 (`R-EDGE-3`) — the shared place-resolution guard.

`test_query_coverage.py` asserts the *shapes* across ~60 queries; this file
asserts the parts of the contract that shape alone does not reach: what the
wire form carries, that a fallback is always accompanied by the sentence
disclosing it, and the boundaries of the coordinate parser.
"""
from datetime import datetime, timedelta, timezone

from orca import place_resolution as pr
from orca.data.loaders import DEFAULT_LAT, DEFAULT_LON


def test_a_resolved_place_carries_its_position_and_nothing_to_disclose():
    r = pr.resolve_or_ask("is it safe near Veraval")
    assert (r.status, r.disclosure) == ("resolved", None)
    assert r.place is not None and r.place.name == "veraval"
    assert r.as_dict()["place_source"] == "gazetteer"


def test_every_unanswerable_or_fallback_outcome_carries_a_sentence():
    """The contract the whole point rests on: a fallback that is not disclosed
    is a lie, and "I can't" with no reason is not an answer either."""
    for query in [
        "is it safe near my village",     # unresolvable
        "is it safe in Kerala",           # ambiguous (region)
        "compare Chennai and Pamban",     # ambiguous (two places)
        "is it safe to go to sea",        # fallback (no place named)
    ]:
        r = pr.resolve_or_ask(query)
        assert r.status != "resolved", query
        assert r.disclosure, query


def test_the_regional_default_is_named_as_a_default_not_as_the_users_place():
    r = pr.resolve_or_ask("is it safe to go to sea tomorrow")
    assert r.status == "fallback"
    assert r.place is not None
    assert (r.place.lat, r.place.lon) == (DEFAULT_LAT, DEFAULT_LON)
    assert r.place.source == "regional_default"
    assert "not your position" in (r.disclosure or "")


def test_a_carried_over_place_is_used_but_attributed_to_the_earlier_turn():
    r = pr.resolve_or_ask("what about tomorrow?", {"last_place": (9.2833, 79.2, "pamban")})
    assert r.status == "fallback"
    assert r.place is not None and r.place.source == "session_carried"
    assert "last place this conversation named" in (r.disclosure or "")


def test_ambiguous_candidates_reach_the_wire_with_coordinates():
    """"Did you mean Veraval or Porbandar?" is not a real choice without
    them — the caller has to be able to re-ask at one."""
    wire = pr.resolve_or_ask("is it safe in Gujarat").as_dict()
    assert wire["status"] == "ambiguous"
    assert len(wire["candidates"]) >= 2
    assert all({"name", "lat", "lon"} <= set(c) for c in wire["candidates"])


def test_a_passage_naming_two_places_is_answered_at_the_origin_not_refused():
    r = pr.resolve_or_ask("safest route from Thoothukudi to Pamban")
    assert r.status == "resolved"
    assert r.place is not None and r.place.name == "thoothukudi"
    assert len(r.candidates) == 2
    assert "passage" in (r.disclosure or "")


# --- the coordinate parser -------------------------------------------------

def test_coordinate_shapes_a_plotter_actually_produces():
    for text, expected in [
        ("conditions at 8.75N 78.25E", (8.75, 78.25)),
        ("8.75 N, 78.25 E please", (8.75, 78.25)),
        ("lat 8.75 lon 78.25", (8.75, 78.25)),
        ("we are at 8.75, 78.25", (8.75, 78.25)),
    ]:
        place = pr.parse_coordinates(text)
        assert place is not None, text
        assert (round(place.lat, 4), round(place.lon, 4)) == expected, text
        assert place.source == "coordinates"


def test_things_that_look_like_numbers_but_are_not_a_position():
    for text in [
        "boat 2, 3 men aboard",        # bare integers are not a fix
        "is it safe to go to sea",     # no numbers at all
        "we are at 200.0N 400.0E",     # out of range, not clamped
    ]:
        assert pr.parse_coordinates(text) is None, text


# --- the time and position guards ------------------------------------------

def test_the_time_guard_names_the_horizon_in_both_directions():
    assert "past" in (pr.time_guard("was it rough yesterday") or "")
    beyond = pr.time_guard("is it safe in 3 weeks") or ""
    assert str(pr.FORECAST_HORIZON_DAYS) in beyond


def test_a_date_inside_the_horizon_passes_and_one_outside_it_does_not():
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    inside = (now + timedelta(days=3)).date().isoformat()
    outside = (now + timedelta(days=30)).date().isoformat()
    assert pr.time_guard(f"is it safe on {inside}", now=now) is None
    assert pr.time_guard(f"is it safe on {outside}", now=now) is not None


def test_the_position_guard_lets_the_default_through_and_stops_the_open_ocean():
    assert pr.position_guard(DEFAULT_LAT, DEFAULT_LON) is None
    off_somalia = pr.position_guard(12.0, 50.0)
    assert off_somalia is not None and "outside the sea area" in off_somalia
