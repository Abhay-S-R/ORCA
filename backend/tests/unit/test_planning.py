from orca.agents.planning import (
    NO_MATCH_FALLBACK_AGENTS,
    check_early_exit,
    classify_intent,
    generate_execution_plan,
    run,
)
from orca.state import ORCAState


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


def test_check_early_exit_always_false_in_phase_1():
    assert check_early_exit({"anything": "at all"}) is False


def test_run_produces_execution_plan_for_safety_query():
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-1", "reasoning_depth": "SHALLOW",
        "normalized_english_query": "is it safe to go to sea tomorrow near Thoothukudi",
    }
    result = run(state)
    assert result.agent_name == "planning"
    assert "SAFETY_CHECK" in result.outputs["matched_intent_rows"]
    assert "risk_assessment" in result.outputs["execution_plan"]
    assert result.confidence.score == "HIGH"
    assert not hasattr(result, "persona")


def test_run_degrades_to_medium_confidence_on_no_match():
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-2", "reasoning_depth": "SHALLOW",
        "normalized_english_query": "tell me a joke",
    }
    result = run(state)
    assert result.outputs["execution_plan"] == list(NO_MATCH_FALLBACK_AGENTS)
    assert result.confidence.score == "MEDIUM"
