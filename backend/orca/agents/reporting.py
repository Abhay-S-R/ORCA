"""Agent 9 (Reporting) — plan §4 S6 Day 6 (thin core), extended §5 D1 Day 12
(4-persona rendering matrix, result_refs, export formatter).

Assembles the AgentResults already sitting in ORCAState into one
citation-backed payload, mints one citation per contributing agent —
exit criterion 4 ("every number on screen carries dataset + timestamp")
depends on citations existing, not on prose — and links each citation back
to its full AgentResult via `result_refs` so a provenance popover can
resolve without a second query.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Literal

from orca.contracts import AgentResult

_CONFIDENCE_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW_DATA": 2}

Persona = Literal["fisherman", "commercial_navigator", "researcher", "coastal_authority"]


@dataclass(frozen=True)
class Citation:
    agent_name: str
    dataset: str
    acquisition_timestamp: str
    freshness_minutes: int


@dataclass(frozen=True)
class AssembledResponse:
    query_id: str
    summary_lines: tuple[str, ...]
    citations: tuple[Citation, ...]
    confidence_tier: str  # worst of the contributing agents' confidence scores
    # One dict per citation, same order, linking it back to the AgentResult
    # that produced it (Architecture §6 `source_provenance` + §13 traceability)
    # — a frontend provenance popover reads this instead of a second query.
    result_refs: tuple[dict[str, Any], ...] = ()


def assemble_response(query_id: str, results: list[AgentResult]) -> AssembledResponse:
    """Combine every completed agent's output into one citation-backed payload.

    `results` should be only agents that actually ran — a failed or skipped
    agent contributes nothing rather than a placeholder sentence.
    """
    usable = [r for r in results if r.status in ("ok", "degraded")]
    summary_lines = tuple(f"{r.agent_name}: {_format_outputs(r.outputs)}" for r in usable)
    citations = tuple(
        Citation(
            agent_name=r.agent_name,
            dataset=r.source_provenance.dataset,
            acquisition_timestamp=r.source_provenance.acquisition_timestamp,
            freshness_minutes=r.source_provenance.freshness_minutes,
        )
        for r in usable
    )
    result_refs = tuple(
        {"agent_name": r.agent_name, "outputs": r.outputs, "confidence": r.confidence.score}
        for r in usable
    )
    worst = max(
        (r.confidence.score for r in usable),
        key=lambda s: _CONFIDENCE_RANK.get(s, 2),
        default="LOW_DATA",
    )
    return AssembledResponse(
        query_id=query_id, summary_lines=summary_lines, citations=citations,
        confidence_tier=worst, result_refs=result_refs,
    )


def _format_outputs(outputs: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in outputs.items())


# Architecture §2.6 output rendering matrix — one instruction block per
# persona, appended to the shared prompt skeleton in synthesize_narrative.
# Each entry describes *how* to say it; the verdict itself (*what* to say)
# is fixed above this and never touched here (Ground Rule 2).
_PERSONA_RENDERING_INSTRUCTIONS: dict[str, str] = {
    "fisherman": (
        "Plain, simple language a fisherman reads at a glance. 2-3 short "
        "sentences. Where rule 1 requires the GO/CAUTION/NO_GO banner, lead with "
        "it, then one distance and direction if relevant (e.g. 'boundary is "
        "12nm east'). No jargon, "
        "no numbers beyond what changes the decision."
    ),
    "commercial_navigator": (
        "Waypoint-style and ETA-relevant. Reference bathymetry and tidal "
        "timing where the telemetry supports it. More technical than the "
        "fisherman rendering — assume the reader plans a route, not just a "
        "yes/no trip decision. 3-5 sentences."
    ),
    "researcher": (
        "Full statistical summary: report exact measured values with units, "
        "sensor/dataset provenance, and freshness for each figure cited. "
        "State uncertainty or discrepancy explicitly where the telemetry "
        "shows it (e.g. cross-source deltas). Citable, methodology-first tone."
    ),
    "coastal_authority": (
        "District-level threat summary in CAP-alert structure: severity, "
        "affected area, recommended action, and effective time window. "
        "Broadcast/SMS-template tone — terse, unambiguous, suitable for "
        "onward relay to an IVR or SMS channel without further editing."
    ),
}


def describe_location(user_location: dict[str, Any] | None) -> str:
    """One sentence naming the position every number in a response was
    computed at, for the narrative prompt.

    This exists because the alternative is silent substitution. The LLM sees
    the raw user query, so if it is not told which position the telemetry
    belongs to it will happily narrate Thoothukudi's numbers under whatever
    place name the user typed — 53 nm from the maritime boundary instead of
    0.4 nm. When nothing resolved, the prompt has to say so in as many words,
    because "somewhere in the pilot region" is the honest claim.
    """
    loc = user_location or {}
    lat, lon = loc.get("lat"), loc.get("lon")
    position = f"{lat}, {lon}" if lat is not None and lon is not None else "an unknown position"
    if loc.get("place_source") == "regional_default":
        return (
            f"The telemetry below was measured at the pilot region's default position ({position}) "
            "because the query named no location that could be resolved and no GPS fix was supplied."
        )
    name = loc.get("place_name")
    return f"The telemetry below was measured at {name} ({position})." if name else (
        f"The telemetry below was measured at the position supplied with the query ({position})."
    )


def synthesize_narrative(
    query: str,
    verdict: dict[str, Any],
    results: list[AgentResult],
    persona: str = "fisherman",
    user_location: dict[str, Any] | None = None,
    lead_with_verdict: bool = True,
) -> str:
    """Synthesizes a persona-tailored narrative using the mid-tier LLM.

    CRITICAL INVARIANTS:
    1. Ground Rule 2: The safety verdict (GO / CAUTION / NO_GO) is predetermined by
       deterministic Python arithmetic (Agent 7) and MUST NOT be altered.
    2. Ground Rule 1: Intent decides what fires; persona decides how it's said.
    3. Fallback: If the LLM is not configured, errors out, or attempts to
       change the verdict, degrade immediately to the deterministic verdict line.
    4. The narrative may only claim the location it was actually given
       (`user_location`), never the one the user's wording implies.
    5. `lead_with_verdict=False` suppresses the verdict *header* on an answer
       to a question that was not about safety — it never suppresses the
       verdict itself. See `should_lead_with_verdict`.
    """
    verdict_str = verdict.get("go_no_go", "UNKNOWN")
    reason_str = verdict.get("reason", "no verdict computed")
    fallback_line = f"{verdict_str}: {reason_str}"
    # A non-GO verdict is never demoted, whatever was asked, so re-derive the
    # floor here rather than trusting the caller with a life-safety decision.
    lead_with_verdict = lead_with_verdict or should_lead_with_verdict(verdict, [])

    try:
        from orca.llm.tiers import llm
        client = llm("mid")
    except Exception:  # noqa: BLE001
        return fallback_line

    facts = []
    for r in results:
        if r.status in ("ok", "degraded"):
            outputs_str = ", ".join(f"{k}={v}" for k, v in r.outputs.items() if v is not None)
            facts.append(f"- {r.agent_name} ({r.source_provenance.dataset}): {outputs_str}")
    facts_block = "\n".join(facts) if facts else "No active sensor inputs."

    rendering_instruction = _PERSONA_RENDERING_INSTRUCTIONS.get(
        persona, _PERSONA_RENDERING_INSTRUCTIONS["fisherman"]
    )

    header_rule = (
        f'Your response MUST begin with the exact verdict header: "{verdict_str}: {reason_str}".'
        if lead_with_verdict
        else (
            "Answer the question that was actually asked. The verdict above is a clear "
            f'"{verdict_str}" and the user did not ask about safety, so do NOT open with a '
            "safety verdict header — mention conditions only where they bear on the answer."
        )
    )

    prompt = f"""You are a marine safety advisor communicating critical advice to a {persona}.

USER QUERY: "{query}"

LOCATION THIS ADVICE IS FOR:
{describe_location(user_location)}

DETERMINISTIC SAFETY ASSESSMENT (ALREADY COMPUTED BY SAFETY RULES):
- VERDICT: {verdict_str}
- REASON: {reason_str}

MEASURED TELEMETRY & FACTS:
{facts_block}

CRITICAL RULES:
1. {header_rule}
2. You MUST NOT alter, contradict, soften, or question the verdict. The arithmetic is final.
3. Rendering for this persona: {rendering_instruction}
4. Location honesty. Refer only to the location stated above. If the user named a
   different place, do NOT present these readings as being for that place — say
   plainly that you have no data for it and that the readings are for the location
   stated above. Never name a place the location line does not name.
5. Never mention agents, models, internal component names, or that you are an AI.
6. Keep the tone calm, practical, direct, and authoritative for sea navigation. Do not use generic AI disclaimers."""

    try:
        narrative = client.complete([{"role": "user", "content": prompt}]).strip()
        # The header is re-asserted only when it was required. Prepending it to
        # an answer that was never supposed to carry one is how "where are the
        # nearest fishing zones?" ended up opening with
        # "GO: All Parameters Within Safe Operational Limits".
        if lead_with_verdict and verdict_str not in narrative:
            return f"{fallback_line}\n\n{narrative}"
        return narrative
    except Exception:  # noqa: BLE001
        return fallback_line


# Intent rows that are questions about safety. A verdict header belongs at the
# top of an answer to one of these; on anything else it is noise that trains
# people to skim past the one line that matters when it is not "GO".
_SAFETY_SHAPED_ROWS = frozenset({"SAFETY_CHECK", "HAZARD_ALERTS", "ZONES_TO_AVOID"})


def should_lead_with_verdict(verdict: dict[str, Any], matched_intent_rows: list[str]) -> bool:
    """Whether the narrative opens with the safety verdict.

    Ground Rule 2 is untouched: the verdict is still computed by deterministic
    arithmetic for every query and still shipped in the structured response.
    This decides presentation only, and it is deliberately asymmetric — a
    CAUTION or NO_GO leads *whatever* was asked, because someone who asked
    about tides while a squall builds still has to be told not to sail. Only a
    GO on a question that was not about safety is demoted, so the header keeps
    meaning something when it appears.
    """
    if verdict.get("go_no_go") != "GO":
        return True
    return bool(_SAFETY_SHAPED_ROWS & set(matched_intent_rows or []))


def format_export(assembled: AssembledResponse, fmt: Literal["csv", "json"]) -> str:
    """Export-formatter mode (Architecture §2.6 researcher rendering: 'CSV/
    NetCDF export'; NetCDF is out of scope — it needs gridded array data no
    agent here produces, CSV/JSON cover the same tabular citations). Every
    row carries its own dataset + timestamp + freshness metadata columns,
    the same provenance fields exit criterion 4 requires on-screen."""
    if fmt == "json":
        return json.dumps(
            {
                "query_id": assembled.query_id,
                "confidence_tier": assembled.confidence_tier,
                "citations": [
                    {
                        "agent_name": c.agent_name,
                        "dataset": c.dataset,
                        "acquisition_timestamp": c.acquisition_timestamp,
                        "freshness_minutes": c.freshness_minutes,
                    }
                    for c in assembled.citations
                ],
                "result_refs": list(assembled.result_refs),
            },
            indent=2,
        )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["agent_name", "dataset", "acquisition_timestamp", "freshness_minutes", "outputs"])
    refs_by_agent = {ref["agent_name"]: ref["outputs"] for ref in assembled.result_refs}
    for c in assembled.citations:
        writer.writerow([
            c.agent_name, c.dataset, c.acquisition_timestamp, c.freshness_minutes,
            json.dumps(refs_by_agent.get(c.agent_name, {})),
        ])
    return buf.getvalue()


if __name__ == "__main__":
    from orca.contracts import Confidence, SourceProvenance

    results = [
        AgentResult(
            agent_name="geospatial",
            query_id="q-1",
            reasoning_depth="STANDARD",
            inputs_consumed={"lat": 8.70, "lon": 78.50},
            outputs={"imbl_distance_nm": 16.29},
            source_provenance=SourceProvenance(
                dataset="Marine Regions VLIZ EEZ", acquisition_timestamp="2026-09-02T00:00:00Z", freshness_minutes=0
            ),
            confidence=Confidence(score="HIGH", rationale="static reference geometry"),
        ),
        AgentResult(
            agent_name="risk_assessment",
            query_id="q-1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs={"verdict": "CAUTION"},
            source_provenance=SourceProvenance(
                dataset="evaluate_marine_safety", acquisition_timestamp="2026-09-02T00:00:00Z", freshness_minutes=5
            ),
            confidence=Confidence(score="MEDIUM", rationale="one stale input"),
        ),
    ]
    assembled = assemble_response("q-1", results)
    assert len(assembled.citations) == 2
    assert assembled.confidence_tier == "MEDIUM"  # worst of HIGH, MEDIUM
    print("reporting self-check ok:", assembled)
