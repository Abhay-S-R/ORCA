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


def test_every_numeric_output_field_has_a_non_empty_source_provenance() -> None:
    """P0.12, principle 2 / R-JUDGE-4: a fabricated-number guard cannot be
    checked statically (any agent can compute a number), so this is the
    runtime check instead — build a final_response-shaped payload from a
    fixture with several agents, each contributing several numeric fields,
    and confirm every one of them traces back to a citation with a real
    dataset name and acquisition timestamp, not a placeholder."""
    results = [
        AgentResult(
            agent_name="weather_intelligence", query_id="q-1", reasoning_depth="STANDARD",
            inputs_consumed={}, outputs={"wave_height_m": 1.2, "wind_speed_kmh": 18.5},
            source_provenance=SourceProvenance(
                dataset="Open-Meteo Marine API", acquisition_timestamp="2026-09-20T06:00:00Z", freshness_minutes=30
            ),
            confidence=Confidence(score="HIGH", rationale="test"),
        ),
        AgentResult(
            agent_name="geospatial", query_id="q-1", reasoning_depth="STANDARD",
            inputs_consumed={}, outputs={"imbl_distance_nm": 4.7},
            source_provenance=SourceProvenance(
                dataset="IMBL reference line", acquisition_timestamp="2026-09-20T00:00:00Z", freshness_minutes=0
            ),
            confidence=Confidence(score="HIGH", rationale="test"),
        ),
    ]
    assembled = assemble_response("q-1", results)

    numeric_fields = {
        r.agent_name: [k for k, v in r.outputs.items() if isinstance(v, (int, float))]
        for r in results
    }
    citation_by_agent = {c.agent_name: c for c in assembled.citations}

    for agent_name, fields in numeric_fields.items():
        assert fields, f"fixture bug: {agent_name} has no numeric field to check"
        citation = citation_by_agent.get(agent_name)
        assert citation is not None, f"{agent_name} contributed numeric fields {fields} but no citation"
        assert citation.dataset, f"{agent_name} citation has an empty dataset name"
        assert citation.acquisition_timestamp, f"{agent_name} citation has an empty acquisition timestamp"
