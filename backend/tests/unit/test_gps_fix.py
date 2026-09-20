"""The browser's GPS fix is only a position when there is sea at it.

`fix_lat`/`fix_lon` let the Ask page answer at the caller's actual location
when the query names nowhere ORCA holds. The failure this guards is the one
found in a live demo: the caller was in Bengaluru, 300 km inland, so the fix
resolved to a point with no sea at it and every query that didn't name a port
came back "12.9380, 77.4953 is on land" — worse than the regional default it
had replaced.
"""
from __future__ import annotations

from orca.api.main import _usable_fix

# Off Thoothukudi — open water in the pilot region.
AT_SEA = (8.60, 78.40)
# Bengaluru city centre: a real GPS reading, 300 km from any coast.
INLAND = (12.9380, 77.4953)


def test_a_fix_at_sea_is_usable():
    assert _usable_fix(*AT_SEA) is True


def test_an_inland_fix_is_not_a_position():
    assert _usable_fix(*INLAND) is False


def test_no_fix_at_all_is_not_a_position():
    assert _usable_fix(None, None) is False
    assert _usable_fix(8.60, None) is False
    assert _usable_fix(None, 78.40) is False


def test_a_gps_fix_turn_is_not_carried_into_the_next_turn():
    """Ambient position is context for its own turn only.

    The Ask page re-sends the fix on every request, so carrying it costs
    nothing to drop — and keeping it meant one turn answered at the caller's
    position pinned every later turn in the chat to it, ahead of the query
    text. For a caller inland that turned the whole chat into "on land".
    """
    from orca.session import last_place

    turns = [
        {"user_location": {"lat": 12.9380, "lon": 77.4953, "place_source": "gps_fix"}},
    ]
    assert last_place(turns) is None

    # A place the user actually named is still carried.
    turns.insert(0, {"user_location": {"lat": 21.08, "lon": 70.10,
                                       "place_name": "mangrol", "place_source": "gazetteer"}})
    assert last_place(turns) == (21.08, 70.10, "mangrol")


def test_a_discarded_inland_fix_is_disclosed_to_the_narrator():
    """"No GPS fix was supplied" is false when one was — and an undisclosed
    discard is how the default's numbers reach a caller 1,500 km away as
    "your nearest fishing zone"."""
    from orca.agents.reporting import describe_location

    base = {"lat": 8.80, "lon": 78.30, "place_source": "regional_default"}
    assert "no GPS fix was supplied" in describe_location(base)

    told = describe_location({**base, "fix_on_land": True})
    assert "no GPS fix was supplied" not in told
    assert "inland" in told
    assert "your nearest" in told  # the prompt forbids the phrase by name
