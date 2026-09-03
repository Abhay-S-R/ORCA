from unittest.mock import MagicMock, patch

from orca.agents.reporting import (
    _PERSONA_RENDERING_INSTRUCTIONS,
    assemble_response,
    format_export,
    synthesize_narrative,
)
from orca.contracts import AgentResult, Confidence, SourceProvenance

_VERDICT = {"go_no_go": "GO", "reason": "conditions within safe thresholds"}


def _result(agent_name: str = "risk_assessment") -> AgentResult:
    return AgentResult(
        agent_name=agent_name,
        query_id="q-1",
        reasoning_depth="STANDARD",
        inputs_consumed={},
        outputs={"wave_height_m": 0.8, "wind_speed_10m": 5.0},
        source_provenance=SourceProvenance(
            dataset="Open-Meteo Marine", acquisition_timestamp="2026-09-03T00:00:00Z", freshness_minutes=10
        ),
        confidence=Confidence(score="HIGH", rationale="fresh data"),
    )


def test_all_four_personas_have_a_rendering_instruction():
    assert set(_PERSONA_RENDERING_INSTRUCTIONS) == {
        "fisherman", "commercial_navigator", "researcher", "coastal_authority",
    }


def test_each_persona_produces_a_structurally_different_prompt():
    seen_prompts = set()
    for persona in _PERSONA_RENDERING_INSTRUCTIONS:
        fake_client = MagicMock()
        fake_client.complete.side_effect = lambda messages: messages[0]["content"]
        with patch("orca.llm.tiers.llm", return_value=fake_client):
            synthesize_narrative("is it safe today", _VERDICT, [_result()], persona=persona)
        prompt_used = fake_client.complete.call_args[0][0][0]["content"]
        assert persona in prompt_used
        seen_prompts.add(prompt_used)
    assert len(seen_prompts) == 4  # every persona's prompt is unique


def test_verdict_header_and_ground_rule_2_hold_across_every_persona():
    for persona in _PERSONA_RENDERING_INSTRUCTIONS:
        fake_client = MagicMock()
        fake_client.complete.return_value = f"{_VERDICT['go_no_go']}: {_VERDICT['reason']} — safe out there, {persona}."
        with patch("orca.llm.tiers.llm", return_value=fake_client):
            narrative = synthesize_narrative("is it safe today", _VERDICT, [_result()], persona=persona)
        assert narrative.startswith("GO:")


def test_unconfigured_llm_falls_back_to_deterministic_verdict_line_for_every_persona():
    for persona in _PERSONA_RENDERING_INSTRUCTIONS:
        with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no API key")):
            narrative = synthesize_narrative("is it safe today", _VERDICT, [_result()], persona=persona)
        assert narrative == "GO: conditions within safe thresholds"


def test_result_refs_resolve_back_to_the_agent_result_that_produced_the_citation():
    assembled = assemble_response("q-1", [_result("geospatial"), _result("risk_assessment")])
    assert len(assembled.result_refs) == len(assembled.citations)
    ref_agents = {ref["agent_name"] for ref in assembled.result_refs}
    citation_agents = {c.agent_name for c in assembled.citations}
    assert ref_agents == citation_agents
    geospatial_ref = next(r for r in assembled.result_refs if r["agent_name"] == "geospatial")
    assert geospatial_ref["outputs"]["wave_height_m"] == 0.8


def test_export_csv_contains_provenance_metadata_columns():
    assembled = assemble_response("q-1", [_result()])
    csv_text = format_export(assembled, "csv")
    header = csv_text.splitlines()[0]
    assert "dataset" in header and "acquisition_timestamp" in header and "freshness_minutes" in header
    assert "Open-Meteo Marine" in csv_text


def test_export_json_contains_full_provenance_per_data_point():
    import json

    assembled = assemble_response("q-1", [_result()])
    payload = json.loads(format_export(assembled, "json"))
    assert payload["query_id"] == "q-1"
    assert payload["citations"][0]["dataset"] == "Open-Meteo Marine"
    assert payload["result_refs"][0]["outputs"]["wind_speed_10m"] == 5.0
