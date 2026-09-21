"""ORCAState — the shared LangGraph state object. Frozen contract (plan §6, Day 3).

Verbatim from Architecture §5 (v4). Do not add fields here without updating
the architecture doc first — this file follows that doc, it does not lead it.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ORCAState(TypedDict):
    session_id: str
    query_id: str
    raw_user_query: str
    normalized_english_query: str
    detected_language: str

    session_history: list[dict[str, Any]]  # prior turns for follow-up resolution

    stakeholder_persona: str  # "fisherman" | "commercial_navigator" | "researcher" |
    # "coastal_authority" | "unresolved"
    stakeholder_persona_source: str  # "explicit" | "inferred_high" | "inferred_low"
    stakeholder_persona_confidence: float  # 0.0-1.0, only set when source starts with "inferred"
    reasoning_depth: str  # "SHALLOW" | "STANDARD" | "DEEP"

    execution_plan: list[str]
    matched_intent_rows: list[str]  # which routing-table rows matched (supports multi-match)
    early_exit_triggered: bool  # did an early-cancel rule cancel any pending calls?
    next_node: str
    completed_nodes: Annotated[list[str], operator.add]

    target_bbox: dict[str, float]
    target_time_window: dict[str, str]
    user_location: dict[str, Any] | None
    vessel_class: str | None  # required by Agent 7's vessel-class threshold deltas (§4.6)

    discovery_data: dict[str, Any]
    weather_data: dict[str, Any]
    ocean_data: dict[str, Any]
    geospatial_data: dict[str, Any]
    risk_assessment: dict[str, Any]
    visualization_payload: dict[str, Any]

    critic_pass: bool | None  # set on every query since P2.5 (was DEEP-only)
    critic_iteration_count: int
    # P2.5 (`R-AGENT-1`) — the Critic-driven re-invocation loop. `critic_issues`
    # is what the last pass found (rubric item, description, the agent it
    # traces back to); `critic_reinvoke_agent` is the specialist the graph is
    # routing back to right now, read by that agent as the critique to answer;
    # `critic_reinvocations` is the spent budget, capped at
    # critic.MAX_REINVOCATIONS so the loop cannot run away on a judge's query.
    critic_issues: list[dict[str, Any]]
    critic_reinvoke_agent: str | None
    critic_critique: str | None
    critic_reinvocations: int

    # P2.6 (`R-AGENT-2`, `R-PS-4`) — Agent 3's chosen-sources-with-rationale,
    # decided ONCE before the fan-out and consumed by the three specialists,
    # instead of each of them picking its own sources independently and the
    # result being smuggled out as a field on Ocean Analytics.
    discovery_sources: dict[str, Any]

    # P2.7 (`R-JUDGE-3`) — presentation, separated from execution. `skipped_agents`
    # records what the plan (or P2.12's early exit) decided not to surface and
    # why, so a smaller answer is visibly a decision rather than a gap.
    # Additive (operator.add), like `disclosures`: more than one node can skip
    # or cancel in the same query (Ocean Analytics AND Visualization for a
    # subscription question; either of them plus a P2.12-cancelled Critic), and
    # a plain overwrite silently kept only the last writer — found by the live
    # run, where a span said "skipped" that the response's own list omitted.
    skipped_agents: Annotated[list[dict[str, Any]], operator.add]
    # P2.4 (`R-PS-5`, `R-AGENT-3`) — where two sources covering the same
    # variable disagreed, what was done about it, and by how much.
    reconciliation: list[dict[str, Any]]
    # P2.13 — how many provider calls this query actually made.
    llm_call_count: int

    distress_flag: bool  # set by Agent 12's detection, checked before any other node executes
    sentinel_subscription: dict[str, Any] | None  # set on ALERT_SUBSCRIPTION intent

    # Phase 1. `query_outcome` is one of contracts.QueryOutcome — set by the
    # graph's own guards, never by an agent. `place_resolution` is
    # place_resolution.PlaceResolution.as_dict(): which position every number
    # below was computed at, whether that position was the user's choice, and
    # the candidates to offer when it was not. `disclosures` is additive
    # because more than one node has something to disclose about the same
    # answer (a carried-over place AND a fallback sector), and dropping one of
    # them is the "a fallback that is not disclosed is a lie" failure.
    query_outcome: str
    place_resolution: dict[str, Any] | None
    disclosures: Annotated[list[str], operator.add]

    final_english_response: str
    final_vernacular_response: str
    evidence_citations: list[dict[str, Any]]
    confidence_tier: str
    persona_correction_available: bool
    audit_trace_log: Annotated[list[dict[str, Any]], operator.add]
