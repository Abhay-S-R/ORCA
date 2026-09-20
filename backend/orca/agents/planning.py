"""Agent 2 — Planning / Orchestrator (Architecture §3.1 + §4 routing table).
Three routing tiers, tried in order (plan §5 D1 Day 11): rules (exact
keyword match) -> embedding-similarity fallback -> LLM at "cheap". Tier 1
handles almost everything; 2 and 3 only run when it finds nothing.

Ground Rule 1, load-bearing here specifically: classify_intent inspects
(normalized_query, session_history) — NEVER persona. This is the exact
function where the v1.0 routing bug would be reintroduced if persona ever
leaked in, which is why the CI persona-leak guard scans this whole package.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.state import ORCAState


@dataclass(frozen=True)
class RoutingRow:
    name: str
    keywords: tuple[str, ...]
    agents: tuple[str, ...]


# Architecture §4 routing table (orca_final §3.2). Every row does real work:
# the first five dispatch the agents that answer them; the last seven (P5.29)
# also get one concrete action on the answer card from orca/intent_actions.py,
# built from what exists today. A row that could only dispatch to nothing is
# still left out — the scenario rows (TIMING, COUNTERFACTUAL, COMPARISON,
# ENDURANCE, WORTHWHILENESS) arrive with P5.9 and HISTORICAL with P5.25.
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
    RoutingRow(
        "ROUTE",
        ("safest route", "route from", "route to", "passage from", "voyage from", "plan a voyage", "plan my route", "navigate from"),
        ("geospatial", "weather_intelligence", "risk_assessment"),
    ),
    RoutingRow(
        "DIAGNOSTIC",
        ("why has", "declined", "decline in", "fewer fish", "productivity", "catch dropped", "catch has dropped"),
        ("marine_data_discovery", "ocean_analytics"),
    ),
    RoutingRow(
        "REGULATORY",
        ("allowed to fish", "fishing ban", "ban period", "fishing banned", "closed season", "fishing season", "legal to fish"),
        ("geospatial", "risk_assessment"),
    ),
    RoutingRow(
        "META",
        ("how do you know", "are you sure", "who made you", "where does this data", "your source", "can i trust", "how sure are you"),
        (),
    ),
    RoutingRow(
        "EXPORT",
        ("export", "download", "csv", "geojson", "netcdf", "as a spreadsheet"),
        ("marine_data_discovery", "ocean_analytics"),
    ),
    RoutingRow(
        "SUBSCRIPTION",
        ("watch for me", "notify me", "alert me when", "tell me when", "subscribe", "keep an eye on"),
        ("weather_intelligence", "risk_assessment"),
    ),
    RoutingRow(
        "ADMINISTRATIVE",
        ("change my home port", "update my boat", "my profile", "register my boat", "change my vessel", "my account"),
        (),
    ),
)

# §4.2 no-match fallback — Discovery + Weather + Ocean Analytics, never an
# empty response.
NO_MATCH_FALLBACK_AGENTS = ("marine_data_discovery", "weather_intelligence", "ocean_analytics")


def _tier1_rules(normalized_query: str) -> list[tuple[str, float]]:
    """Tier 1 — deterministic keyword match. Confidence is 1.0 on any match
    (a rules tier has no partial credit) or absent from the list entirely
    on no match."""
    query_lower = normalized_query.lower()
    matches = []
    for row in ROUTING_TABLE:
        if any(kw in query_lower for kw in row.keywords):
            matches.append((row.name, 1.0))
    return matches


_STOPWORDS = {
    "is", "it", "to", "the", "a", "an", "i", "my", "can", "you", "today",
    "tomorrow", "near", "and", "in", "at", "of", "for", "this", "me", "do",
}

# Small hand-curated synonym expansion — this is a word-overlap scorer, not
# a sentence-transformer (plan §5 D1 Day 11 explicitly allows this: "basic
# TF-IDF / word-overlap scoring — no external model needed"). Expanding a
# handful of common paraphrase words is what lets "take my boat out" land on
# SAFETY_CHECK's "go to sea" keywords despite sharing no literal words.
_SYNONYMS: dict[str, set[str]] = {
    "boat": {"sea", "vessel", "fish", "venture"},
    "out": {"venture", "go"},
    "take": {"go", "venture"},
    "vessel": {"boat", "sea"},
}

_TIER2_THRESHOLD = 0.45


def _significant_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOPWORDS}


def _expand(words: set[str]) -> set[str]:
    expanded = set(words)
    for w in words:
        expanded |= _SYNONYMS.get(w, set())
    return expanded


def _tier2_embedding_similarity(normalized_query: str) -> list[tuple[str, float]]:
    """Tier 2 — word-overlap similarity fallback (Architecture §9.5). Scores
    each row 0.0-1.0 as (shared words / row's keyword-word count) after
    synonym expansion, and keeps any row at or above `_TIER2_THRESHOLD`.
    Catches paraphrases Tier 1's exact-substring match misses."""
    query_words = _expand(_significant_words(normalized_query))
    matches: list[tuple[str, float]] = []
    for row in ROUTING_TABLE:
        row_words = _significant_words(" ".join(row.keywords))
        if not row_words:
            continue
        overlap = len(query_words & row_words) / len(row_words)
        if overlap >= _TIER2_THRESHOLD:
            matches.append((row.name, round(overlap, 2)))
    return matches


def _tier3_llm_fallback(normalized_query: str, session_history: list[dict] | None = None) -> list[tuple[str, float]]:
    """Tier 3 — LLM at "cheap" (plan §5 D1 Day 11), tried only when Tiers 1
    and 2 both find nothing. Confidence is fixed at 0.7 — LLM-inferred, not
    the rules tier's certain 1.0 — and any answer outside the known routing
    row names (including a raised exception, missing API key, or "NONE")
    degrades to no match, never a made-up row."""
    try:
        from orca.llm.tiers import llm
        client = llm("cheap")
    except Exception:  # noqa: BLE001 — no LLM configured is a normal no-match path here
        return []

    row_names = ", ".join(row.name for row in ROUTING_TABLE)
    # A follow-up is classified in the context of the question before it.
    # Without this the model read "What about tomorrow evening?" cold, guessed
    # CONDITIONS, and a safety question's follow-up lost its safety intent —
    # carry_intent never ran because this tier had already "matched".
    previous = (session_history or [{}])[-1]
    previous_query = previous.get("english_query") or previous.get("query")
    context = (
        f'This is a follow-up. The previous question in the conversation was: "{previous_query}". '
        "Classify what the user is asking now, reading the query in that context.\n"
        if previous_query
        else ""
    )
    prompt = (
        "Classify this fisherman's marine-safety query into exactly one of "
        f"these categories: {row_names}, or NONE if none apply.\n"
        f"{context}"
        f'Query: "{normalized_query}"\n'
        "Respond with only the category name, nothing else."
    )
    try:
        raw = client.complete([{"role": "user", "content": prompt}]).strip().upper()
    except Exception:  # noqa: BLE001 — an LLM failure is a no-match, not a crash
        return []

    valid_names = {row.name for row in ROUTING_TABLE}
    if raw in valid_names:
        return [(raw, 0.7)]
    return []


def classify_intent(normalized_query: str, session_history: list[dict] | None = None) -> list[tuple[str, float]]:
    """Tool per Architecture §3.1 Agent 2. Tries Tier 1 (rules), then Tier 2
    (embedding/word-overlap similarity), then Tier 3 (LLM cheap-tier) in
    order, returning the first tier's matches — a higher tier only runs when
    every tier before it found nothing (plan §5 D1 Day 11). Only Tier 3 reads
    `session_history`: the deterministic tiers match this query's own words."""
    for tier in (_tier1_rules, _tier2_embedding_similarity):
        matches = tier(normalized_query)
        if matches:
            return matches
    return _tier3_llm_fallback(normalized_query, session_history)


# Below Tier 1's certain 1.0 and Tier 3's 0.7: inherited from the conversation,
# not read off this query's own words — planning.run reports it as MEDIUM.
_CARRIED_INTENT_SCORE = 0.6


def carry_intent(session_history: list[dict] | None) -> list[tuple[str, float]]:
    """Architecture §8.8's multi-turn case: "What about tomorrow evening?"
    matches no routing row on its own, but it is still the same question as
    the turn before it. Only called once classify_intent found nothing, and
    only ever reads the *immediately* previous turn — if that turn was itself
    a general question, the conversation moved on and nothing is carried.
    Reads session_history, never persona (Ground Rule 1)."""
    if not session_history:
        return []
    valid = {row.name for row in ROUTING_TABLE}
    rows = [r for r in session_history[-1].get("intent_rows") or [] if r in valid]
    return [(r, _CARRIED_INTENT_SCORE) for r in rows]


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


def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Distress bypass (Architecture §4, last
    row) is NOT handled here — it happens in orca/graph/ before Planning is
    even invoked, per the architecture's own framing: distress "bypasses
    this table entirely," which means bypassing this agent, not a branch
    inside it."""
    query = state.get("normalized_english_query") or state.get("raw_user_query", "")
    matches = classify_intent(query, state.get("session_history"))
    carried = False
    if not matches:
        matches = carry_intent(state.get("session_history"))
        carried = bool(matches)
    matched_rows = [name for name, _ in matches]
    execution_plan = generate_execution_plan(matched_rows, state.get("reasoning_depth", "SHALLOW"))

    if matched_rows:
        # Tier 1 always scores every match 1.0; a Tier 2/3 match brings the
        # average below that, which is why HIGH is gated on avg >= 0.95
        # rather than "any match" — a Tier 3 LLM guess is real confidence
        # 0.7, not the rules tier's certainty, and the AgentResult should say so.
        avg_score = sum(score for _, score in matches) / len(matches)
        confidence = Confidence(
            score="HIGH" if avg_score >= 0.95 else "MEDIUM",
            rationale=(
                f"Follow-up with no routing match of its own — continuing the previous turn's "
                f"{', '.join(matched_rows)}"
                if carried
                else f"Matched routing row(s): {', '.join(matched_rows)} (avg tier confidence {avg_score:.2f})"
            ),
        )
    else:
        confidence = Confidence(score="MEDIUM", rationale="No routing row matched — answering the closest general-conditions interpretation")

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
