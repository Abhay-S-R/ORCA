import pytest

from orca.agents import planning
from orca.agents.planning import (
    NO_MATCH_FALLBACK_AGENTS,
    classify_intent,
    generate_execution_plan,
    run,
)
from orca.state import ORCAState


@pytest.fixture(autouse=True)
def _model_off(monkeypatch):
    """`planning.run` reads the message with a language model first. These tests exercise the
    offline path, so the model is switched off for the duration of each test only. (Several files
    used to write ORCA_LLM_ENABLED into os.environ for the whole process, which made other tests
    depend on collection order and made these ones call a real model on a machine with keys.)"""
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")


def test_safety_check_matches_and_includes_risk_assessment():
    matches = classify_intent("is it safe to go to sea tomorrow morning")
    assert ("SAFETY_CHECK", 1.0) in matches


def test_no_match_returns_empty_list():
    assert classify_intent("what is the capital of Tamil Nadu") == []


def test_multi_match_union_not_just_first_row():
    # "safe" + "zones to avoid" should activate the union of both rows
    matches = classify_intent("is it safe, and what zones to avoid near the boundary")
    names = [n for n, _ in matches]
    assert "SAFETY_CHECK" in names and "ZONES_TO_AVOID" in names

    plan = generate_execution_plan(names, "STANDARD")
    assert "risk_assessment" in plan and "geospatial" in plan and "weather_intelligence" in plan


def test_execution_plan_has_no_duplicate_agents_across_matched_rows():
    # SAFETY_CHECK and HAZARD_ALERTS both include weather_intelligence
    plan = generate_execution_plan(["SAFETY_CHECK", "HAZARD_ALERTS"], "SHALLOW")
    assert plan.count("weather_intelligence") == 1


def test_no_match_fallback_is_never_empty():
    plan = generate_execution_plan([], "SHALLOW")
    assert plan == list(NO_MATCH_FALLBACK_AGENTS)
    assert len(plan) > 0


def test_unknown_row_name_is_ignored_not_a_crash():
    plan = generate_execution_plan(["SOME_ROW_THAT_DOES_NOT_EXIST"], "SHALLOW")
    assert plan == list(NO_MATCH_FALLBACK_AGENTS)  # falls through to fallback, never empty


def test_run_produces_execution_plan_for_safety_query():
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-1", "reasoning_depth": "SHALLOW",
        "raw_user_query": "is it safe to go to sea tomorrow near Thoothukudi",
        "normalized_english_query": "is it safe to go to sea tomorrow near Thoothukudi",
        "user_location": {"lat": 8.8, "lon": 78.1},
        "session_history": [],
        "distress_flag": False,
    }
    result = run(state)
    assert result.agent_name == "planning"
    assert "SAFETY_CHECK" in result.outputs["matched_intent_rows"]
    assert "risk_assessment" in result.outputs["execution_plan"]
    assert result.confidence.score == "HIGH"
    assert not hasattr(result, "persona")


def test_run_degrades_to_medium_confidence_on_no_match(monkeypatch):
    """An in-scope question that matches no routing row still gets the §4.2
    fallback path. Tier 3 is stubbed out because an LLM that happens to guess
    a row would make this assert nothing."""
    monkeypatch.setattr(planning, "_tier3_llm_fallback", lambda q, history=None: [])
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-2", "reasoning_depth": "SHALLOW",
        "raw_user_query": "what colour is the sea near Pamban",
        "normalized_english_query": "what colour is the sea near Pamban",
        "user_location": {"lat": 9.3, "lon": 79.1},
        "session_history": [],
        "distress_flag": False,
    }
    result = run(state)
    assert result.outputs["matched_intent_rows"] == []
    # PC3.3: execution_plan now includes required agents (weather, geospatial, risk) per D3
    assert "marine_data_discovery" in result.outputs["execution_plan"]
    assert "weather_intelligence" in result.outputs["execution_plan"]
    assert "geospatial" in result.outputs["execution_plan"]
    assert "risk_assessment" in result.outputs["execution_plan"]
    assert result.confidence.score == "MEDIUM"


def test_a_non_marine_question_is_refused_rather_than_answered_about_the_sea(monkeypatch):
    """P1.3 (`R-EDGE-1`). "tell me a joke" used to take the §4.2 no-match path
    and come back with a general-conditions answer — marine content produced
    for a question that asked for none."""
    monkeypatch.setattr(planning, "_tier3_llm_fallback", lambda q, history=None: [])
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-3", "reasoning_depth": "SHALLOW",
        "normalized_english_query": "tell me a joke",
    }
    result = run(state)
    assert result.outputs["matched_intent_rows"] == [planning.OUT_OF_SCOPE_ROW]
    assert result.outputs["execution_plan"] == []


# --- "current" the adjective vs "current" the ocean current, found 2026-09-26 --

def test_current_time_or_location_does_not_match_marine_vocab_on_current_alone():
    for q in ("do you know whats current time is", "do you know the current location", "current date please"):
        assert planning.is_out_of_scope(q.lower()) is True, q


def test_a_genuine_ocean_current_question_still_matches_marine_vocab():
    for q in ("current speed near Kochi", "ocean current near Chennai", "what is the current wave height"):
        assert planning.is_out_of_scope(q.lower()) is False, q


def test_self_context_questions_are_recognised():
    for q in ("do you know whats current time is",
              "okay fine, do you know atleast current location? i wanted to ask some questions about it",
              "where am I", "what time is it"):
        assert planning.is_self_context_question(q) is True, q
    for q in ("sea conditions near Kochi", "current speed near Kochi", "is it safe today"):
        assert planning.is_self_context_question(q) is False, q
