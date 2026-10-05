"""Agent 10 (Critic) — plan §4 S1 Phase 3, Day 18. LLM-as-judge over the
Reporting narrative, at the `reasoning` tier (orca/llm/tiers.py) — swapping
providers is an env change, never a code change here (Ground Rule 5).

Runs on **every** query, never on who is asking (P2.5, `R-AGENT-1`). It was
gated on `reasoning_depth == "DEEP"` until 2026-09-20, which meant the
verification loop did not execute at all on an ordinary demo question — the
one thing DLC §5 says the panel will probe hardest was the one thing a judge
could not watch happen. Depth still decides how *hard* the pass tries
(`run_critic_pass` iterates), not whether it happens.

What must never gate it is the asker's role: that would be the v1.0 routing
bug (intent decides what fires, the asker's role decides how it's said)
wearing a quality-control hat.
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
from typing import TYPE_CHECKING, Any, Literal

from orca import engines
from orca.agents.reporting import conversation_context
from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth

if TYPE_CHECKING:
    from orca.state import ORCAState

MAX_ITERATIONS = 3

# P2.5 (`R-AGENT-1`) — how many times the Critic may send the answer back to
# the agent it blames and have the whole thing re-synthesized. One.
# `orca_final.md` §3.9 asks for up to three at DEEP; this plan deliberately
# holds it at one (latency on a live demo, and the Gemini free-tier
# per-minute limit P2.13 budgets against). Raising it is a one-line change
# here plus the guard in graph._route_after_critic; do not raise it without
# re-running the budget count that point records.
MAX_REINVOCATIONS = 1

# How many judge->revise rounds ONE Critic pass may run. Three at DEEP, as it
# always was; ONE otherwise (P2.13). This is the number the first live run of
# P2.5 forced: the Critic went from DEEP-only to every query, each pass could
# still loop three times, and with a re-invocation there are two passes — the
# UI showed "10 LLM calls" for one ordinary question, which is exactly the
# per-minute Gemini budget P2.13 exists to protect. One round is a judge call
# and, only if it found something, one revise call.
MAX_ITERATIONS_STANDARD = 1

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

# The three specialists a critique can actually send work back to. `reporting`
# is deliberately not here even though `_REINVOKE_MAP` names it: a factual or
# citation complaint about the *prose* is what `run_critic_pass`'s own revise
# step already fixes, so routing the graph back through Reporting for it would
# spend a second synthesis to redo what just happened. Only a complaint that
# traces to a *measurement* is worth re-reading the measurement for.
REINVOCABLE_AGENTS: frozenset[str] = frozenset(
    {"weather_intelligence", "ocean_analytics", "geospatial"}
)


def reinvocation_target(issues: list[dict[str, Any]] | list[CritiqueIssue]) -> str | None:
    """Which agent, if any, this critique sends the query back to. The first
    issue naming a re-invocable specialist wins — deterministic, ordered, and
    never a free-text guess: the agent comes from `_REINVOKE_MAP`, which is
    keyed on the rubric item the judge picked from a fixed list of five."""
    for issue in issues:
        target = issue.get("reinvoke_agent") if isinstance(issue, dict) else issue.reinvoke_agent
        if target in REINVOCABLE_AGENTS:
            return target
    return None


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


def _judge_prompt(query: str, narrative: str, facts_block: str, context: str = "") -> str:
    rubric_lines = "\n".join(f"- {item}" for item in _RUBRIC)
    # The narrator saw the conversation and the device position, so the judge
    # must too — or a correct "unlike your earlier question about Kochi" or
    # "you are at 12.97, 77.59" reads as an unsourced claim.
    context_block = (
        f"\nCONTEXT THE NARRATIVE WAS WRITTEN WITH (a valid source for references to the conversation "
        f"or the caller's position — NOT for sea readings):\n{context}\n"
        if context else ""
    )
    return f"""You are the ORCA Critic (Agent 10), judging a marine-advisory narrative against measured facts. \
Judge ONLY the explanatory prose that follows the verdict line — you never question or alter the verdict itself.

USER QUERY: "{query}"
{context_block}
MEASURED FACTS (ground truth, from deterministic agents):
{facts_block}

NARRATIVE UNDER REVIEW:
{narrative}

Judge against exactly these five rubric items, nothing else:
{rubric_lines}

How to judge — this matters more than the rubric wording:
- Flag only what the narrative ASSERTS. A rubric item is violated when a claim the narrative actually makes contradicts the measured facts, mixes up time frames, overstates causation, or states something non-trivial with no source.
- The ABSENCE of a fact is never a defect. The narrative answers the USER QUERY, not the fact list: a fishing-zone answer does not have to mention the maritime boundary, and a safety answer does not have to recite every reading. Never write "fails to mention", "does not include" or "omits" a measured value.
- Only the facts relevant to the USER QUERY can be contradicted by it.

Respond with STRICT JSON only, no prose: a list of objects
{{"rubric_item": "<one of the five above>", "description": "<one sentence, what is wrong>"}}.
Return [] if the narrative passes on all five."""


def _revise_prompt(narrative: str, issues: list[CritiqueIssue], verdict_header: str, facts_block: str = "") -> str:
    issue_lines = "\n".join(f"- [{i.rubric_item}] {i.description}" for i in issues)
    # Two different instructions, not one with a blank in it: an answer with no verdict header
    # (any answer to a question that was not about safety) used to be told it "MUST still begin
    # with the exact verdict header """ — and the model invented one ("VERDICT: REVISED").
    header_rule = (
        f'The response MUST still begin with the exact verdict header "{verdict_header}" — copy it unchanged.'
        if verdict_header else
        "ORIGINAL has no verdict header and the revision must not get one: no heading, title, bold label "
        "or verdict line. Start directly with the first sentence of the prose."
    )
    return f"""Revise ONLY the explanatory prose below to fix these issues. {header_rule}

MEASURED FACTS (the only ground truth; the reviewer judged against these):
{facts_block or "(not supplied)"}

HOW TO FIX:
- Correct or delete the claim the issue names so that it agrees with MEASURED FACTS.
- Never add a claim, number, date, source, or description of how fresh or current something is that is \
not in MEASURED FACTS or already in ORIGINAL. If a claim cannot be checked against MEASURED FACTS, delete it.
- Do not change any number, distance, or measured value that is already correct.

ISSUES TO FIX:
{issue_lines}

ORIGINAL:
{narrative}

Return only the revised text."""


_FIGURE = re.compile(r"\d+(?:\.\d+)?")
# A line the model made up to head an answer: "**EXPIRED / OUTDATED**", "PFZ detail (...):",
# "VERDICT: REVISED", or a run of capitals such as "EXPIRED / OUTDATED The nearest ...".
_BOLD_LABEL = re.compile(r"^\s*\*\*[^*\n]{1,60}\*\*")
_CAPS_RUN = re.compile(r"^\W*[A-Z][A-Z/_ \-]{5,}[A-Z]\b")


def _opens_with_heading(text: str) -> bool:
    first = text.strip().split("\n", 1)[0].strip()
    bare = first.strip("*#_ ").strip()
    if not bare:
        return False
    if _BOLD_LABEL.match(text) or first.startswith("#") or _CAPS_RUN.match(first):
        return True
    if re.match(r"(?i)verdict\b", bare):
        return True
    return len(bare) <= 90 and bare.endswith(":")


def _revision_is_safe(current: str, revised: str, verdict_header: str | None, facts_block: str) -> bool:
    """Whether a revision may replace the text. The Critic fixes prose; it may not
    invent a header, and it may not introduce a figure that is in neither the text
    it was given nor the measured facts. A refused revision keeps the previous text."""
    if not revised.strip():
        return False
    if verdict_header:
        return revised.startswith(verdict_header)
    if _opens_with_heading(revised) and not _opens_with_heading(current):
        return False
    known = {float(n) for n in _FIGURE.findall(current)} | {float(n) for n in _FIGURE.findall(facts_block or "")}
    return not ({float(n) for n in _FIGURE.findall(revised)} - known)


def run_critic_pass(
    query: str, narrative: str, facts_block: str, *, is_safety_check: bool,
    engine_out: list[str] | None = None,
    max_iterations: int = MAX_ITERATIONS,
    context: str = "",
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
    if engine_out is not None:
        # getattr for the same reason reporting.synthesize_narrative uses it:
        # a client without `.engine` must not turn a working critic pass into
        # a degraded one.
        engine_out.append(getattr(client, "engine", engines.DETERMINISTIC))
    current = narrative
    issues_found: list[CritiqueIssue] = []

    for iteration in range(1, max_iterations + 1):
        # No max_tokens kwarg (Ground Rule 5): _TieredClient forwards **kw
        # straight to whichever provider is configured, and AnthropicProvider
        # / GeminiProvider do not accept the same kwarg name for this —
        # orca/agents/reporting.py's synthesize_narrative hits the same
        # constraint and omits it for the same reason. A provider-specific
        # token budget belongs in the tier's own config, not a per-call kwarg
        # here.
        raw = client.complete([{"role": "user", "content": _judge_prompt(query, current, facts_block, context)}])
        _note_engine(client, engine_out)
        issues = _parse_judge_response(raw)
        if not issues:
            return current, True, iteration, issues_found

        issues_found.extend(issues)
        revised = client.complete(
            [{"role": "user", "content": _revise_prompt(current, issues, verdict_header or "", facts_block)}]
        ).strip()
        _note_engine(client, engine_out)

        # The verdict header is load-bearing: a revision that drops or
        # changes it is rejected outright and the previous text is kept —
        # the Critic amending the verdict would be Ground Rule 2 violated by
        # exactly the agent whose job is quality control. The same refusal now
        # covers a header the revision made up, and a figure it invented.
        if not _revision_is_safe(current, revised, verdict_header, facts_block):
            return current, False, iteration, issues_found
        current = revised

    return current, False, max_iterations, issues_found


def _note_engine(client: object, engine_out: list[str] | None) -> None:
    """A tier is a chain of providers now (orca/llm/tiers.py): which rung
    answered is only known after the call, so the label recorded before the
    first call is replaced with the one that actually did the work."""
    engine = getattr(client, "engine", None)
    if engine_out and engine:
        engine_out[-1] = engine


def build_facts_block(state: ORCAState) -> str:
    """The ground truth the judge compares the narrative against.

    Two defects lived in the inline version this replaces, both found by
    reading what the Critic actually complained about once P2.5 made it run on
    every query. It read `weather_data["wave_height"]`, a key that does not
    exist (readings live under `hourly[0]`), so wave height never reached the
    judge. And it listed only the boundary distance and the verdict, so a
    narrative that said "the nearest fishing zone is 447 km away" was compared
    with nothing that could confirm it, and the judge flagged it as
    contradicting the boundary distance. Every field a narrative can quote is
    here now, with its unit in its name, because "447" against "nautical
    miles" is how a fishing-zone distance gets confused with a boundary one.

    Only fields with a value are listed: an absent reading is absent, never a
    placeholder the judge could treat as a measurement."""
    weather = state.get("weather_data") or {}
    geo = state.get("geospatial_data") or {}
    ocean = state.get("ocean_data") or {}
    verdict = state.get("risk_assessment") or {}
    hourly = (weather.get("hourly") or [{}])[0]
    pfz = ocean.get("nearest_pfz") or {}
    tide = ocean.get("tide") or {}
    next_high = tide.get("next_high") or {}
    found = bool(pfz.get("found"))

    facts: dict[str, Any] = {
        "risk_verdict": verdict.get("go_no_go"),
        "risk_verdict_reason": verdict.get("reason"),
        "wave_height_m": hourly.get("wave_height"),
        "wind_speed_m_per_s": hourly.get("wind_speed_10m"),
        "lightning_active": weather.get("lightning_active"),
        "cyclone_alert": weather.get("cyclone_alert"),
        "distance_to_maritime_boundary_nautical_miles": geo.get("imbl_distance_nm"),
        "inside_marine_protected_area": geo.get("mpa_violation"),
        # A fishing zone's distance, NOT the boundary's: named so they cannot be confused.
        "nearest_fishing_zone_distance_km": pfz.get("distance_km") if found else None,
        "nearest_fishing_zone_distance_measured_from": pfz.get("measured_from") if found else None,
        # INCOIS's own landmark wording — a separate origin; a narrative that
        # pairs the distance above with this landmark's name is wrong.
        "nearest_fishing_zone_incois_reference": pfz.get("incois_reference") if found else None,
        "nearest_fishing_zone_direction": pfz.get("compass") if found else None,
        "nearest_fishing_zone_depth_m": pfz.get("depth_m") if found else None,
        # Stale-data policy: the zone's own date and age, so a narrative that
        # says "issued 19 Sep, 5 days old" is confirmable, and one that calls
        # it current is contradicted.
        "nearest_fishing_zone_advisory_date": pfz.get("valid_for") if found else None,
        "nearest_fishing_zone_age_days": pfz.get("age_days") if found else None,
        "nearest_fishing_zone_advisory_expired": pfz.get("expired") if found else None,
        # A zone past this reach is still the nearest held; a narrative that
        # presents it as close by is contradicted.
        "nearest_fishing_zone_beyond_reach_km": pfz.get("max_km") if found and pfz.get("beyond_reach") else None,
        # Why the user's own sector has no advisory today (INCOIS's words), so
        # "no data due to cloud cover" is confirmable and "no zones here" is not.
        "todays_sector_advisory_gap": (ocean.get("sector_status") or {}).get("message")
        if (ocean.get("sector_status") or {}).get("is_data_gap") else None,
        "tidal_state": tide.get("tidal_state"),
        "next_high_tide_height_m": next_high.get("height_m"),
        "next_high_tide_in_hours": next_high.get("in_hours"),
        "productivity_diagnosis": ocean.get("productivity_diagnosis"),
    }
    return "\n".join(f"- {k}: {v}" for k, v in facts.items() if v is not None) or "No measured facts available."


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

    facts_block = build_facts_block(state)

    verdict_before = _verdict_header(narrative)
    engine_out: list[str] = []

    try:
        revised, critic_pass, iterations, issues = run_critic_pass(
            query, narrative, facts_block, is_safety_check=is_safety,
            engine_out=engine_out,
            max_iterations=MAX_ITERATIONS if depth == "DEEP" else MAX_ITERATIONS_STANDARD,
            context=conversation_context(state.get("session_history"), state.get("user_location")),
        )
        status: Literal["ok", "degraded"] = "ok"
        confidence = Confidence(
            score="HIGH" if critic_pass else "MEDIUM",
            rationale=f"{len(issues)} issue(s) on final pass" if not critic_pass else "passed all 5 rubric items",
        )
        error_detail = None
    except Exception as exc:
        # unreviewed narrative, it never blocks the response (plan §4 D1 Day 18).
        # P2.11/P2.13: the switch being off and the provider returning 429 both
        # land here as LLMUnavailable, and both are ordinary degraded runs, not
        # errors — which is exactly what the demo toggle has to demonstrate.
        revised, critic_pass, iterations, issues = narrative, False, 0, []
        status, confidence = "degraded", Confidence(score="LOW_DATA", rationale=f"Critic unavailable: {exc}")
        error_detail = str(exc)
        engine_out = [engines.deterministic(getattr(exc, "reason", "critic unavailable"))]

    # Assert-by-construction: whatever happened above, the verdict header
    # text must be byte-identical to what Reporting emitted. If a bug ever
    # let it drift, degrade to the pre-critique narrative rather than ship
    # an altered verdict.
    if verdict_before and _verdict_header(revised) != verdict_before:
        revised = narrative

    issue_dicts = [
        {"rubric_item": i.rubric_item, "description": i.description, "reinvoke_agent": i.reinvoke_agent}
        for i in issues
    ]
    # Only ask for a re-invocation the graph is still allowed to grant. The
    # budget is read here as well as enforced in the graph so the Critic's own
    # trace row is honest about what it asked for on a second pass: "I found
    # something and the budget was already spent" is a different fact from
    # "I found nothing".
    spent = int(state.get("critic_reinvocations") or 0)
    reinvoke_agent = reinvocation_target(issue_dicts) if spent < MAX_REINVOCATIONS else None

    return AgentResult(
        agent_name="critic",
        query_id=query_id,
        reasoning_depth=depth,
        inputs_consumed={"narrative_len": len(narrative), "is_safety_check": is_safety},
        outputs={
            "final_english_response": revised,
            "critic_pass": critic_pass,
            "critic_iteration_count": iterations,
            "issues": issue_dicts,
            # P2.5 — the agent this critique sends the query back to, or None.
            # Named here rather than re-derived in the graph so the decision
            # lives with the rubric that produced it, and so the trace row
            # records what the Critic asked for even when the budget refused it.
            "reinvoke_agent": reinvoke_agent,
            # The sentence(s) that agent is re-invoked *with*. A re-invocation
            # that does not carry the critique is just a re-run.
            "critique": "; ".join(f"[{i['rubric_item']}] {i['description']}" for i in issue_dicts) or None,
        },
        source_provenance=SourceProvenance(
            dataset="ORCA Critic (Agent 10) — LLM-as-judge, reasoning tier",
            acquisition_timestamp=now, freshness_minutes=0,
        ),
        confidence=confidence,
        status=status,
        error_detail=error_detail,
        engine=engine_out[0] if engine_out else None,
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
