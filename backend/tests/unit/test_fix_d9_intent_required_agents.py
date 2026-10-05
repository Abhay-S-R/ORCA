"""D-9 — the execution plan keeps every agent the matched routing rows name.

`ocean_analytics` is the only agent that finds a PFZ. PC3.3 built the plan from
the model's own agent list, so when the model left it out a PFZ question was
answered "no PFZ data" with the data on disk. The model may add agents; it may
not remove what the matched intent requires.
"""
from __future__ import annotations

import pytest

from orca.agents.planning import ROUTING_TABLE, enforce_planning_invariants

CORE = {"weather_intelligence", "geospatial", "risk_assessment", "reporting", "critic", "marine_data_discovery"}


@pytest.mark.parametrize("model_plan", [[], ["visualization"], ["weather_intelligence"], ["fake_agent"]])
def test_a_pfz_question_always_runs_ocean_analytics(model_plan):
    plan = enforce_planning_invariants(model_plan, True, ["PFZ_NEAREST"])
    assert "ocean_analytics" in plan
    assert "visualization" in plan  # the row also names it: the PFZ map


def test_every_routing_row_keeps_its_own_agents_whatever_the_model_says():
    for row in ROUTING_TABLE:
        plan = enforce_planning_invariants([], True, [row.name])
        for agent in row.agents:
            if agent != "marine_data_discovery":
                assert agent in plan, (row.name, agent, plan)


def test_the_model_can_still_add_agents_a_row_does_not_name():
    # HAZARD_ALERTS does not name ocean_analytics; asking for it is honoured.
    assert "ocean_analytics" not in enforce_planning_invariants([], True, ["HAZARD_ALERTS"])
    assert "ocean_analytics" in enforce_planning_invariants(["ocean_analytics"], True, ["HAZARD_ALERTS"])


def test_unknown_rows_and_no_rows_change_nothing():
    assert enforce_planning_invariants([], True, ["NOT_A_ROW"]) == enforce_planning_invariants([], True)
    assert enforce_planning_invariants([], True, None) == enforce_planning_invariants([], True, [])


def test_multiple_rows_union_and_core_still_always_run():
    plan = enforce_planning_invariants([], True, ["PFZ_NEAREST", "HAZARD_ALERTS"])
    assert CORE <= set(plan) and "ocean_analytics" in plan


def test_order_is_still_the_codes_not_the_models():
    plan = enforce_planning_invariants(["visualization", "ocean_analytics"], True, ["PFZ_NEAREST"])
    assert plan.index("marine_data_discovery") == 0
    assert plan.index("ocean_analytics") < plan.index("risk_assessment") < plan.index("visualization") < plan.index("reporting")


def test_a_non_sea_question_is_untouched_by_intent_rows():
    assert enforce_planning_invariants([], False, ["PFZ_NEAREST"]) == enforce_planning_invariants([], False)
