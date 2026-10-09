"""PLAN-FORCE-1 (2026-10-10): a question that asks for tide, fishing zones, SST or chlorophyll cannot lose ocean_analytics.

Approved with the PC3.1 sign-off. Seven routing rows do not list ocean_analytics (HAZARD_ALERTS, ZONES_TO_AVOID, ROUTE, ...),
so an SST question the planner labelled with one of them, and where the model left the agent out, skipped it and the answer
said "no reading is held". The rule only adds an agent; the verdict inputs and the other invariants are unchanged.
"""
from __future__ import annotations

import pytest

from orca.agents.planning import asks_for_ocean_data, enforce_planning_invariants

CORE = {"weather_intelligence", "geospatial", "risk_assessment", "reporting", "critic", "marine_data_discovery"}


@pytest.mark.parametrize("query", [
    "udupi sst plus chlorophyll values wanted", "what is the tide at kochi", "high tide tomorrow", "nearest PFZ near malpe",
    "where are the fishing zones", "potential fishing zone near goa", "sea surface temperature off karwar", "plankton bloom near kochi",
    "Chlorophyll at Kundapura", "water temperature near mangalore",
])
def test_questions_about_ocean_data_force_the_agent(query):
    assert asks_for_ocean_data(query) is True


@pytest.mark.parametrize("query", [
    "is it safe near kochi", "wave height near goa", "wind speed today", "show me the route to pamban", "is the boundary close",
    "go outside the harbour", "outside the breakwater is it safe", "hello",
])
def test_other_questions_do_not(query):
    assert asks_for_ocean_data(query) is False   # "outside" must not match "tide"


def test_a_follow_up_inherits_the_subject_of_the_last_two_turns_only():
    history = [{"english_query": "udupi sst plus chlorophyll values wanted"}]
    assert asks_for_ocean_data("ok and for kundapura now", history, is_followup=True) is True
    assert asks_for_ocean_data("ok and for kundapura now", history, is_followup=False) is False
    old = [{"english_query": "tide at kochi"}, {"english_query": "wave near goa"}, {"english_query": "wind near goa"}]
    assert asks_for_ocean_data("and tomorrow", old, is_followup=True) is False


@pytest.mark.parametrize("rows", [["HAZARD_ALERTS"], ["ZONES_TO_AVOID"], ["ROUTE"], []])
def test_the_agent_runs_even_when_the_model_and_the_routing_row_leave_it_out(rows):
    plan = enforce_planning_invariants([], True, rows, force_ocean=True)
    assert "ocean_analytics" in plan and CORE <= set(plan)


def test_without_the_flag_nothing_changes():
    assert "ocean_analytics" not in enforce_planning_invariants([], True, ["HAZARD_ALERTS"])
    assert "ocean_analytics" in enforce_planning_invariants(["ocean_analytics"], True, ["HAZARD_ALERTS"])


def test_the_forced_plan_keeps_the_fixed_order():
    plan = enforce_planning_invariants([], True, ["ROUTE"], force_ocean=True)
    assert plan.index("marine_data_discovery") == 0 and plan.index("ocean_analytics") < plan.index("risk_assessment") < plan.index("reporting") < plan.index("critic")


def test_a_non_sea_question_is_never_forced():
    assert "ocean_analytics" not in enforce_planning_invariants([], False, [], force_ocean=True)


def test_planning_wires_the_flag_for_sea_questions_only():
    import inspect

    from orca.agents import planning

    assert "force_ocean=is_sea_question and asks_for_ocean_data(" in inspect.getsource(planning.run)
