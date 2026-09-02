from orca.agents.reporting import assemble_response
from orca.contracts import AgentResult, Confidence, SourceProvenance


def _result(agent_name: str, score: str, status: str = "ok") -> AgentResult:
    return AgentResult(
        agent_name=agent_name,
        query_id="q-1",
        reasoning_depth="STANDARD",
        inputs_consumed={},
        outputs={"x": 1},
        source_provenance=SourceProvenance(
            dataset=f"{agent_name}-dataset", acquisition_timestamp="2026-09-02T00:00:00Z", freshness_minutes=10
        ),
        confidence=Confidence(score=score, rationale="test"),
        status=status,
    )


def test_confidence_tier_is_worst_of_contributors() -> None:
    assembled = assemble_response("q-1", [_result("a", "HIGH"), _result("b", "MEDIUM")])
    assert assembled.confidence_tier == "MEDIUM"


def test_failed_agents_produce_no_citation() -> None:
    assembled = assemble_response("q-1", [_result("a", "HIGH"), _result("b", "HIGH", status="failed")])
    assert len(assembled.citations) == 1
    assert assembled.citations[0].agent_name == "a"


def test_every_output_carries_a_citation_with_dataset_and_timestamp() -> None:
    assembled = assemble_response("q-1", [_result("geospatial", "HIGH")])
    citation = assembled.citations[0]
    assert citation.dataset == "geospatial-dataset"
    assert citation.acquisition_timestamp == "2026-09-02T00:00:00Z"


def test_empty_results_defaults_to_low_data() -> None:
    assembled = assemble_response("q-1", [])
    assert assembled.confidence_tier == "LOW_DATA"
    assert assembled.citations == ()
