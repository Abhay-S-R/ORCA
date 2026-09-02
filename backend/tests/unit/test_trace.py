from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.state import ORCAState
from orca.trace import run_traced_node


def _ok_agent(state: ORCAState) -> AgentResult:
    return AgentResult(
        agent_name="fake_agent", query_id=state["query_id"], reasoning_depth="SHALLOW",
        inputs_consumed={}, outputs={"x": 1},
        source_provenance=SourceProvenance(dataset="fake", acquisition_timestamp="", freshness_minutes=0),
        confidence=Confidence(score="HIGH", rationale="fake"),
    )


def _raising_agent(state: ORCAState) -> AgentResult:
    raise ValueError("simulated agent bug")


def test_successful_node_produces_a_trace_entry():
    state: ORCAState = {"query_id": "q-1"}  # type: ignore[typeddict-item]
    result, entry = run_traced_node("fake_agent", _ok_agent, state)
    assert result.status == "ok"
    assert entry["agent_name"] == "fake_agent"
    assert entry["status"] == "ok"
    assert entry["latency_ms"] >= 0


def test_raising_agent_produces_a_failed_result_not_a_crash():
    # §5.7 exception boundary — this must not propagate the ValueError up
    # through run_traced_node.
    state: ORCAState = {"query_id": "q-2"}  # type: ignore[typeddict-item]
    result, entry = run_traced_node("fake_agent", _raising_agent, state)
    assert result.status == "failed"
    assert result.confidence.score == "LOW_DATA"
    assert "simulated agent bug" in result.error_detail
    assert entry["status"] == "failed"
    assert "simulated agent bug" in entry["error_detail"]


def test_trace_entry_query_id_matches_state_even_on_failure():
    state: ORCAState = {"query_id": "q-3"}  # type: ignore[typeddict-item]
    _, entry = run_traced_node("fake_agent", _raising_agent, state)
    assert entry["query_id"] == "q-3"
