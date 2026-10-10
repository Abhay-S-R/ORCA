"""PC1.1 (`R-NEW-1`, `R-EDGE-3`) — unit tests for :func:`validate_reading`.

Done-when (Consolidation Plan §4 PC1.1):
  * unknown place             → ``NEEDS_PLACE``
  * ``when`` past             → ``OUT_OF_RANGE``
  * ``when`` beyond horizon   → ``OUT_OF_RANGE``
  * explicit land coordinate  → ``OUT_OF_RANGE`` (position_guard disclosure)
  * valid inputs              → ``None``

Existing guard tests in ``test_place_resolution.py`` are not touched.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orca.place_resolution import (
    FORECAST_HORIZON_DAYS,
    validate_reading,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 10, 4, 6, 0, 0, tzinfo=UTC)  # fixed clock for all tests

# A known good place from the gazetteer (used across several tests).
_VERAVAL = [{"raw": "Veraval", "normalized": "veraval"}]

# A known sea position inside the data extent.
_SEA_LOCATION = {"lat": 8.80, "lon": 78.30, "place_source": "gazetteer"}

# A position outside the data extent, provided as an explicit GPS fix.
_OUTSIDE_EXTENT = {"lat": 12.0, "lon": 50.0, "place_source": "gps_fix"}


def _iso(days_offset: int) -> str:
    """Return an ISO-8601 date string offset from _NOW by *days_offset* days."""
    return (_NOW + timedelta(days=days_offset)).date().isoformat() + "T00:00:00Z"


# ---------------------------------------------------------------------------
# Place validation
# ---------------------------------------------------------------------------

def test_unknown_place_returns_needs_place():
    """A place name the model extracted that is not in the gazetteer must
    never silently fall back to the regional default — it must surface as
    NEEDS_PLACE so the user can clarify."""
    outcome = validate_reading(
        places=[{"raw": "Chandamaruta", "normalized": "Chandamaruta"}],
        when=None,
        user_location=None,
        now=_NOW,
    )
    assert outcome is not None
    assert outcome.code == "NEEDS_PLACE"
    assert outcome.body  # non-empty — something to show the user


def test_unknown_place_with_typo_offers_candidates():
    """A near-miss (e.g. 'gujurat' → Gujarat) surfaces as NEEDS_PLACE with
    the corrected candidates listed in the body."""
    outcome = validate_reading(
        places=[{"raw": "gujurat", "normalized": "gujurat"}],
        when=None,
        user_location=None,
        now=_NOW,
    )
    assert outcome is not None
    assert outcome.code == "NEEDS_PLACE"
    # The body should contain candidate names from the Gujarat coastline.
    assert "N " in outcome.body or "did you mean" in outcome.body.lower()


def test_known_good_place_does_not_refuse():
    """A gazetteer-resolved place must not trigger a refusal."""
    outcome = validate_reading(
        places=_VERAVAL,
        when=None,
        user_location=None,
        now=_NOW,
    )
    assert outcome is None


def test_inland_place_returns_needs_place():
    """A real but inland place (e.g. Delhi) must not fall through to the
    regional default — it is unresolvable, which maps to NEEDS_PLACE."""
    outcome = validate_reading(
        places=[{"raw": "Delhi", "normalized": "Delhi"}],
        when=None,
        user_location=None,
        now=_NOW,
    )
    assert outcome is not None
    assert outcome.code == "NEEDS_PLACE"


def test_international_place_returns_out_of_range():
    """An international place outside India's maritime waters (e.g. New York, Dubai)
    must be refused with OUT_OF_RANGE, not NEEDS_PLACE."""
    for raw_name, norm_name in [("New York", "new york"), ("Dubai", "dubai"), ("London", "london")]:
        outcome = validate_reading(
            places=[{"raw": raw_name, "normalized": norm_name}],
            when=None,
            user_location=None,
            now=_NOW,
        )
        assert outcome is not None, raw_name
        assert outcome.code == "OUT_OF_RANGE", raw_name
        assert "outside India's maritime waters" in outcome.body, raw_name


def test_empty_places_list_does_not_refuse():
    """No places extracted means the model found no place — validate_reading
    does not refuse; the caller decides whether a place is required."""
    outcome = validate_reading(
        places=[],
        when=None,
        user_location=None,
        now=_NOW,
    )
    assert outcome is None


def test_entry_with_empty_normalized_is_skipped():
    """An entry where both 'normalized' and 'raw' are absent/empty must be
    skipped, not treated as an unknown place."""
    outcome = validate_reading(
        places=[{"raw": "", "normalized": ""}],
        when=None,
        user_location=None,
        now=_NOW,
    )
    assert outcome is None


# ---------------------------------------------------------------------------
# Time / horizon validation
# ---------------------------------------------------------------------------

def test_past_date_returns_out_of_range():
    """A start date in the past must be refused as OUT_OF_RANGE."""
    past = _iso(-2)
    outcome = validate_reading(
        places=[],
        when={"start": past, "end": past},
        user_location=None,
        now=_NOW,
    )
    assert outcome is not None
    assert outcome.code == "OUT_OF_RANGE"
    assert "past" in outcome.body.lower()


def test_date_beyond_horizon_returns_out_of_range():
    """A start date beyond the forecast horizon must be refused as
    OUT_OF_RANGE.  This is the PC1.2 Done-when: 'safe near kochi on
    2026-10-30' refused using the model's `when`."""
    beyond = _iso(FORECAST_HORIZON_DAYS + 5)
    outcome = validate_reading(
        places=[],
        when={"start": beyond, "end": beyond},
        user_location=None,
        now=_NOW,
    )
    assert outcome is not None
    assert outcome.code == "OUT_OF_RANGE"
    assert str(FORECAST_HORIZON_DAYS) in outcome.body


def test_date_at_horizon_boundary_passes():
    """The last valid forecast day (today + FORECAST_HORIZON_DAYS) must not
    be refused — the check is strictly greater-than."""
    at_horizon = _iso(FORECAST_HORIZON_DAYS)
    outcome = validate_reading(
        places=[],
        when={"start": at_horizon, "end": at_horizon},
        user_location=None,
        now=_NOW,
    )
    assert outcome is None


def test_date_within_horizon_passes():
    """A start date inside the horizon must not be refused."""
    inside = _iso(3)
    outcome = validate_reading(
        places=[],
        when={"start": inside, "end": inside},
        user_location=None,
        now=_NOW,
    )
    assert outcome is None


def test_malformed_when_does_not_crash():
    """A malformed ISO string in `when` must be swallowed, not raised — the
    offline fallback (time_guard on raw text) will catch it in PC1.2."""
    outcome = validate_reading(
        places=[],
        when={"start": "not-a-date", "end": ""},
        user_location=None,
        now=_NOW,
    )
    assert outcome is None  # no crash, no false refusal


def test_none_when_is_not_checked():
    """``when=None`` means the model did not extract a time — no time check
    runs and the call must pass through to the next check."""
    outcome = validate_reading(
        places=[],
        when=None,
        user_location=_SEA_LOCATION,
        now=_NOW,
    )
    assert outcome is None


# ---------------------------------------------------------------------------
# Position / extent validation
# ---------------------------------------------------------------------------

def test_explicit_position_outside_extent_returns_out_of_range():
    """A GPS fix outside the data extent must be refused as OUT_OF_RANGE."""
    outcome = validate_reading(
        places=[],
        when=None,
        user_location=_OUTSIDE_EXTENT,
        now=_NOW,
    )
    assert outcome is not None
    assert outcome.code == "OUT_OF_RANGE"
    assert "outside" in outcome.body.lower()


def test_non_explicit_position_outside_extent_does_not_hard_stop():
    """A position inferred from a place name that happens to be outside the
    extent is a soft disclosure, not a hard stop.  validate_reading returns
    None — the caller adds the disclosure to ``disclosures``."""
    outside_inferred = {"lat": 12.0, "lon": 50.0, "place_source": "gazetteer"}
    outcome = validate_reading(
        places=[],
        when=None,
        user_location=outside_inferred,
        now=_NOW,
    )
    assert outcome is None


def test_valid_sea_position_passes():
    """A sea position inside the data extent must not be refused."""
    outcome = validate_reading(
        places=[],
        when=None,
        user_location=_SEA_LOCATION,
        now=_NOW,
    )
    assert outcome is None


def test_none_user_location_skips_position_check():
    """``user_location=None`` must not crash and must not refuse."""
    outcome = validate_reading(
        places=[],
        when=None,
        user_location=None,
        now=_NOW,
    )
    assert outcome is None


# ---------------------------------------------------------------------------
# Combined: fully valid reading returns None
# ---------------------------------------------------------------------------

def test_valid_place_time_and_position_returns_none():
    """The expected happy-path: known place, date inside horizon, sea position
    → None (proceed, no guard fires)."""
    inside = _iso(2)
    outcome = validate_reading(
        places=_VERAVAL,
        when={"start": inside, "end": inside},
        user_location=_SEA_LOCATION,
        now=_NOW,
    )
    assert outcome is None


# ---------------------------------------------------------------------------
# Combined: place check fires before time / position checks
# ---------------------------------------------------------------------------

def test_place_check_fires_before_time_check():
    """When both a bad place and a past date are present, the place refusal
    is returned first (loop order)."""
    past = _iso(-1)
    outcome = validate_reading(
        places=[{"raw": "Chandamaruta", "normalized": "Chandamaruta"}],
        when={"start": past, "end": past},
        user_location=None,
        now=_NOW,
    )
    assert outcome is not None
    assert outcome.code == "NEEDS_PLACE"


# ---------------------------------------------------------------------------
# A position the caller chose is the place (the "which did you mean?" chip)
# ---------------------------------------------------------------------------

_GUJARAT = [{"raw": "gujarat", "normalized": "gujarat"}]
_VERAVAL_AT = {"lat": 20.90, "lon": 70.37, "place_name": "veraval", "place_source": "explicit"}


def test_a_chosen_position_settles_a_whole_coastline_named_in_the_text():
    """A picked chip sends "... near gujarat (at veraval)" with Veraval's coordinates."""
    assert validate_reading(_GUJARAT, None, _VERAVAL_AT, now=_NOW) is None


def test_the_same_coastline_still_asks_when_no_position_was_chosen():
    for source in ("gazetteer", "gps_fix", "home_port", "session_carried", "regional_default"):
        loc = {**_VERAVAL_AT, "place_source": source}
        outcome = validate_reading(_GUJARAT, None, loc, now=_NOW)
        assert outcome is not None and outcome.code == "NEEDS_PLACE", source


def test_typed_coordinates_count_as_a_chosen_position():
    loc = {"lat": 20.90, "lon": 70.37, "place_source": "coordinates"}
    assert validate_reading(_GUJARAT, None, loc, now=_NOW) is None


def test_a_chosen_position_does_not_excuse_a_date_beyond_the_horizon():
    outcome = validate_reading(_GUJARAT, {"start": _iso(30), "end": _iso(30)}, _VERAVAL_AT, now=_NOW)
    assert outcome is not None and outcome.code == "OUT_OF_RANGE"


def test_a_chosen_position_outside_the_data_extent_is_still_refused():
    loc = {"lat": 12.0, "lon": 50.0, "place_source": "explicit"}
    outcome = validate_reading(_GUJARAT, None, loc, now=_NOW)
    assert outcome is not None and outcome.code == "OUT_OF_RANGE"
