"""LangGraph pipeline:

    distress_check --[distress_flag]--> END (response built in this node)
                   --[else]-----------> language_ingress
                                            |
                                         planning
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
                                       reporting
                                            |
                                            v
                                    language_egress --> END

geospatial and reporting are the real Agents 6/9 (S5/S6) — no longer
fixtures. language_ingress/egress are Agent 1, run twice per query (before
Planning, after Reporting), matching "Ingress & Egress" in its own name.
visualization (Agent 8, Phase 2 D3) is a sibling of risk_assessment, not
downstream of it — it shapes weather_data/geospatial_data into map layers
and charts, and never reads the safety verdict to do so.
ocean_analytics (Agent 5, Phase 2 D2) is a third sibling of weather/geospatial
— tide, PFZ proximity/persistence, sector status, and the DEEP catch-decline
diagnosis; it also carries Agent 3's source-selection narratives out on
discovery_data for the answer card.
"""
from __future__ import annotations

from dataclasses import asdict

from langgraph.graph import END, START, StateGraph

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
    return {
        "matched_intent_rows": result.outputs["matched_intent_rows"],
        "execution_plan": result.outputs["execution_plan"],
        "audit_trace_log": [entry],
        "completed_nodes": ["planning"],
    }


def weather_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("weather_intelligence", weather_intelligence.run, state)
    return {
        # Same shape the geospatial node stores: Agent 7's compute_confidence
        # reads weather_data["confidence"], so dropping it here meant a cached
        # or degraded weather feed could never degrade the verdict tier.
        # An empty outputs dict means the agent failed, and downstream code
        # tests weather_data for truthiness — so don't make it truthy with a
        # lone confidence key.
        "weather_data": {**result.outputs, "confidence": result.confidence} if result.outputs else {},
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
        return {}

    result, entry = run_traced_node("ocean_analytics", ocean_analytics.run, state)
    update: dict = {
        "ocean_data": {**result.outputs, "confidence": result.confidence} if result.outputs else {},
        "audit_trace_log": [entry],
        "completed_nodes": ["ocean_analytics"],
    }
    # Agent 3's source-selection narratives ride out on discovery_data (a
    # state field that already exists and nothing else writes) so the answer
    # card and activity strip can render them (differentiator 4).
    selections = result.outputs.get("source_selections") if result.outputs else None
    if selections:
        update["discovery_data"] = {"source_selections": selections}
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
    )


def geospatial_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("geospatial", geospatial_run, state)
    return {
        "geospatial_data": {**result.outputs, "confidence": result.confidence},
        "audit_trace_log": [entry],
        "completed_nodes": ["geospatial"],
    }


def risk_assessment_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("risk_assessment", risk_assessment.run, state)
    return {
        "risk_assessment": result.outputs,
        "confidence_tier": result.confidence.score,
        "audit_trace_log": [entry],
        "completed_nodes": ["risk_assessment"],
    }


def visualization_node(state: ORCAState) -> dict:
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

    # Cost-based short-circuit (Architecture §9.3, plan §6 Phase 4) — RAA
    # never reads ocean_data (confirmed: it only consumes weather + geospatial),
    # so Ocean Analytics' PFZ/tide/trend content is exactly the "co-occurring
    # PFZ lookup" the architecture names as safe to drop from a NO_GO
    # response. This is response trimming, not compute avoidance: the
    # ocean_analytics node still ran (LangGraph's static fan-in has no
    # supported mid-flight cancellation, see phase4 plan §2.1) — only the
    # content surfaced to the user is cut, which is the half of §9.3 that is
    # actually about what a fisherman sees. Never trimmed if the user
    # separately asked for zone/condition data (matched_intent_rows).
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
    # user_location travels with the verdict, not just the coordinates: Agent 9
    # must never narrate these readings under a place name they do not belong to.
    final_english = reporting.synthesize_narrative(
        query_text, verdict, results, persona=persona, user_location=state.get("user_location"),
        # A GO banner on top of "where are the nearest fishing zones?" is noise
        # that teaches people to skim the one line that matters when it is not
        # GO. Non-GO verdicts still lead, whatever was asked.
        lead_with_verdict=reporting.should_lead_with_verdict(verdict, matched_rows),
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
        },
        source_provenance=SourceProvenance(dataset="ORCA synthesis (Agent 9, thin — no LLM pass, plan §4 S6)", acquisition_timestamp="", freshness_minutes=0),
        confidence=Confidence(
            score=coerce_confidence_score(assembled.confidence_tier),
            rationale=f"Worst of {len(results)} contributing agents",
        ),
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
    # DEEP only, never persona (Ground Rule 1 / plan §4 D1 Day 18) — the
    # verdict SSE frame (reporting_node's final_english_response) has
    # already been emitted upstream by the time this routes, since
    # main.py's SSE stream flushes on every graph step, so the critique
    # frame this produces necessarily lands after it.
    return "critic" if state.get("reasoning_depth") == "DEEP" else "language_egress"


def critic_node(state: ORCAState) -> dict:
    result, entry = run_traced_node("critic", critic.run, state)
    return {
        "final_english_response": result.outputs["final_english_response"],
        "critic_pass": result.outputs["critic_pass"],
        "critic_iteration_count": result.outputs["critic_iteration_count"],
        "audit_trace_log": [entry],
        "completed_nodes": ["critic"],
    }


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
    g = StateGraph(ORCAState)
    g.add_node("distress_check", distress_check_node)
    g.add_node("language_ingress", language_ingress_node)
    g.add_node("planning", planning_node)
    g.add_node("weather_intelligence", weather_node)
    g.add_node("geospatial", geospatial_node)
    g.add_node("ocean_analytics", ocean_analytics_node)
    g.add_node("risk_assessment", risk_assessment_node)
    g.add_node("visualization", visualization_node)
    g.add_node("reporting", reporting_node)
    g.add_node("critic", critic_node)
    g.add_node("language_egress", language_egress_node)

    g.add_edge(START, "distress_check")
    g.add_conditional_edges("distress_check", _route_after_distress, {END: END, "language_ingress": "language_ingress"})
    g.add_edge("language_ingress", "planning")
    g.add_edge("planning", "weather_intelligence")
    g.add_edge("planning", "geospatial")
    g.add_edge("planning", "ocean_analytics")
    g.add_edge(["weather_intelligence", "geospatial", "ocean_analytics"], "risk_assessment")
    g.add_edge(["weather_intelligence", "geospatial", "ocean_analytics"], "visualization")
    g.add_edge(["risk_assessment", "visualization"], "reporting")
    g.add_conditional_edges("reporting", _route_after_reporting, {"critic": "critic", "language_egress": "language_egress"})
    g.add_edge("critic", "language_egress")
    g.add_edge("language_egress", END)
    return g.compile()
