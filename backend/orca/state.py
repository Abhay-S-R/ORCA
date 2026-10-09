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
    # P3.1 (`R-AUTH-1`) — a signed-in user's `users.language`, used only when
    # script detection finds no Indic codepoint at all (empty text — a voice
    # query that transcribed to nothing, or the SOS control with no message);
    # a language actually detected IN the text always wins. None for an
    # anonymous caller or one with no stored language preference.
    user_language_default: str | None
    # The /query handler's own translation of raw_user_query — {"raw",
    # "language", "english", "rung"} — so ingress does not translate twice.
    pretranslated: dict[str, str] | None

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
    # P6.6 — set only by `/demo`. Present -> marine_data_discovery,
    # weather_intelligence, ocean_analytics and geospatial each return a
    # pinned prior real reading (orca/demo_fixtures.py) instead of fetching
    # live, so a scenario's verdict survives whatever the weather is doing on
    # demo day. None on every ordinary query — every one of those four checks
    # it first and falls through to its normal live path when it is absent.
    demo_scenario: str | None

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

    # Prompt Routing Revamp §6 & Pipeline Consolidation PC2 — Planning agent's
    # structured understanding and validation output (unified in planning_node).
    understood_kind: str | None  # "sea_question" | "greeting_or_small_talk" | ...
    understood_intents: list[str]  # subset of ROUTING_TABLE row names
    understood_places: list[dict[str, Any]]  # [{raw, normalized}, ...]
    understood_when: dict[str, Any] | None  # {start, end} ISO or None
    understood_is_followup: bool
    # PC2.1 (`R-AGENT-2`, `PS-ARCH`) — the agent set Understand suggested for this
    # query, validated against _KNOWN_SPECIALISTS in understand.py. Recorded here
    # for the trace and for PC2+ to consume; routing is unchanged until PC3.
    planned_agents: list[str]  # subset of understand._KNOWN_SPECIALISTS
    # PC5.2 (`PS-C1`, `PS-C10`) — the message in plain English as the planning model read it.
    # DISPLAY ONLY: never used for routing, place lookup or validation (so a wrong reading cannot
    # move a verdict). PC5.5 shows it on the answer card.
    understood_english_reading: str | None
    # PC5.8 (`PS-C2`) — the language the user EXPLICITLY asked the answer in, one of the ten
    # supported codes, validated in understand.py; None when no language was requested. When set it
    # overrides the language egress would otherwise pick (the script of the question).
    reply_language: str | None
    # CONTEXT-2: the finished frame of the last answer re-rendered in `reply_language` (set by planning_node)
    language_rerender: dict[str, Any]

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
    # Chatbot plan C0.2 — which engine wrote `final_english_response`
    # (orca/engines.py label: "gemini · …", "ollama · … (fallback)", or
    # "Deterministic — …" for the last-resort paragraph the UI labels), and
    # whether a refused message was only a greeting or small talk.
    response_engine: str | None
    small_talk: bool
    evidence_citations: list[dict[str, Any]]
    confidence_tier: str
    confidence_reason: str | None
    persona_correction_available: bool
    audit_trace_log: Annotated[list[dict[str, Any]], operator.add]
