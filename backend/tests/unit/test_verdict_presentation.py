"""When the safety verdict leads the narrative, and when the execution plan
gates a node.

Ground Rule 2 is not at stake here: the verdict is still computed by
deterministic arithmetic on every query and still shipped in the structured
response. What is at stake is that a "GO: All Parameters Within Safe
Operational Limits" banner stapled to the top of "where are the nearest
fishing zones?" teaches people to skim the banner — so it stops meaning
anything on the day it says NO_GO.
"""
from __future__ import annotations

from orca.agents.reporting import should_lead_with_verdict
from orca.graph.graph import ocean_analytics_node

GO = {"go_no_go": "GO", "reason": "All Parameters Within Safe Operational Limits"}
CAUTION = {"go_no_go": "CAUTION", "reason": "Rough Sea State / Boundary Proximity"}
NO_GO = {"go_no_go": "NO_GO", "reason": "Severe Weather / Cyclone Threshold Exceeded"}


def test_a_go_leads_only_when_safety_was_actually_asked_about():
    assert should_lead_with_verdict(GO, ["SAFETY_CHECK"]) is True
    assert should_lead_with_verdict(GO, ["HAZARD_ALERTS"]) is True
    assert should_lead_with_verdict(GO, ["ZONES_TO_AVOID"]) is True
    assert should_lead_with_verdict(GO, ["PFZ_NEAREST"]) is False
    assert should_lead_with_verdict(GO, ["CONDITIONS"]) is False
    assert should_lead_with_verdict(GO, []) is False


def test_a_non_go_always_leads_whatever_was_asked():
    """Someone who asked about tides while a squall builds still has to be
    told not to sail. The demotion is one-directional by design."""
    for verdict in (CAUTION, NO_GO):
        for rows in ([], ["PFZ_NEAREST"], ["CONDITIONS"], ["SAFETY_CHECK"]):
            assert should_lead_with_verdict(verdict, rows) is True, (verdict, rows)


def test_synthesize_never_prepends_a_header_it_was_told_to_omit(monkeypatch):
    import orca.agents.reporting as reporting
    import orca.llm.tiers as tiers

    class _Client:
        def complete(self, messages):
            return "The nearest fishing zone is 12 nm west-southwest."

    monkeypatch.setattr(tiers, "llm", lambda tier: _Client())
    out = reporting.synthesize_narrative(
        "where are the nearest fishing zones", GO, [], lead_with_verdict=False,
    )
    assert not out.startswith("GO:")

    # ...but the floor is re-derived inside, so a caller cannot demote a NO_GO.
    out = reporting.synthesize_narrative(
        "where are the nearest fishing zones", NO_GO, [], lead_with_verdict=False,
    )
    assert out.startswith("NO_GO:")


def test_execution_plan_gates_ocean_analytics():
    """Agent 2's plan was computed and then ignored by every node. This is the
    one branch it can gate: risk_assessment never reads ocean_data, so its
    absence costs content and nothing else."""
    skipped = ocean_analytics_node({"execution_plan": ["geospatial", "risk_assessment"]})  # type: ignore[arg-type]
    assert skipped == {}


def test_an_empty_plan_does_not_gate_anything_off():
    """A missing plan means Planning did not run or failed — that must not
    silently disable a branch."""
    state = {"execution_plan": [], "query_id": "t", "reasoning_depth": "SHALLOW",
             "user_location": {"lat": 8.80, "lon": 78.30}}
    assert ocean_analytics_node(state) != {}  # type: ignore[arg-type]
