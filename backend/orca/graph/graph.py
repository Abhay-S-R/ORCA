"""LangGraph pipeline:

    distress_check --[distress_flag]--> END (response built in this node)
                   --[else]-----------> query_guard
                                            |
                        --[can't place it / can't reach that time]--> END
                                            |
                                     language_ingress
                                            |
                                         planning
                                            |
                        --[OUT_OF_SCOPE]--> out_of_scope --> END
                                            |
                                  marine_data_discovery        (P2.6, Agent 3)
                                            |
                        +-------------------+-------------------+
                        v                   v                   v
                weather_intelligence   geospatial        ocean_analytics
                        |                   |                   |
                        +-------------------+-------------------+
                                            |
                              +-------------+-------------+
                              v                            v
                      risk_assessment              visualization
                              |                            |
                              +-------------+-------------+
                                             v
                                        reporting <----------------+
                                             |                     |
               --[hard-constraint NO_GO]--> critic_cancelled       |
               --[reinvoc budget spent]---> language_egress        |
                                             |                     |
                                           critic                  |
                                             |                     |
                         --[names an agent, budget unspent]--> critic_reinvoke
                                             |
                                    language_egress --> END

geospatial and reporting are the real Agents 6/9 (S5/S6) — no longer
fixtures. language_ingress/egress are Agent 1, run twice per query (before
Planning, after Reporting), matching "Ingress & Egress" in its own name.
visualization (Agent 8, Phase 2 D3) is a sibling of risk_assessment, not
downstream of it — it shapes weather_data/geospatial_data into map layers
and charts, and never reads the safety verdict to do so.
ocean_analytics (Agent 5, Phase 2 D2) is a third sibling of weather/geospatial
— tide, PFZ proximity/persistence, sector status, and the DEEP catch-decline
diagnosis. Agent 3's source-selection narratives now come from
marine_data_discovery (P2.6), which runs once before the fan-out; Ocean
Analytics reads that decision rather than making its own.

query_guard and out_of_scope (Phase 1, P1.2-P1.4) are guards, not agents: they
run no model, read no dataset, and emit no trace entry. Both sit downstream of
distress_check and nowhere else, which is the ordering the phase depends on —
a garbled, place-less, out-of-scope-looking message is exactly what someone in
trouble sends, and Agent 12 sees every one of them first.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from orca import engines, place_resolution, reconcile
from orca.agents import (
    critic,
    distress,
    geospatial,
    language,
    ocean_analytics,
    planning,
    reporting,
    risk_assessment,
    visualization,
    weather_intelligence,
)
from orca.agents.planning import OUT_OF_SCOPE_ROW
from orca.contracts import AgentResult, Confidence, coerce_confidence_score
from orca.state import ORCAState
from orca.trace import run_traced_node

# Boundary names geospatial.py actually loaded these under (checked against
# the real GeoJSON `name` properties, not assumed) — see plan §4 S5 exit
# note: "The IMBL distance is the single highest-consequence number in the
# product." There is no dedicated IMBL treaty-line geometry in the data;
# the Sri Lanka EEZ boundary is the practical stand-in in this region, named
# explicitly here rather than left implicit in a magic string at the call site.
_IMBL_PROXY_BOUNDARY = "Sri Lankan Exclusive Economic Zone"
_MPA_BOUNDARY = "Gulf of Mannar Marine National Park"


def _not_run(
    agent_name: str, state: ORCAState, reason: str,
    status: Literal["skipped", "cancelled"],
) -> dict:
    """A node that deliberately did not run, as a first-class span.

    P2.7 and P2.12 both need this and they mean different things by it:
    `skipped` is "the plan did not ask for this", decided before anything ran;
    `cancelled` is "this was pending and a hard constraint made it pointless",
    decided mid-flight. The reasoning graph draws the second dotted.

    It emits a real `audit_trace_log` entry and a real `completed_nodes` entry
    — both, in lockstep, because `api/main.py` pairs those two lists
    index-for-index and a node contributing to one but not the other silently
    mislabels every span after it. `outputs` is empty on purpose: a span that
    did not run has no measurement, and LOW_DATA is the honest confidence for
    one (never HIGH, which would read as "confidently nothing")."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entry: dict[str, Any] = {
        "agent_name": agent_name,
        "query_id": state.get("query_id", ""),
        "status": status,
        "confidence": "LOW_DATA",
        "confidence_score": None,
        "confidence_detail": None,
        "engine": engines.DETERMINISTIC,
        "started_at": now,
        "ended_at": now,
        "latency_ms": 0.0,
        "error_detail": reason,
        "inputs_consumed": {},
        "outputs": {},
        "source_provenance": None,
        "skip_reason": reason,
    }
    return {
        "audit_trace_log": [entry],
        "completed_nodes": [agent_name],
        "skipped_agents": [{"agent_name": agent_name, "status": status, "reason": reason}],
    }


def _skipped(agent_name: str, state: ORCAState, reason: str) -> dict:
    return _not_run(agent_name, state, reason, "skipped")


def _cancelled(agent_name: str, state: ORCAState, reason: str) -> dict:
    return _not_run(agent_name, state, reason, "cancelled")


def _scored(result: AgentResult, entry: dict) -> Confidence:
    """The confidence downstream agents compose from: the band of the measured
    score (orca/confidence_score.py), which is never above the agent's own
    rule label. Using the rule label here let a 50 h-old cached forecast read
    MEDIUM on the answer card while its own pill read LOW."""
    detail = entry.get("confidence_detail") or {}
    factors = "; ".join(f"{f['factor']} {f['detail']}" for f in detail.get("factors", []) if f.get("value") is not None)
    return Confidence(
        score=coerce_confidence_score(entry.get("confidence", result.confidence.score)),
        rationale=f"{result.confidence.rationale} [score {detail.get('score', '?')}: {factors}]",
    )


def distress_check_node(state: ORCAState) -> dict:
    """Runs Agent 12 exactly ONCE. Previously this node only extracted the
    boolean flag, and a separate distress_response_node re-ran distress.run()
    from scratch to get the MRCC/handoff payload — on the one path where
    latency matters most (SOS, <2s), that meant duplicating detection,
    MRCC lookup and handoff formatting for no reason, and it left two
    "distress" entries in the trace for what is genuinely one agent
    invocation. Everything downstream needs is computed here, once."""
    result, entry = run_traced_node("distress", distress.run, state)
    is_distress = result.outputs["detection"]["is_distress"]
    update = {
        "distress_flag": is_distress,
        "audit_trace_log": [entry],
        "completed_nodes": ["distress_check"],
    }
    if is_distress:
        # Bypasses Reporting entirely (Architecture §3.2 step 1) — surfaces
        # MRCC contact directly, never synthesized/persona-rendered.
        mrcc = result.outputs["mrcc_contact"]
        # The wire field a client branches on, set HERE and not only in
        # main.py's _initial_state: that one is seeded from the `distress=`
        # query parameter (the SOS button), so a distress call detected from
        # the TEXT left `query_outcome` reading "ANSWERED" while the body said
        # DISTRESS DETECTED. The one outcome that must never be mislabelled.
        update["query_outcome"] = "DISTRESS"
        update["final_english_response"] = (
            f"DISTRESS DETECTED. Coast Guard MRCC: {mrcc['primary']['phone']} "
            f"(nationwide: {mrcc['nationwide_fallback']['phone']}), VHF channel {mrcc['primary']['vhf_channel']}. "
            "This handoff is SIMULATED — no live DAT-SG/telephony integration exists yet."
        )
        update["confidence_tier"] = "HIGH"
    return update


def _route_after_distress(state: ORCAState) -> str:
    # END is untyped (a plain interned str, not a Literal) in langgraph's own
    # stubs, so this can't be a Literal return type without mypy complaining
    # about the exact thing that makes END work at all.
    return END if state.get("distress_flag") else "query_guard"


def _candidate_list(candidates: list[dict]) -> str:
    return ", ".join(f"{c['name'].title()} ({c['lat']:.2f}N {c['lon']:.2f}E)" for c in candidates)


def _refusal(outcome: str, body: str) -> dict:
    """A stop with no marine content in it. Certainty about *not knowing* is
    still certainty, so the tier is HIGH: no reading was taken, so nothing
    here can be stale or thin, and a LOW_DATA label would read as "a weak
    answer" rather than "no answer, and here is what I need"."""
    return {
        "query_outcome": outcome,
        "final_english_response": body,
        "final_vernacular_response": body,
        "confidence_tier": "HIGH",
        "disclosures": [body],
    }


def query_guard_node(state: ORCAState) -> dict:
    """P1.2 (`R-NEW-1`) and P1.4 (`R-EDGE-3`) — the position-and-time gate, and
    the second node in the graph for a reason: it sits *after* distress_check
    and before everything else, so "we are sinking near my village" is an SOS,
    never a request to name a port.

    Seven of P1.4's eight guard clauses land here, in the order a wrong answer
    would have been built: which place (unresolvable, ambiguous name, several
    places at once, bare coordinates), then which time (past dates, beyond the
    forecast horizon), then whether the place is one any marine reading is
    valid at (inland, outside the data extent). The eighth, expired cache,
    belongs to the reading rather than the question — see risk_assessment_node.

    Every clause names the actual limit; "I can't help with that" without the
    number is the thing this point exists to replace.

    Emits no audit_trace_log/completed_nodes entry: it is a guard, not an
    agent, and main.py pairs those two lists index-for-index."""
    resolution = state.get("place_resolution") or {}
    if resolution.get("status") in ("ambiguous", "unresolvable"):
        disclosure = resolution.get("disclosure") or "I could not work out where this question is about."
        candidates = resolution.get("candidates") or []
        body = disclosure if not candidates else f"{disclosure} Did you mean: {_candidate_list(candidates)}?"
        return _refusal("NEEDS_PLACE", body)

    # Time before position: "was it rough off Veraval last Tuesday?" has a
    # perfectly good position and still has no answer here.
    when = place_resolution.time_guard(state.get("raw_user_query", "") or "")
    if when is not None:
        return _refusal("OUT_OF_RANGE", when)

    location = state.get("user_location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        return {}
    where = place_resolution.position_guard(float(lat), float(lon))
    if where is None:
        return {}
    # Whose position is it? A fix the caller supplied — an explicit lat/lon or
    # a coordinate pair typed into the question — that turns out to be inland
    # or off the data extent is an answerless question, and saying so is the
    # whole guard. A *named* place is different: "wave height at Kanyakumari"
    # is a perfectly good question, and the on-land reading is an artefact of
    # the gazetteer holding the town's coordinates rather than the harbour
    # approach's. Refusing it would blame the user for our table.
    #
    # KNOWN GAP, do not mistake this disclosure for a fix: 47 of the 83
    # distinct gazetteer places are on land by GEBCO (audited 2026-09-20).
    # The real repair is snapping each to its nearest wet cell — the machinery
    # exists in scripts/orca_grid_utils.py — which is a data pass, not a guard
    # clause, and is not in P1.4's scope. Until it happens, a depth-dependent
    # answer at those places is thin and now says so.
    # A GPS fix belongs with the coordinate sources, not the gazetteer ones:
    # there is no "the town, not the harbour" to disclose about it — it is the
    # caller's actual position, so out of range means out of range.
    if location.get("place_source") in ("explicit", "coordinates", "gps_fix"):
        return _refusal("OUT_OF_RANGE", where)
    return {"disclosures": [where + " The position held for this place is the town, not the harbour approach, so depth-dependent readings here may be missing."]}


def _route_after_query_guard(state: ORCAState) -> str:
    return END if state.get("query_outcome") in ("NEEDS_PLACE", "OUT_OF_RANGE") else "language_ingress"


def out_of_scope_node(state: ORCAState) -> dict:
    """P1.3 (`R-EDGE-1`) — a first-class "I can't answer that": a short
    refusal plus a redirect, and emphatically zero marine content. No agent
    below Planning has run, so there is no number here to be wrong."""
    body = (
        "I can't answer that. I only answer questions about conditions at sea off India — "
        "whether it is safe to go out, waves, wind, tides, fishing zones, and maritime "
        "boundaries. Ask me one of those and name a place, or tap SOS if you are in trouble."
    )
    return {
        "query_outcome": "OUT_OF_SCOPE",
        "final_english_response": body,
        "final_vernacular_response": body,
        "confidence_tier": "HIGH",
        "execution_plan": [],
    }


def _route_after_planning(state: ORCAState) -> list[str] | str:
    if OUT_OF_SCOPE_ROW in (state.get("matched_intent_rows") or []):
        return "out_of_scope"
    # P2.6 — the fan-out no longer starts here. Agent 3 decides the sources
    # first, once, and the three specialists consume that decision.
    return "marine_data_discovery"


# P2.6 (`R-AGENT-2`, `R-PS-4`) — which data types Agent 3 settles a source for
# before the specialists run. The core four are always resolved because the
# safety verdict is computed for every query whatever was asked (see
# ocean_analytics_node's note on fail-safe execution); the rest are added only
# when an intent actually asks for them, so a "is it safe?" query does not pay
# to pick a chlorophyll source it will never read.
_CORE_DATA_TYPES: tuple[str, ...] = ("wave_height", "wind_speed", "boundary", "lightning", "cyclone")
# What Ocean Analytics consumes when it runs. Resolved by Agent 3 whenever
# Ocean is in the plan (or the plan is empty, which gates nothing off), NOT
# only when an intent happens to name them: the first live run of P2.6 showed
# Ocean deciding `pfz` and `catch_statistics` for itself on a plain safety
# question, because Agent 3 had never been asked for them — which is the
# "each specialist picks its own sources" arrangement this node replaces.
_OCEAN_DATA_TYPES: tuple[str, ...] = ("pfz", "tide", "catch_statistics")
_INTENT_DATA_TYPES: dict[str, tuple[str, ...]] = {
    "SAFETY_CHECK": ("tide", "cyclone"),
    "PFZ_NEAREST": ("pfz", "bathymetry"),
    "CONDITIONS": ("tide", "current_speed", "sst"),
    "HAZARD_ALERTS": ("cyclone", "hazard"),
    "ZONES_TO_AVOID": ("eez", "mpa"),
    "ROUTE": ("bathymetry", "current_speed"),
    "DIAGNOSTIC": ("sst", "chlorophyll", "catch_statistics"),
    "REGULATORY": ("fishing_ban", "mpa"),
    "EXPORT": ("pfz", "tide"),
    "SUBSCRIPTION": ("cyclone",),
}


def _data_types_for(matched_rows: list[str], plan: list[str] | None = None) -> list[str]:
    wanted = list(_CORE_DATA_TYPES)
    # Ocean runs unless the plan gates it off; an empty/absent plan gates
    # nothing (Planning did not run, or failed).
    if not plan or "ocean_analytics" in plan:
        for dtype in _OCEAN_DATA_TYPES:
            if dtype not in wanted:
                wanted.append(dtype)
    for row in matched_rows or []:
        for dtype in _INTENT_DATA_TYPES.get(row, ()):
            if dtype not in wanted:
                wanted.append(dtype)
    return wanted


def marine_data_discovery_run(state: ORCAState) -> AgentResult:
    """Agent 3 as a real node (P2.6).

    `discovery.py` has always been the most genuinely agentic component here —
    a declared cascade, a ranking, and a narrated comparison — and it was not
    an agent: it ran inside Ocean Analytics and its output was smuggled out on
    that agent's `discovery_data`. So a query that never reached Ocean
    Analytics showed no source reasoning at all, and the two specialists that
    DID fetch data chose their sources without ever consulting it.

    It now runs once, before the fan-out, and its decision is the one the
    specialists read. Arrival is validated per source
    (`discovery.select_validated_source`): an empty payload, an unreadable
    file or an out-of-range value drops that rung and the cascade moves on,
    named on this span rather than discovered later as a blank field.
    """
    from orca.agents import discovery
    from orca.contracts import SourceProvenance, coerce_reasoning_depth

    wanted = _data_types_for(state.get("matched_intent_rows") or [], state.get("execution_plan") or [])
    selections: list[dict] = []
    unusable: list[str] = []
    for dtype in wanted:
        decision = discovery.select_validated_source(dtype)
        if decision is None:
            # Nothing in the catalog covers it. Recorded, not silently
            # dropped — "we hold no source for this" is an answer.
            unusable.append(dtype)
            continue
        selections.append(decision)
        if decision["chosen"] is None:
            unusable.append(dtype)

    fell_through = [s for s in selections if s.get("fell_through")]

    if unusable:
        confidence = Confidence(
            score="LOW_DATA",
            rationale=f"No usable source for: {', '.join(unusable)}",
        )
    elif fell_through:
        confidence = Confidence(
            score="MEDIUM",
            rationale=f"{len(fell_through)} of {len(selections)} data types fell to a declared fallback rung",
        )
    else:
        confidence = Confidence(
            score="HIGH",
            rationale=f"Primary source available for all {len(selections)} data types",
        )

    return AgentResult(
        agent_name="marine_data_discovery",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"data_types": wanted, "matched_intent_rows": state.get("matched_intent_rows") or []},
        outputs={
            "source_selections": selections,
            "unusable_data_types": unusable,
            "fell_through": [s["data_type"] for s in fell_through],
        },
        source_provenance=SourceProvenance(
            dataset="ORCA source catalog (Agent 3) — Architecture §12.1 cascades",
            acquisition_timestamp="", freshness_minutes=0,
        ),
        confidence=confidence,
        # Coverage means what confidence_score.py means by it: how many of the
        # data types asked for actually got a usable source. It is NOT "how many
        # sources could be pre-checked" — that was the first version of this,
        # and the scorer read 3-of-8 pre-checkable as 3-of-8 readings present,
        # so an agent that found a source for every one of its 8 data types went
        # LOW on the strip. Caught by the screenshot, not by a test. How many
        # were pre-checkable is real information and stays in the outputs
        # (`arrival.checked` per selection); it just is not a coverage figure.
        coverage=(len(wanted) - len(unusable), len(wanted)) if wanted else None,
    )


def marine_data_discovery_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("marine_data_discovery", marine_data_discovery_run, state)
    selections = (result.outputs or {}).get("source_selections") or []
    return {
        "discovery_sources": {
            "selections": selections,
            "unusable_data_types": (result.outputs or {}).get("unusable_data_types") or [],
            # Keyed for the specialists, which ask "what did Agent 3 pick for
            # wave_height?" rather than walking the list.
            "by_data_type": {s["data_type"]: s for s in selections},
        },
        # The card and the activity strip read `discovery_data.source_selections`
        # (differentiator 4) and have since before this node existed. Written
        # here now rather than by Ocean Analytics, so the narratives appear on
        # every query instead of only the ones that reached Agent 5.
        "discovery_data": {"source_selections": selections},
        "audit_trace_log": [entry],
        "completed_nodes": ["marine_data_discovery"],
    }


def language_ingress_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("language_ingress", language.run_ingress, state)
    # run_traced_node's exception boundary degrades any agent failure (e.g. a
    # missing optional translation dependency) to outputs={} — indexing into
    # it unconditionally would turn that documented degrade-not-crash contract
    # into a KeyError that aborts the whole streamed response (matches the
    # `if result.outputs else {}` guard weather_node already uses below).
    outputs = result.outputs or {
        "detected_language": "en",
        "normalized_english_query": state.get("raw_user_query", ""),
    }
    return {
        "detected_language": outputs["detected_language"],
        "normalized_english_query": outputs["normalized_english_query"],
        "audit_trace_log": [entry],
        "completed_nodes": ["language_ingress"],
    }


def planning_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("planning", planning.run, state)
    update = {
        "matched_intent_rows": result.outputs["matched_intent_rows"],
        "execution_plan": result.outputs["execution_plan"],
        "audit_trace_log": [entry],
        "completed_nodes": ["planning"],
    }
    # A "why has the catch dropped?" question is what DEEP exists for — the
    # productivity diagnosis only runs there (P5.29). Only ever raises depth.
    if "DIAGNOSTIC" in update["matched_intent_rows"]:
        update["reasoning_depth"] = "DEEP"
    return update


def _attach_discovery(entry: dict, state: ORCAState, data_types: tuple[str, ...]) -> None:
    """P2.6 — record on this specialist's span which Agent 3 decisions it was
    handed. The specialists' *fetch* logic stays their own (a live API cannot
    be pre-probed, so Weather still tries live then its cache; Geospatial reads
    local geometry), so what they consume from Agent 3 is the decision and its
    rationale — named here so a judge opening the span sees the hand-off and
    the source the answer will cite, rather than each agent silently choosing.
    Written into `inputs_consumed`, the field the inspector already renders."""
    decided = (state.get("discovery_sources") or {}).get("by_data_type") or {}
    handed = {
        dtype: {"chosen": decided[dtype].get("chosen"), "narrative": decided[dtype].get("narrative")}
        for dtype in data_types
        if dtype in decided
    }
    if handed:
        entry["inputs_consumed"] = {**(entry.get("inputs_consumed") or {}), "discovery_decision": handed}


def weather_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("weather_intelligence", weather_intelligence.run, state)
    _attach_discovery(entry, state, ("wave_height", "wind_speed", "lightning", "cyclone"))
    return {
        # Same shape the geospatial node stores: Agent 7's compute_confidence
        # reads weather_data["confidence"], so dropping it here meant a cached
        # or degraded weather feed could never degrade the verdict tier.
        # An empty outputs dict means the agent failed, and downstream code
        # tests weather_data for truthiness — so don't make it truthy with a
        # lone confidence key.
        "weather_data": {**result.outputs, "confidence": _scored(result, entry)} if result.outputs else {},
        "audit_trace_log": [entry],
        "completed_nodes": ["weather_intelligence"],
    }


def ocean_analytics_node(state: ORCAState) -> dict:
    """Agent 5 (Ocean Analytics, Phase 2 D2) — a sibling of weather/geospatial,
    fed by planning, feeding the risk_assessment + visualization join and
    reporting. It exports run(state) -> AgentResult directly, so no adapter
    wrapper is needed here (unlike geospatial/reporting)."""
    # The one place Agent 2's execution_plan actually gates execution. The
    # graph's other fan-out branches deliberately do not consult it: weather
    # and geospatial are the inputs risk_assessment computes the verdict from,
    # and the verdict is fail-safe — it is computed for every query, including
    # ones the router did not read as a safety question, because a misrouted
    # "what's the tide" from someone about to put to sea in a gale must still
    # produce a hazard warning. Ocean Analytics is the only branch whose
    # absence costs nothing but content (see reporting_run's early_exit note:
    # risk_assessment never reads ocean_data), so it is the only one skippable.
    plan = state.get("execution_plan") or []
    if plan and "ocean_analytics" not in plan:
        # P2.7 (`R-JUDGE-3`) — a skip is now *visible*. This used to return an
        # empty dict, so a query that deliberately did not need Agent 5 looked
        # exactly like one where Agent 5 silently vanished: no span, no reason,
        # a gap in the strip. Execution is unchanged (the decision is still the
        # plan's, and it is still the only skippable branch); what changes is
        # that the decision is now something a judge can see being made.
        return _skipped(
            "ocean_analytics", state,
            f"not in this query's execution plan ({', '.join(plan)})",
        )

    result, entry = run_traced_node("ocean_analytics", ocean_analytics.run, state)
    update: dict = {
        "ocean_data": {**result.outputs, "confidence": _scored(result, entry)} if result.outputs else {},
        "audit_trace_log": [entry],
        "completed_nodes": ["ocean_analytics"],
    }
    # P2.6 — Agent 3's narratives no longer ride out on this agent's output:
    # marine_data_discovery_node writes `discovery_data` before the fan-out, so
    # they appear on every query rather than only the ones that reached Agent 5.
    # P1.6 — a sector that is a fallback rather than this position's own says
    # so on the card, not only in the payload.
    sector_note = result.outputs.get("sector_disclosure") if result.outputs else None
    if sector_note:
        update["disclosures"] = [sector_note]
    return update


def geospatial_run(state: ORCAState) -> AgentResult:
    """Not exported from orca/agents/geospatial.py as run(state) — S5 built
    tool-level functions (check_boundary_proximity, point_in_polygon), not
    an agent-level wrapper matching the S1-S3 convention. This is that
    wrapper, kept in graph.py rather than geospatial.py so the adapter (see
    below) sits next to the graph that actually needs this exact shape."""
    from orca.contracts import SourceProvenance, coerce_reasoning_depth

    location = state.get("user_location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        # No third hardcoded copy of the default coordinate. The API is the one
        # place that decides what position a query is about (main.py's /query),
        # and it always records how it decided; a duplicate literal here would
        # silently answer with Thoothukudi's boundary distance for a request
        # that never had a position at all — the §5.7 fabricated-input failure.
        # conservative_or's contract applies: absent input, named, never guessed.
        raise ValueError("user_location is missing lat/lon — the caller must resolve a position before the graph runs")

    imbl = geospatial.check_boundary_proximity(lat, lon, _IMBL_PROXY_BOUNDARY)
    mpa = geospatial.check_boundary_proximity(lat, lon, _MPA_BOUNDARY)

    return AgentResult(
        agent_name="geospatial",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        # The whole location dict, not just the pair: `place_source` is what
        # tells a later re-render (trace_routes' /render) whether this position
        # was resolved from the query or fell back to the regional default.
        inputs_consumed={"lat": lat, "lon": lon, "user_location": dict(location)},
        outputs={
            "imbl_distance_nm": imbl.distance_nm,
            "imbl_alert_level": imbl.alert_level,
            "mpa_violation": mpa.alert_level == "INSIDE",
            "mpa_alert_level": mpa.alert_level,
            "dataset": "Marine Regions VLIZ EEZ + UNEP-WCMC WDPA (via Agent 6)",
        },
        source_provenance=SourceProvenance(
            dataset="Marine Regions VLIZ EEZ + UNEP-WCMC WDPA",
            # Static reference data, but not undated: this is when the VLIZ /
            # WDPA files were acquired (criterion 4 covers the IMBL distance).
            acquisition_timestamp=geospatial.boundary_data_vintage(),
            freshness_minutes=0,
        ),
        # Real geometry, not a stub — but geodesic distance to a coarse
        # boundary proxy (not the literal IMBL treaty line) stays MEDIUM
        # until that's independently verified (plan §4 S5 exit note).
        confidence=Confidence(score="MEDIUM", rationale=f"Real boundary check against {_IMBL_PROXY_BOUNDARY} (IMBL proxy) and {_MPA_BOUNDARY}"),
        # Boundary geometry is STATIC-class reference data; coverage is whether
        # both proximity checks returned a distance.
        freshness_class="STATIC",
        data_age_minutes=0,
        fallback_depth=0,
        coverage=(sum(1 for c in (imbl, mpa) if c.distance_nm == c.distance_nm), 2),  # NaN != NaN
    )


def geospatial_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("geospatial", geospatial_run, state)
    _attach_discovery(entry, state, ("boundary",))
    return {
        "geospatial_data": {**result.outputs, "confidence": _scored(result, entry)},
        "audit_trace_log": [entry],
        "completed_nodes": ["geospatial"],
    }


def risk_assessment_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("risk_assessment", risk_assessment.run, state)
    # Annotated rather than inferred: without it the dict literal's value type
    # is a union of everything assigned here, so the `disclosures` append below
    # reads as list[dict | str] against ORCAState's list[str]. Runtime is fine
    # (`reconcile.statements` returns list[str]); the annotation is what makes
    # a stricter checker than mypy — pyrefly — agree.
    update: dict[str, Any] = {
        "risk_assessment": result.outputs,
        "confidence_tier": result.confidence.score,
        "audit_trace_log": [entry],
        "completed_nodes": ["risk_assessment"],
    }
    # P1.4's eighth guard clause, expired cache. The detection is P0.5's and
    # stays there (freshness.past_staleness_ceiling floors this verdict and
    # names the age in `reason`); what Phase 1 adds is putting that fact where
    # the card shows it BEFORE the answer, rather than only inside a verdict
    # reason the eye skips. `disclosures` is additive, so this sits alongside
    # any place disclosure rather than replacing it.
    if not result.outputs:
        # The safety agent itself failed (run_traced_node's exception boundary
        # returns empty outputs). No verdict is not the same as a calm sea, and
        # a card that simply omits the verdict panel reads as one. Say it first
        # (plan principle 3, degrade loudly) — found when P2.9's vessel bug
        # blanked a verdict and nothing on screen said so.
        update["disclosures"] = [(
            "The safety assessment could not be computed for this question, so there is NO "
            "go / no-go verdict below. Do not treat the absence of a warning as safe conditions."
        )]
        return update
    status = (result.outputs or {}).get("status")
    if status in ("CAUTION_STALE_DATA", "CAUTION_MISSING_DATA"):
        update["disclosures"] = [result.outputs.get("reason", status)]
    # P2.4 — the reconciliation rows travel on their own state field rather
    # than inside `risk_assessment`, which a dozen call sites read as
    # {status, go_no_go, reason} and one of which (reporting_run) feeds
    # verbatim into an LLM prompt. The trace row keeps the full copy.
    reconciliation = (result.outputs or {}).get("reconciliation") or []
    # Always stripped, not only when non-empty: an empty list left in the
    # verdict dict rode the wire as `risk_assessment.reconciliation = []` and
    # into Reporting's prompt as a fact named "reconciliation=[]".
    update["risk_assessment"] = {k: v for k, v in (result.outputs or {}).items() if k != "reconciliation"}
    if reconciliation:
        update["reconciliation"] = reconciliation
    # Two sources disagreeing is exactly the kind of fact that belongs ABOVE
    # the answer (principle 3) — it changes which number the verdict used.
    said = reconcile.statements(reconciliation)
    if said:
        update["disclosures"] = [*update.get("disclosures", []), *said]
    return update


# P2.12 (orca_final §4.1, §24) — the constraints that make the rest of a
# response pointless rather than merely negative. Both are *hard*: no amount of
# additional context changes "there is a red-alert cyclone" or "you are inside
# one nautical mile of the IMBL" into a workable trip. A rough-sea NO_GO is
# deliberately NOT here: it is the case where the tide window and the nearest
# sheltered zone are the most useful things on the page.
_HARD_CONSTRAINT_STATUSES = ("DANGER", "CRITICAL_GEOFENCE")


def hard_constraint_no_go(verdict: dict) -> str | None:
    """The reason, when a verdict is a hard-constraint NO_GO; None otherwise.

    Returning the reason rather than a bool is the point: a cancelled span has
    to name what cancelled it, or a dotted node in the reasoning graph is just
    a node that mysteriously did not run."""
    if verdict.get("go_no_go") != "NO_GO":
        return None
    if verdict.get("status") not in _HARD_CONSTRAINT_STATUSES:
        return None
    return verdict.get("reason") or verdict.get("status")


def visualization_node(state: ORCAState) -> dict:
    # P2.7 — the second plan-gated branch, and the first that is skipped on the
    # strength of the routing table rather than by hand. Agent 8 shapes
    # already-gathered data into map layers and charts and never reads the
    # verdict, so its absence costs content and nothing else — which is the
    # test for a branch being genuinely optional. Like Ocean Analytics, an
    # empty plan means Planning did not run and gates nothing off.
    plan = state.get("execution_plan") or []
    if plan and "visualization" not in plan:
        return _skipped(
            "visualization", state,
            f"this question produces nothing to draw — not in its execution plan ({', '.join(plan)})",
        )
    result, entry = run_traced_node("visualization", visualization.run, state)
    return {
        # Plain dicts (asdict), same reason geospatial_routes.py does it for
        # ProximityResult/DepthResult — visualization_payload has to survive
        # json.dumps() in main.py's SSE stream, and a frozen dataclass doesn't.
        "visualization_payload": {
            "map_layers": [asdict(layer) for layer in result.outputs["map_layers"]],
            "chart_specs": [asdict(chart) for chart in result.outputs["chart_specs"]],
            "validation_dropped": result.outputs["validation_dropped"],
        },
        "audit_trace_log": [entry],
        "completed_nodes": ["visualization"],
    }


def reporting_run(state: ORCAState) -> AgentResult:
    """Not exported from orca/agents/reporting.py as run(state) either —
    assemble_response(query_id, results: list[AgentResult]) expects the full
    envelope objects, but this graph only ever stores each specialist's
    flattened `.outputs` dict into state (weather_data, geospatial_data,
    risk_assessment), not the AgentResult it came from — nobody tracks that
    list end to end yet. Reconstructing full AgentResults here from what's
    actually in state is the pragmatic bridge; unifying this properly (the
    graph tracking a real list[AgentResult]) is a fair Phase 2 cleanup, not
    done here to avoid widening this change into a state-schema rework."""
    from orca.contracts import SourceProvenance, coerce_reasoning_depth

    query_id = state.get("query_id", "")
    depth = coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW"))
    results: list[AgentResult] = []

    weather = state.get("weather_data") or {}
    if weather:
        results.append(AgentResult(
            agent_name="weather_intelligence", query_id=query_id, reasoning_depth=depth,
            inputs_consumed={}, outputs={"lightning_active": weather.get("lightning_active"), "cyclone_alert": weather.get("cyclone_alert")},
            source_provenance=SourceProvenance(
                dataset=weather.get("dataset", "Open-Meteo Marine API + Forecast API"),
                acquisition_timestamp=weather.get("acquisition_timestamp", ""),
                freshness_minutes=weather.get("freshness_minutes", 0),
            ),
            confidence=weather.get("confidence") or Confidence(score="HIGH", rationale="see weather_intelligence trace entry"),
        ))

    geo = state.get("geospatial_data") or {}
    if geo:
        geo_confidence = geo.get("confidence") or Confidence(score="MEDIUM", rationale="geospatial")
        results.append(AgentResult(
            agent_name="geospatial", query_id=query_id, reasoning_depth=depth,
            inputs_consumed={}, outputs={"imbl_distance_nm": geo.get("imbl_distance_nm"), "mpa_violation": geo.get("mpa_violation")},
            source_provenance=SourceProvenance(
                dataset=geo.get("dataset", "Marine Regions VLIZ EEZ + UNEP-WCMC WDPA"),
                # Same vintage the geospatial node cites — the boundary files'
                # own acquisition date, not a blank (criterion 4).
                acquisition_timestamp=geospatial.boundary_data_vintage(), freshness_minutes=0,
            ),
            confidence=geo_confidence,
        ))

    verdict = state.get("risk_assessment") or {}

    # Cost-based short-circuit (Architecture §9.3, plan §6 Phase 4) — the
    # *verdict* never reads ocean_data: risk_assessment consumes weather +
    # geospatial only, and since P2.4 it additionally reads ocean_data's OSF
    # wave/wind readings to reconcile them against Open-Meteo. It still
    # consults no PFZ, tide or trend value, which is what this trim depends
    # on, so Ocean Analytics' PFZ/tide/trend content remains exactly the
    # "co-occurring PFZ lookup" the architecture names as safe to drop from a
    # NO_GO response. This is response trimming, not compute avoidance: the
    # ocean_analytics node still ran (LangGraph's static fan-in has no
    # supported mid-flight cancellation, see phase4 plan §2.1) — only the
    # content surfaced to the user is cut, which is the half of §9.3 that is
    # actually about what a fisherman sees. The compute half is P2.12's, and
    # it acts on the only work that is genuinely still pending at the point
    # the verdict exists: see _route_after_reporting. Never trimmed if the
    # user separately asked for zone/condition data (matched_intent_rows).
    matched_rows = state.get("matched_intent_rows") or []
    early_exit = verdict.get("go_no_go") == "NO_GO" and not ({"PFZ_NEAREST", "CONDITIONS"} & set(matched_rows))

    ocean = {} if early_exit else (state.get("ocean_data") or {})
    if ocean:
        ocean_conf = ocean.get("confidence") or Confidence(score="LOW_DATA", rationale="ocean_analytics")
        results.append(AgentResult(
            agent_name="ocean_analytics", query_id=query_id, reasoning_depth=depth,
            inputs_consumed={},
            outputs={
                k: ocean.get(k)
                for k in ("tide", "nearest_pfz", "sector_status", "pfz_persistence", "productivity_diagnosis")
                if ocean.get(k) is not None
            },
            source_provenance=SourceProvenance(
                dataset="INCOIS PFZ advisories + Survey of India 2026 tide tables (Agent 5)",
                acquisition_timestamp="", freshness_minutes=0,
            ),
            confidence=ocean_conf,
        ))

    if verdict:
        results.append(AgentResult(
            agent_name="risk_assessment", query_id=query_id, reasoning_depth=depth,
            inputs_consumed={}, outputs=verdict,
            source_provenance=SourceProvenance(
                dataset="Deterministic rules over Agent 4 + Agent 6 outputs",
                acquisition_timestamp=weather.get("acquisition_timestamp", ""), freshness_minutes=0,
            ),
            confidence=Confidence(
                score=coerce_confidence_score(state.get("confidence_tier", "LOW_DATA")),
                rationale="risk_assessment verdict",
            ),
        ))

    assembled = reporting.assemble_response(query_id, results)
    query_text = state.get("normalized_english_query") or state.get("raw_user_query") or ""
    persona = state.get("stakeholder_persona") or "fisherman"
    engine_out: list[str] = []
    # user_location travels with the verdict, not just the coordinates: Agent 9
    # must never narrate these readings under a place name they do not belong to.
    final_english = reporting.synthesize_narrative(
        query_text, verdict, results, persona=persona, user_location=state.get("user_location"),
        # A GO banner on top of "where are the nearest fishing zones?" is noise
        # that teaches people to skim the one line that matters when it is not
        # GO. Non-GO verdicts still lead, whatever was asked.
        lead_with_verdict=reporting.should_lead_with_verdict(verdict, matched_rows),
        session_history=state.get("session_history"),
        # P2.5 — on the second pass this carries the Critic's own words, so
        # the re-synthesis actually answers the critique. A re-invocation that
        # does not hand the critique to the agent that has to act on it is a
        # re-run wearing a loop's clothes.
        critique=state.get("critic_critique"),
        engine_out=engine_out,
    )

    return AgentResult(
        agent_name="reporting", query_id=query_id, reasoning_depth=depth,
        inputs_consumed={"contributing_agents": [r.agent_name for r in results]},
        outputs={
            "final_english_response": final_english,
            "citations": [
                {
                    "agent_name": c.agent_name, "dataset": c.dataset,
                    "acquisition_timestamp": c.acquisition_timestamp, "freshness_minutes": c.freshness_minutes,
                }
                for c in assembled.citations
            ],
            "early_exit_triggered": early_exit,
            # P2.3 (`R-JUDGE-4`) — the inputs the tier below was actually the
            # worst OF. assemble_response takes the worst of exactly these
            # results, so this is the derivation itself, not a description of
            # it: the card can say "MEDIUM — worst of 4 inputs: geospatial
            # MEDIUM (IMBL proxy boundary, not treaty line)" and every word of
            # that is read off this list.
            "confidence_inputs": [
                {"agent_name": r.agent_name, "tier": r.confidence.score, "rationale": r.confidence.rationale}
                for r in results
            ],
        },
        source_provenance=SourceProvenance(dataset="ORCA synthesis (Agent 9, thin — no LLM pass, plan §4 S6)", acquisition_timestamp="", freshness_minutes=0),
        confidence=Confidence(
            score=coerce_confidence_score(assembled.confidence_tier),
            rationale=f"Worst of {len(results)} contributing agents",
        ),
        engine=engine_out[0] if engine_out else None,
    )


def reporting_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("reporting", reporting_run, state)
    return {
        "final_english_response": result.outputs["final_english_response"],
        "evidence_citations": result.outputs["citations"],
        "confidence_tier": result.confidence.score,
        "early_exit_triggered": result.outputs.get("early_exit_triggered", False),
        "audit_trace_log": [entry],
        "completed_nodes": ["reporting"],
    }


def _route_after_reporting(state: ORCAState) -> str:
    """P2.5 (`R-AGENT-1`) — the Critic runs on **every** query now, not only
    at DEEP. It was DEEP-only until 2026-09-20, which meant the verification
    loop did not execute at all on an ordinary demo question; §5 is the clause
    the panel probes hardest and it was the clause nothing demonstrated.

    P2.12 is the one exception, and it is a cost rule rather than a quality
    one: on a hard-constraint NO_GO (a red/orange cyclone, lightning, an IMBL
    or MPA breach) the answer is "do not go out", the Critic reviews only the
    explanatory prose around it, and a reasoning-tier call to polish that prose
    is the plan-optional work §9.3 exists to cancel. It is recorded as a
    `cancelled` span naming the constraint, never as a silent absence.

    Bug fixed 2026-09-21: when `critic_reinvoke` sends the query back through
    Reporting for a second synthesis, this router previously routed to `critic`
    again — the Critic ran twice on every reinvocation (critic → reinvoke →
    reporting → critic). The fix: if the reinvocation budget is already spent
    (critic_reinvocations >= MAX_REINVOCATIONS), route directly to
    `language_egress`. The second Critic pass brings no value after the budget
    check in `_route_after_critic` would have sent it to `language_egress`
    anyway; running it costs one extra reasoning-tier LLM call per query that
    triggers a reinvoke.

    Never persona (Ground Rule 1 / plan §4 D1 Day 18). The verdict SSE frame
    has already been emitted upstream by the time this routes, since main.py's
    stream flushes on every graph step, so the critique frame necessarily
    lands after it."""
    if hard_constraint_no_go(state.get("risk_assessment") or {}):
        return "critic_cancelled"
    # Second reporting pass (after a critic reinvoke): the budget is spent;
    # routing back to critic would run it twice for the cost of running it once.
    if int(state.get("critic_reinvocations") or 0) >= critic.MAX_REINVOCATIONS:
        return "language_egress"
    return "critic"


def critic_cancelled_node(state: ORCAState) -> dict:
    reason = hard_constraint_no_go(state.get("risk_assessment") or {}) or "hard constraint"
    return _cancelled(
        "critic", state,
        f"hard-constraint NO_GO ({reason}); the verdict is final and "
        "reviewing the prose around it cannot change the advice",
    )


def critic_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("critic", critic.run, state)
    outputs = result.outputs or {}
    return {
        # A degraded Critic (no provider, the P2.11 switch off, a P2.13 429)
        # returns the unreviewed narrative rather than nothing — but if the
        # node itself raised, run_traced_node hands back outputs={}, and
        # indexing it would abort the answer the Critic is only meant to
        # improve. Keep whatever Reporting already produced.
        "final_english_response": outputs.get("final_english_response") or state.get("final_english_response", ""),
        "critic_pass": outputs.get("critic_pass", False),
        "critic_iteration_count": outputs.get("critic_iteration_count", 0),
        "critic_issues": outputs.get("issues") or [],
        "critic_reinvoke_agent": outputs.get("reinvoke_agent"),
        "critic_critique": outputs.get("critique"),
        "audit_trace_log": [entry],
        "completed_nodes": ["critic"],
    }


# The three specialists a critique can send the query back to, mapped to the
# function that re-runs each. `critic.REINVOCABLE_AGENTS` is the vocabulary;
# this is the wiring, kept here because geospatial's runner is this module's.
_REINVOKE_RUNNERS = {
    "weather_intelligence": weather_intelligence.run,
    "ocean_analytics": ocean_analytics.run,
    "geospatial": geospatial_run,
}


def critic_reinvoke_node(state: ORCAState) -> dict:
    """P2.5 — the re-invocation the DLC asks for and `_REINVOKE_MAP` only ever
    described. The Critic names the agent whose output a deficiency traces
    back to; that agent actually runs again, and Reporting re-synthesizes with
    the critique attached (see reporting_run's `critique=`).

    The budget is spent here rather than in the Critic, because this is the
    node that costs something. One re-invocation, capped by
    `critic.MAX_REINVOCATIONS` and enforced in `_route_after_critic` — the
    second Critic pass therefore always ends at language_egress, whatever it
    finds, which is what keeps a live demo from looping on a judge's query.

    The agent's second reading may well be identical to its first. That is a
    real outcome, not a failed one: "we re-read the boundary distance and it
    has not changed" is exactly what a verification loop is for.
    """
    agent_name = state.get("critic_reinvoke_agent")
    runner = _REINVOKE_RUNNERS.get(agent_name or "")
    if agent_name is None or runner is None:  # defensive: _route_after_critic already checked
        return _skipped("critic_reinvoke", state, f"no runner for {agent_name!r}")

    result, entry = run_traced_node(agent_name, runner, state)
    # The critique is what makes this a re-invocation rather than a re-run, so
    # it is recorded on the span itself — a judge opening this node sees what
    # it was asked to go back and check.
    entry["inputs_consumed"] = {
        **(entry.get("inputs_consumed") or {}),
        "critic_reinvocation": True,
        "critique": state.get("critic_critique"),
    }
    update: dict = {
        "audit_trace_log": [entry],
        "completed_nodes": [agent_name],
        "critic_reinvocations": int(state.get("critic_reinvocations") or 0) + 1,
    }
    # Write the fresh reading back under the same state key the first pass
    # used, so Reporting composes from the re-read value rather than the one
    # the Critic complained about.
    key = {
        "weather_intelligence": "weather_data",
        "ocean_analytics": "ocean_data",
        "geospatial": "geospatial_data",
    }[agent_name]
    if result.outputs:
        update[key] = {**result.outputs, "confidence": _scored(result, entry)}
    return update


def _route_after_critic(state: ORCAState) -> str:
    """Back to a specialist, or on to egress. Three conditions, all of which
    must hold: the Critic named a re-invocable agent, that agent has a runner
    wired here, and the budget is unspent. Anything else ends the loop."""
    agent_name = state.get("critic_reinvoke_agent")
    if not agent_name or agent_name not in _REINVOKE_RUNNERS:
        return "language_egress"
    if int(state.get("critic_reinvocations") or 0) >= critic.MAX_REINVOCATIONS:
        return "language_egress"
    return "critic_reinvoke"


def language_egress_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("language_egress", language.run_egress, state)
    # Same degrade-not-crash guard as language_ingress_node — fall back to the
    # English answer already in state rather than KeyError on an empty outputs.
    vernacular = (result.outputs or {}).get("final_vernacular_response") or state.get("final_english_response", "")
    return {
        "final_vernacular_response": vernacular,
        "audit_trace_log": [entry],
        "completed_nodes": ["language_egress"],
    }


def build_graph():
    # ORCAState IS a typing.TypedDict, but LangGraph's StateT bound is a set of
    # structural protocols that a checker cannot match a TypedDict against
    # through `from __future__ import annotations`. Runtime is unaffected.
    # pyrefly: ignore[bad-specialization]
    g = StateGraph(ORCAState)
    g.add_node("distress_check", distress_check_node)
    g.add_node("query_guard", query_guard_node)
    g.add_node("out_of_scope", out_of_scope_node)
    g.add_node("language_ingress", language_ingress_node)
    g.add_node("planning", planning_node)
    g.add_node("marine_data_discovery", marine_data_discovery_node)
    g.add_node("weather_intelligence", weather_node)
    g.add_node("geospatial", geospatial_node)
    g.add_node("ocean_analytics", ocean_analytics_node)
    g.add_node("risk_assessment", risk_assessment_node)
    g.add_node("visualization", visualization_node)
    g.add_node("reporting", reporting_node)
    g.add_node("critic", critic_node)
    g.add_node("critic_cancelled", critic_cancelled_node)
    g.add_node("critic_reinvoke", critic_reinvoke_node)
    g.add_node("language_egress", language_egress_node)

    g.add_edge(START, "distress_check")
    g.add_conditional_edges("distress_check", _route_after_distress, {END: END, "query_guard": "query_guard"})
    g.add_conditional_edges("query_guard", _route_after_query_guard, {END: END, "language_ingress": "language_ingress"})
    g.add_edge("language_ingress", "planning")
    g.add_conditional_edges(
        "planning", _route_after_planning,
        {
            "out_of_scope": "out_of_scope",
            "marine_data_discovery": "marine_data_discovery",
        },
    )
    g.add_edge("out_of_scope", END)
    # P2.6 — the fan-out now hangs off Agent 3 rather than Planning, so the
    # three specialists consume one already-made source decision instead of
    # each making its own. Still an unconditional fan-out to all three: the
    # join edges below wait for all of them, and routing around a branch would
    # leave that join un-triggered. The plan's decision is applied *inside*
    # ocean_analytics_node (the only skippable branch) and is visible there as
    # a `skipped` span — P2.7 separates presentation from execution, and
    # execution stays fail-safe on purpose.
    for specialist in ("weather_intelligence", "geospatial", "ocean_analytics"):
        g.add_edge("marine_data_discovery", specialist)
    g.add_edge(["weather_intelligence", "geospatial", "ocean_analytics"], "risk_assessment")
    g.add_edge(["weather_intelligence", "geospatial", "ocean_analytics"], "visualization")
    g.add_edge(["risk_assessment", "visualization"], "reporting")
    g.add_conditional_edges(
        "reporting", _route_after_reporting,
        {"critic": "critic", "critic_cancelled": "critic_cancelled", "language_egress": "language_egress"},
    )
    g.add_edge("critic_cancelled", "language_egress")
    # P2.5 — the loop. critic -> the named specialist -> reporting -> critic
    # again, once. `critic_reinvoke` reaches reporting on a plain edge, NOT
    # through the ["risk_assessment", "visualization"] join above: that join
    # is an all-of trigger and a second pass never re-runs both of its
    # members, so routing the loop into it would hang the graph.
    g.add_conditional_edges(
        "critic", _route_after_critic,
        {"critic_reinvoke": "critic_reinvoke", "language_egress": "language_egress"},
    )
    g.add_edge("critic_reinvoke", "reporting")
    g.add_edge("language_egress", END)
    return g.compile()
