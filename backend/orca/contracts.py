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
