"""PC2.2 (`R-PS-1`, `PS-C1`) — planning.run() now owns the single LLM call.

Done-when (plan §5 PC2.2):
- planning.run() LLM-up: returns both understood_* fields and matched_intent_rows.
- planning.run() LLM-down: falls back deterministically, same routing outputs.
- LLM-call count per turn is NOT higher than PC0.2 baseline (≤ 1 cheap call).
- understand.run() is no longer called from graph (understand node gone).
- The PC0 baseline pass rate is ≥ before (verified by existing test_pc0_baseline.py).
- /ask behaviour is unchanged: query_guard still runs between planning and fan-out.
"""
from __future__ import annotations

import os
import unittest.mock as mock

import pytest

os.environ.setdefault("ORCA_LLM_ENABLED", "0")


# ── helpers ──────────────────────────────────────────────────────────────────

def _state(**kwargs):
    base = {
        "query_id": "t0",
        "raw_user_query": kwargs.pop("query", "what are the wave conditions near Kochi today?"),
        "session_history": [],
        "user_location": None,
        "reasoning_depth": "SHALLOW",
        "normalized_english_query": None,
    }
    base.update(kwargs)
    return base


# ── 1. planning.run() outputs understood_* fields ────────────────────────────

def test_planning_run_outputs_kind():
    """planning.run() must include 'kind' in outputs (PC2.2)."""
    from orca.agents import planning
    result = planning.run(_state(query="hi there"))
    assert "kind" in result.outputs


def test_planning_run_outputs_all_understand_fields():
    """planning.run() outputs must contain all six understand fields."""
    from orca.agents import planning
    result = planning.run(_state(query="safe to fish near Rameswaram tomorrow?"))
    for field in ("kind", "intents", "places", "when", "is_followup", "agents"):
        assert field in result.outputs, f"missing field: {field}"


def test_planning_run_outputs_routing_fields():
    """planning.run() outputs must contain routing fields alongside understand fields."""
    from orca.agents import planning
    result = planning.run(_state(query="wave height at Kochi"))
    for field in ("matched_intent_rows", "execution_plan", "routing_tier"):
        assert field in result.outputs, f"missing routing field: {field}"


def test_planning_run_sea_question_has_nonempty_matched_rows():
    """Sea question must produce at least one matched_intent_row."""
    from orca.agents import planning
    result = planning.run(_state(query="tide conditions near Chennai today"))
    assert result.outputs["matched_intent_rows"], "expected non-empty matched rows"


def test_planning_run_greeting_has_empty_execution_plan():
    """Greeting kind must produce empty execution_plan (no specialists needed)."""
    from orca.agents import planning
    result = planning.run(_state(query="hello"))
    assert result.outputs["execution_plan"] == []


def test_planning_run_kind_is_valid_string():
    """Kind must be one of the valid UnderstoodPrompt kind values."""
    from orca.agents import planning
    from orca.agents.understand import _KIND_VALUES
    result = planning.run(_state(query="nearest fishing zone"))
    assert result.outputs["kind"] in _KIND_VALUES


def test_planning_run_agents_is_list():
    """agents field must be a list (may be empty)."""
    from orca.agents import planning
    result = planning.run(_state(query="safe to venture out today?"))
    assert isinstance(result.outputs["agents"], list)


def test_planning_run_agents_subset_of_known_specialists():
    """agents field must only contain known specialist names."""
    from orca.agents import planning
    from orca.agents.understand import _KNOWN_SPECIALISTS
    result = planning.run(_state(query="cyclone warning near Vizag"))
    for name in result.outputs["agents"]:
        assert name in _KNOWN_SPECIALISTS, f"hallucinated agent name: {name}"


# ── 2. LLM-call count is not higher than baseline ────────────────────────────

def test_planning_run_makes_at_most_one_llm_call_lm_up():
    """LLM-up path: planning.run() must make exactly one cheap-tier call (PC0.2)."""
    from orca.agents import planning

    with mock.patch("orca.llm.tiers.llm") as mock_llm_factory:
        mock_client = mock.Mock()
        mock_client.complete.return_value = (
            '{"kind":"sea_question","intents":["CONDITIONS"],'
            '"places":[{"raw":"Kochi","normalized":"Kochi"}],'
            '"when":null,"is_followup":false,"agents":["weather_intelligence"]}'
        )
        mock_llm_factory.return_value = mock_client

        planning.run(_state(query="wave height at Kochi"))

        # Exactly one call to the LLM (the understand+plan merged call)
        assert mock_client.complete.call_count == 1


# ── 3. Fallback (LLM down) still produces routing outputs ────────────────────

def test_planning_run_llm_down_still_routes():
    """LLM-down: fallback path must still return matched_intent_rows."""
    from orca.agents import planning
    # ORCA_LLM_ENABLED=0 forces fallback already — just call run and assert
    result = planning.run(_state(query="nearest fishing zone near Tuticorin"))
    assert result.outputs["matched_intent_rows"]  # non-empty for sea question


def test_planning_run_llm_down_kind_is_set():
    """LLM-down: kind must still be set by the fallback understand."""
    from orca.agents import planning
    result = planning.run(_state(query="wave height near Kochi"))
    assert result.outputs["kind"]  # non-None


def test_planning_run_llm_down_agents_from_planning_table():
    """LLM-down: agents must be derived from the planning table (subset of known)."""
    from orca.agents import planning
    from orca.agents.understand import _KNOWN_SPECIALISTS
    result = planning.run(_state(query="is it safe to go to sea near Vizag today?"))
    for name in result.outputs["agents"]:
        assert name in _KNOWN_SPECIALISTS


# ── 4. Graph — understand node no longer registered ──────────────────────────

def test_graph_has_no_understand_node():
    """PC2.2 — 'understand' must not be a node in the compiled graph."""
    from orca.graph.graph import build_graph
    g = build_graph()
    assert "understand" not in g.nodes, "understand node must be removed in PC2.2"


def test_graph_planning_node_exists():
    """'planning' node must still be in the graph."""
    from orca.graph.graph import build_graph
    g = build_graph()
    assert "planning" in g.nodes


def test_graph_has_no_query_guard_node():
    """PC2.3 — 'query_guard' must not be a node in the compiled graph."""
    from orca.graph.graph import build_graph
    g = build_graph()
    assert "query_guard" not in g.nodes, "query_guard node must be removed in PC2.3"


# ── 5. planning_node stores understood_* in state ────────────────────────────

def test_planning_node_sets_understood_kind():
    """planning_node must store understood_kind in the returned state patch."""
    from orca.graph.graph import planning_node
    patch = planning_node(_state(query="hello"))
    assert "understood_kind" in patch


def test_planning_node_sets_planned_agents():
    """planning_node must store planned_agents in the returned state patch (PC2.1)."""
    from orca.graph.graph import planning_node
    patch = planning_node(_state(query="safe to fish near Kochi?"))
    assert "planned_agents" in patch
    assert isinstance(patch["planned_agents"], list)


def test_planning_node_sets_all_understood_fields():
    """planning_node must expose all understood_* fields."""
    from orca.graph.graph import planning_node
    patch = planning_node(_state(query="wave height at Kochi today"))
    for field in ("understood_kind", "understood_intents", "understood_places",
                  "understood_when", "understood_is_followup", "planned_agents"):
        assert field in patch, f"planning_node missing state field: {field}"


def test_planning_node_sets_matched_intent_rows():
    """planning_node must set matched_intent_rows in the state patch."""
    from orca.graph.graph import planning_node
    patch = planning_node(_state(query="tide conditions near Mumbai"))
    assert "matched_intent_rows" in patch


def test_planning_node_sets_execution_plan():
    """planning_node must set execution_plan in the state patch."""
    from orca.graph.graph import planning_node
    patch = planning_node(_state(query="tide conditions near Mumbai"))
    assert "execution_plan" in patch


# ── 6. Regression: understand.py helpers still importable ────────────────────

def test_understand_helpers_still_importable():
    """understand.py helper functions must remain importable (used by planning.run)."""
    from orca.agents.understand import (  # noqa: F401
        _build_understand_prompt,
        _parse_understand_output,
        _fallback_understand,
        _KNOWN_SPECIALISTS,
        UnderstoodPrompt,
    )


def test_understand_module_run_still_callable():
    """understand.run() may still exist for backward compatibility / tests."""
    from orca.agents import understand
    assert callable(understand.run)


# ── 7. LLM-call count baseline (no understand call from graph) ───────────────

def test_planning_node_does_not_call_understand_run_separately():
    """planning_node must not call understand.run() as a separate step."""
    import orca.agents.understand as understand_mod
    from orca.graph.graph import planning_node

    with mock.patch.object(understand_mod, "run", wraps=understand_mod.run) as mock_run:
        planning_node(_state(query="wave height near Kochi"))
        assert mock_run.call_count == 0, (
            "planning_node must not call understand.run() — it calls the helpers directly"
        )
