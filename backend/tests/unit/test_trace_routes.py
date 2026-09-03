"""Unit tests over build_trace_graph / _rows_to_agent_results /
render_persona's core logic, using plain namespaces that duck-type
AuditTraceLog's attributes — no real Postgres needed (the ORM model itself
is exercised by infra/db integration, not here; see plan §5.1)."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from orca.api.trace_routes import (
    PersonaRenderRequest,
    _rows_to_agent_results,
    build_trace_graph,
    render_persona,
)

QID = "11111111-1111-1111-1111-111111111111"


def _row(agent_name, status="ok", confidence="HIGH", outputs=None, inputs=None, prov=None, latency=10.0, error=None):
    return SimpleNamespace(
        query_id=QID, agent_name=agent_name, status=status, confidence=confidence,
        latency_ms=latency, outputs=outputs or {}, inputs_consumed=inputs or {},
        source_provenance=prov or {"dataset": f"{agent_name}-source", "acquisition_timestamp": "2026-09-03T00:00:00Z", "freshness_minutes": 5},
        error_detail=error,
    )


def _standard_rows():
    return [
        _row("distress", outputs={"detection": {"is_distress": False}}),
        _row("language_ingress"),
        _row("planning", outputs={"matched_intent_rows": ["SAFETY_CHECK"]}, inputs={"query": "is it safe today"}),
        _row("weather_intelligence", outputs={"wave_height": 0.8, "lightning_active": False}),
        _row("geospatial", outputs={"imbl_distance_nm": 16.3, "mpa_violation": False}),
        _row("ocean_analytics", outputs={"tide": "rising"}),
        _row("risk_assessment", outputs={"go_no_go": "GO", "reason": "conditions favorable"}),
        _row("visualization", outputs={}),
        _row("reporting", outputs={"final_english_response": "GO: conditions favorable"}),
        _row("language_egress"),
    ]


def test_build_trace_graph_produces_one_node_per_distinct_agent():
    graph = build_trace_graph(QID, _standard_rows())
    assert {n.agent_name for n in graph.nodes} == {r.agent_name for r in _standard_rows()}


def test_every_node_resolves_a_real_depth_not_the_unknown_fallback():
    graph = build_trace_graph(QID, _standard_rows())
    assert all(n.depth != 99 for n in graph.nodes)


def test_fanout_group_contains_the_three_parallel_specialists():
    graph = build_trace_graph(QID, _standard_rows())
    fanout = next(g for g in graph.groups if set(g.node_ids) & {"weather_intelligence", "geospatial", "ocean_analytics"})
    assert set(fanout.node_ids) == {"weather_intelligence", "geospatial", "ocean_analytics"}


def test_deterministic_agents_flagged_as_not_using_an_llm():
    graph = build_trace_graph(QID, _standard_rows())
    by_name = {n.agent_name: n for n in graph.nodes}
    assert by_name["risk_assessment"].used_llm is False
    assert by_name["geospatial"].used_llm is False
    assert by_name["reporting"].used_llm is True


def test_critic_loop_draws_a_dashed_edge_to_the_reinvoked_agent():
    rows = _standard_rows() + [
        _row("critic", outputs={
            "final_english_response": "GO: conditions favorable, revised.",
            "critic_pass": True, "critic_iteration_count": 2,
            "issues": [{"rubric_item": "causal_claim_strength", "description": "x", "reinvoke_agent": "ocean_analytics"}],
        }),
    ]
    graph = build_trace_graph(QID, rows)
    loop_edges = [e for e in graph.edges if e.kind == "critic_loop"]
    assert len(loop_edges) == 1
    assert loop_edges[0].from_ == "critic"
    assert loop_edges[0].to == "ocean_analytics"


def test_a_repeated_agent_name_keeps_only_the_first_row():
    rows = _standard_rows() + [_row("planning", outputs={"matched_intent_rows": ["OTHER"]})]
    graph = build_trace_graph(QID, rows)
    planning_nodes = [n for n in graph.nodes if n.agent_name == "planning"]
    assert len(planning_nodes) == 1
    assert planning_nodes[0].reasoning_summary  # from the first row, not the duplicate


def test_rows_to_agent_results_excludes_synthesis_and_review_agents():
    results = _rows_to_agent_results(_standard_rows())
    names = {r.agent_name for r in results}
    assert "reporting" not in names
    assert "language_ingress" not in names
    assert "risk_assessment" in names
    assert "geospatial" in names


def test_render_persona_calls_only_reporting_never_a_specialist_agent():
    fake_session = MagicMock()
    fake_llm = MagicMock()
    fake_llm.complete.return_value = "GO: conditions favorable, for a researcher."
    with patch("orca.api.trace_routes.get_sessionmaker", return_value=lambda: fake_session), \
         patch("orca.api.trace_routes.get_trace_entries", return_value=_standard_rows()), \
         patch("orca.llm.tiers.llm", return_value=fake_llm), \
         patch("orca.agents.weather_intelligence.run") as weather_run, \
         patch("orca.agents.geospatial.check_boundary_proximity") as geo_check:
        resp = render_persona(PersonaRenderRequest(query_id=QID, persona="researcher"))

    weather_run.assert_not_called()
    geo_check.assert_not_called()
    assert resp.persona == "researcher"
    assert resp.query_id == QID


def test_render_persona_numbers_are_identical_across_personas():
    fake_session = MagicMock()
    responses = {}
    for persona in ("fisherman", "researcher"):
        fake_llm = MagicMock()
        fake_llm.complete.return_value = f"GO: conditions favorable, rendered for {persona}."
        with patch("orca.api.trace_routes.get_sessionmaker", return_value=lambda: fake_session), \
             patch("orca.api.trace_routes.get_trace_entries", return_value=_standard_rows()), \
             patch("orca.llm.tiers.llm", return_value=fake_llm):
            responses[persona] = render_persona(PersonaRenderRequest(query_id=QID, persona=persona))
    assert responses["fisherman"].citations == responses["researcher"].citations
    assert responses["fisherman"].confidence_tier == responses["researcher"].confidence_tier
    assert responses["fisherman"].final_english_response != responses["researcher"].final_english_response


def test_render_persona_404s_when_nothing_is_stored():
    import pytest
    from fastapi import HTTPException

    fake_session = MagicMock()
    with (
        patch("orca.api.trace_routes.get_sessionmaker", return_value=lambda: fake_session),
        patch("orca.api.trace_routes.get_trace_entries", return_value=[]),
        pytest.raises(HTTPException) as exc_info,
    ):
        render_persona(PersonaRenderRequest(query_id=QID, persona="fisherman"))
    assert exc_info.value.status_code == 404
