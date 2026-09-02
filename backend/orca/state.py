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
    user_location: dict[str, float] | None
    vessel_class: str | None  # required by Agent 7's vessel-class threshold deltas (§4.6)

    discovery_data: dict[str, Any]
    weather_data: dict[str, Any]
    ocean_data: dict[str, Any]
    geospatial_data: dict[str, Any]
    risk_assessment: dict[str, Any]
    visualization_payload: dict[str, Any]

    critic_pass: bool | None  # only set when reasoning_depth == "DEEP"
    critic_iteration_count: int

    distress_flag: bool  # set by Agent 12's detection, checked before any other node executes
    sentinel_subscription: dict[str, Any] | None  # set on ALERT_SUBSCRIPTION intent

    final_english_response: str
    final_vernacular_response: str
    evidence_citations: list[dict[str, Any]]
    confidence_tier: str
    persona_correction_available: bool
    audit_trace_log: Annotated[list[dict[str, Any]], operator.add]
