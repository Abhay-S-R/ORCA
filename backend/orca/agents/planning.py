"""Agent 2 — Planning / Orchestrator (Architecture §3.1 + §4 routing table).
Rules tier only in Phase 1 — embedding-similarity and LLM fallback are
Phase 2 (plan §3.2 table: Agent 2 is "fallback only", rarely fires).

Ground Rule 1, load-bearing here specifically: classify_intent inspects
(normalized_query, session_history) — NEVER persona. This is the exact
function where the v1.0 routing bug would be reintroduced if persona ever
leaked in, which is why the CI persona-leak guard scans this whole package.
"""
from __future__ import annotations

from dataclasses import dataclass

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.state import ORCAState


@dataclass(frozen=True)
class RoutingRow:
    name: str
    keywords: tuple[str, ...]
    agents: tuple[str, ...]


# Architecture §4 routing table. Only the rows meaningful without Agents 3/5
# (Phase 2) or Agent 11 (Phase 3) are populated with real keyword sets;
# export/notify-me/proactive-geofence rows are named but return no match in
# Phase 1 — they need agents that don't exist yet, and a row that always
# fails to match is more honest than one that matches and dispatches to
# nothing.
ROUTING_TABLE: tuple[RoutingRow, ...] = (
    RoutingRow(
        "SAFETY_CHECK",
        ("safe to go to sea", "safe to fish", "venture into sea", "is it safe", "go to sea today", "go to sea tomorrow"),
        ("marine_data_discovery", "weather_intelligence", "ocean_analytics", "risk_assessment"),
    ),
    RoutingRow(
        "PFZ_NEAREST",
        ("nearest pfz", "fishing zone", "persistent fishing zone", "where to fish", "potential fishing"),
        ("marine_data_discovery", "ocean_analytics", "geospatial"),
    ),
    RoutingRow(
        "CONDITIONS",
        ("tide", "sea conditions", "current conditions", "wave height", "wind speed"),
        ("marine_data_discovery", "weather_intelligence", "ocean_analytics"),
    ),
    RoutingRow(
        "HAZARD_ALERTS",
        ("lightning", "cyclone", "storm alert", "hazard warning", "weather warning"),
        ("weather_intelligence", "risk_assessment"),
    ),
    RoutingRow(
        "ZONES_TO_AVOID",
        ("zones to avoid", "boundary", "geofence", "restricted zone", "marine park"),
        ("geospatial", "risk_assessment"),
    ),
)

# §4.2 no-match fallback — Discovery + Weather + Ocean Analytics, never an
# empty response.
NO_MATCH_FALLBACK_AGENTS = ("marine_data_discovery", "weather_intelligence", "ocean_analytics")


def classify_intent(normalized_query: str) -> list[tuple[str, float]]:
    """Tool per Architecture §3.1 Agent 2. Deterministic keyword match —
    confidence is 1.0 on any match (a rules tier has no partial credit) or
    absent from the list entirely on no match."""
    query_lower = normalized_query.lower()
    matches = []
    for row in ROUTING_TABLE:
        if any(kw in query_lower for kw in row.keywords):
            matches.append((row.name, 1.0))
    return matches


def generate_execution_plan(matched_intent_rows: list[str], reasoning_depth: str) -> list[str]:
    """Tool per Architecture §3.1 Agent 2. §4.1 multi-match: union of every
    matched row's agents, not just the first. §4.2 no-match: the minimal
    default path, never an empty plan."""
    if not matched_intent_rows:
        return list(NO_MATCH_FALLBACK_AGENTS)

    by_name = {row.name: row for row in ROUTING_TABLE}
    agents: list[str] = []
    for row_name in matched_intent_rows:
        row = by_name.get(row_name)
        if row is None:
            continue
        for agent in row.agents:
            if agent not in agents:
                agents.append(agent)
    return agents or list(NO_MATCH_FALLBACK_AGENTS)


def check_early_exit(partial_agent_results: dict) -> bool:
    """Tool per Architecture §3.1 Agent 2 / §9.3. NOT implemented in Phase 1
    — always returns False. §9 optimizations (including cost-based early
    exit) are explicitly Phase 4 only, on a graph that is already stable;
    building this now, before there is a stable graph to short-circuit,
    is exactly the scope creep the plan forbids."""
    return False


def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Distress bypass (Architecture §4, last
    row) is NOT handled here — it happens in orca/graph/ before Planning is
    even invoked, per the architecture's own framing: distress "bypasses
    this table entirely," which means bypassing this agent, not a branch
    inside it."""
    query = state.get("normalized_english_query") or state.get("raw_user_query", "")
    matches = classify_intent(query)
    matched_rows = [name for name, _ in matches]
    execution_plan = generate_execution_plan(matched_rows, state.get("reasoning_depth", "SHALLOW"))

    confidence = (
        Confidence(score="HIGH", rationale=f"Matched routing row(s): {', '.join(matched_rows)}")
        if matched_rows
        else Confidence(score="MEDIUM", rationale="No routing row matched — answering the closest general-conditions interpretation")
    )

    return AgentResult(
        agent_name="planning",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"normalized_query": query},
        outputs={"matched_intent_rows": matched_rows, "execution_plan": execution_plan},
        source_provenance=SourceProvenance(
            dataset="Deterministic rules-tier routing table (Architecture §4)",
            acquisition_timestamp="",
            freshness_minutes=0,
        ),
        confidence=confidence,
    )
