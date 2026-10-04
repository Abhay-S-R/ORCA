"""PC1.2 (`R-NEW-1`) — unit tests for the rewired query_guard_node.

Done-when (Consolidation Plan §4 PC1.2):
  * With the model's ``understood_when`` set to a date beyond the horizon,
    ``query_guard_node`` returns ``query_outcome == "OUT_OF_RANGE"``.
  * With a valid place and no ``understood_when``, the guard passes through
    (returns no stop code).
  * With the model's ``understood_places`` containing an unknown place,
    the guard returns ``query_outcome == "NEEDS_PLACE"``.
  * With ``understood_when`` absent (LLM down), the deterministic
    ``time_guard`` fallback fires when the raw query contains a far-future date.

These tests do not call the LLM — they inject pre-parsed ``understood_*``
fields into state to confirm the guard now reads the model's output, not
just raw-text word lists.

Graph wiring confirmed (Consolidation Plan §4 PC1.2):
    distress_check → language_ingress → understand → query_guard → planning
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

# PC2.3: query_guard folded into planning_node
from orca.graph.graph import planning_node as query_guard_node
from orca.place_resolution import FORECAST_HORIZON_DAYS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 10, 4, 6, 0, 0, tzinfo=timezone.utc)
_TODAY = _NOW.date()


def _iso(days_offset: int) -> str:
    return (_TODAY + timedelta(days=days_offset)).isoformat() + "T00:00:00Z"


def _base_state(**overrides) -> dict:
    """Minimal ORCAState-shaped dict that skips all early-exit paths."""
    state: dict = {
        "raw_user_query": "safe near kochi",
        "normalized_english_query": "safe near kochi",
        "understood_kind": "sea_safety_check",   # not a non-sea kind → guard runs
        "understood_places": [],
        "understood_when": None,
        "user_location": None,
        "place_resolution": {},
        "query_outcome": None,
        "disclosures": [],
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# PC1.2 core: guard reads the model's `understood_when`
# ---------------------------------------------------------------------------

def test_beyond_horizon_understood_when_returns_out_of_range():
    """PC1.2 Done-when case A: 'safe near kochi on 2026-10-30'.

    The model parses the date and sets understood_when.  The guard must
    refuse using *that* structured date, not by running time_guard on raw text.
    """
    far_date = _iso(FORECAST_HORIZON_DAYS + 10)
    state = _base_state(
        understood_when={"start": far_date, "end": far_date},
    )
    result = query_guard_node(state)
    assert result.get("query_outcome") == "OUT_OF_RANGE", (
        f"Expected OUT_OF_RANGE for date beyond horizon; got {result}"
    )
    # The refusal body must name the horizon day count.
    body = result.get("final_english_response") or result.get("query_outcome_body") or ""
    assert str(FORECAST_HORIZON_DAYS) in body, (
        "Refusal body must name the forecast horizon day count"
    )


def test_past_understood_when_returns_out_of_range():
    """A `when` in the past must also be refused by validate_reading."""
    past = _iso(-3)
    state = _base_state(
        understood_when={"start": past, "end": past},
    )
    result = query_guard_node(state)
    assert result.get("query_outcome") == "OUT_OF_RANGE"


def test_within_horizon_understood_when_passes():
    """A date inside the horizon must not be refused."""
    inside = _iso(3)
    state = _base_state(
        understood_when={"start": inside, "end": inside},
    )
    result = query_guard_node(state)
    assert result.get("query_outcome") is None, (
        "A date inside the horizon must not trigger a refusal"
    )


# ---------------------------------------------------------------------------
# PC1.2 core: guard reads the model's `understood_places`
# ---------------------------------------------------------------------------

def test_unknown_place_in_understood_places_returns_needs_place():
    """PC1.2 Done-when: the guard now validates model-extracted places.

    'pfzs near rameshwaram' should route through (Rameswaram is in the
    gazetteer).  A fabricated place like 'Chandamaruta' must be refused.
    """
    state = _base_state(
        understood_places=[{"raw": "Chandamaruta", "normalized": "Chandamaruta"}],
    )
    result = query_guard_node(state)
    assert result.get("query_outcome") == "NEEDS_PLACE", (
        "An unknown place extracted by the model must surface as NEEDS_PLACE"
    )


def test_known_place_in_understood_places_passes():
    """PC1.2 Done-when case B: 'pfzs near rameshwaram' still answers."""
    state = _base_state(
        understood_places=[{"raw": "Rameswaram", "normalized": "Rameswaram"}],
    )
    result = query_guard_node(state)
    assert result.get("query_outcome") is None, (
        "A gazetteer-resolved place must not be refused"
    )


# ---------------------------------------------------------------------------
# PC1.2 fallback: when understood_when is absent, time_guard fires on raw text
# ---------------------------------------------------------------------------

def test_time_guard_fallback_fires_when_understood_when_absent():
    """When the model returns no `when` (e.g. LLM down), the deterministic
    time_guard fallback must fire on the raw query text.

    Uses a hardcoded far-future date (2026-12-31) that is unambiguously
    beyond any 7-day horizon, regardless of when the test runs.

    NOTE: query_guard_node passes `normalized_english_query` first to
    time_guard (the fallback preferring the normalised text over raw),
    so the date must appear there, not only in raw_user_query.
    """
    state = _base_state(
        raw_user_query="safe near kochi on 2026-12-31",
        normalized_english_query="safe near kochi on 2026-12-31",
        understood_when=None,
    )
    result = query_guard_node(state)
    assert result.get("query_outcome") == "OUT_OF_RANGE", (
        "time_guard fallback must catch a far-future date in raw text "
        "when understood_when is absent"
    )


def test_time_guard_fallback_silent_when_no_time_in_query():
    """With no time in the raw query and no understood_when, the guard
    must pass through without refusing."""
    state = _base_state(
        raw_user_query="safe near kochi",
        understood_when=None,
    )
    result = query_guard_node(state)
    assert result.get("query_outcome") is None


# ---------------------------------------------------------------------------
# PC1.2: non-sea kinds skip the guard entirely
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", [
    "greeting_or_small_talk",
    "clock_or_position",
    "what_can_orca_do",
    "reset_or_language_switch",
    "off_topic",
])
def test_non_sea_kinds_pass_through_guard(kind: str):
    """query_guard_node must short-circuit for non-sea kinds so they
    reach out_of_scope_node for friendly handling."""
    state = _base_state(
        understood_kind=kind,
        understood_places=[{"raw": "Chandamaruta", "normalized": "Chandamaruta"}],
        understood_when={"start": _iso(FORECAST_HORIZON_DAYS + 10), "end": _iso(FORECAST_HORIZON_DAYS + 10)},
    )
    result = query_guard_node(state)
    # No hard stop — the bad place and bad date are ignored for non-sea kinds.
    assert result.get("query_outcome") is None, (
        f"Non-sea kind {kind!r} must not trigger a hard stop in query_guard"
    )


# ---------------------------------------------------------------------------
# PC1.2: explicit GPS position outside extent → OUT_OF_RANGE
# ---------------------------------------------------------------------------

def test_explicit_gps_outside_extent_returns_out_of_range():
    """An explicit GPS fix outside the data extent must be refused."""
    state = _base_state(
        user_location={"lat": 12.0, "lon": 50.0, "place_source": "gps_fix"},
    )
    result = query_guard_node(state)
    assert result.get("query_outcome") == "OUT_OF_RANGE"
