import json
from unittest.mock import MagicMock, patch

from orca.agents.critic import (
    _REINVOKE_MAP,
    _RUBRIC,
    MAX_ITERATIONS,
    _verdict_header,
    run,
    run_critic_pass,
)

_NARRATIVE = "GO: conditions within safe thresholds. Wave height 0.8m, well below the 2.0m caution band."


def _deep_state(matched_intent_rows: list[str] | None = None) -> dict:
    return {
        "query_id": "q-1",
        "reasoning_depth": "DEEP",
        "normalized_english_query": "why has catch declined",
        "final_english_response": _NARRATIVE,
        "matched_intent_rows": matched_intent_rows or [],
        "risk_assessment": {"go_no_go": "GO"},
        "weather_data": {"wave_height": 0.8},
        "geospatial_data": {"imbl_distance_nm": 16.3},
        "ocean_data": {},
    }


def test_rubric_and_reinvoke_map_cover_the_same_five_items():
    assert set(_REINVOKE_MAP) == set(_RUBRIC)
    assert len(_RUBRIC) == 5


def test_clean_narrative_passes_on_first_iteration():
    fake_client = MagicMock()
    fake_client.complete.return_value = "[]"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        final, passed, iterations, issues = run_critic_pass(
            "q", _NARRATIVE, "wave_height_m: 0.8", is_safety_check=True,
        )
    assert passed is True
    assert iterations == 1
    assert issues == []
    assert final == _NARRATIVE
    fake_client.complete.assert_called_once()  # judge only, no revise call needed


def test_flagged_narrative_gets_revised_and_verdict_header_survives():
    fake_client = MagicMock()
    judge_response = json.dumps([{"rubric_item": "causal_claim_strength", "description": "overclaims causation"}])
    fake_client.complete.side_effect = [
        judge_response,
        "GO: conditions within safe thresholds. Catch decline correlates with, but is not proven caused by, SST rise.",
        "[]",
    ]
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        final, passed, iterations, _issues = run_critic_pass(
            "q", _NARRATIVE, "wave_height_m: 0.8", is_safety_check=False,
        )
    assert final.startswith("GO:")
    assert passed is True
    assert iterations == 2


def test_revision_that_drops_the_verdict_header_is_rejected():
    fake_client = MagicMock()
    judge_response = json.dumps([{"rubric_item": "spatial_accuracy", "description": "wrong distance"}])
    fake_client.complete.side_effect = [judge_response, "conditions are fine, no verdict here"]
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        final, passed, _iterations, _issues = run_critic_pass(
            "q", _NARRATIVE, "imbl_distance_nm: 16.3", is_safety_check=False,
        )
    assert final == _NARRATIVE  # kept the pre-revision text
    assert passed is False


def test_never_exceeds_max_iterations():
    fake_client = MagicMock()
    always_flag = json.dumps([{"rubric_item": "temporal_coherence", "description": "tense mismatch"}])
    fake_client.complete.side_effect = [
        always_flag, "GO: conditions within safe thresholds. revised.",
    ] * MAX_ITERATIONS
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        _, passed, iterations, _ = run_critic_pass("q", _NARRATIVE, "facts", is_safety_check=False)
    assert iterations == MAX_ITERATIONS
    assert passed is False


def test_run_never_alters_the_verdict_header_even_on_llm_failure():
    with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no key")):
        result = run(_deep_state())
    assert result.status == "degraded"
    assert result.outputs["final_english_response"] == _NARRATIVE
    assert result.outputs["critic_pass"] is False


def test_run_on_safety_check_reviews_prose_only_never_the_verdict():
    fake_client = MagicMock()
    fake_client.complete.return_value = "[]"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        result = run(_deep_state(matched_intent_rows=["SAFETY_CHECK"]))
    assert _verdict_header(result.outputs["final_english_response"]) == "GO:"
    assert result.outputs["critic_pass"] is True


def test_run_never_references_persona_the_ci_guard_would_catch():
    import re

    from orca import agents

    guard_pattern = re.compile(r"\bstakeholder_persona\b|\bpersona['\"]?\s*[:=]|\[['\"]persona['\"]]|\.get\(['\"]persona")
    critic_path = f"{agents.__path__[0]}/critic.py"
    with open(critic_path, encoding="utf-8") as f:
        code_only = "\n".join(line for line in f if not line.strip().startswith("#"))
    # Strip the module/function docstrings (triple-quoted blocks) before
    # checking, the same way a human reviewer reads code vs. comments — the
    # guard's own regex has no docstring awareness, so this mirrors what CI
    # actually executes rather than a laxer approximation of it.
    code_only = re.sub(r'"""[\s\S]*?"""', "", code_only)
    assert not guard_pattern.search(code_only)


if __name__ == "__main__":
    print("run via pytest: pytest backend/tests/unit/test_critic.py")
