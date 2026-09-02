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
