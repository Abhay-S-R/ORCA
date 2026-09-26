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

from orca import engines
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
        ("marine_data_discovery", "weather_intelligence", "ocean_analytics", "risk_assessment", "visualization"),
    ),
    RoutingRow(
        "PFZ_NEAREST",
        ("nearest pfz", "fishing zone", "persistent fishing zone", "where to fish", "potential fishing"),
        ("marine_data_discovery", "ocean_analytics", "geospatial", "visualization"),
    ),
    RoutingRow(
        "CONDITIONS",
        ("tide", "sea conditions", "current conditions", "wave height", "wind speed"),
        ("marine_data_discovery", "weather_intelligence", "ocean_analytics", "visualization"),
    ),
    RoutingRow(
        "HAZARD_ALERTS",
        ("lightning", "cyclone", "storm alert", "hazard warning", "weather warning"),
        ("weather_intelligence", "risk_assessment", "visualization"),
    ),
    RoutingRow(
        "ZONES_TO_AVOID",
        ("zones to avoid", "boundary", "geofence", "restricted zone", "marine park"),
        ("geospatial", "risk_assessment", "visualization"),
    ),
    RoutingRow(
        "ROUTE",
        ("safest route", "route from", "route to", "passage from", "voyage from", "plan a voyage", "plan my route", "navigate from"),
        ("geospatial", "weather_intelligence", "risk_assessment", "visualization"),
    ),
    RoutingRow(
        "DIAGNOSTIC",
        ("why has", "declined", "decline in", "fewer fish", "productivity", "catch dropped", "catch has dropped"),
        ("marine_data_discovery", "ocean_analytics", "visualization"),
    ),
    RoutingRow(
        "REGULATORY",
        ("allowed to fish", "fishing ban", "ban period", "fishing banned", "closed season", "fishing season", "legal to fish"),
        ("geospatial", "risk_assessment", "visualization"),
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
    # --- P5.9 scenario shapes: the six the PS implies beyond a bare verdict ---
    RoutingRow(
        "WORTHWHILENESS",
        ("worth going", "worth it", "worth the fuel", "worth the trip", "worth a trip", "any point going",
         "any fish nearby", "point in going"),
        ("marine_data_discovery", "weather_intelligence", "ocean_analytics", "risk_assessment", "visualization"),
    ),
    RoutingRow(
        "TIMING",
        ("when should i leave", "best time to go", "best time to leave", "what time should i leave",
         "when is it safe to leave", "when can i go"),
        ("marine_data_discovery", "weather_intelligence", "ocean_analytics", "risk_assessment", "visualization"),
    ),
    RoutingRow(
        "COUNTERFACTUAL",
        ("what if i wait", "what if i leave later", "what about this evening", "what about tomorrow instead",
         "if i go later", "if i wait until"),
        ("marine_data_discovery", "weather_intelligence", "ocean_analytics", "risk_assessment", "visualization"),
    ),
    RoutingRow(
        "COMPARISON",
        (" or ", "compare", "better between", "which is safer", "which one is safer", "versus", " vs "),
        ("marine_data_discovery", "weather_intelligence", "ocean_analytics", "risk_assessment", "visualization"),
    ),
    RoutingRow(
        "ENDURANCE",
        ("how long can i stay out", "how far can i go", "how long can i fish", "endurance", "how far and back",
         "range of my boat"),
        ("marine_data_discovery", "ocean_analytics", "visualization"),
    ),
    RoutingRow(
        "FUEL_ECONOMICS",
        ("how much fuel", "fuel cost", "fuel economics", "diesel cost", "cost of fuel", "fuel to get there"),
        ("marine_data_discovery", "ocean_analytics", "visualization"),
    ),
    # --- P5.25: the historical path SAFETY_CHECK/CONDITIONS route away from ---
    RoutingRow(
        "HISTORICAL",
        ("last week", "last month", "was it rougher", "how rough was", "compared to last", "historically",
         "in past years", "used to be"),
        ("marine_data_discovery", "ocean_analytics", "visualization"),
    ),
)

# P2.7 — "visualization" is now named by every row that produces something to
# draw (a map layer or a chart) and deliberately NOT by EXPORT, SUBSCRIPTION or
# ADMINISTRATIVE, which never do: for those the plan-gate skips it, visibly,
# instead of building map layers nobody asked for. Every other agent's
# inclusion here stays as it was; execution of the safety inputs is fail-safe
# regardless of the plan (see graph.ocean_analytics_node).
#
# §4.2 no-match fallback — Discovery + Weather + Ocean Analytics (+ the map),
# never an empty response.
NO_MATCH_FALLBACK_AGENTS = ("marine_data_discovery", "weather_intelligence", "ocean_analytics", "visualization")


# P1.3 (`R-EDGE-1`) — the out-of-scope test, ahead of every routing tier.
#
# The bias is deliberate and one-directional: **refusing a real marine
# question is far worse than answering a junk one.** So this says "out of
# scope" only when the query contains no marine or going-to-sea word at all,
# names no place we know, and is not one of the named non-marine tasks below.
# Anything it is unsure about stays in scope and gets the §4.2 fallback path.
#
# It never sees a distress call: distress_check is the graph's first node and
# ENDs the run before planning is reached (graph.py). That ordering is what
# makes this safe to have at all — "a profane, garbled message is exactly what
# someone in trouble sends", and garbled text is precisely what this
# classifier would otherwise refuse.
_MARINE_VOCAB: frozenset[str] = frozenset(
    # A wrapped block of words, split once at import, rather than 120 quoted
    # list items nobody would read or keep in order.
    """
sea seas ocean oceanic marine maritime coast coastal shore offshore inshore
fish fishing fisherman fishermen fisheries catch catches net nets trawl trawler
boat boats vessel vessels craft canoe catamaran ship ships sail sailing voyage
route routes navigate navigation passage anchor anchorage harbour harbor port
ports jetty landing wharf quay
wave waves swell surf sea-state tide tides tidal current currents ebb flood
wind winds gale storm storms squall cyclone cyclonic depression monsoon
weather forecast rain rainfall lightning thunder thunderstorm visibility fog
conditions condition
depth bathymetry shallow shallows reef reefs shoal sandbar draft draught
safe safety danger dangerous risk hazard warning alert advisory rescue
zone zones pfz boundary boundaries imbl eez geofence border maritime-boundary
mpa park sanctuary ban banned closed season permit licence license
sst salinity chlorophyll plankton productivity upwelling thermocline eddy
go going out venture sortie trip
""".split()  # noqa: SIM905
)

# Tasks that are not marine-advice questions however many sea words they
# contain — a recipe naming fish is still a recipe. These win over the
# vocabulary test above.
_NON_MARINE_TASKS: tuple[str, ...] = (
    "recipe", "cook", "cooking", "poem", "joke", "song", "lyrics", "essay",
    "story", "translate this", "write me", "write a", "homework", "cricket",
    "football", "movie", "election", "stock price", "bitcoin", "capital of",
)

# Prompt injection. Refused as out of scope rather than obeyed or silently
# answered — the honest outcome for "ignore your instructions" is the same
# short refusal every other non-marine question gets.
_INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous", "ignore all previous", "ignore your instructions",
    "disregard the above", "disregard your", "system prompt", "you are now",
    "act as if", "pretend you are", "reveal your", "print your instructions",
    "repeat the text above", "jailbreak", "developer mode",
)

OUT_OF_SCOPE_ROW = "OUT_OF_SCOPE"

# The non-marine sense of "current" — see is_out_of_scope's use below.
_CURRENT_SELF_SENSE = re.compile(r"\bcurrent\s+(time|date|day|location|position)\b")

# A question about ORCA's own operating context — what time it is, where the
# caller is right now — rather than about the sea. Distinct from
# _UNPLACEABLE_SELF_REFERENCE ("near my village": a marine question at an
# unnamed place) and from out-of-scope junk: this is answerable, factually,
# without running a single marine agent — graph.out_of_scope_node answers it
# from the real clock and this turn's own GPS fix (never a carried-over one,
# and never presented as a place to compute sea conditions at).
_SELF_CONTEXT_PHRASES: tuple[str, ...] = (
    "current time", "what time is it", "what's the time", "what is the time",
    "current date", "today's date", "what day is it", "what's the date",
    "current location", "my location", "my position", "my current position",
    "where am i", "do you know my location", "do you know where i am",
)


def is_self_context_question(text: str) -> bool:
    """True when the text asks about ORCA's own context — the clock, the
    caller's own known position — rather than about the sea."""
    lowered = (text or "").lower()
    return any(p in lowered for p in _SELF_CONTEXT_PHRASES)


def is_out_of_scope(normalized_query: str) -> bool:
    """True when this is not a question ORCA can honestly take marine data to.

    Deterministic, no LLM: a refusal decided by a model is a refusal that
    cannot be explained to a judge, and the failure mode (refusing a real
    safety question) is the one this whole phase exists to prevent.
    """
    lowered = (normalized_query or "").strip().lower()
    if not lowered:
        return True
    if any(p in lowered for p in _INJECTION_PATTERNS):
        return True
    if any(p in lowered for p in _NON_MARINE_TASKS):
        return True
    # "current" is real marine vocabulary (an ocean current) and also an
    # ordinary English adjective ("current time", "current location") that
    # has nothing to do with the sea. Found 2026-09-26: "do you know the
    # current location" matched _MARINE_VOCAB on that word alone and ran the
    # full marine pipeline, which then answered — accurately, but pointlessly
    # — with the pilot region's default-position disclosure. Stripped, in
    # this one ambiguous sense only, before the vocabulary test — a copy, so
    # the coordinate/place-name checks below still see the original text. A
    # genuine "current speed near Kochi" still matches on "speed"/the place
    # name, and "ocean current" still matches on "ocean".
    vocab_text = _CURRENT_SELF_SENSE.sub(" ", lowered)
    if _significant_words(vocab_text) & _MARINE_VOCAB:
        return False
    # Text still carrying non-Latin script has not been through a successful
    # translation pass, so an English vocabulary test says nothing about it.
    # Never refuse on that basis.
    if any(ord(ch) > 127 for ch in lowered):
        return False
    # A bare coordinate pair ("conditions at 8.75N 78.25E") names a real
    # position even though it names no gazetteer place and no vocabulary
    # word. place_resolution.parse_coordinates already parses this shape —
    # resolve_all_places_from_text below does not — so without this check
    # this function and the pipeline's own place resolution disagreed about
    # whether the query named anywhere at all, and this refused a query that
    # was answered a moment later when phrased with a marine word instead.
    from orca.place_resolution import parse_coordinates

    if parse_coordinates(lowered) is not None:
        return False
    from orca.data.loaders import resolve_all_places_from_text

    return not resolve_all_places_from_text(lowered)


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


def _tier2_word_overlap(normalized_query: str) -> list[tuple[str, float]]:
    """The original Tier 2 — word-overlap similarity (Architecture §9.5).
    Scores each row 0.0-1.0 as (shared words / row's keyword-word count) after
    synonym expansion, and keeps any row at or above `_TIER2_THRESHOLD`.

    **Kept as the fallback-of-the-fallback, not as Tier 2.** P2.8 replaced the
    scorer with sentence embeddings, but the embedding model is a 120 MB
    download and a machine that cannot have it must still route better than
    "nothing matched" — so this runs when `orca/intent_embeddings.py` reports
    itself unavailable. It is why an offline checkout still behaves exactly as
    ORCA did before P2.8 rather than losing a routing tier."""
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


def _tier2_embedding_similarity(normalized_query: str) -> list[tuple[str, float]]:
    """Tier 2 — multilingual sentence-embedding similarity (P2.8, `R-PS-1`).

    `orca/intent_embeddings.py` holds the model and the per-row example
    phrasings; this is only the tier wiring. It distinguishes the two ways
    that module can return nothing: `None` means the model is not available at
    all and the word-overlap scorer takes the tier, `[]` means the model ran
    and this query genuinely matches no row, which must fall through to Tier 3
    rather than be rescued by a weaker scorer."""
    from orca import intent_embeddings

    matches = intent_embeddings.match(normalized_query)
    if matches is None:
        return _tier2_word_overlap(normalized_query)
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
    except Exception:
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
    except Exception:
        return []

    valid_names = {row.name for row in ROUTING_TABLE}
    if raw in valid_names:
        return [(raw, 0.7)]
    return []


def classify_intent(
    normalized_query: str,
    session_history: list[dict] | None = None,
    tier_out: list[str] | None = None,
) -> list[tuple[str, float]]:
    """Tool per Architecture §3.1 Agent 2. Tier 1 (rules) → Tier 2 (sentence
    embeddings) → Tier 3 (LLM, cheap tier). Only Tier 3 reads
    `session_history`: the deterministic tiers match this query's own words.

    **Tier 3 is no longer only a last resort (P2.8).** It was reached only when
    Tiers 1 and 2 both found nothing, which meant a Tier-2 match at 0.84
    cosine — a real guess — was acted on with exactly as little scrutiny as
    Tier 1's certainty. It now also runs as a *confirmation pass* whenever the
    deterministic tiers came back below 1.0, and the two results are unioned:
    agreement raises the reported confidence, disagreement dispatches both
    interpretations. Union rather than override, deliberately — execution is
    fail-safe (P2.7), and the cost of running an extra specialist is smaller
    than the cost of answering the wrong half of an ambiguous question.

    `tier_out`, when given, receives the name of the tier that decided, for
    the span (P2.1) and for the answer to name its own inferred intent."""
    def _record(tier: str) -> None:
        if tier_out is not None:
            tier_out.append(tier)

    tier1 = _tier1_rules(normalized_query)
    if tier1:
        _record("tier1_rules")
        return tier1

    tier2 = _tier2_embedding_similarity(normalized_query)
    if tier2:
        confirmation = _tier3_llm_fallback(normalized_query, session_history)
        if not confirmation:
            # No LLM, or it declined to name a row. The Tier-2 match stands on
            # its own — an unavailable confirmation is not a refutation.
            _record("tier2_embeddings")
            return tier2
        confirmed = {name for name, _ in confirmation}
        names = {name for name, _ in tier2}
        if confirmed & names:
            # Two independent methods agreeing is worth more than either
            # alone, so the matched rows are re-scored to Tier 1's certainty.
            _record("tier2_embeddings+tier3_confirmed")
            return [(name, 1.0 if name in confirmed else score) for name, score in tier2]
        _record("tier2_embeddings+tier3_disagreed")
        merged = dict(tier2)
        for name, score in confirmation:
            merged.setdefault(name, score)
        return sorted(merged.items(), key=lambda kv: kv[1], reverse=True)

    tier3 = _tier3_llm_fallback(normalized_query, session_history)
    if tier3:
        _record("tier3_llm")
    return tier3


def classify_intent_deterministic(normalized_query: str) -> list[tuple[str, float]]:
    """Tiers 1 and 2 only — the part of the routing decision that needs no
    key, no network and no paid call. Split out so a test (or any caller that
    must not spend a token) can ask "would this route on its own words?" and
    get the same answer the real classifier would, minus the LLM.

    Tier 2 may load a local embedding model here; that is still "no key, no
    network" once the model is cached, and it degrades to word overlap when it
    is not available at all."""
    for tier in (_tier1_rules, _tier2_embedding_similarity):
        matches = tier(normalized_query)
        if matches:
            return matches
    return []


# Below Tier 1's certain 1.0 and Tier 3's 0.7: inherited from the conversation,
# not read off this query's own words — planning.run reports it as MEDIUM.
_CARRIED_INTENT_SCORE = 0.6


# A follow-up that continues the previous question rather than starting a new
# one. Matched only at the START of the query, and only on a short one: "and
# in a trawler?" continues, "and what about the fishing zones near Chennai
# tomorrow" is long enough to be its own question and is treated as one.
#
# This exists because of P2.8. Tier 2 used to be a literal word-overlap
# scorer, so a contentless follow-up matched nothing and fell through to
# `carry_intent` — which is the correct answer for it. A sentence-embedding
# scorer always has a nearest row, so "and in a trawler?" started matching
# CONDITIONS on its own, and the safety intent of the conversation it was part
# of was dropped. Caught by running P2.9's own three-turn Done-when, not by a
# unit test. See `run` for what is done about it.
_CONTINUATION_OPENERS: tuple[str, ...] = (
    "and ", "what about", "how about", "what if", "and what about",
    "also ", "then ", "or ", "but ", "in a ", "on a ", "with a ",
)
_CONTINUATION_MAX_WORDS = 7


def is_continuation(normalized_query: str) -> bool:
    """True when this reads as a continuation of the previous question rather
    than a new one. Deterministic and deliberately narrow — the cost of a
    false positive is one extra agent running (fail-safe), and the cost of a
    false negative is only that nothing is carried, which is today's
    behaviour."""
    lowered = (normalized_query or "").strip().lower()
    if not lowered or len(lowered.split()) > _CONTINUATION_MAX_WORDS:
        return False
    return lowered.startswith(_CONTINUATION_OPENERS)


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
    history = state.get("session_history")
    tier_out: list[str] = []
    carried = False

    # The out-of-scope test now sits BETWEEN Tier 1 and the semantic tiers,
    # and the reason is P2.8.
    #
    # It used to run last, once every tier had found nothing, on the stated
    # grounds that "a query that reached any routing row is a marine query by
    # definition". That was true while Tiers 1 and 2 were both *literal*
    # matchers — a row only matched if its own words were present. It stopped
    # being true the moment Tier 2 became a sentence-embedding scorer, because
    # an embedding scorer always has a nearest row: "asdkjh askjdh askjd"
    # landed on one above threshold and Phase 1's exit gate ("ten junk queries
    # produce ten refusals") went red. Caught by `test_query_coverage.py`,
    # which is exactly the unrehearsed-query gate P1.9 exists to be.
    #
    # So the precedence is now: a literal Tier-1 keyword match still proves
    # the query is marine and wins outright; anything that needs a *semantic*
    # match has to pass the deterministic scope test first. Two exemptions,
    # both load-bearing: text still in a non-Latin script (is_out_of_scope
    # returns False for it — an English vocabulary test says nothing about
    # Tamil), and a follow-up whose intent carries from the previous turn
    # ("what about tomorrow?"), which reads as contentless on its own and must
    # never be refused for it. Refusing a real marine question stays far worse
    # than answering a junk one; this only narrows which tier may rescue one.
    matches = _tier1_rules(query)
    if matches:
        tier_out.append("tier1_rules")
    else:
        carried_rows = carry_intent(history)
        if is_out_of_scope(query) and not carried_rows:
            matches = []
        else:
            matches = classify_intent(query, history, tier_out=tier_out)
            if not matches:
                matches = carried_rows
                carried = bool(matches)
                if carried:
                    tier_out.append("carried_from_previous_turn")
            elif carried_rows and is_continuation(query):
                # A continuation-shaped follow-up keeps the conversation's
                # intent AND takes whatever this turn matched — a union, not
                # an override, for the same reason the Tier-3 confirmation
                # pass unions: execution is fail-safe, and the cost of running
                # one more specialist is far below the cost of answering
                # "and in a trawler?" as a conditions question when the
                # conversation it belongs to was a safety question.
                #
                # The carried rows are appended *below* this turn's own
                # matches so the new topic still leads the answer.
                matched_names = {name for name, _ in matches}
                inherited = [(name, score) for name, score in carried_rows if name not in matched_names]
                if inherited:
                    matches = [*matches, *inherited]
                    carried = True
                    tier_out.append("continuation_kept_previous_intent")

    routing_tier = tier_out[0] if tier_out else "no_match"
    out_of_scope = not matches and is_out_of_scope(query)
    if out_of_scope:
        matched_rows, execution_plan = [OUT_OF_SCOPE_ROW], []
    else:
        matched_rows = [name for name, _ in matches]
        execution_plan = generate_execution_plan(matched_rows, state.get("reasoning_depth", "SHALLOW"))

    if out_of_scope:
        confidence = Confidence(
            score="HIGH",
            rationale="Deterministically out of scope — no marine vocabulary, no known place, "
            "or an explicit non-marine task/injection pattern. No agent was run and no marine "
            "content was produced.",
        )
    elif matched_rows:
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
        outputs={
            "matched_intent_rows": matched_rows,
            "execution_plan": execution_plan,
            # P2.8 — which tier decided, named in the response rather than
            # inferable only from a confidence number. P2.7 renders it beside
            # the intents: "Intents: SAFETY_CHECK + PFZ_NEAREST (sentence
            # embeddings, confirmed) → 5 agents dispatched".
            "routing_tier": routing_tier,
            "routing_scores": [{"row": name, "score": score} for name, score in matches],
        },
        source_provenance=SourceProvenance(
            dataset="Deterministic rules-tier routing table (Architecture §4)",
            acquisition_timestamp="",
            freshness_minutes=0,
        ),
        confidence=confidence,
        # P2.1 — Planning is deterministic unless Tier 3 actually ran. The
        # span must not read "Deterministic" on a query an LLM classified, and
        # must not read a model id on the ~all of them it did not.
        engine=(
            engines.llm_engine("cheap") if "tier3" in routing_tier
            else engines.DETERMINISTIC
        ),
    )
