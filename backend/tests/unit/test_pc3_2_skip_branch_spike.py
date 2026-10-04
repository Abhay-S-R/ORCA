"""PC3.2 — Spike: how to skip a branch without hanging the join.

This test verifies that the existing pattern (node checks execution_plan and returns _skipped)
allows the all-of join to fire correctly. The key insight is that the node still runs
and emits a trace span, but does no actual work. Each specialist writes to its own
state key (like the real ORCA graph).
"""
import operator
from typing import Annotated
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict


class TestState(TypedDict):
    execution_plan: list[str]
    executed: Annotated[list[str], operator.add]
    specialist_a_result: dict[str, str]
    specialist_b_result: dict[str, str]
    specialist_c_result: dict[str, str]


def _skipped(agent_name: str, state: TestState, reason: str) -> dict:
    """A node that deliberately did not run, as a first-class span."""
    return {
        "executed": [agent_name],
        f"{agent_name}_result": {"status": "skipped", "reason": reason},
    }


def specialist_a(state: TestState) -> dict:
    plan = state.get("execution_plan") or []
    if plan and "specialist_a" not in plan:
        return _skipped("specialist_a", state, f"not in this query's execution plan ({', '.join(plan)})")
    return {"executed": ["specialist_a"], "specialist_a_result": {"status": "done"}}


def specialist_b(state: TestState) -> dict:
    plan = state.get("execution_plan") or []
    if plan and "specialist_b" not in plan:
        return _skipped("specialist_b", state, f"not in this query's execution plan ({', '.join(plan)})")
    return {"executed": ["specialist_b"], "specialist_b_result": {"status": "done"}}


def specialist_c(state: TestState) -> dict:
    plan = state.get("execution_plan") or []
    if plan and "specialist_c" not in plan:
        return _skipped("specialist_c", state, f"not in this query's execution plan ({', '.join(plan)})")
    return {"executed": ["specialist_c"], "specialist_c_result": {"status": "done"}}


def join_node(state: TestState) -> dict:
    results = {}
    if state.get("specialist_a_result"):
        results["specialist_a"] = state["specialist_a_result"]
    if state.get("specialist_b_result"):
        results["specialist_b"] = state["specialist_b_result"]
    if state.get("specialist_c_result"):
        results["specialist_c"] = state["specialist_c_result"]
    return {"executed": ["join"], "join_result": results}


def test_skip_pattern_two_of_three():
    """Test that skipping one specialist still allows join to fire."""
    g = StateGraph(TestState)
    g.add_node("discovery", lambda s: {"execution_plan": ["specialist_a", "specialist_c"]})
    g.add_node("specialist_a", specialist_a)
    g.add_node("specialist_b", specialist_b)
    g.add_node("specialist_c", specialist_c)
    g.add_node("join", join_node)

    # Unconditional fan-out to all three
    g.add_edge(START, "discovery")
    for spec in ("specialist_a", "specialist_b", "specialist_c"):
        g.add_edge("discovery", spec)
    # All-of join - waits for ALL three
    g.add_edge(["specialist_a", "specialist_b", "specialist_c"], "join")
    g.add_edge("join", END)

    compiled = g.compile()
    result = compiled.invoke({"execution_plan": [], "executed": [], "specialist_a_result": {}, "specialist_b_result": {}, "specialist_c_result": {}})

    # All three ran, but specialist_b was skipped
    assert "specialist_a" in result["executed"]
    assert "specialist_b" in result["executed"]
    assert "specialist_c" in result["executed"]
    assert "join" in result["executed"]
    assert result["specialist_a_result"]["status"] == "done"
    assert result["specialist_b_result"]["status"] == "skipped"
    assert result["specialist_c_result"]["status"] == "done"


def test_skip_pattern_all_three():
    """Test that all three run when all are in plan."""
    g = StateGraph(TestState)
    g.add_node("discovery", lambda s: {"execution_plan": ["specialist_a", "specialist_b", "specialist_c"]})
    g.add_node("specialist_a", specialist_a)
    g.add_node("specialist_b", specialist_b)
    g.add_node("specialist_c", specialist_c)
    g.add_node("join", join_node)

    g.add_edge(START, "discovery")
    for spec in ("specialist_a", "specialist_b", "specialist_c"):
        g.add_edge("discovery", spec)
    g.add_edge(["specialist_a", "specialist_b", "specialist_c"], "join")
    g.add_edge("join", END)

    compiled = g.compile()
    result = compiled.invoke({"execution_plan": [], "executed": [], "specialist_a_result": {}, "specialist_b_result": {}, "specialist_c_result": {}})

    assert "specialist_a" in result["executed"]
    assert "specialist_b" in result["executed"]
    assert "specialist_c" in result["executed"]
    assert "join" in result["executed"]
    assert result["specialist_a_result"]["status"] == "done"
    assert result["specialist_b_result"]["status"] == "done"
    assert result["specialist_c_result"]["status"] == "done"


def test_skip_pattern_single():
    """Test that only one specialist runs when only one is in plan."""
    g = StateGraph(TestState)
    g.add_node("discovery", lambda s: {"execution_plan": ["specialist_b"]})
    g.add_node("specialist_a", specialist_a)
    g.add_node("specialist_b", specialist_b)
    g.add_node("specialist_c", specialist_c)
    g.add_node("join", join_node)

    g.add_edge(START, "discovery")
    for spec in ("specialist_a", "specialist_b", "specialist_c"):
        g.add_edge("discovery", spec)
    g.add_edge(["specialist_a", "specialist_b", "specialist_c"], "join")
    g.add_edge("join", END)

    compiled = g.compile()
    result = compiled.invoke({"execution_plan": [], "executed": [], "specialist_a_result": {}, "specialist_b_result": {}, "specialist_c_result": {}})

    assert "specialist_a" in result["executed"]
    assert "specialist_b" in result["executed"]
    assert "specialist_c" in result["executed"]
    assert "join" in result["executed"]
    assert result["specialist_a_result"]["status"] == "skipped"
    assert result["specialist_b_result"]["status"] == "done"
    assert result["specialist_c_result"]["status"] == "skipped"


def test_skip_pattern_empty_plan():
    """Test that empty plan means all run (fail-safe)."""
    g = StateGraph(TestState)
    g.add_node("discovery", lambda s: {"execution_plan": []})
    g.add_node("specialist_a", specialist_a)
    g.add_node("specialist_b", specialist_b)
    g.add_node("specialist_c", specialist_c)
    g.add_node("join", join_node)

    g.add_edge(START, "discovery")
    for spec in ("specialist_a", "specialist_b", "specialist_c"):
        g.add_edge("discovery", spec)
    g.add_edge(["specialist_a", "specialist_b", "specialist_c"], "join")
    g.add_edge("join", END)

    compiled = g.compile()
    result = compiled.invoke({"execution_plan": [], "executed": [], "specialist_a_result": {}, "specialist_b_result": {}, "specialist_c_result": {}})

    assert "specialist_a" in result["executed"]
    assert "specialist_b" in result["executed"]
    assert "specialist_c" in result["executed"]
    assert "join" in result["executed"]
    assert result["specialist_a_result"]["status"] == "done"
    assert result["specialist_b_result"]["status"] == "done"
    assert result["specialist_c_result"]["status"] == "done"