"""Agent 9 (Reporting), thin — plan §4 S6 Day 6.

Assembles the AgentResults already sitting in ORCAState into one
citation-backed payload. Deliberately thin: narrative generation is a
fuller Agent 9 job for later phases. Phase 1 has no LLM pass here, so this
concatenates outputs and mints one citation per contributing agent —
exit criterion 4 ("every number on screen carries dataset + timestamp")
depends on citations existing, not on prose.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orca.contracts import AgentResult

_CONFIDENCE_RANK = {"HIGH": 0, "MEDIUM": 1, "LOW_DATA": 2}


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
    worst = max(
        (r.confidence.score for r in usable),
        key=lambda s: _CONFIDENCE_RANK.get(s, 2),
        default="LOW_DATA",
    )
    return AssembledResponse(
        query_id=query_id, summary_lines=summary_lines, citations=citations, confidence_tier=worst
    )


def _format_outputs(outputs: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in outputs.items())


def synthesize_narrative(
    query: str,
    verdict: dict[str, Any],
    results: list[AgentResult],
    persona: str = "fisherman",
) -> str:
    """Synthesizes a persona-tailored narrative using the mid-tier LLM.

    CRITICAL INVARIANTS:
    1. Ground Rule 2: The safety verdict (GO / CAUTION / NO_GO) is predetermined by
       deterministic Python arithmetic (Agent 7) and MUST NOT be altered.
    2. Ground Rule 1: Intent decides what fires; persona decides how it's said.
    3. Fallback: If the LLM is not configured, errors out, or attempts to
       change the verdict, degrade immediately to the deterministic verdict line.
    """
    verdict_str = verdict.get("go_no_go", "UNKNOWN")
    reason_str = verdict.get("reason", "no verdict computed")
    fallback_line = f"{verdict_str}: {reason_str}"

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

    prompt = f"""You are ORCA Reporting Agent (Agent 9), communicating critical marine safety advice to a {persona} in South Tamil Nadu (Thoothukudi / Gulf of Mannar).

USER QUERY: "{query}"

DETERMINISTIC SAFETY ASSESSMENT (ALREADY COMPUTED BY SAFETY RULES):
- VERDICT: {verdict_str}
- REASON: {reason_str}

MEASURED TELEMETRY & FACTS:
{facts_block}

CRITICAL RULES:
1. Your response MUST begin with the exact verdict header: "{verdict_str}: {reason_str}".
2. You MUST NOT alter, contradict, soften, or question the verdict. The arithmetic is final.
3. In 2-3 sentences directly addressing the {persona}, explain the conditions (wave height, wind speed, lightning/cyclone, and distance to Sri Lanka EEZ/boundary) based strictly on the telemetry.
4. Keep the tone calm, practical, direct, and authoritative for sea navigation. Do not use generic AI disclaimers."""

    try:
        narrative = client.complete([{"role": "user", "content": prompt}]).strip()
        if verdict_str not in narrative:
            return f"{fallback_line}\n\n{narrative}"
        return narrative
    except Exception:  # noqa: BLE001
        return fallback_line


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
