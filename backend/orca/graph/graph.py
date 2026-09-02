"""LangGraph skeleton (plan §Phase-1, S1 Day 4):

    distress_check --[distress_flag]--> END (response built in this node)
                   --[else]-----------> planning
                                            |
                              +-------------+-------------+
                              v                            v
                      weather_intelligence          geospatial_stub
                              |                            |
                              +-------------+-------------+
                                            v
                                     risk_assessment
                                            |
                                            v
                                     reporting_stub --> END

Fixed shape for Phase 1 — Planning's execution_plan is computed and recorded
in state/trace (visible, narratable) but does not yet dynamically drive graph
routing; that is a Phase 2 sophistication, not specified for this slice
(plan §Phase-1 Day 4: "stub nodes: Planning -> [WIA || GRA] -> RAA ->
Reporting", a fixed pipeline). geospatial_stub and reporting_stub stand in
for Agents 6 and 9 (S5, S6 — not built yet), per the plan's own fixture
strategy: "S1 wires the graph against fixtures before real agents exist."
"""
from __future__ import annotations

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from orca.agents import distress, planning, risk_assessment, weather_intelligence
from orca.contracts import Confidence
from orca.state import ORCAState
from orca.trace import make_stub_entry, run_traced_node

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def _load_geospatial_stub() -> dict:
    with open(FIXTURES_DIR / "geospatial__stub_thoothukudi.json", encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def distress_check_node(state: ORCAState) -> dict:
    """Runs Agent 12 exactly ONCE. Previously this node only extracted the
    boolean flag, and a separate distress_response_node re-ran distress.run()
    from scratch to get the MRCC/handoff payload — on the one path where
    latency matters most (SOS, <2s), that meant duplicating detection,
    MRCC lookup and handoff formatting for no reason, and it left two
    "distress" entries in the trace for what is genuinely one agent
    invocation. Everything downstream needs is computed here, once."""
    result, entry = run_traced_node("distress", distress.run, state)
    is_distress = result.outputs["detection"]["is_distress"]
    update = {
        "distress_flag": is_distress,
        "audit_trace_log": [entry],
        "completed_nodes": ["distress_check"],
    }
    if is_distress:
        # Bypasses Reporting entirely (Architecture §3.2 step 1) — surfaces
        # MRCC contact directly, never synthesized/persona-rendered.
        mrcc = result.outputs["mrcc_contact"]
        update["final_english_response"] = (
            f"DISTRESS DETECTED. Coast Guard MRCC: {mrcc['primary']['phone']} "
            f"(nationwide: {mrcc['nationwide_fallback']['phone']}), VHF channel {mrcc['primary']['vhf_channel']}. "
            "This handoff is SIMULATED — no live DAT-SG/telephony integration exists yet."
        )
        update["confidence_tier"] = "HIGH"
    return update


def _route_after_distress(state: ORCAState) -> str:
    # END is untyped (a plain interned str, not a Literal) in langgraph's own
    # stubs, so this can't be a Literal return type without mypy complaining
    # about the exact thing that makes END work at all.
    return END if state.get("distress_flag") else "planning"


def planning_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("planning", planning.run, state)
    return {
        "matched_intent_rows": result.outputs["matched_intent_rows"],
        "execution_plan": result.outputs["execution_plan"],
        "audit_trace_log": [entry],
        "completed_nodes": ["planning"],
    }


def weather_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("weather_intelligence", weather_intelligence.run, state)
    return {
        "weather_data": result.outputs,
        "audit_trace_log": [entry],
        "completed_nodes": ["weather_intelligence"],
    }


def geospatial_stub_node(state: ORCAState) -> dict:
    """STUB — Agent 6 is S5's Phase 1 work, not yet built. See
    tests/fixtures/geospatial__stub_thoothukudi.json for why the number in
    here must never be treated as a real measurement."""
    stub_data = _load_geospatial_stub()
    entry = make_stub_entry("geospatial", state.get("query_id", ""), "STUB — Agent 6 (S5) not yet built")
    return {
        "geospatial_data": {
            **stub_data,
            "confidence": Confidence(score="LOW_DATA", rationale="STUB fixture — Agent 6 (S5) not yet built"),
        },
        "audit_trace_log": [entry],
        "completed_nodes": ["geospatial_stub"],
    }


def risk_assessment_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("risk_assessment", risk_assessment.run, state)
    return {
        "risk_assessment": result.outputs,
        "confidence_tier": result.confidence.score,
        "audit_trace_log": [entry],
        "completed_nodes": ["risk_assessment"],
    }


def reporting_stub_node(state: ORCAState) -> dict:
    """STUB — Agent 9 is S6's Phase 1 work. Plain English sentence from the
    risk verdict; no persona rendering, no citation formatting, no
    translation. Real Reporting replaces this node wholesale, not this
    function's internals — swap the node, not patch it."""
    verdict = state.get("risk_assessment") or {}
    text = f"{verdict.get('go_no_go', 'UNKNOWN')}: {verdict.get('reason', 'no verdict computed')}"
    entry = make_stub_entry("reporting", state.get("query_id", ""), "STUB — Agent 9 (S6) not yet built")
    return {
        "final_english_response": text,
        "confidence_tier": state.get("confidence_tier", "LOW_DATA"),
        "audit_trace_log": [entry],
        "completed_nodes": ["reporting_stub"],
    }


def build_graph():
    g = StateGraph(ORCAState)
    g.add_node("distress_check", distress_check_node)
    g.add_node("planning", planning_node)
    g.add_node("weather_intelligence", weather_node)
    g.add_node("geospatial_stub", geospatial_stub_node)
    g.add_node("risk_assessment", risk_assessment_node)
    g.add_node("reporting_stub", reporting_stub_node)

    g.add_edge(START, "distress_check")
    g.add_conditional_edges("distress_check", _route_after_distress, {END: END, "planning": "planning"})
    g.add_edge("planning", "weather_intelligence")
    g.add_edge("planning", "geospatial_stub")
    g.add_edge(["weather_intelligence", "geospatial_stub"], "risk_assessment")
    g.add_edge("risk_assessment", "reporting_stub")
    g.add_edge("reporting_stub", END)
    return g.compile()
