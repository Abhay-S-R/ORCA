"""resolve_port_from_text (backend/orca/api/main.py's /query location fallback):
the one check that fails if a real port name in a query stops resolving to
that port's real coordinates — the bug this exists to catch is "near Pamban"
silently answering as if it had been asked about Thoothukudi instead.
"""
from orca.data.loaders import port_coordinates, resolve_port_from_text


def test_known_port_name_resolves_to_its_own_coordinates():
    resolved = resolve_port_from_text("is it safe to go to sea near Pamban tomorrow")
    assert resolved is not None
    port, lat, lon = resolved
    assert port == "pamban"
    assert (lat, lon) == port_coordinates()["pamban"]


def test_alias_resolves_to_the_canonical_port():
    resolved = resolve_port_from_text("wave height at Cochin harbour")
    assert resolved is not None
    assert resolved[0] == "kochi"


def test_match_is_case_insensitive():
    resolved = resolve_port_from_text("CHENNAI weather today")
    assert resolved is not None
    assert resolved[0] == "chennai"


def test_no_known_port_named_returns_none():
    assert resolve_port_from_text("is it safe to go to sea tomorrow morning") is None
