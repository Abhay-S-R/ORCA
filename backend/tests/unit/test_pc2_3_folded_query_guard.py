"""PC2.3 (`R-NEW-1`) — Fold query_guard into planning's validate step.

Done-when (plan §5 PC2.3):
- graph.py no longer defines query_guard.
- 'query_guard' is not in build_graph().nodes.
- planning.run() calls validate_reading itself and sets query_outcome.
- planning_node() sets query_outcome and generates guard refusal response.
- _route_after_planning routes NEEDS_PLACE / OUT_OF_RANGE to END from planning.
- The PC1.2 prompts give identical replies.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from orca.agents import planning
from orca.graph.graph import _route_after_planning, build_graph, planning_node
from orca.place_resolution import FORECAST_HORIZON_DAYS

os.environ.setdefault("ORCA_LLM_ENABLED", "0")

_NOW = datetime(2026, 10, 4, 6, 0, 0, tzinfo=timezone.utc)
_TODAY = _NOW.date()


def _iso(days_offset: int) -> str:
    return (_TODAY + timedelta(days=days_offset)).isoformat() + "T00:00:00Z"


def _base_state(**overrides) -> dict:
    state: dict = {
        "raw_user_query": "safe near kochi",
        "normalized_english_query": "safe near kochi",
        "understood_kind": "sea_safety_check",
        "understood_places": [],
        "understood_when": None,
        "user_location": None,
        "place_resolution": {},
        "query_outcome": None,
        "disclosures": [],
        "matched_intent_rows": [],
        "execution_plan": [],
        "audit_trace_log": [],
        "completed_nodes": [],
    }
    state.update(overrides)
    return state


# ── 1. Graph verification: no query_guard in graph.py or compiled graph ────────

def test_graph_has_no_query_guard_node():
    """query_guard must not be a node in the compiled graph."""
    g = build_graph()
    assert "query_guard" not in g.nodes, "query_guard node must be deleted from graph in PC2.3"


def test_graph_does_not_define_query_guard():
    """graph.py must not define query_guard_node."""
    import orca.graph.graph as graph_mod
    assert not hasattr(graph_mod, "query_guard_node"), "query_guard_node function must be removed"


def test_graph_edges_language_ingress_to_planning():
    """Graph must route directly from language_ingress to planning."""
    g = build_graph()
    edges = {(e.source, e.target) for e in g.get_graph().edges}
    assert ("language_ingress", "planning") in edges


# ── 2. planning.run() validation ──────────────────────────────────────────────

def test_planning_run_beyond_horizon_sets_out_of_range():
    """planning.run() with date beyond forecast horizon must set OUT_OF_RANGE."""
    far_date = _iso(FORECAST_HORIZON_DAYS + 10)
    state = _base_state(
        understood_when={"start": far_date, "end": far_date},
    )
    result = planning.run(state)
    assert result.outputs.get("query_outcome") == "OUT_OF_RANGE"
    assert result.outputs.get("execution_plan") == []


def test_planning_run_unknown_place_sets_needs_place():
    """planning.run() with unknown place must set NEEDS_PLACE."""
    state = _base_state(
        understood_places=[{"raw": "Chandamaruta", "normalized": "Chandamaruta"}],
    )
    result = planning.run(state)
    assert result.outputs.get("query_outcome") == "NEEDS_PLACE"
    assert result.outputs.get("execution_plan") == []


def test_planning_run_valid_place_passes_validation():
    """planning.run() with valid place and valid time must pass validation (query_outcome is None)."""
    inside_date = _iso(2)
    state = _base_state(
        understood_places=[{"raw": "Kochi", "normalized": "Kochi"}],
        understood_when={"start": inside_date, "end": inside_date},
    )
    result = planning.run(state)
    assert result.outputs.get("query_outcome") is None
    assert result.outputs.get("execution_plan") != []


# ── 3. planning_node state patch and refusal ──────────────────────────────────

def test_planning_node_sets_refusal_fields_on_out_of_range():
    """planning_node() must set final_english_response and query_outcome on OUT_OF_RANGE."""
    far_date = _iso(FORECAST_HORIZON_DAYS + 10)
    state = _base_state(
        understood_when={"start": far_date, "end": far_date},
    )
    patch = planning_node(state)
    assert patch.get("query_outcome") == "OUT_OF_RANGE"
    assert patch.get("final_english_response")
    assert str(FORECAST_HORIZON_DAYS) in patch.get("final_english_response", "")


def test_planning_node_sets_refusal_fields_on_needs_place():
    """planning_node() must set final_english_response and query_outcome on NEEDS_PLACE."""
    state = _base_state(
        understood_places=[{"raw": "Chandamaruta", "normalized": "Chandamaruta"}],
    )
    patch = planning_node(state)
    assert patch.get("query_outcome") == "NEEDS_PLACE"
    assert patch.get("final_english_response")


# ── 4. _route_after_planning routing ──────────────────────────────────────────

def test_route_after_planning_routes_refusals_to_end():
    """_route_after_planning must return END for NEEDS_PLACE and OUT_OF_RANGE."""
    from langgraph.graph import END

    state_range = _base_state(query_outcome="OUT_OF_RANGE")
    assert _route_after_planning(state_range) == END

    state_place = _base_state(query_outcome="NEEDS_PLACE")
    assert _route_after_planning(state_place) == END


def test_route_after_planning_routes_sea_question_to_discovery():
    """_route_after_planning must return marine_data_discovery for valid sea question."""
    state_ok = _base_state(query_outcome=None, matched_intent_rows=["SAFETY_CHECK"])
    assert _route_after_planning(state_ok) == "marine_data_discovery"


def test_route_after_planning_routes_out_of_scope():
    """_route_after_planning must return out_of_scope for OUT_OF_SCOPE row."""
    from orca.agents.planning import OUT_OF_SCOPE_ROW
    state_oos = _base_state(query_outcome=None, matched_intent_rows=[OUT_OF_SCOPE_ROW])
    assert _route_after_planning(state_oos) == "out_of_scope"
