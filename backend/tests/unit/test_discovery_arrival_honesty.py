"""AGENT-AUDIT 4 (marine_data_discovery), phase A1 (2026-10-10): the arrival check answers "can this source answer THIS question".

Before: "137 tide events, heights within range" was true of the whole Survey of India file while the station asked about had
no rows or its rows ended before the requested time; the PFZ probe read the cloud-cover fallback geojson, not the advisory the
answer quotes; the Stormglass rung (a cache on disk) was labelled "live, validated on fetch"; a one-station gap opened the
breaker for every station; and Agent 3 asked the breaker about an id nothing ever trips.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest

from orca import resilience
from orca.agents import discovery
from orca.agents.discovery import select_validated_source, validate_arrival
from orca.data import analytics_loaders as al

NOW = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)


def _ev(code, day, height=1.0):
    return {"station_code": code, "station_name": code, "when": datetime(2026, 10, day, 6, 0, tzinfo=UTC), "tide_event": "HIGH TIDE", "height_m": height, "source": "t"}


@pytest.fixture(autouse=True)
def _clean_breakers():
    ids = ("soi_tide_tables", "stormglass_tides", "incois_pfz", "open_meteo", "open_meteo_marine", "incois_hazard_bulletins", "incois_hazard_osf")
    for i in ids:
        resilience._breaker_opened_at.pop(i, None)
        resilience._breaker_failures.pop(i, None)
    yield
    for i in ids:
        resilience._breaker_opened_at.pop(i, None)
        resilience._breaker_failures.pop(i, None)


def _tides(soi=(), storm=None, station="KOC"):
    storm = storm or {}
    return mock.patch.multiple(
        al, load_soi_tide_events=lambda: list(soi), load_stormglass_tide_events=lambda code: list(storm.get(code, [])),
    ), mock.patch("orca.agents.ocean_analytics.nearest_station", lambda lat, lon: {"station_code": station})


def _decide(soi, storm, station, when=NOW):
    a, b = _tides(soi, storm, station)
    with a, b:
        return select_validated_source("tide", ctx={"lat": 9.9, "lon": 76.2, "when": when.isoformat()})


# --- tide: per station and per requested time --------------------------------------------------------------------------------

def test_a_station_with_rows_covering_the_requested_time_is_valid():
    d = _decide([_ev("KOC", 12), _ev("KOC", 16)], {}, "KOC")
    assert d is not None and d["chosen"] == "soi_tide_tables" and d["fell_through"] is False
    assert "station KOC" in d["arrival"]["detail"] and "covering 2026-10-10" in d["arrival"]["detail"]


def test_a_station_with_no_rows_falls_to_the_stormglass_cache_and_says_why():
    d = _decide([_ev("KOC", 12)], {"NMP": [_ev("NMP", 14)]}, "NMP")
    assert d is not None and d["chosen"] == "stormglass_tides" and d["fell_through"] is True
    assert d["rejected"] == [{"source_id": "soi_tide_tables", "reason": "no Survey of India rows for station NMP"}]


def test_rows_that_end_before_the_requested_time_are_rejected_not_called_valid():
    d = _decide([_ev("KOC", 12)], {}, "KOC", when=NOW + timedelta(days=20))
    assert d is not None and d["chosen"] is None and "all rungs failed" in d["arrival"]["detail"]
    assert any("ends 2026-10-12, before the requested 2026-10-30" in r["reason"] for r in d["rejected"])


def test_both_tide_rungs_short_is_reported_as_no_usable_source_not_hidden():
    d = _decide([_ev("KOC", 12)], {"KOC": [_ev("KOC", 13)]}, "KOC", when=NOW + timedelta(days=20))
    assert d["chosen"] is None and {r["source_id"] for r in d["rejected"]} == {"soi_tide_tables", "stormglass_tides"}


def test_the_stormglass_rung_is_probed_it_is_a_cache_not_a_live_source():
    a, b = _tides([], {"KOC": [_ev("KOC", 14)]}, "KOC")
    with a, b:
        check = validate_arrival("stormglass_tides", {"lat": 9.9, "lon": 76.2, "when": NOW.isoformat()})
    assert check.checked is True and check.ok is True and "cached Stormglass extremes" in check.detail


# --- a coverage gap is about the question, not about the source being broken ----------------------------------------------------

def test_one_station_gap_does_not_open_the_breaker_for_every_station():
    for _ in range(6):
        d = _decide([_ev("KOC", 12)], {"NMP": [_ev("NMP", 14)]}, "NMP")
        assert d["chosen"] == "stormglass_tides"
    assert not resilience.circuit_open("soi_tide_tables")
    again = _decide([_ev("KOC", 12), _ev("KOC", 16)], {}, "KOC")
    assert again["chosen"] == "soi_tide_tables"      # the next question, another station, still gets the Survey of India table


def test_an_unreadable_source_still_counts_against_the_breaker():
    def boom():
        raise OSError("file unreadable")

    with mock.patch.object(al, "load_soi_tide_events", boom), mock.patch("orca.agents.ocean_analytics.nearest_station", lambda lat, lon: {"station_code": "KOC"}):
        for _ in range(6):
            assert validate_arrival("soi_tide_tables", {"lat": 1.0, "lon": 1.0}).ok is False
    assert resilience.circuit_open("soi_tide_tables")


def test_an_empty_table_is_a_systemic_failure():
    with mock.patch.object(al, "load_soi_tide_events", list):
        assert validate_arrival("soi_tide_tables", {}).ok is False


# --- PFZ: the advisory the answer quotes, with its age -----------------------------------------------------------------------

def _pfz_rows(age, expired):
    return [{"sector_id": "SEC006", "valid_for": "2026-10-02", "age_days": age, "expired": expired, "band": "history"}]


def test_the_pfz_probe_reads_the_advisory_not_the_fallback_geojson_and_reports_its_age():
    with mock.patch.object(al, "load_pfz_latest", lambda today=None: _pfz_rows(8, True)):
        check = validate_arrival("incois_pfz", {})
    assert check.ok is True and check.stale is True
    assert "valid for 2026-10-02" in check.detail and "8 day(s) old" in check.detail and "expired" in check.detail


def test_an_old_advisory_is_kept_not_rejected():
    # the standing rule: an old advisory is still the best information there is
    with mock.patch.object(al, "load_pfz_latest", lambda today=None: _pfz_rows(8, True)):
        d = select_validated_source("pfz")
    assert d is not None and d["chosen"] == "incois_pfz" and d["arrival"]["stale"] is True


def test_a_current_advisory_is_not_stale():
    with mock.patch.object(al, "load_pfz_latest", lambda today=None: _pfz_rows(0, False)):
        check = validate_arrival("incois_pfz", {})
    assert check.ok is True and check.stale is False and "current" in check.detail


def test_no_advisory_rows_is_a_failure():
    with mock.patch.object(al, "load_pfz_latest", lambda today=None: []):
        assert validate_arrival("incois_pfz", {}).ok is False


# --- the breaker the specialists trip is the one Agent 3 consults ---------------------------------------------------------------

def test_agent_3_skips_open_meteo_once_weather_has_given_up_on_it():
    first = discovery.select_source_with_fallback("wave_height")
    assert first is not None and first.chosen.id == "open_meteo_marine"
    for _ in range(6):
        resilience.record_failure("open_meteo")          # the key weather_intelligence trips
    assert resilience.circuit_open("open_meteo")
    second = discovery.select_source_with_fallback("wave_height")
    assert second is not None and second.chosen.id != "open_meteo_marine"


def test_the_hazard_alias_is_the_same_story():
    for _ in range(6):
        resilience.record_failure("incois_hazard_bulletins")
    assert discovery._breaker_open("incois_hazard_osf") is True


# --- the graph hands the question's context to the probes, and stale shows up on the span ---------------------------------------

def test_the_node_passes_position_and_time_and_marks_stale_data_medium():
    from orca.graph.graph import marine_data_discovery_run

    seen = {}
    real = discovery.select_validated_source

    def spy(dtype, **kw):
        seen.setdefault("ctx", kw.get("ctx"))
        return real(dtype, **kw)

    state = {"query_id": "q", "matched_intent_rows": ["PFZ_NEAREST"], "execution_plan": [],
             "user_location": {"lat": 13.3, "lon": 74.7}, "understood_when": {"start": "2026-10-11T00:00:00+00:00"}}
    with mock.patch.object(discovery, "select_validated_source", spy), mock.patch.object(al, "load_pfz_latest", lambda today=None: _pfz_rows(8, True)):
        result = marine_data_discovery_run(state)  # type: ignore[arg-type]
    assert seen["ctx"] == {"lat": 13.3, "lon": 74.7, "when": "2026-10-11T00:00:00+00:00"}
    assert "pfz" in result.outputs["stale"] and "stale: pfz" in result.confidence.rationale and result.confidence.score in ("MEDIUM", "LOW_DATA")
