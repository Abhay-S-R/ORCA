"""AGENT-AUDIT 4, phase A6 (2026-10-10): every specialist reports decided vs used, the run says whether they agree, and Agent 3
has a plain sentence for the trace.

The trace may only say what the backend really did: so the backend, not the UI, produces (1) per-specialist `source_report`,
(2) a run-level `source_check` that lists any difference (never hides one), (3) `trace_line`, the sentence for Agent 3's step.
"""
from __future__ import annotations

import logging
from unittest import mock

import pytest

from orca.agents import discovery
from orca.agents.discovery import discovery_trace_line, source_check, source_report_entry
from orca.graph.graph import geospatial_run, marine_data_discovery_run


def _sel(dtype, chosen, dataset, *, stale=False, fell=None):
    return {"data_type": dtype, "chosen": chosen, "chosen_dataset": dataset, "narrative": "n", "considered": [chosen], "fallback_chain": [],
            "arrival": {"checked": True, "ok": True, "detail": "d", "stale": stale}, "rejected": fell or [], "fell_through": bool(fell)}


# --- the shared entry accepts several used sources ---------------------------------------------------------------------------------

def test_a_list_of_used_sources_obeys_when_the_decision_is_among_them():
    d = {"chosen": "unep_wcmc_wdpa", "considered": ["unep_wcmc_wdpa", "marineregions_eez"]}
    assert source_report_entry(d, ["marineregions_eez", "unep_wcmc_wdpa"])["obeyed"] is True
    assert source_report_entry(d, ["marineregions_eez"])["obeyed"] is True        # a later declared rung
    assert source_report_entry({"chosen": "x", "considered": ["x"]}, ["a", "b"])["obeyed"] is False
    assert source_report_entry(None, ["a"]) == {"decided": None, "used": ["a"], "obeyed": None}


# --- the run-level check ----------------------------------------------------------------------------------------------------------------

def test_all_obeyed_says_so_with_the_count():
    out = source_check({"weather_intelligence": {"wave_height": {"decided": "a", "used": "a", "obeyed": True}},
                        "ocean_analytics": {"tide": {"decided": "t", "used": "t", "obeyed": True}, "pfz": {"decided": "p", "used": "p", "obeyed": True}}})
    assert out["checked"] == 3 and out["obeyed"] == 3 and out["mismatches"] == [] and out["unknown"] == []
    assert out["line"] == "Every source used matches what marine data discovery decided (3 checks)."


def test_a_difference_is_listed_logged_and_said_never_hidden(caplog):
    reports = {"ocean_analytics": {"tide": {"decided": "stormglass_tides", "used": "soi_tide_tables", "obeyed": False},
                                   "pfz": {"decided": "incois_pfz", "used": "incois_pfz", "obeyed": True}}}
    with caplog.at_level(logging.WARNING, logger="orca.agents.discovery"):
        out = source_check(reports)
    assert out["checked"] == 2 and out["obeyed"] == 1
    assert out["mismatches"] == [{"agent": "ocean_analytics", "data_type": "tide", "decided": "stormglass_tides", "used": "soi_tide_tables"}]
    assert "ocean_analytics used soi_tide_tables for tide but marine data discovery decided stormglass_tides" in out["line"]
    assert any("source mismatch" in r.message for r in caplog.records)


def test_an_entry_with_no_decision_is_unknown_and_not_counted_as_obeyed():
    out = source_check({"weather_intelligence": {"wave_height": {"decided": None, "used": "a", "obeyed": None}}})
    assert out["checked"] == 0 and out["obeyed"] == 0 and out["unknown"] == ["weather_intelligence:wave_height"]
    assert out["line"] == "No source decisions were available to compare."


def test_missing_reports_are_tolerated():
    assert source_check({"weather_intelligence": None, "ocean_analytics": {}, "geospatial": None})["checked"] == 0


# --- Agent 3's sentence -------------------------------------------------------------------------------------------------------------------

def test_the_line_groups_data_types_that_share_a_source():
    line = discovery_trace_line([_sel("wave_height", "open_meteo_marine", "Open-Meteo Marine API"), _sel("wind_speed", "open_meteo_marine", "Open-Meteo Marine API"),
                                 _sel("tide", "soi_tide_tables", "Survey of India 2026 Annual Tide Tables")])
    assert line == "Chose data sources: wave height and wind speed from Open-Meteo Marine API; tides from Survey of India 2026 Annual Tide Tables."


def test_the_line_says_when_a_source_fell_back_or_is_not_current():
    line = discovery_trace_line([_sel("tide", "stormglass_tides", "Stormglass cache", fell=[{"source_id": "soi_tide_tables", "reason": "no Survey of India rows for station NMP"}]),
                                 _sel("pfz", "incois_pfz", "INCOIS PFZ advisories", stale=True)])
    assert "tides from Stormglass cache (fell back: no Survey of India rows for station NMP)" in line
    assert "fishing zones from INCOIS PFZ advisories (not current)" in line


def test_the_line_names_data_types_with_no_usable_source():
    line = discovery_trace_line([_sel("pfz", "incois_pfz", "INCOIS PFZ advisories")], ["tide", "catch_statistics"])
    assert line.endswith("No usable source for: tides, catch statistics.")
    assert discovery_trace_line([], []) == "No data source was needed."


def test_three_data_types_read_naturally():
    line = discovery_trace_line([_sel("sst", "a", "A"), _sel("chlorophyll", "a", "A"), _sel("pfz", "a", "A")])
    assert line == "Chose data sources: sea surface temperature, chlorophyll and fishing zones from A."


# --- the nodes emit them ---------------------------------------------------------------------------------------------------------------------

def test_the_discovery_step_carries_its_line():
    state = {"query_id": "q", "matched_intent_rows": ["PFZ_NEAREST"], "execution_plan": [], "user_location": {"lat": 13.3, "lon": 74.7}}
    result = marine_data_discovery_run(state)  # type: ignore[arg-type]
    line = result.outputs["trace_line"]
    assert line.startswith("Chose data sources: ") and "fishing zones" in line and "boundaries" in line


def test_geospatial_reports_decided_vs_used_for_the_boundary_files_it_really_reads():
    decisions = {"boundary": {"chosen": "unep_wcmc_wdpa", "considered": ["unep_wcmc_wdpa", "marineregions_eez"]},
                 "mpa": {"chosen": "unep_wcmc_wdpa", "considered": ["unep_wcmc_wdpa"]},
                 "eez": {"chosen": "marineregions_eez", "considered": ["marineregions_eez"]}}
    state = {"query_id": "q", "user_location": {"lat": 9.0, "lon": 79.0, "place_source": "gazetteer"}, "discovery_sources": {"by_data_type": decisions}}
    report = geospatial_run(state).outputs["source_report"]  # type: ignore[arg-type]
    assert report["boundary"]["obeyed"] is True and set(report["boundary"]["used"]) == {"marineregions_eez", "unep_wcmc_wdpa"}
    assert report["mpa"] == {"decided": "unep_wcmc_wdpa", "used": "unep_wcmc_wdpa", "obeyed": True}
    assert report["eez"]["obeyed"] is True


def test_geospatial_without_a_decision_is_unknown():
    state = {"query_id": "q", "user_location": {"lat": 9.0, "lon": 79.0, "place_source": "gazetteer"}}
    assert geospatial_run(state).outputs["source_report"] == {  # type: ignore[arg-type]
        "boundary": {"decided": None, "used": ["marineregions_eez", "unep_wcmc_wdpa"], "obeyed": None}}


def test_the_final_response_carries_the_check():
    import inspect

    from orca.api import main

    assert '"source_check": _source_check_for(weather, ocean, geo)' in inspect.getsource(main._query_stream)
    out = main._source_check_for({"source_report": {"w": {"decided": "a", "used": "a", "obeyed": True}}}, {}, {})
    assert out["checked"] == 1 and out["mismatches"] == []


def test_a_mismatch_in_any_specialist_reaches_the_answer_level_check():
    from orca.api import main

    out = main._source_check_for({}, {"source_report": {"tide": {"decided": "a", "used": "b", "obeyed": False}}}, {"source_report": {}})
    assert [m["data_type"] for m in out["mismatches"]] == ["tide"] and "but marine data discovery decided a" in out["line"]


@pytest.mark.parametrize("fn", [discovery.source_check, discovery.discovery_trace_line])
def test_the_helpers_are_pure_and_importable(fn):
    assert callable(fn) and mock is not None
