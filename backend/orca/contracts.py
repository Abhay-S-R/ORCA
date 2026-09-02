"""AgentResult envelope — the frozen inter-agent hand-off contract (plan §6, Day 3).

Matches Architecture §6. `persona_context` is deliberately absent: specialist
agents never learn who is asking (Ground Rule 1 — intent decides what fires,
persona decides how it's said). Only Agent 1 (ingress/egress) and Agent 9
(Reporting) ever see persona.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class SourceProvenance:
    dataset: str  # e.g. "Open-Meteo Marine API / ECMWF WAM Blend"
    acquisition_timestamp: str  # ISO 8601, UTC
    freshness_minutes: int


@dataclass(frozen=True)
class Confidence:
    # Underscore, not hyphen — matches the confidence_tier Postgres enum
    # (infra/db/001_init.sql). Postgres enums cannot contain hyphens; the
    # architecture doc writes "LOW-DATA" for readability only. LOW_DATA is
    # canonical everywhere in code.
    score: Literal["HIGH", "MEDIUM", "LOW_DATA"]
    rationale: str


@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    query_id: str
    reasoning_depth: Literal["SHALLOW", "STANDARD", "DEEP"]
    inputs_consumed: dict[str, Any]
    outputs: dict[str, Any]
    source_provenance: SourceProvenance
    confidence: Confidence
    status: Literal["ok", "degraded", "failed", "skipped", "cancelled"] = "ok"
    error_detail: str | None = None


_VALID_REASONING_DEPTHS = ("SHALLOW", "STANDARD", "DEEP")


def coerce_reasoning_depth(value: str) -> Literal["SHALLOW", "STANDARD", "DEEP"]:
    """ORCAState.reasoning_depth is a plain `str` (verbatim from Architecture
    §5); AgentResult.reasoning_depth is the stricter Literal these three
    values. Every agent's run() constructs an AgentResult from state, so this
    is the one place that gap gets validated — a typo or a stale value in
    state should fail loud (or degrade to SHALLOW here, logged) rather than
    silently satisfy a type checker that can't see the actual runtime value."""
    if value in _VALID_REASONING_DEPTHS:
        return value  # type: ignore[return-value]  # narrowed by the check above
    return "SHALLOW"


_VALID_CONFIDENCE_SCORES = ("HIGH", "MEDIUM", "LOW_DATA")


def coerce_confidence_score(value: str) -> Literal["HIGH", "MEDIUM", "LOW_DATA"]:
    """Same gap as coerce_reasoning_depth, for confidence_tier — ORCAState
    carries it as a plain `str` (e.g. reconstructing a Confidence from
    state["confidence_tier"] when the graph needs one), Confidence.score is
    the stricter Literal. An invalid/stale value degrades to the most
    conservative reading (LOW_DATA), never the most confident one — the
    failure direction that matters here is never claiming more certainty
    than actually validated."""
    if value in _VALID_CONFIDENCE_SCORES:
        return value  # type: ignore[return-value]  # narrowed by the check above
    return "LOW_DATA"
