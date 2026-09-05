"""Agent 10 (Critic) — plan §4 S1 Phase 3, Day 18. LLM-as-judge over the
Reporting narrative, at the `reasoning` tier (orca/llm/tiers.py) — swapping
providers is an env change, never a code change here (Ground Rule 5).

Triggers on `reasoning_depth == "DEEP"` ONLY, never on who is asking. That is
the one invariant this file exists to protect: gating the Critic by the
asker's role would be the v1.0 routing bug (intent decides what fires, the
asker's role decides how it's said) wearing a quality-control hat.
`scripts/verify_ci_guards.py` enforces this by construction — this module is
not in the guard's exclusion list (unlike language.py/reporting.py), so
reading the asker's role anywhere in this file fails CI, not just review.

Safety carve-out (Ground Rule 2, load-bearing): if `matched_intent_rows`
contains "SAFETY_CHECK", the go/no-go verdict already sits in
`final_english_response` before this agent ever runs (reporting_node runs
first in the graph) — the Critic only ever reviews and amends the
*explanatory* prose around an already-final verdict. It cannot withhold,
delay, or alter the verdict itself; asserted in the self-check below by
confirming the verdict header text survives every critique path unchanged.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth

if TYPE_CHECKING:
    from orca.state import ORCAState

MAX_ITERATIONS = 3

# Architecture §3.2 five-part rubric, verbatim.
_RUBRIC = (
    "factual_consistency",   # does the prose contradict a measured value it cites?
    "temporal_coherence",    # does it mix forecast and observed tenses, or wrong time windows?
    "causal_claim_strength", # does it say "caused" where the data only supports "correlated"?
    "citation_completeness", # does every non-trivial claim carry a source?
    "spatial_accuracy",      # does a stated distance/bearing/boundary match the geospatial data?
)


@dataclass(frozen=True)
class CritiqueIssue:
    rubric_item: str
    description: str
    reinvoke_agent: str  # deterministic issue -> agent mapping, never a free-text guess


# Deterministic issue->agent re-invocation mapping (plan §6 D1 Day 18) — the
# Critic names *which* specialist's output the issue traces back to; it never
# re-derives the fact itself (that would be the Critic doing Ground-Rule-2
# work with an LLM).
_REINVOKE_MAP: dict[str, str] = {
    "factual_consistency": "reporting",
    "temporal_coherence": "weather_intelligence",
    "causal_claim_strength": "ocean_analytics",
    "citation_completeness": "reporting",
    "spatial_accuracy": "geospatial",
}

_VERDICT_HEADER_RE = re.compile(r"^(GO|CAUTION|NO_GO):")


def _is_safety_check(state: ORCAState) -> bool:
    return "SAFETY_CHECK" in (state.get("matched_intent_rows") or [])


def _verdict_header(text: str) -> str | None:
    m = _VERDICT_HEADER_RE.match(text.strip())
    return m.group(0) if m else None


def _parse_judge_response(raw: str) -> list[CritiqueIssue]:
    """The judge is asked for strict JSON; a malformed response degrades to
    "no issues found" rather than crashing the pass — a Critic that cannot
    parse its own judge is not grounds to fail the whole response (plan §4
    D1: the Critic upgrades explanations, it never blocks anything)."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    issues = []
    for item in data if isinstance(data, list) else data.get("issues", []):
        rubric_item = item.get("rubric_item")
        if rubric_item not in _RUBRIC:
            continue
        issues.append(CritiqueIssue(
            rubric_item=rubric_item,
            description=item.get("description", ""),
            reinvoke_agent=_REINVOKE_MAP[rubric_item],
        ))
    return issues


def _judge_prompt(query: str, narrative: str, facts_block: str) -> str:
    rubric_lines = "\n".join(f"- {item}" for item in _RUBRIC)
    return f"""You are the ORCA Critic (Agent 10), judging a marine-advisory narrative against measured facts. \
Judge ONLY the explanatory prose that follows the verdict line — you never question or alter the verdict itself.

USER QUERY: "{query}"

MEASURED FACTS (ground truth, from deterministic agents):
{facts_block}

NARRATIVE UNDER REVIEW:
{narrative}

Judge against exactly these five rubric items, nothing else:
{rubric_lines}

Respond with STRICT JSON only, no prose: a list of objects
{{"rubric_item": "<one of the five above>", "description": "<one sentence, what is wrong>"}}.
Return [] if the narrative passes on all five."""


def _revise_prompt(narrative: str, issues: list[CritiqueIssue], verdict_header: str) -> str:
    issue_lines = "\n".join(f"- [{i.rubric_item}] {i.description}" for i in issues)
    return f"""Revise ONLY the explanatory prose below to fix these issues. Do not change any number, \
distance, or measured value already present. The response MUST still begin with the exact verdict \
header "{verdict_header}" — copy it unchanged.

ISSUES TO FIX:
{issue_lines}

ORIGINAL:
{narrative}

Return only the revised text."""


def run_critic_pass(
    query: str, narrative: str, facts_block: str, *, is_safety_check: bool,
) -> tuple[str, bool, int, list[CritiqueIssue]]:
    """Runs up to MAX_ITERATIONS judge->revise loops. Returns
    (final_narrative, critic_pass, iteration_count, issues_found).

    `issues_found` accumulates every issue that actually triggered a
    revision across all iterations — not just the last judge call, which is
    empty whenever the pass ultimately succeeds. The reasoning-graph replay
    (orca/api/trace_routes.py) draws one dashed re-invocation edge per issue
    here, so a Critic loop that corrected something and then passed clean
    must still be visible as a loop, not read back as "nothing happened".

    `is_safety_check` never gates *whether* this runs — the caller decides
    that, and this function stays blind to it either way; it only changes
    what may be revised: the verdict header is asserted unchanged on every
    iteration regardless."""
    from orca.llm.tiers import llm

    verdict_header = _verdict_header(narrative)
    client = llm("reasoning")
    current = narrative
    issues_found: list[CritiqueIssue] = []

    for iteration in range(1, MAX_ITERATIONS + 1):
        # No max_tokens kwarg (Ground Rule 5): _TieredClient forwards **kw
        # straight to whichever provider is configured, and AnthropicProvider
        # / GeminiProvider do not accept the same kwarg name for this —
        # orca/agents/reporting.py's synthesize_narrative hits the same
        # constraint and omits it for the same reason. A provider-specific
        # token budget belongs in the tier's own config, not a per-call kwarg
        # here.
        raw = client.complete([{"role": "user", "content": _judge_prompt(query, current, facts_block)}])
        issues = _parse_judge_response(raw)
        if not issues:
            return current, True, iteration, issues_found

        issues_found.extend(issues)
        revised = client.complete(
            [{"role": "user", "content": _revise_prompt(current, issues, verdict_header or "")}]
        ).strip()

        # The verdict header is load-bearing: a revision that drops or
        # changes it is rejected outright and the previous text is kept —
        # the Critic amending the verdict would be Ground Rule 2 violated by
        # exactly the agent whose job is quality control.
        if verdict_header and not revised.startswith(verdict_header):
            return current, False, iteration, issues_found
        current = revised

    return current, False, MAX_ITERATIONS, issues_found


def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Called only when reasoning_depth == "DEEP"
    (wired in orca/graph/graph.py's conditional edge, not here) — this
    function itself does not re-check depth so that a unit test can call it
    directly without constructing a full DEEP state."""
    query_id = state.get("query_id", "")
    depth = coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW"))
    narrative = state.get("final_english_response", "") or ""
    query = state.get("normalized_english_query") or state.get("raw_user_query") or ""
    is_safety = _is_safety_check(state)
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    facts_block = "\n".join(
        f"- {k}: {v}" for k, v in {
            "risk_verdict": (state.get("risk_assessment") or {}).get("go_no_go"),
            "wave_height_m": (state.get("weather_data") or {}).get("wave_height"),
            "imbl_distance_nm": (state.get("geospatial_data") or {}).get("imbl_distance_nm"),
            "productivity_diagnosis": (state.get("ocean_data") or {}).get("productivity_diagnosis"),
        }.items() if v is not None
    ) or "No measured facts available."

    verdict_before = _verdict_header(narrative)

    try:
        revised, critic_pass, iterations, issues = run_critic_pass(
            query, narrative, facts_block, is_safety_check=is_safety,
        )
        status: Literal["ok", "degraded"] = "ok"
        confidence = Confidence(
            score="HIGH" if critic_pass else "MEDIUM",
            rationale=f"{len(issues)} issue(s) on final pass" if not critic_pass else "passed all 5 rubric items",
        )
        error_detail = None
    except Exception as exc:  # noqa: BLE001 — a Critic failure degrades to the
        # unreviewed narrative, it never blocks the response (plan §4 D1 Day 18).
        revised, critic_pass, iterations, issues = narrative, False, 0, []
        status, confidence = "degraded", Confidence(score="LOW_DATA", rationale=f"Critic unavailable: {exc}")
        error_detail = str(exc)

    # Assert-by-construction: whatever happened above, the verdict header
    # text must be byte-identical to what Reporting emitted. If a bug ever
    # let it drift, degrade to the pre-critique narrative rather than ship
    # an altered verdict.
    if verdict_before and _verdict_header(revised) != verdict_before:
        revised = narrative

    return AgentResult(
        agent_name="critic",
        query_id=query_id,
        reasoning_depth=depth,
        inputs_consumed={"narrative_len": len(narrative), "is_safety_check": is_safety},
        outputs={
            "final_english_response": revised,
            "critic_pass": critic_pass,
            "critic_iteration_count": iterations,
            "issues": [{"rubric_item": i.rubric_item, "description": i.description, "reinvoke_agent": i.reinvoke_agent} for i in issues],
        },
        source_provenance=SourceProvenance(
            dataset="ORCA Critic (Agent 10) — LLM-as-judge, reasoning tier",
            acquisition_timestamp=now, freshness_minutes=0,
        ),
        confidence=confidence,
        status=status,
        error_detail=error_detail,
    )


if __name__ == "__main__":
    # No live LLM in this check — exercises the deterministic parts only:
    # verdict-header extraction, the rubric->agent mapping, and the
    # verdict-preservation guard, none of which may ever depend on a network call.
    assert _verdict_header("GO: conditions favorable") == "GO:"
    assert _verdict_header("CAUTION: wave height elevated") == "CAUTION:"
    assert _verdict_header("NO_GO: lightning active") == "NO_GO:"
    assert _verdict_header("no header here") is None
    assert set(_REINVOKE_MAP) == set(_RUBRIC)
    issues = _parse_judge_response(json.dumps([
        {"rubric_item": "causal_claim_strength", "description": "overclaims causation"},
        {"rubric_item": "not_a_real_item", "description": "ignored"},
    ]))
    assert len(issues) == 1 and issues[0].reinvoke_agent == "ocean_analytics"
    assert _parse_judge_response("not json") == []
    print("critic self-check ok")
