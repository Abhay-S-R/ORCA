"""AGENT-AUDIT 4, phase A5 (2026-10-10): SST, chlorophyll and PFZ obey marine_data_discovery.

Before: the satellite grids were "live source, validated on fetch" although they are files, so Agent 3's pick said nothing about
whether the place had a reading; ocean_analytics chose the national product as the headline by a constant; chlorophyll was only
settled for the DIAGNOSTIC row. Now: Agent 3 probes each grid for a cell at the position and its age, settles sst and chlorophyll
whenever the question asks for them, the headline follows its decision, and ocean's `source_report` says decided / used / obeyed.
"""
from __future__ import annotations

from unittest import mock

import pytest

from orca import resilience
from orca.agents import ocean_analytics as oa
from orca.agents.discovery import select_validated_source, source_report_entry, validate_arrival
from orca.graph.graph import marine_data_discovery_run


def _grid(cells, freshness_min=1440, when="2026-10-09T00:00:00Z"):
    return {"frame": cells, "provenance": {"dataset": "X", "acquisition_timestamp": when, "freshness_minutes": freshness_min}}


def _cell(v, lat=13.34, lon=74.74):
    return {"lat": lat, "lon": lon, "value": v}


def _tables(sst_a=None, sst_b=None, chl_a=None, chl_b=None):
    return mock.patch.multiple(
        oa,
        _SST_SOURCES=(("INSAT-3DR SST", lambda b: sst_a), ("CMEMS SST", lambda b: sst_b)),
        _CHL_SOURCES=(("EOS-06 OCM-3 chlorophyll", lambda b: chl_a), ("CMEMS ocean-colour chlorophyll", lambda b: chl_b)),
        nearest_osf_point_forecast=lambda lat, lon: {},
    )


@pytest.fixture(autouse=True)
def _clean():
    for i in ("mosdac_open_sst", "mosdac_open_chl", "copernicus_cmems"):
        resilience._breaker_opened_at.pop(i, None)
        resilience._breaker_failures.pop(i, None)
    yield


CTX = {"lat": 13.33, "lon": 74.74}


# --- Agent 3 probes the grids for a cell at the position --------------------------------------------------------------------------

def test_a_grid_with_a_cell_at_the_position_is_valid_with_its_distance_and_age():
    with _tables(sst_a=_grid([_cell(27.0)])):
        d = select_validated_source("sst", ctx=CTX)
    assert d is not None and d["chosen"] == "mosdac_open_sst" and d["fell_through"] is False
    assert "INSAT-3DR SST: cell" in d["arrival"]["detail"] and "observed 2026-10-09" in d["arrival"]["detail"] and d["arrival"]["stale"] is False


def test_a_granule_older_than_three_days_is_kept_but_marked_stale():
    with _tables(sst_a=_grid([_cell(27.0)], freshness_min=6 * 1440, when="2026-10-04T00:00:00Z")):
        d = select_validated_source("sst", ctx=CTX)
    assert d is not None and d["chosen"] == "mosdac_open_sst" and d["arrival"]["stale"] is True


def test_when_insat_has_no_cell_at_the_place_agent_3_falls_to_cmems_and_says_why():
    with _tables(sst_a=_grid([_cell(27.0, lat=20.0, lon=70.0)]), sst_b=_grid([_cell(28.5)])):
        d = select_validated_source("sst", ctx=CTX)
    assert d is not None and d["chosen"] == "copernicus_cmems" and d["fell_through"] is True
    assert d["rejected"][0]["source_id"] == "mosdac_open_sst" and "no sst cell within 60 km" in d["rejected"][0]["reason"]


def test_a_missing_cell_does_not_trip_the_breaker_for_every_other_place():
    with _tables(chl_a=_grid([_cell(0.1, lat=20.0, lon=70.0)]), chl_b=_grid([_cell(1.0)])):
        for _ in range(6):
            assert select_validated_source("chlorophyll", ctx=CTX)["chosen"] == "copernicus_cmems"
    assert not resilience.circuit_open("mosdac_open_chl")


def test_with_no_grid_cell_anywhere_agent_3_names_the_declared_live_last_rung():
    with _tables():
        d = select_validated_source("chlorophyll", ctx=CTX)
    assert d is not None and d["chosen"] == "noaa_coastwatch" and d["arrival"]["checked"] is False   # live: validated on fetch
    assert {r["source_id"] for r in d["rejected"]} == {"mosdac_open_chl", "copernicus_cmems"}


def test_ocean_reads_the_last_rung_only_when_agent_3_decided_it_and_never_speculatively():
    calls = []

    def coastwatch(bbox):
        calls.append(bbox)
        return _grid([_cell(0.4)])

    with _tables(), mock.patch.dict(oa._COASTWATCH, {"chlorophyll": ("NOAA CoastWatch chlorophyll", coastwatch, "mg/m3"), "sst": oa._COASTWATCH["sst"]}):
        none_decided = oa.point_readings(13.33, 74.74)
        assert calls == [] and none_decided["chlorophyll_a"]["headline"] is None          # no decision, no network call
        decided = oa.point_readings(13.33, 74.74, {"chlorophyll": "noaa_coastwatch"})
    assert len(calls) == 1 and decided["chlorophyll_a"]["headline"]["source_id"] == "noaa_coastwatch"
    assert decided["chlorophyll_a"]["headline"]["value"] == 0.4


def test_a_data_type_the_grid_probe_has_nothing_to_say_about_is_unchecked_not_ok():
    check = validate_arrival("copernicus_cmems", {"lat": 13.3, "lon": 74.7, "data_type": "current_speed"})
    assert check.checked is False and "no probe for this data type" in check.detail


def test_without_a_position_the_grid_probe_is_unchecked():
    assert validate_arrival("mosdac_open_sst", {"data_type": "sst"}).checked is False


# --- the readings follow the decision -------------------------------------------------------------------------------------------------

def test_the_headline_follows_agent_3_s_decision():
    with _tables(sst_a=_grid([_cell(26.8)]), sst_b=_grid([_cell(29.7)]), chl_a=_grid([_cell(0.07)]), chl_b=_grid([_cell(10.5)])):
        default = oa.point_readings(13.33, 74.74)
        decided = oa.point_readings(13.33, 74.74, {"sst": "copernicus_cmems", "chlorophyll": "copernicus_cmems"})
    assert default["sea_surface_temperature"]["headline"]["source"] == "INSAT-3DR SST"
    assert decided["sea_surface_temperature"]["headline"]["source"] == "CMEMS SST"
    assert decided["sea_surface_temperature"]["headline"]["source_id"] == "copernicus_cmems"
    assert [r["source"] for r in decided["sea_surface_temperature"]["cross_checks"]] == ["INSAT-3DR SST"]
    assert decided["chlorophyll_a"]["headline"]["source"] == "CMEMS ocean-colour chlorophyll"


def test_a_decided_source_with_no_reading_leaves_the_default_headline_not_nothing():
    with _tables(sst_a=_grid([_cell(26.8)])):
        out = oa.point_readings(13.33, 74.74, {"sst": "copernicus_cmems"})
    assert out["sea_surface_temperature"]["headline"]["source"] == "INSAT-3DR SST"   # CMEMS had no cell; INSAT is still a reading


def test_every_reading_names_its_catalog_source():
    with _tables(sst_a=_grid([_cell(26.8)]), chl_a=_grid([_cell(0.07)])):
        out = oa.point_readings(13.33, 74.74)
    assert out["sea_surface_temperature"]["headline"]["source_id"] == "mosdac_open_sst"
    assert out["chlorophyll_a"]["headline"]["source_id"] == "mosdac_open_chl"


# --- the report ---------------------------------------------------------------------------------------------------------------------------------

def test_the_report_entry_semantics():
    cascade = {"chosen": "mosdac_open_sst", "considered": ["mosdac_open_sst", "copernicus_cmems"]}
    assert source_report_entry(cascade, "mosdac_open_sst") == {"decided": "mosdac_open_sst", "used": "mosdac_open_sst", "obeyed": True}
    assert source_report_entry(cascade, "copernicus_cmems")["obeyed"] is True        # a later declared rung
    assert source_report_entry(cascade, "noaa_coastwatch")["obeyed"] is False        # something outside the cascade
    assert source_report_entry({"chosen": "copernicus_cmems", "considered": ["copernicus_cmems", "mosdac_open_sst"]}, "mosdac_open_sst")["obeyed"] is True
    assert source_report_entry({"chosen": "copernicus_cmems", "considered": ["mosdac_open_sst", "copernicus_cmems"]}, "mosdac_open_sst")["obeyed"] is False
    assert source_report_entry(None, "x") == {"decided": None, "used": "x", "obeyed": None}


def _state(query, decisions, rows=("CONDITIONS",)):
    return {"query_id": "q", "raw_user_query": query, "normalized_english_query": query, "matched_intent_rows": list(rows),
            "user_location": {"lat": 13.33, "lon": 74.74, "place_name": "udupi", "place_source": "gazetteer"},
            "discovery_sources": {"by_data_type": decisions}}


def _dec(chosen, considered=None):
    return {"data_type": "x", "chosen": chosen, "chosen_dataset": "x", "narrative": "n", "considered": considered or [chosen], "fallback_chain": [], "rejected": []}


def test_ocean_reports_decided_used_obeyed_for_sst_chlorophyll_pfz_and_tide():
    decisions = {"sst": _dec("copernicus_cmems", ["copernicus_cmems", "mosdac_open_sst"]), "chlorophyll": _dec("mosdac_open_chl"),
                 "pfz": _dec("incois_pfz"), "tide": _dec("soi_tide_tables")}
    with _tables(sst_a=_grid([_cell(26.8)]), sst_b=_grid([_cell(29.7)]), chl_a=_grid([_cell(0.07)]), chl_b=_grid([_cell(1.0)])):
        out = oa.run(_state("sst and chlorophyll at udupi", decisions)).outputs  # type: ignore[arg-type]
    report = out["source_report"]
    assert report["sst"] == {"decided": "copernicus_cmems", "used": "copernicus_cmems", "obeyed": True}
    assert report["chlorophyll"] == {"decided": "mosdac_open_chl", "used": "mosdac_open_chl", "obeyed": True}
    assert report["pfz"]["decided"] == "incois_pfz" and report["pfz"]["used"] in ("incois_pfz", None)
    assert report["tide"]["decided"] == "soi_tide_tables"
    assert out["sea_colour_readings_at_the_place"]["sea_surface_temperature"]["headline"]["source"] == "CMEMS SST"


def test_the_report_has_no_colour_entries_for_a_question_that_did_not_ask():
    out = oa.run(_state("is it safe near udupi", {}, rows=("SAFETY_CHECK",))).outputs  # type: ignore[arg-type]
    assert set(out["source_report"]) == {"tide", "pfz"} and "sea_colour_readings_at_the_place" not in out


def test_with_no_decisions_everything_is_unknown_not_obeyed():
    with _tables(sst_a=_grid([_cell(26.8)]), chl_a=_grid([_cell(0.07)])):
        report = oa.run(_state("sst and chlorophyll at udupi", {})).outputs["source_report"]  # type: ignore[arg-type]
    assert all(v["obeyed"] is None for v in report.values())


# --- Agent 3 settles SST and chlorophyll whenever the question asks ---------------------------------------------------------------------

@pytest.mark.parametrize("query,rows,expected", [
    ("udupi sst and chlorophyll please", ["CONDITIONS"], True),
    ("what is the water temperature", ["CONDITIONS"], True),
    ("is it safe near udupi", ["SAFETY_CHECK"], False),
])
def test_agent_3_settles_both_colour_types_only_when_asked(query, rows, expected):
    state = {"query_id": "q", "raw_user_query": query, "normalized_english_query": query, "matched_intent_rows": rows,
             "execution_plan": [], "user_location": {"lat": 13.33, "lon": 74.74}}
    with _tables(sst_a=_grid([_cell(26.8)]), chl_a=_grid([_cell(0.07)])):
        result = marine_data_discovery_run(state)  # type: ignore[arg-type]
    types = {s["data_type"] for s in result.outputs["source_selections"]}
    assert ({"sst", "chlorophyll"} <= types) is expected
    if expected:
        by = {s["data_type"]: s for s in result.outputs["source_selections"]}
        assert by["sst"]["chosen"] == "mosdac_open_sst" and by["chlorophyll"]["chosen"] == "mosdac_open_chl"
