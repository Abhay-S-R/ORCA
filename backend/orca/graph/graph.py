"""LangGraph pipeline:

    distress_check --[distress_flag]--> END (response built in this node)
                   --[else]-----------> language_ingress
                                            |
                                        understand
                                            |
                                        query_guard
                                            |
                        --[can't place it / can't reach that time]--> END
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
read no dataset and emit no trace entry. Since chatbot plan C0.2d a model
*words* their reply (reporting.write_guard_reply) — the guard still decides
whether to stop and what the reply must say, and a reply carrying a figure the
guard did not supply is discarded. Both sit downstream of
distress_check and nowhere else, which is the ordering the phase depends on —
a garbled, place-less, out-of-scope-looking message is exactly what someone in
trouble sends, and Agent 12 sees every one of them first.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from orca import engines, query_cache, reconcile
from orca.agents import (
    critic,
    distress,
    distress_escalation,
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
# product." P5.5: the treaty-line dataset (32 features — Pakistan, Bangladesh,
# Sri Lanka, Maldives, Myanmar/Thailand/Indonesia) is on disk and read via
# geospatial.nearest_boundary_line(), which names whichever line is actually
# nearest — a position off Sir Creek now reads the Pakistan line instead of a
# Sri Lanka distance that has nothing to do with it. The Sri Lanka EEZ polygon
# stays only as the fallback if that line file is ever absent from a fresh
# clone (its own geodesic distance, computed the same way containment checks
# always were).
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


def _distress_with_escalation(state: ORCAState) -> AgentResult:
    """Agent 12 with its escalate-only model check supplied. `distress.py` stays model-free;
    the check is handed in here, and can only turn "no distress" into "distress"."""
    return distress.run(state, escalate=distress_escalation.escalate_with_model)


def distress_check_node(state: ORCAState) -> dict:
    """Runs Agent 12 exactly ONCE. Previously this node only extracted the
    boolean flag, and a separate distress_response_node re-ran distress.run()
    from scratch to get the MRCC/handoff payload — on the one path where
    latency matters most (SOS, <2s), that meant duplicating detection,
    MRCC lookup and handoff formatting for no reason, and it left two
    "distress" entries in the trace for what is genuinely one agent
    invocation. Everything downstream needs is computed here, once."""
    result, entry = run_traced_node("distress", _distress_with_escalation, state)
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
    return END if state.get("distress_flag") else "language_ingress"


def _candidate_list(candidates: list[dict]) -> str:
    return ", ".join(f"{c['name'].title()} ({c['lat']:.2f}N {c['lon']:.2f}E)" for c in candidates)


def _conversation_context(state: ORCAState) -> str:
    return reporting.conversation_context(state.get("session_history"), state.get("user_location"))


def _guard_reply(state: ORCAState, required: str, *, allow_small_talk: bool = False) -> dict:
    """Chatbot plan C0.2d — the reply to a stopped message, worded by a model.
    The guard has already decided everything; `required` is what the reply
    must say, and stays the reply if no model answers (reporting.write_guard_reply).
    The model writes in the user's own language, so both response fields hold
    the same text."""
    reply, engine, small_talk = reporting.write_guard_reply(
        state.get("raw_user_query", "") or "", required, allow_small_talk=allow_small_talk,
        context=_conversation_context(state),
    )
    return {
        "final_english_response": reply,
        "final_vernacular_response": reply,
        "response_engine": engine,
        "small_talk": small_talk,
    }


def _refusal(outcome: str, body: str, state: ORCAState) -> dict:
    """A stop with no marine content in it. Certainty about *not knowing* is
    still certainty, so the tier is HIGH: no reading was taken, so nothing
    here can be stale or thin, and a LOW_DATA label would read as "a weak
    answer" rather than "no answer, and here is what I need". `disclosures`
    keeps the guard's own fixed wording, whatever the model made of it."""
    return {
        "query_outcome": outcome,
        **_guard_reply(state, body),
        "confidence_tier": "HIGH",
        "disclosures": [body],
    }




def out_of_scope_node(state: ORCAState) -> dict:
    """P1.3 (`R-EDGE-1`) — a first-class "I can't answer that": a short
    refusal plus a redirect, and emphatically zero marine content. No agent
    below Planning has run, so there is no number here to be wrong.

    Prompt Routing Revamp §6: uses Understand agent's `kind` to route
    greeting, clock, off-topic, capability, reset to model-written replies.
    The deterministic word lists stay as the offline fallback.
    """
    understood_kind = state.get("understood_kind")
    query = state.get("raw_user_query", "") or ""

    if understood_kind == "clock_or_position" or planning.is_self_context_question(query) or planning.is_self_context_question(state.get("normalized_english_query") or ""):
        reply, engine = reporting.write_self_context_reply(query, _self_context_facts(state), _conversation_context(state))
        return {
            "query_outcome": "OUT_OF_SCOPE",
            "final_english_response": reply,
            "final_vernacular_response": reply,
            "response_engine": engine,
            "small_talk": True,
            "confidence_tier": "HIGH",
            "execution_plan": [],
        }

    if understood_kind == "greeting_or_small_talk":
        body = "Hello! I'm Sagar Sarathi — I help with sea conditions off India's coast: safety to go out, waves, wind, tides, fishing zones, and maritime boundaries. What would you like to know?"
        return {
            "query_outcome": "OUT_OF_SCOPE",
            **_guard_reply(state, body, allow_small_talk=True),
            "confidence_tier": "HIGH",
            "execution_plan": [],
        }

    if understood_kind == "inland_place":
        # An inland place is not a refusal and not a sea question: say plainly that ORCA has no
        # sea data for it and what it can do instead. No agent runs, so no number can be wrong.
        body = (
            "That place is inland, away from the coast, so I have no sea data for it. I only cover the sea off "
            "India's coast. Name a coastal place or send your position and I'll tell you the conditions there."
        )
        facts = (
            f"{reporting.CAPABILITY_FACTS} The place the user asked about is inland, away from the coast: "
            "Sagar Sarathi has no weather or sea data for it, and does not give land-based forecasts."
        )
        reply, engine = reporting.write_chat_reply(query, facts, body, _conversation_context(state))
        return {
            "query_outcome": "OUT_OF_SCOPE",
            "final_english_response": reply,
            "final_vernacular_response": reply,
            "response_engine": engine,
            "small_talk": True,
            "confidence_tier": "HIGH",
            "execution_plan": [],
        }

    if understood_kind in ("what_can_orca_do", "chat_followup"):
        # Conversation, not a refusal: the model answers the message from what ORCA can do,
        # as the next turn of the chat. The fixed sentence is only the no-model fallback.
        body ="I answer questions about conditions at sea off India — whether it's safe to go out, wave height, wind speed, tides, nearest fishing zones, and maritime boundaries. Name a coastal place or send your position, and I'll answer for it."
        reply, engine = reporting.write_chat_reply(query, reporting.CAPABILITY_FACTS, body, _conversation_context(state))
        return {
            "query_outcome": "OUT_OF_SCOPE",
            "final_english_response": reply,
            "final_vernacular_response": reply,
            "response_engine": engine,
            "small_talk": True,
            "confidence_tier": "HIGH",
            "execution_plan": [],
        }

    if understood_kind == "reset_or_language_switch":
        body = "Sure thing — just let me know what you'd like to change."
        return {
            "query_outcome": "OUT_OF_SCOPE",
            **_guard_reply(state, body, allow_small_talk=True),
            "confidence_tier": "HIGH",
            "execution_plan": [],
        }

    # off_topic or any other kind not handled above
    body = (
        "I can't answer that. I only answer questions about conditions at sea off India — "
        "whether it is safe to go out, waves, wind, tides, fishing zones, and maritime "
        "boundaries. Ask me one of those and name a place, or tap SOS if you are in trouble."
    )
    return {
        "query_outcome": "OUT_OF_SCOPE",
        **_guard_reply(state, body, allow_small_talk=True),
        "confidence_tier": "HIGH",
        "execution_plan": [],
    }


_IST = timezone(timedelta(hours=5, minutes=30))


def _self_context_facts(state: ORCAState) -> str:
    """What is actually true right now, for write_self_context_reply. A
    position is included only when the browser sent a real fix THIS turn
    (`place_source == "gps_fix"` or `fix_lat`/`fix_lon` present) — never the
    pilot default and never a place carried over from an earlier turn, both of
    which are a guess about where the caller is, not a report of it."""
    now = datetime.now(_IST).strftime("%H:%M IST on %d %b %Y")
    loc = state.get("user_location") or {}
    raw_lat = loc.get("fix_lat") if loc.get("fix_lat") is not None else (loc.get("lat") if loc.get("place_source") == "gps_fix" else None)
    raw_lon = loc.get("fix_lon") if loc.get("fix_lon") is not None else (loc.get("lon") if loc.get("place_source") == "gps_fix" else None)
    if raw_lat is not None and raw_lon is not None:
        land_note = " (on land near the coast)" if loc.get("fix_on_land") else ""
        return (
            f"The current time is {now}. The browser shared your current position: "
            f"{raw_lat:.4f}, {raw_lon:.4f}{land_note}. This is for information only — it is not a "
            "place to answer a sea-conditions question at unless the caller names it or asks about it."
        )
    return (
        f"The current time is {now}. No position has been shared for this question — a browser "
        "does not send one automatically, and none was included with this message."
    )


def _route_after_planning(state: ORCAState) -> list[str] | str:
    """PC2.3 — validation folded into planning. If query_outcome is a refusal
    (NEEDS_PLACE or OUT_OF_RANGE), route to END. Otherwise route to out_of_scope
    for non-marine queries, or marine_data_discovery to start the specialist run.
    """
    if state.get("query_outcome") in ("NEEDS_PLACE", "OUT_OF_RANGE"):
        return END
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
    from orca import demo_fixtures

    pinned = demo_fixtures.fixture_result(state, "marine_data_discovery")
    if pinned is not None:
        return pinned

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
    # Same degrade-not-crash guard as language_ingress_node — fall back to the
    # English answer already in state rather than KeyError on an empty outputs.
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
    """PC2.2 & PC2.3 — planning now owns prompt understanding, validation (folded
    from query_guard), and routing in one node.
    Stores understood_* classification fields, validation outcome, and routing fields.
    """
    result, entry = run_traced_node("planning", planning.run, state)
    outputs = result.outputs or {}
    update = {
        # Understood classification fields (previously set by understand_node)
        "understood_kind": outputs.get("kind"),
        "understood_intents": outputs.get("intents", []),
        "understood_places": outputs.get("places", []),
        "understood_when": outputs.get("when"),
        "understood_is_followup": outputs.get("is_followup", False),
        "planned_agents": outputs.get("agents", []),  # PC2.1
        "understood_english_reading": outputs.get("english_reading"),  # PC5.2, display only
        "reply_language": outputs.get("reply_language"),  # PC5.8, only when explicitly requested
        # Validation / guard fields (PC2.3)
        "query_outcome": outputs.get("query_outcome"),
        # Routing fields
        "matched_intent_rows": outputs.get("matched_intent_rows", []),
        "execution_plan": outputs.get("execution_plan", []),
        "audit_trace_log": [entry],
        "completed_nodes": ["planning"],
    }
    # PC2.3: If validation produced a refusal (NEEDS_PLACE or OUT_OF_RANGE),
    # generate the refusal response directly so the graph routes to END.
    if outputs.get("query_outcome") in ("NEEDS_PLACE", "OUT_OF_RANGE"):
        refusal_update = _refusal(outputs["query_outcome"], outputs.get("query_outcome_body") or "", state)
        update.update(refusal_update)
    elif outputs.get("disclosures"):
        update["disclosures"] = outputs["disclosures"]

    # A "why has the catch dropped?" question is what DEEP exists for — the
    # productivity diagnosis only runs there (P5.29). Only ever raises depth.
    if "DIAGNOSTIC" in (update.get("matched_intent_rows") or []):
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
    # PC3.3: Check execution_plan to allow skipping (consistent with ocean_analytics pattern)
    plan = state.get("execution_plan") or []
    if plan and "weather_intelligence" not in plan:
        return _skipped(
            "weather_intelligence", state,
            f"not in this query's execution plan ({', '.join(plan)})",
        )

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
    from orca import demo_fixtures

    pinned = demo_fixtures.fixture_result(state, "geospatial")
    if pinned is not None:
        return pinned

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

    line = geospatial.nearest_boundary_line(lat, lon)
    if line is not None:
        imbl_distance_nm = line["distance_nm"]
        imbl_alert_level = line["alert_level"]
        imbl_boundary_name = line["line_name"]
        imbl_between = line["between"]
        imbl_confidence_note = f"nearest of 32 treaty lines: {line['line_name']}"
    else:
        # india_maritime_boundary_lines.geojson absent from this clone — the
        # EEZ-polygon proxy this replaced, never a fabricated number.
        fallback = geospatial.check_boundary_proximity(lat, lon, _IMBL_PROXY_BOUNDARY)
        imbl_distance_nm = fallback.distance_nm
        imbl_alert_level = fallback.alert_level
        imbl_boundary_name = _IMBL_PROXY_BOUNDARY
        imbl_between = None
        imbl_confidence_note = f"treaty-line dataset absent, fell back to {_IMBL_PROXY_BOUNDARY} proxy"
    mpa = geospatial.check_boundary_proximity(lat, lon, _MPA_BOUNDARY)
    ban = geospatial.fishing_ban_status(lat, lon)

    return AgentResult(
        agent_name="geospatial",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        # The whole location dict, not just the pair: `place_source` is what
        # tells a later re-render (trace_routes' /render) whether this position
        # was resolved from the query or fell back to the regional default.
        inputs_consumed={"lat": lat, "lon": lon, "user_location": dict(location)},
        outputs={
            "imbl_distance_nm": imbl_distance_nm,
            "imbl_alert_level": imbl_alert_level,
            "imbl_boundary_name": imbl_boundary_name,
            "imbl_between": imbl_between,
            "mpa_violation": mpa.alert_level == "INSIDE",
            "mpa_alert_level": mpa.alert_level,
            "fishing_ban": ban,
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
        confidence=Confidence(score="MEDIUM", rationale=f"Real boundary check — {imbl_confidence_note} — and {_MPA_BOUNDARY}"),
        # Boundary geometry is STATIC-class reference data; coverage is whether
        # both proximity checks returned a distance.
        freshness_class="STATIC",
        data_age_minutes=0,
        fallback_depth=0,
        coverage=(sum(1 for d in (imbl_distance_nm, mpa.distance_nm) if d is not None), 2),
    )


def geospatial_node(state: ORCAState) -> dict:
    # PC3.3: Check execution_plan to allow skipping (consistent with ocean_analytics pattern)
    plan = state.get("execution_plan") or []
    if plan and "geospatial" not in plan:
        return _skipped(
            "geospatial", state,
            f"not in this query's execution plan ({', '.join(plan)})",
        )

    result, entry = run_traced_node("geospatial", geospatial_run, state)
    _attach_discovery(entry, state, ("boundary",))
    update: dict[str, Any] = {
        "geospatial_data": {**result.outputs, "confidence": _scored(result, entry)},
        "audit_trace_log": [entry],
        "completed_nodes": ["geospatial"],
    }
    # P5.5 — a REGULATORY constraint, not a safety one (fishing_ban_status's
    # own docstring: it never becomes a NO_GO by itself, and never a GO
    # either). It is stated regardless of location whenever the uniform ban
    # is in force and actually reaches this position (outside the 12 NM
    # state-waters carve-out) — the answer below must not omit it just
    # because the physical verdict came back GO.
    ban = (result.outputs or {}).get("fishing_ban") or {}
    if ban.get("available") and ban.get("in_ban_period") and ban.get("applies_here"):
        file_number = (ban.get("order") or {}).get("file_number", "")
        update["disclosures"] = [
            (f"REGULATORY: uniform seasonal fishing ban in force on the {ban.get('coast')} coast "
            f"({ban.get('window', '')}{', ' + file_number if file_number else ''}) — this applies "
            "regardless of the sea-state verdict below.")
        ]
    return update


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
    weather_data = state.get("weather_data") or {}
    # P6.11 (orca_final §4.6) — CAUTION_MISSING_DATA with an entirely empty
    # weather_data means every source in the cascade failed, not just one
    # field: "insufficient data" is honest but useless next to a real,
    # if aging, verdict for the same spot. Try that before accepting the
    # empty one. Gated on weather_data specifically (not ocean/geospatial
    # gaps) because that is the one agent whose cascade this system treats
    # as "every live source", per P2.4/P2.6's own reconciliation logic.
    if status == "CAUTION_MISSING_DATA" and not weather_data:
        location = state.get("user_location") or {}
        lat, lon = location.get("lat"), location.get("lon")
        cached = (
            query_cache.get_last_known_verdict(float(lat), float(lon), state.get("vessel_class"))
            if lat is not None and lon is not None else None
        )
        if cached:
            import datetime as _dt

            computed_at = _dt.datetime.fromisoformat(cached["computed_at"])
            age_minutes = round((_dt.datetime.now(_dt.timezone.utc) - computed_at).total_seconds() / 60)
            age_text = f"{age_minutes} min" if age_minutes < 120 else f"{round(age_minutes / 60, 1)} h"
            cached_verdict = cached["risk_assessment"]
            update["risk_assessment"] = {**cached_verdict, "status": f"{cached_verdict.get('status', 'SAFE')}_CACHED"}
            update["confidence_tier"] = "LOW_DATA"
            update["disclosures"] = [
                (f"Live data unavailable right now. This is Sagar Sarathi's last computed verdict for this "
                f"location, from {age_text} ago — not a fresh read of current conditions.")
            ]
            return update
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
    # P5.8 — safe is not the same claim as worthwhile. A GO with the sector
    # cloud-suppressed and the nearest PFZ far away is technically correct
    # and practically useless; say so instead of leaving a fisherman to read
    # a bare "GO" as "there's fish nearby today". Only on a real GO — a
    # CAUTION/NO_GO already carries its own reason and doesn't need this one
    # competing for attention above it.
    if (result.outputs or {}).get("go_no_go") == "GO":
        worthwhile_note = _worthwhileness_disclosure(state.get("ocean_data") or {})
        if worthwhile_note:
            update["disclosures"] = [*update.get("disclosures", []), worthwhile_note]
    # P6.11 — this query's weather data was real, so its verdict is worth
    # keeping as the next outage's fallback. Never stores a verdict that was
    # itself a P6.11 fallback (that branch already returned above) or one
    # computed on missing data (status check below), so a fallback can never
    # become the source for the next fallback.
    if weather_data and status not in ("CAUTION_MISSING_DATA", "CAUTION_STALE_DATA"):
        location = state.get("user_location") or {}
        lat, lon = location.get("lat"), location.get("lon")
        if lat is not None and lon is not None:
            query_cache.store_last_known_verdict(float(lat), float(lon), state.get("vessel_class"), update["risk_assessment"])
    return update


# P5.8 — a fixed, disclosed cut for "reachable today", not a per-vessel reach
# calculation (that is the `/zones` cruise-speed filter, a frontend-only
# feature with no cruise speed threaded into this backend state yet). Named
# in the disclosure text itself rather than hidden in a silent comparison.
_PFZ_DAY_TRIP_KM = 50.0


def _worthwhileness_disclosure(ocean: dict[str, Any]) -> str | None:
    sector = ocean.get("sector_status") or {}
    if not sector.get("is_data_gap"):
        return None  # a real advisory (or a genuinely empty one) needs no caveat
    reason = "cloud cover" if sector.get("status") == "NO_DATA_CLOUD_COVER" else "no advisory on record for your sector today"
    near = ocean.get("nearest_pfz") or {}
    if not near.get("found"):
        return f"Safe to sail. But there is no fishing advisory for your sector today ({reason}), and none was found nearby either."
    distance = near.get("distance_km")
    if isinstance(distance, (int, float)) and distance > _PFZ_DAY_TRIP_KM:
        compass = f" ({near['compass']})" if near.get("compass") else ""
        return (
            f"Safe to sail. But no fishing advisory for your sector today ({reason}), and the "
            f"nearest is {distance:.0f} km away{compass} — not a realistic day trip."
        )
    return None


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
        # The boundary distance is narrated only when the question was about
        # boundaries or it is part of why the verdict is not GO; otherwise
        # "146.6 nm to the Maldives line" tailed every answer about fishing zones.
        boundary_asked = "ZONES_TO_AVOID" in (state.get("matched_intent_rows") or []) or (
            (state.get("risk_assessment") or {}).get("go_no_go") not in (None, "GO")
        )
        results.append(AgentResult(
            agent_name="geospatial", query_id=query_id, reasoning_depth=depth,
            inputs_consumed={},
            outputs={"imbl_distance_nm": geo.get("imbl_distance_nm") if boundary_asked else None,
                     "mpa_violation": geo.get("mpa_violation")},
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
                for k in (
                    "tide", "nearest_pfz", "sector_status", "pfz_persistence",
                    "productivity_diagnosis",
                    # Chatbot plan F1 / defect 3 (2026-09-25): the INCOIS OSF
                    # wave/current point forecast, and its own age_days/band/
                    # expired (stale-data policy §7), used to reach only the
                    # /query trace's Ocean Analytics span — never the written
                    # narrative, so a question near one of the 8 pre-extracted
                    # pilot ports never mentioned it however old it was.
                    "osf_point_forecast",
                )
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
    reading = state.get("understood_english_reading")
    if state.get("reply_language") and reading:
        # PC5.8: the narrative must see the question, not "say it in Kannada:", which it obeys
        # (writes Kannada) or translates (answers with the question itself).
        query_text = reading
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
            # What made the answer LOW_DATA, so "Data limited" can say why
            # instead of reading as doubt about the safety check.
            # (minus the "[score N: …]" suffix _scored appends for the trace).
            "confidence_reason": ("; ".join(
                r.confidence.rationale.split(" [score ")[0] for r in results
                if r.confidence.score == "LOW_DATA" and r.agent_name != "risk_assessment"
            ) or None) if assembled.confidence_tier == "LOW_DATA" else None,
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
        # Chatbot plan C0.2e — which engine wrote it; "Deterministic — …" is
        # the facts paragraph, which the chat UI labels as such.
        "response_engine": result.engine,
        "evidence_citations": result.outputs["citations"],
        "confidence_tier": result.confidence.score,
        "confidence_reason": result.outputs.get("confidence_reason"),
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
    if (state.get("critic_reinvocations") or 0) >= critic.MAX_REINVOCATIONS:
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
    revised = outputs.get("final_english_response")
    # A Critic rewrite is text its own model wrote — including a rewrite of
    # Reporting's facts paragraph, which then stops being a template answer.
    rewrote = bool(revised) and revised != state.get("final_english_response") and bool(result.engine)
    return {
        **({"response_engine": result.engine} if rewrote else {}),
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
        "critic_reinvocations": (state.get("critic_reinvocations") or 0) + 1,
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
    if (state.get("critic_reinvocations") or 0) >= critic.MAX_REINVOCATIONS:
        return "language_egress"
    return "critic_reinvoke"


def language_egress_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("language_egress", language.run_egress, state)
    # Same degrade-not-crash guard as language_ingress_node — fall back to the
    # English answer already in state rather than KeyError on an empty outputs.
    vernacular = (result.outputs or {}).get("final_vernacular_response") or state.get("final_english_response", "")
    return {
        "final_vernacular_response": vernacular,
        "confidence_reason": (result.outputs or {}).get("confidence_reason") or state.get("confidence_reason"),
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
    g.add_node("out_of_scope", out_of_scope_node)
    g.add_node("language_ingress", language_ingress_node)
    # PC2.2 & PC2.3: understand & query_guard removed; planning owns LLM understanding & validation.
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
    g.add_conditional_edges("distress_check", _route_after_distress, {END: END, "language_ingress": "language_ingress"})
    # PC2.2 & PC2.3: language_ingress goes straight to planning, which validates reading
    # and routes to END (refusal), out_of_scope (non-marine), or marine_data_discovery (sea question).
    g.add_edge("language_ingress", "planning")
    g.add_conditional_edges(
        "planning", _route_after_planning,
        {
            END: END,
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
