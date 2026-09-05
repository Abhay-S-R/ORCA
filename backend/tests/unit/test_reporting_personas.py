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


# --- location honesty ---------------------------------------------------------
# The narrative prompt sees the raw user query, so if it is not told which
# position the telemetry belongs to it will narrate the default position's
# numbers under whatever place the user typed.

def test_describe_location_names_a_resolved_place():
    from orca.agents.reporting import describe_location

    text = describe_location({"lat": 9.2833, "lon": 79.2, "place_name": "pamban", "place_source": "pilot_gazetteer"})
    assert "pamban" in text
    assert "9.2833" in text and "79.2" in text


def test_describe_location_admits_the_regional_default():
    from orca.agents.reporting import describe_location

    text = describe_location({"lat": 8.8, "lon": 78.3, "place_name": None, "place_source": "regional_default"})
    assert "default" in text.lower()
    assert "no location that could be resolved" in text


def test_the_prompt_carries_the_location_and_forbids_naming_another():
    """A GO computed at the default position must not be narrated as a GO for
    the place the user named. The instruction is what stops that."""
    import orca.agents.reporting as reporting

    captured = {}

    class _Client:
        def complete(self, messages):
            captured["prompt"] = messages[0]["content"]
            return "NO_GO: nope"

    import orca.llm.tiers as tiers

    original = tiers.llm
    tiers.llm = lambda tier: _Client()
    try:
        reporting.synthesize_narrative(
            "is it safe off Mangalore", {"go_no_go": "NO_GO", "reason": "nope"}, [],
            user_location={"lat": 8.8, "lon": 78.3, "place_name": None, "place_source": "regional_default"},
        )
    finally:
        tiers.llm = original

    prompt = captured["prompt"]
    assert "LOCATION THIS ADVICE IS FOR" in prompt
    assert "default position" in prompt
    assert "Never name a place the location line does not name." in prompt
    # No agent-identity leak into user-facing text.
    assert "Agent 9" not in prompt and "ORCA Reporting Agent" not in prompt
