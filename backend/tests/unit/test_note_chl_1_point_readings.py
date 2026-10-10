"""NOTE-CHL-1 / NOTE-CHL-2 (2026-10-09/10): SST and chlorophyll AT a place, as ONE headline reading per quantity.

NOTE-CHL-1: "SST and chlorophyll at kundapura" was answered "not tracked" although the grids exist; the agent never returned
the value at the place. NOTE-CHL-2: two sources of one quantity are different products with a consistent offset (measured over
~45 ports: INSAT reads 0.8 C cooler than CMEMS offshore and 1.6 C at the coast; the 25 km EOS-06 chlorophyll is 8x to 28x lower
than the 4 km CMEMS), not conflicting evidence. So the answer gives the headline (the national mission product) with its source
and date, the others stay cross-checks, and a gap is reported ONLY when it is outside the normal offset.
"""
from __future__ import annotations

import inspect
from unittest import mock

import pytest

from orca.agents import ocean_analytics as oa
from orca.agents.critic import build_facts_block
from orca.agents.reporting import (
    _colour_lines,
    facts_paragraph,
    synthesize_narrative,
    with_colour_readings,
)
from orca.contracts import AgentResult, Confidence, SourceProvenance


def _grid(cells, freshness_min=14000, when="2026-09-30T00:00:00Z"):
    return {"frame": cells, "provenance": {"dataset": "X", "acquisition_timestamp": when, "freshness_minutes": freshness_min}}


def _cell(value, lat=13.64, lon=74.63):
    return {"lat": lat, "lon": lon, "value": value}


def _patch(sst_a=None, sst_b=None, chl_a=None, chl_b=None, osf=None):
    sst = (("INSAT-3DR SST", lambda b: sst_a), ("CMEMS SST", lambda b: sst_b))
    chl = (("EOS-06 OCM-3 chlorophyll", lambda b: chl_a), ("CMEMS ocean-colour chlorophyll", lambda b: chl_b))
    return mock.patch.multiple(oa, _SST_SOURCES=sst, _CHL_SOURCES=chl, nearest_osf_point_forecast=lambda lat, lon: osf or {})


def _readings(sst_a=26.81, sst_b=29.71, chl_a=0.0746, chl_b=10.58, osf=None):
    with _patch(_grid([_cell(sst_a)]) if sst_a is not None else None, _grid([_cell(sst_b)]) if sst_b is not None else None,
                _grid([_cell(chl_a)]) if chl_a is not None else None, _grid([_cell(chl_b)]) if chl_b is not None else None, osf):
        return oa.point_readings(13.63, 74.62)


def _results(readings):
    def _r(name, outputs):
        return AgentResult(agent_name=name, query_id="q", reasoning_depth="SHALLOW", inputs_consumed={}, outputs=outputs,
                           source_provenance=SourceProvenance(dataset="d", acquisition_timestamp="", freshness_minutes=0),
                           confidence=Confidence(score="HIGH", rationale="t"))
    return [_r("ocean_analytics", {"sea_colour_readings_at_the_place": readings})]


# --- one headline per quantity ----------------------------------------------------------------------------------------------

def test_the_headline_is_the_national_mission_product_with_source_date_and_cell():
    out = _readings()
    head = out["sea_surface_temperature"]["headline"]
    assert head["source"] == "INSAT-3DR SST" and head["value"] == 26.81 and head["unit"] == "degC"
    assert head["observed"] == "2026-09-30" and head["age_days"] == pytest.approx(9.7, abs=0.1) and head["cell_distance_km"] < 3
    assert out["chlorophyll_a"]["headline"]["source"] == "EOS-06 OCM-3 chlorophyll"


def test_the_other_sources_are_cross_checks_not_competing_answers():
    out = _readings(osf={"grid_cell": {"distance_km": 19.4, "sea_surface_temp_c": 28.72}})
    assert [r["source"] for r in out["sea_surface_temperature"]["cross_checks"]] == ["CMEMS SST", "INCOIS Ocean State Forecast (0.5 deg model grid)"]
    assert [r["source"] for r in out["chlorophyll_a"]["cross_checks"]] == ["CMEMS ocean-colour chlorophyll"]


def test_when_the_preferred_source_has_no_cell_the_next_one_is_the_headline():
    out = _readings(sst_a=None, chl_a=None)
    assert out["sea_surface_temperature"]["headline"]["source"] == "CMEMS SST"
    assert out["chlorophyll_a"]["headline"]["source"] == "CMEMS ocean-colour chlorophyll"


# --- no "disagree" unless the gap is outside the normal offset ---------------------------------------------------------------

@pytest.mark.parametrize("sst_a,sst_b", [(26.81, 29.71), (26.5, 29.38), (28.0, 28.6), (29.0, 27.5)])
def test_the_normal_sst_offset_is_not_reported_as_a_disagreement(sst_a, sst_b):
    assert _readings(sst_a=sst_a, sst_b=sst_b)["sea_surface_temperature"]["unusual_gap"] is None


@pytest.mark.parametrize("chl_a,chl_b", [(0.0746, 10.58), (0.08, 1.97), (0.11, 1.19), (0.3, 0.5)])
def test_the_normal_chlorophyll_offset_is_not_reported_as_a_disagreement(chl_a, chl_b):
    assert _readings(chl_a=chl_a, chl_b=chl_b)["chlorophyll_a"]["unusual_gap"] is None


def test_a_gap_beyond_the_normal_offset_is_reported():
    out = _readings(sst_a=24.0, sst_b=29.7)
    assert out["sea_surface_temperature"]["unusual_gap"] and "larger than these products normally have" in out["sea_surface_temperature"]["unusual_gap"]
    assert _readings(chl_a=0.5, chl_b=0.05)["chlorophyll_a"]["unusual_gap"]       # CMEMS below a third of EOS: the unusual direction
    assert _readings(chl_a=0.02, chl_b=9.0)["chlorophyll_a"]["unusual_gap"]       # more than 200x


def test_the_chlorophyll_level_is_a_class_of_the_headline_value():
    assert _readings(chl_a=0.08)["chlorophyll_a"]["level"] == "low"
    assert _readings(chl_a=0.5)["chlorophyll_a"]["level"] == "moderate"
    assert _readings(chl_a=2.4)["chlorophyll_a"]["level"] == "high"


def test_near_the_coast_the_chlorophyll_is_marked_indicative_and_offshore_it_is_not():
    with mock.patch.object(oa, "_near_a_port", return_value=True):
        assert _readings()["chlorophyll_a"]["near_shore_indicative"] is True
    with mock.patch.object(oa, "_near_a_port", return_value=False):
        assert _readings()["chlorophyll_a"]["near_shore_indicative"] is False


def test_a_cell_too_far_from_the_place_is_not_a_reading_and_nothing_is_invented():
    with _patch(_grid([_cell(28.0, lat=16.0, lon=74.0)])):
        out = oa.point_readings(13.63, 74.62)
    assert out["sea_surface_temperature"]["headline"] is None and out["available"] is False


def test_a_loader_that_fails_is_skipped_not_fatal():
    def boom(b):
        raise OSError("unreadable")

    with mock.patch.multiple(oa, _SST_SOURCES=(("A", boom), ("B", lambda b: None)), _CHL_SOURCES=(("C", lambda b: {"frame": []}),),
                             nearest_osf_point_forecast=lambda lat, lon: {}):
        out = oa.point_readings(13.63, 74.62)
    assert out["available"] is False and out["chlorophyll_a"]["headline"] is None


# --- the question decides whether the readings are fetched -------------------------------------------------------------------

@pytest.mark.parametrize("query,rows,expected", [
    ("give me the sst and chlorophyll details of kundapur", [], True),
    ("what is the water temperature near kochi", [], True),
    ("is it safe near kochi", [], False),
    ("is it safe near kochi", ["DIAGNOSTIC"], True),
    ("wave height near goa", ["CONDITIONS"], False),
])
def test_readings_are_fetched_only_for_sea_colour_questions(query, rows, expected):
    assert oa._asks_sea_colour({"matched_intent_rows": rows}, query) is expected


# --- what the answer says ----------------------------------------------------------------------------------------------------

def test_the_answer_gives_one_reading_per_quantity_and_never_says_the_sources_disagree():
    with mock.patch.object(oa, "_near_a_port", return_value=True):
        readings = _readings()
    text = " ".join(_colour_lines(readings, "Udupi"))
    assert "26.81 °C (INSAT-3DR SST, 2026-09-30, 9.7 days old)" in text and "0.07 mg/m3 (EOS-06" in text
    assert "is low for these waters" in text and "only indicative" in text
    assert "29.71" not in text and "10.58" not in text                      # the cross-checks are not offered as competing answers
    for word in ("disagree", "conflict", "contradict"):
        assert word not in text.lower()


def test_an_unusual_gap_is_said():
    text = " ".join(_colour_lines(_readings(sst_a=24.0, sst_b=29.7), "Udupi"))
    assert "larger than these products normally have" in text


def test_no_headline_is_said_plainly_not_called_not_tracked():
    out = _readings(sst_a=None, sst_b=None, chl_a=None, chl_b=None)
    text = facts_paragraph({"go_no_go": "GO", "reason": "ok"}, _results(out), {"place_name": "kundapur", "lat": 13.63, "lon": 74.62})
    assert "No sea surface temperature reading is held for Kundapur" in text and "No chlorophyll-a reading is held for Kundapur" in text
    assert "not tracked" not in text


def test_the_narrative_prompt_forbids_calling_a_normal_offset_a_disagreement():
    seen = {}

    class _C:
        engine = "fake"

        def complete(self, messages, **kw):
            seen["prompt"] = messages[0]["content"]
            return "ok"

    with mock.patch("orca.llm.tiers.llm", lambda tier: _C()):
        synthesize_narrative("sst of kundapur", {"go_no_go": "GO", "reason": "ok"}, _results(_readings()), user_location={"place_name": "kundapur"})
    prompt = " ".join(seen["prompt"].split())
    assert "sea_colour_readings_at_the_place" in prompt and "HEADLINE reading" in prompt
    assert "do not say the sources disagree, conflict or contradict" in prompt and "Do NOT quote a cross-check's value or source at all unless unusual_gap" in prompt and 'Never use the words "headline" or "cross-check"' in prompt


# --- completion: the figures come from the data -----------------------------------------------------------------------------

def test_a_narrative_that_omits_the_headline_is_completed_from_the_data():
    out = with_colour_readings("Conditions are calm.", _results(_readings()), {"place_name": "kundapur"})
    assert "26.81 °C (INSAT-3DR SST" in out and "0.07 mg/m3 (EOS-06" in out


def test_a_narrative_that_already_quotes_the_headlines_is_left_alone():
    said = "SST 26.81 C; chlorophyll 0.07 mg/m3, low."
    assert with_colour_readings(said, _results(_readings()), {"place_name": "kundapur"}) == said


def test_nothing_is_added_when_the_question_did_not_ask_for_the_readings():
    plain = [AgentResult(agent_name="ocean_analytics", query_id="q", reasoning_depth="SHALLOW", inputs_consumed={}, outputs={"tide": {}},
                         source_provenance=SourceProvenance(dataset="d", acquisition_timestamp="", freshness_minutes=0),
                         confidence=Confidence(score="HIGH", rationale="t"))]
    assert with_colour_readings("Waves are 0.5 m.", plain, {"place_name": "kundapur"}) == "Waves are 0.5 m."


# --- the critic must be able to confirm what the answer quotes ---------------------------------------------------------------

def test_the_critic_is_given_the_headline_the_cross_checks_and_the_level_as_facts():
    block = build_facts_block({"ocean_data": {"sea_colour_readings_at_the_place": _readings()}})  # type: ignore[typeddict-item]
    assert "sea_surface_temperature_readings: headline 26.81 degC (INSAT-3DR SST, 2026-09-30" in block
    assert "cross-checks (a normal offset, not a contradiction): 29.71 degC (CMEMS SST" in block
    assert "level low" in block and "UNUSUAL GAP" not in block


def test_the_critic_lists_nothing_when_no_reading_is_held():
    block = build_facts_block({"ocean_data": {}})  # type: ignore[typeddict-item]
    assert "sea_surface_temperature_readings" not in block and "chlorophyll_a_readings" not in block


def test_the_reporting_node_passes_the_readings_on_to_the_narrative():
    # found by a live run: an allow-list in reporting_node dropped the key, so the model never saw the readings
    from orca.graph import graph

    assert '"sea_colour_readings_at_the_place"' in inspect.getsource(graph)


# --- a follow-up inherits the subject of the turns before it ("and for kundapura now?") ---------------------------------------

_HISTORY = [{"english_query": "udupi sst plus chlorophyll values wanted", "query": "udupi sst plus chlorophyll values wanted"}]


def test_a_follow_up_after_a_sea_colour_question_is_still_that_question():
    state = {"matched_intent_rows": ["CONDITIONS"], "understood_is_followup": True, "session_history": _HISTORY}
    assert oa._asks_sea_colour(state, "ok and for kundapura now, in kannada") is True


def test_a_follow_up_after_an_ordinary_question_is_not():
    state = {"matched_intent_rows": ["CONDITIONS"], "understood_is_followup": True,
             "session_history": [{"english_query": "wave height near udupi"}]}
    assert oa._asks_sea_colour(state, "and for kundapura now") is False


def test_a_new_question_does_not_inherit_even_with_a_sea_colour_history():
    state = {"matched_intent_rows": ["SAFETY_CHECK"], "understood_is_followup": False, "session_history": _HISTORY}
    assert oa._asks_sea_colour(state, "is it safe near kochi") is False


def test_only_the_last_two_turns_are_inherited():
    old = [{"english_query": "sst near udupi"}, {"english_query": "wave near goa"}, {"english_query": "wind near goa"}]
    assert oa._asks_sea_colour({"understood_is_followup": True, "session_history": old}, "and tomorrow") is False


def test_only_the_missing_quantity_is_added_not_a_repeat_of_the_one_already_said():
    said = "The sea surface temperature at Kochi is 26.81 °C (INSAT-3DR, 30 Sep, about 10 days old)."
    out = with_colour_readings(said, _results(_readings()), {"place_name": "kochi"})
    assert out.startswith(said) and out.count("26.81") == 1 and "0.07 mg/m3 (EOS-06" in out
