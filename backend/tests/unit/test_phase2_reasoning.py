"""Phase 2 — the conversation that visibly reasons.

Covers the points whose behaviour lives in the graph's wiring rather than in
any one agent, which is exactly where a regression would otherwise be invisible
until a demo:

    P2.5  (`R-AGENT-1`)  the Critic runs on every query, and its critique
                         actually sends the query back to a named specialist —
                         once, and only once.
    P2.6  (`R-AGENT-2`)  Agent 3 is a real node that runs before the fan-out.
    P2.7  (`R-JUDGE-3`)  a skip is a visible decision, not a gap.
    P2.11 (`R-NEW-3`)    with every provider disabled, the verdict, geofence,
                         citations and confidence still render.
    P2.12 (orca_final §4.1) a hard-constraint NO_GO cancels pending optional
                         work, with the reason on the span.
    P2.14 (orca_final §16.2) "forget that, start fresh" is a reset, not a
                         marine question.

No test here calls a live LLM. The Critic's judge is stubbed, which is the
point: what is under test is the *wiring* — that a critique routes, that the
budget holds, that the verdict header survives — none of which may depend on
what a model happens to say today.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orca import session as session_memory
from orca.agents import critic
from orca.graph import graph as g
from orca.llm.tiers import LLMUnavailable, llm_switch


def _state(**overrides):
    base = {
        "query_id": "t-phase2",
        "raw_user_query": "is it safe to go to sea today",
        "normalized_english_query": "is it safe to go to sea today",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 8.80, "lon": 78.30, "place_name": "Thoothukudi", "place_source": "explicit"},
        "matched_intent_rows": ["SAFETY_CHECK"],
        "execution_plan": ["marine_data_discovery", "weather_intelligence", "ocean_analytics", "risk_assessment"],
        "session_history": [],
        "disclosures": [],
    }
    base.update(overrides)
    return base


# --- P2.5: the Critic runs on every query, and re-invokes once --------------

def test_the_critic_runs_on_an_ordinary_shallow_query() -> None:
    """It was gated on reasoning_depth == "DEEP", so on a default demo query
    the verification loop did not execute at all — the one clause DLC §5 says
    the panel probes hardest was the one nothing demonstrated."""
    assert g._route_after_reporting(_state(risk_assessment={"go_no_go": "GO", "status": "SAFE"})) == "critic"


def test_a_critique_naming_a_specialist_routes_back_to_it() -> None:
    state = _state(
        critic_reinvoke_agent="geospatial",
        critic_critique="[spatial_accuracy] the stated distance does not match",
        critic_reinvocations=0,
    )
    assert g._route_after_critic(state) == "critic_reinvoke"


def test_the_reinvocation_budget_is_one_and_is_enforced_by_the_graph() -> None:
    """orca_final §3.9 asks for up to three DEEP iterations; this plan holds
    the cap at one for latency and provider quota. The second Critic pass must
    end the loop whatever it finds, or a judge's query can spin."""
    assert critic.MAX_REINVOCATIONS == 1
    spent = _state(
        critic_reinvoke_agent="geospatial",
        critic_critique="still wrong",
        critic_reinvocations=critic.MAX_REINVOCATIONS,
    )
    assert g._route_after_critic(spent) == "language_egress"


def test_a_critique_naming_reporting_does_not_route_anywhere() -> None:
    """`_REINVOKE_MAP` maps two rubric items to `reporting`, but re-running
    Reporting is what the Critic's own revise step already did — routing the
    graph back through it would buy a second synthesis to redo that."""
    assert "reporting" not in critic.REINVOCABLE_AGENTS
    state = _state(critic_reinvoke_agent="reporting", critic_reinvocations=0)
    assert g._route_after_critic(state) == "language_egress"


def test_reinvocation_target_picks_the_first_specialist_issue_deterministically() -> None:
    issues = [
        {"rubric_item": "citation_completeness", "description": "x", "reinvoke_agent": "reporting"},
        {"rubric_item": "spatial_accuracy", "description": "y", "reinvoke_agent": "geospatial"},
        {"rubric_item": "temporal_coherence", "description": "z", "reinvoke_agent": "weather_intelligence"},
    ]
    assert critic.reinvocation_target(issues) == "geospatial"
    assert critic.reinvocation_target([issues[0]]) is None
    assert critic.reinvocation_target([]) is None


def test_the_reinvoke_node_carries_the_critique_onto_the_span() -> None:
    """A re-invocation that does not record what it was asked to check is a
    re-run. The span is where a judge opens the loop and sees the reason."""
    state = _state(
        critic_reinvoke_agent="geospatial",
        critic_critique="[spatial_accuracy] distance does not match the boundary data",
        critic_reinvocations=0,
    )
    update = g.critic_reinvoke_node(state)  # type: ignore[arg-type]
    (entry,) = update["audit_trace_log"]
    assert entry["agent_name"] == "geospatial"
    assert entry["inputs_consumed"]["critic_reinvocation"] is True
    assert "spatial_accuracy" in entry["inputs_consumed"]["critique"]
    assert update["completed_nodes"] == ["geospatial"]
    assert update["critic_reinvocations"] == 1


def test_a_critic_failure_keeps_the_narrative_reporting_already_produced() -> None:
    """The Critic upgrades explanations; it never blocks a response. A node
    that raised hands back outputs={}, and indexing that would abort the very
    answer this agent exists to improve."""
    state = _state(final_english_response="GO: All Parameters Within Safe Operational Limits")
    with patch.object(g, "run_traced_node", return_value=(MagicMock(outputs={}), {"agent_name": "critic"})):
        update = g.critic_node(state)  # type: ignore[arg-type]
    assert update["final_english_response"] == "GO: All Parameters Within Safe Operational Limits"
    assert update["critic_pass"] is False


# --- P2.6: Agent 3 is a real node ------------------------------------------

def test_planning_routes_to_agent_3_before_the_fan_out() -> None:
    assert g._route_after_planning(_state()) == "marine_data_discovery"


def test_agent_3_resolves_a_source_per_data_type_and_validates_arrival() -> None:
    result = g.marine_data_discovery_run(_state())  # type: ignore[arg-type]
    selections = result.outputs["source_selections"]
    assert selections, "Agent 3 must settle a source for at least the core data types"
    for selection in selections:
        assert selection.get("narrative")
        assert "arrival" in selection, "every selection records whether arrival was checked"
    # A live API cannot be probed before the fetch and must not claim it was.
    by_type = {s["data_type"]: s for s in selections}
    assert by_type["wave_height"]["arrival"]["checked"] is False


def test_agent_3_asks_for_more_data_types_on_a_compound_query_than_a_simple_one() -> None:
    simple = g._data_types_for(["SAFETY_CHECK"])
    compound = g._data_types_for(["SAFETY_CHECK", "PFZ_NEAREST"])
    assert set(simple) < set(compound)


def test_the_core_data_types_are_resolved_whatever_was_asked() -> None:
    """The verdict is computed for every query, including one the router did
    not read as a safety question — so its inputs are never intent-gated."""
    for rows in ([], ["EXPORT"], ["META"], ["PFZ_NEAREST"]):
        assert set(g._CORE_DATA_TYPES) <= set(g._data_types_for(rows))


# --- P2.7: a skip is a visible decision ------------------------------------

def test_a_plan_gated_skip_emits_a_span_with_a_reason() -> None:
    update = g.ocean_analytics_node(_state(execution_plan=["geospatial", "risk_assessment"]))  # type: ignore[arg-type]
    (entry,) = update["audit_trace_log"]
    assert entry["status"] == "skipped"
    assert entry["skip_reason"]
    assert entry["outputs"] == {}
    assert "ocean_data" not in update


def test_a_not_run_span_keeps_the_two_lists_in_lockstep() -> None:
    """api/main.py pairs completed_nodes and audit_trace_log index-for-index.
    A node contributing to one but not the other silently mislabels every
    span after it."""
    for update in (
        g._skipped("ocean_analytics", _state(), "not in plan"),  # type: ignore[arg-type]
        g._cancelled("critic", _state(), "hard constraint"),  # type: ignore[arg-type]
    ):
        assert len(update["audit_trace_log"]) == len(update["completed_nodes"]) == 1


# --- P2.12: the early exit is real and visible ------------------------------

@pytest.mark.parametrize(
    ("verdict", "expected"),
    [
        ({"go_no_go": "NO_GO", "status": "DANGER", "reason": "Active Convective Lightning Strike Zone"}, True),
        ({"go_no_go": "NO_GO", "status": "CRITICAL_GEOFENCE", "reason": "Imminent Boundary or MPA Breach"}, True),
        # A rough-sea NO_GO is deliberately NOT a hard constraint: that is the
        # case where the tide window and a sheltered zone are the most useful
        # things on the page.
        ({"go_no_go": "NO_GO", "status": "WARNING", "reason": "Rough Sea State"}, False),
        ({"go_no_go": "CAUTION", "status": "WARNING", "reason": "Rough Sea State"}, False),
        ({"go_no_go": "GO", "status": "SAFE", "reason": "All Parameters Within Safe Operational Limits"}, False),
        ({}, False),
    ],
)
def test_only_a_hard_constraint_no_go_cancels_pending_work(verdict: dict, expected: bool) -> None:
    assert (g.hard_constraint_no_go(verdict) is not None) is expected


def test_a_cancelled_critic_names_the_constraint_that_cancelled_it() -> None:
    state = _state(risk_assessment={
        "go_no_go": "NO_GO", "status": "DANGER", "reason": "Active Convective Lightning Strike Zone",
    })
    assert g._route_after_reporting(state) == "critic_cancelled"
    update = g.critic_cancelled_node(state)  # type: ignore[arg-type]
    (entry,) = update["audit_trace_log"]
    assert entry["status"] == "cancelled"
    assert "Lightning" in entry["skip_reason"]
    # A span that did not run has no measurement, and LOW_DATA is the honest
    # confidence for one — never HIGH, which reads as "confidently nothing".
    assert entry["confidence"] == "LOW_DATA"


# --- P2.11: the LLM is optional --------------------------------------------

def test_the_switch_makes_every_tier_refuse() -> None:
    from orca.llm.tiers import llm

    with llm_switch(False):
        for tier in ("cheap", "mid", "reasoning"):
            with pytest.raises(LLMUnavailable):
                llm(tier)  # type: ignore[arg-type]


def test_with_no_llm_the_verdict_and_its_reason_still_render() -> None:
    """The whole claim of P2.11: the safety output is deterministic code, so
    turning every provider off degrades the prose and nothing else."""
    from orca.agents import reporting

    verdict = {"go_no_go": "CAUTION", "status": "WARNING", "reason": "Rough Sea State / Boundary Proximity"}
    with llm_switch(False):
        narrative = reporting.synthesize_narrative("is it safe today", verdict, [])
    assert narrative.startswith("CAUTION:")
    assert "Rough Sea State" in narrative


def test_a_disabled_run_labels_its_span_deterministic_rather_than_a_model() -> None:
    from orca.agents import reporting

    engine_out: list[str] = []
    with llm_switch(False):
        reporting.synthesize_narrative(
            "is it safe today", {"go_no_go": "GO", "reason": "clear"}, [], engine_out=engine_out,
        )
    assert engine_out and engine_out[0].startswith("Deterministic")
    assert "disabled" in engine_out[0]


def test_the_switch_does_not_leak_between_requests() -> None:
    from orca.llm.tiers import llm_enabled

    with llm_switch(False):
        assert llm_enabled() is False
    assert llm_enabled() is True


# --- P2.9: a continuation keeps the conversation's intent -------------------

def test_a_continuation_follow_up_keeps_the_previous_intent_as_well_as_its_own() -> None:
    """P2.9's third Done-when clause, and a regression this exact test exists
    to hold. Before P2.8, Tier 2 was a literal word-overlap scorer, so "and in
    a trawler?" matched nothing and fell through to `carry_intent` —
    inheriting SAFETY_CHECK, which is right. A sentence-embedding scorer
    always has a nearest row, so it began matching CONDITIONS on its own and
    the safety intent of the conversation was silently dropped: a trawler
    *safety* question answered as a conditions question, without the verdict
    leading. Caught by running the three-turn Done-when live, not by a unit
    test — hence this one."""
    from orca.agents import planning

    history = [{"english_query": "is it safe near Rameswaram tomorrow", "intent_rows": ["SAFETY_CHECK"]}]
    result = planning.run(_state(
        raw_user_query="and in a trawler",
        normalized_english_query="and in a trawler",
        session_history=history,
        matched_intent_rows=[],
        execution_plan=[],
    ))
    rows = result.outputs["matched_intent_rows"]
    assert "SAFETY_CHECK" in rows, rows


def test_a_full_question_after_a_safety_turn_is_its_own_question() -> None:
    """The other direction, which the union must not break: a follow-up long
    enough to stand alone is a topic change, not a continuation, and must not
    accumulate every intent the conversation has ever had."""
    from orca.agents import planning

    assert planning.is_continuation("and what about the fishing zones near Chennai tomorrow") is False
    assert planning.is_continuation("where are the nearest fishing zones") is False


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("and in a trawler", True),
        ("what about the day after", True),
        ("also tomorrow", True),
        ("is it safe to go to sea today", False),
        ("", False),
    ],
)
def test_continuation_detection(query: str, expected: bool) -> None:
    from orca.agents import planning

    assert planning.is_continuation(query) is expected


def test_a_vessel_named_in_the_question_reaches_the_safety_thresholds() -> None:
    """`vessel_class` only ever arrived as a query parameter, so "and in a
    trawler?" typed into the chat set nothing and the answer used small-boat
    thresholds. Conservative — small_fishing is the strictest band — but the
    wrong answer to the question that was asked."""
    from orca.agents.risk_assessment import risk_vessel_class
    from orca.vessel import vessel_class_from_text

    assert vessel_class_from_text("and in a trawler?") == "trawler"
    assert risk_vessel_class("trawler") == "mechanized_trawler"
    # Not named stays None so risk_assessment applies its own conservative
    # default — the safety default keeps exactly one home.
    assert vessel_class_from_text("what about the day after") is None


# --- P2.14: "forget that, start fresh" --------------------------------------

@pytest.mark.parametrize(
    "phrase",
    [
        "forget that", "Forget it!", "start fresh", "start over", "new chat",
        "reset.", "never mind", "nevermind",
        # The exact phrasing this point is named after, with the comma a
        # person actually types. Edge-stripping alone missed it and the
        # message was routed as a marine question — caught in live
        # verification, not by the first version of this test.
        "forget that, start fresh",
        "Forget that, start fresh.",
        "let's start over",
        "  FORGET   IT  ",
    ],
)
def test_an_english_reset_phrase_is_recognised(phrase: str) -> None:
    assert session_memory.is_reset_request(phrase) is True


def test_a_reset_is_recognised_in_every_core_language() -> None:
    for language, phrases in session_memory._RESET_PHRASES.items():
        for phrase in phrases:
            assert session_memory.is_reset_request(phrase) is True, (language, phrase)


@pytest.mark.parametrize(
    "phrase",
    [
        # The critical negatives: a reset phrase INSIDE a marine question is a
        # marine question. Matching on substring here would silently discard a
        # conversation the user was still having.
        "forget the tide, what about the wind",
        "should I start fresh bait or reuse yesterday's",
        "is it safe to go to sea today",
        "what about tomorrow",
        "",
        "   ",
    ],
)
def test_a_marine_question_containing_a_reset_word_is_not_a_reset(phrase: str) -> None:
    assert session_memory.is_reset_request(phrase) is False


def test_a_reset_clears_both_redis_and_the_in_process_mirror() -> None:
    """Clearing only Redis would let the mirror re-seed a "cleared" session on
    the very next read — the reset would appear to work and then not have."""
    session_id = "test-reset-session"
    session_memory.append_turn(session_id, {"query": "is it safe near Pamban", "intent_rows": ["SAFETY_CHECK"]})
    assert session_memory.get_turns(session_id), "precondition: the turn was remembered"

    session_memory.clear(session_id)
    assert session_memory.get_turns(session_id) == []


def test_no_distress_phrase_is_swallowed_by_the_reset_matcher() -> None:
    """A reset is checked before the graph runs, so a distress call that
    matched it would never reach Agent 12. It cannot happen — the matcher
    compares the whole message — and this asserts it rather than trusting it."""
    from orca.agents.distress import _DISTRESS_PATTERNS

    for language_patterns in _DISTRESS_PATTERNS.values():
        for phrase in language_patterns:
            assert session_memory.is_reset_request(phrase) is False, phrase


# --- P2.13: a 429 is "provider unavailable", never a crashed answer ---------

def test_a_rate_limited_provider_degrades_to_the_deterministic_line() -> None:
    """Gemini's free tier returns 429 inside a demo's question rate. The wrong
    behaviour is a failed span; the right one is the same deterministic path
    P2.11 builds, labelled with why."""
    from orca.agents import reporting
    from orca.llm import tiers

    class _Limited:
        def complete(self, messages, *, model, **kw):
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")

    verdict = {"go_no_go": "CAUTION", "status": "WARNING", "reason": "Rough Sea State / Boundary Proximity"}
    engine_out: list[str] = []
    with patch.object(tiers, "get_provider", return_value=_Limited()):
        narrative = reporting.synthesize_narrative("is it safe today", verdict, [], engine_out=engine_out)

    assert narrative.startswith("CAUTION:"), narrative
    assert engine_out and engine_out[0].startswith("Deterministic")
    assert "429" in engine_out[0], "the span has to say WHY it is deterministic"


def test_every_provider_call_is_counted_including_ones_that_fail() -> None:
    """§6.2's cost-per-query number is measured, so a failed call still cost a
    request against the quota and has to be in it."""
    from orca.llm import tiers

    class _Boom:
        def complete(self, messages, *, model, **kw):
            raise RuntimeError("503 unavailable")

    tiers.reset_llm_call_count()
    with patch.object(tiers, "get_provider", return_value=_Boom()):
        client = tiers._TieredClient("gemini", "m")
        with pytest.raises(LLMUnavailable):
            client.complete([{"role": "user", "content": "x"}])
    assert tiers.llm_call_count() == 1


# --- found by looking at the running UI, not by the tests above -------------

def test_a_standard_critic_pass_is_one_round_and_deep_keeps_three() -> None:
    """The first live run of P2.5 showed "10 LLM calls" for one ordinary
    question: the Critic became every-query, each pass could still loop three
    judge->revise rounds, and a re-invocation makes two passes. That is the
    per-minute Gemini budget P2.13 protects, blown by a single demo question."""
    assert critic.MAX_ITERATIONS_STANDARD == 1
    assert critic.MAX_ITERATIONS == 3

    calls: list[str] = []

    class _AlwaysFinds:
        engine = "test"

        def complete(self, messages):
            calls.append("x")
            body = messages[0]["content"]
            if body.startswith("You are the ORCA Critic"):
                return '[{"rubric_item": "spatial_accuracy", "description": "off"}]'
            return "GO: All Parameters Within Safe Operational Limits — revised"

    from orca.llm import tiers

    with patch.object(tiers, "llm", return_value=_AlwaysFinds()):
        critic.run_critic_pass("q", "GO: All Parameters Within Safe Operational Limits", "f",
                               is_safety_check=True, max_iterations=critic.MAX_ITERATIONS_STANDARD)
        standard_calls = len(calls)
        calls.clear()
        critic.run_critic_pass("q", "GO: All Parameters Within Safe Operational Limits", "f",
                               is_safety_check=True, max_iterations=critic.MAX_ITERATIONS)
        deep_calls = len(calls)
    assert standard_calls == 2, "one judge call and one revise call, no more"
    assert deep_calls == 6, "DEEP keeps its three rounds"


def test_discovery_coverage_counts_usable_sources_not_prechecked_ones() -> None:
    """Caught by a screenshot: coverage was passed as "how many sources could
    be checked before the fetch", the scorer read 3-of-8 as 3-of-8 readings
    present, and an agent that found a usable source for every data type went
    LOW_DATA on the strip."""
    result = g.marine_data_discovery_run(_state(matched_intent_rows=["SAFETY_CHECK", "PFZ_NEAREST"]))  # type: ignore[arg-type]
    present, expected = result.coverage
    assert result.outputs["unusable_data_types"] == []
    assert present == expected, (present, expected)
    from orca.confidence_score import score_agent

    assert score_agent(result)["label"] != "LOW_DATA"


# --- found by the live run, after the first pass was declared done ----------

def test_agent_3_resolves_every_data_type_ocean_analytics_consumes() -> None:
    """The first live run of P2.6 showed Ocean deciding `pfz` and
    `catch_statistics` for itself on a plain safety question: Agent 3 had only
    been asked for the types an intent named. That is the "each specialist
    picks its own sources" arrangement the node exists to replace."""
    plan = ["marine_data_discovery", "weather_intelligence", "ocean_analytics", "risk_assessment"]
    assert {"pfz", "tide", "catch_statistics"} <= set(g._data_types_for(["SAFETY_CHECK"], plan))


def test_agent_3_does_not_resolve_ocean_types_when_ocean_is_gated_off() -> None:
    plan = ["weather_intelligence", "risk_assessment"]
    resolved = set(g._data_types_for(["SUBSCRIPTION"], plan))
    assert not ({"pfz", "catch_statistics"} & resolved)
    # ... but the specialists that always run keep theirs.
    assert set(g._CORE_DATA_TYPES) <= resolved


def test_ocean_reports_agent_3_as_the_decider_for_every_type_it_uses() -> None:
    from orca.agents import ocean_analytics

    state = _state()
    state["discovery_sources"] = {
        "by_data_type": {s["data_type"]: s for s in g.marine_data_discovery_run(state).outputs["source_selections"]}  # type: ignore[arg-type]
    }
    result = ocean_analytics.run(state)  # type: ignore[arg-type]
    selections = result.outputs["source_selections"]
    assert selections
    assert all(s["decided_by"] == "marine_data_discovery" for s in selections), selections


def test_visualization_is_skipped_visibly_when_the_plan_never_names_it() -> None:
    """P2.7: EXPORT and SUBSCRIPTION produce nothing to draw. Their plans do not
    name Visualization, so the gate skips it with the reason on the span."""
    from orca.agents.planning import generate_execution_plan

    for rows in (["SUBSCRIPTION"], ["EXPORT"]):
        plan = generate_execution_plan(rows, "SHALLOW")
        assert "visualization" not in plan, rows
        update = g.visualization_node(_state(execution_plan=plan))  # type: ignore[arg-type]
        (entry,) = update["audit_trace_log"]
        assert entry["status"] == "skipped" and entry["skip_reason"]
        assert "visualization_payload" not in update


def test_a_map_producing_intent_keeps_visualization_in_the_plan() -> None:
    from orca.agents.planning import generate_execution_plan

    for rows in (["SAFETY_CHECK"], ["PFZ_NEAREST"], ["CONDITIONS"], ["ROUTE"], []):
        assert "visualization" in generate_execution_plan(rows, "SHALLOW"), rows


def test_export_that_also_names_a_condition_keeps_visualization() -> None:
    """The live run's own lesson: "export the tide data" matches CONDITIONS as
    well as EXPORT, the plan is the union, and drawing the tide is correct."""
    from orca.agents.planning import classify_intent_deterministic, generate_execution_plan

    rows = [name for name, _ in classify_intent_deterministic("export the tide data as csv for Kavaratti")]
    assert {"EXPORT", "CONDITIONS"} <= set(rows)
    assert "visualization" in generate_execution_plan(rows, "SHALLOW")


def test_two_skips_in_one_query_are_both_recorded_on_the_state() -> None:
    """`skipped_agents` had no reducer, so Ocean Analytics' skip was overwritten
    by Visualization's and the response listed one of two agents that the trace
    showed as skipped. Run through the real compiled graph, because the bug
    only exists at the LangGraph state-merge boundary — a unit call to either
    node in isolation returns the right dict and passes."""
    from orca.graph.graph import build_graph

    state = _state(
        raw_user_query="notify me when it gets dangerous near Karaikal",
        normalized_english_query="notify me when it gets dangerous near Karaikal",
        matched_intent_rows=[],
        execution_plan=[],
    )
    state["place_resolution"] = None
    state["query_outcome"] = "ANSWERED"
    state["distress_flag"] = False
    with llm_switch(False):
        final = build_graph().invoke(state)  # type: ignore[arg-type]
    skipped = {s["agent_name"] for s in final.get("skipped_agents", [])}
    assert {"ocean_analytics", "visualization"} <= skipped, skipped


# --- the Critic's ground truth (found by reading its complaints live) --------

def test_the_critic_fact_block_contains_the_numbers_a_narrative_actually_quotes() -> None:
    """Two defects lived in the inline version. It read a top-level
    `wave_height` that does not exist (readings are under `hourly[0]`), and it
    never listed the fishing-zone distance — so a narrative saying "the nearest
    zone is 447 km away" was compared with nothing that could confirm it and
    the judge flagged it as contradicting the boundary distance."""
    state = _state(
        risk_assessment={"go_no_go": "GO", "reason": "All Parameters Within Safe Operational Limits"},
        weather_data={"hourly": [{"wave_height": 0.86, "wind_speed_10m": 5.8}], "lightning_active": False},
        geospatial_data={"imbl_distance_nm": 270.7, "mpa_violation": False},
        ocean_data={
            "nearest_pfz": {"found": True, "distance_km": 447.2, "compass": "ESE", "depth_m": 48},
            "tide": {"tidal_state": "RISING", "next_high": {"height_m": 0.74, "in_hours": 13.2}},
        },
    )
    facts = critic.build_facts_block(state)  # type: ignore[arg-type]
    assert "wave_height_m: 0.86" in facts
    assert "nearest_fishing_zone_distance_km: 447.2" in facts
    # Boundary vs fishing-zone distance are named so they cannot be confused.
    assert "distance_to_maritime_boundary_nautical_miles: 270.7" in facts
    assert "tidal_state: RISING" in facts


def test_an_absent_reading_is_absent_from_the_fact_block_not_a_placeholder() -> None:
    facts = critic.build_facts_block(_state(risk_assessment={"go_no_go": "GO"}))  # type: ignore[arg-type]
    assert "wave_height_m" not in facts and "nearest_fishing_zone" not in facts
    assert "risk_verdict: GO" in facts
    assert critic.build_facts_block(_state(risk_assessment={}) | {"weather_data": {}}) != ""  # type: ignore[arg-type]


def test_the_judge_is_told_an_absent_fact_is_not_a_defect() -> None:
    prompt = critic._judge_prompt("q", "n", "f")
    assert "ABSENCE of a fact is never a defect" in prompt
    assert "Flag only what the narrative ASSERTS" in prompt


# --- found by asking the follow-up in the browser ---------------------------

def test_a_vessel_named_in_a_follow_up_still_produces_a_verdict() -> None:
    """The first version of P2.9 put the DB-enum name "trawler" into state. The
    risk engine has no such class, `run` raised, the agent's exception boundary
    turned that into an EMPTY verdict, and the follow-up rendered with no safety
    verdict at all — and crashed the card. My earlier live check printed the
    intents and the vessel and never looked at the verdict."""
    from orca.vessel import resolve_vessel_class

    vessel = resolve_vessel_class(None, "and in a trawler", None)
    assert vessel == "mechanized_trawler"

    from orca.agents import risk_assessment

    result = risk_assessment.run({  # type: ignore[arg-type]
        "query_id": "t", "reasoning_depth": "SHALLOW", "vessel_class": vessel,
        "weather_data": {"hourly": [{"wave_height": 1.0, "wind_speed_10m": 3.0}]},
        "geospatial_data": {"imbl_distance_nm": 50.0, "mpa_violation": False},
    })
    assert result.status == "ok"
    assert result.outputs["go_no_go"] in {"GO", "CAUTION", "NO_GO"}


@pytest.mark.parametrize("bad_class", ["trawler", "mechanised", "not_a_class", "", "CARGO"])
def test_an_unknown_vessel_class_never_blanks_the_verdict(bad_class: str) -> None:
    """A vocabulary slip anywhere upstream must degrade to the STRICTEST class,
    never to an empty verdict and never to a more capable boat."""
    from orca.agents import risk_assessment

    result = risk_assessment.run({  # type: ignore[arg-type]
        "query_id": "t", "reasoning_depth": "SHALLOW", "vessel_class": bad_class,
        "weather_data": {"hourly": [{"wave_height": 2.5, "wind_speed_10m": 3.0}]},
        "geospatial_data": {"imbl_distance_nm": 50.0, "mpa_violation": False},
    })
    assert result.status == "ok", result.error_detail
    assert result.outputs["go_no_go"] in {"GO", "CAUTION", "NO_GO"}
    if bad_class in ("not_a_class", ""):
        # 2.5 m is CAUTION for a small boat. Falling to a more capable class
        # would read it as GO — the unsafe direction.
        assert result.outputs["go_no_go"] == "CAUTION"


def test_an_explicit_vessel_parameter_outranks_the_question_and_the_chat() -> None:
    from orca.vessel import resolve_vessel_class

    assert resolve_vessel_class("cargo_vessel", "and in a trawler", "small_fishing") == "cargo_vessel"
    assert resolve_vessel_class(None, "what about tomorrow", "small_fishing") == "small_fishing"
    assert resolve_vessel_class(None, "what about tomorrow", None) is None


def test_a_failed_safety_agent_is_disclosed_not_silently_omitted() -> None:
    """No verdict is not a calm sea. When risk_assessment itself fails the card
    must say so BEFORE the answer, or the missing panel reads as all-clear."""
    with patch.object(g, "run_traced_node", return_value=(MagicMock(outputs={}), {"agent_name": "risk_assessment"})):
        update = g.risk_assessment_node(_state())  # type: ignore[arg-type]
    assert update["disclosures"] and "NO go / no-go verdict" in update["disclosures"][0]


def test_the_verdict_dict_never_carries_the_reconciliation_rows() -> None:
    """`risk_assessment` is read as {status, go_no_go, reason} by a dozen call
    sites and interpolated verbatim into Reporting's prompt. The reconciliation
    rows travel on their own state field — including when there are none."""
    import orca.agents.risk_assessment as ra

    for rows in ([], [{"variable": "wave_height_m", "status": "agree", "confidence_penalty": False}]):
        fake = MagicMock(outputs={"status": "SAFE", "go_no_go": "GO", "reason": "ok", "reconciliation": rows})
        fake.confidence = MagicMock(score="HIGH")
        with patch.object(g, "run_traced_node", return_value=(fake, {"agent_name": "risk_assessment"})):
            update = g.risk_assessment_node(_state())  # type: ignore[arg-type]
        assert "reconciliation" not in update["risk_assessment"]
        assert ("reconciliation" in update) is bool(rows)
    assert ra  # imported for the patch target's module only


def test_all_sources_down_falls_back_to_the_last_known_verdict_with_its_age() -> None:
    """P6.11 (orca_final §4.6) — when `weather_data` is entirely empty (every
    source in the cascade failed, not just one field) and risk_assessment's
    own honest answer is CAUTION_MISSING_DATA, a real prior verdict for the
    same spot is a more useful answer than "insufficient data" — forced to
    LOW-DATA, with its age stated, never presented as a fresh read."""
    from orca import query_cache

    lat, lon = 8.80, 78.30  # matches _state()'s own user_location
    key = query_cache.last_known_key(lat, lon, None)
    query_cache.store_last_known_verdict(lat, lon, None, {"status": "SAFE", "go_no_go": "GO", "reason": "clear"})
    try:
        fake = MagicMock(outputs={"status": "CAUTION_MISSING_DATA", "reason": "no live source reachable"})
        fake.confidence = MagicMock(score="LOW_DATA")
        with patch.object(g, "run_traced_node", return_value=(fake, {"agent_name": "risk_assessment"})):
            update = g.risk_assessment_node(_state(weather_data={}))  # type: ignore[arg-type]
        assert update["confidence_tier"] == "LOW_DATA"
        assert update["risk_assessment"]["status"] == "SAFE_CACHED"
        assert update["risk_assessment"]["go_no_go"] == "GO"
        assert "last computed verdict" in update["disclosures"][0]
        assert "ago" in update["disclosures"][0]
    finally:
        query_cache.redis_client().delete(key)


def test_a_missing_data_verdict_with_no_prior_cached_answer_stays_honest() -> None:
    """The mirror case — nothing to fall back to — must not silently invent
    one; the ordinary CAUTION_MISSING_DATA disclosure still fires."""
    from orca.cache import redis_client
    from orca import query_cache

    lat, lon = -1.23, -4.56  # a spot nothing in this suite has ever cached
    redis_client().delete(query_cache.last_known_key(lat, lon, None))

    fake = MagicMock(outputs={"status": "CAUTION_MISSING_DATA", "reason": "no live source reachable"})
    fake.confidence = MagicMock(score="LOW_DATA")
    with patch.object(g, "run_traced_node", return_value=(fake, {"agent_name": "risk_assessment"})):
        update = g.risk_assessment_node(
            _state(weather_data={}, user_location={"lat": lat, "lon": lon, "place_name": "x", "place_source": "explicit"})
        )  # type: ignore[arg-type]
    assert update["risk_assessment"]["status"] == "CAUTION_MISSING_DATA"
    assert update["disclosures"] == ["no live source reachable"]


def test_reporting_skips_a_second_critic_pass_once_the_reinvocation_budget_is_spent() -> None:
    """After critic -> specialist -> reporting, the router used to send the query back to the
    Critic, whose second pass was then immediately routed to egress by the budget check: a
    reasoning-tier call that changed nothing, and the Critic drawn twice on /ask. Fixed by another
    agent working in parallel; this is the guard it left without a test."""
    ok = {"go_no_go": "GO", "status": "SAFE"}
    assert g._route_after_reporting(_state(risk_assessment=ok, critic_reinvocations=0)) == "critic"
    assert g._route_after_reporting(_state(risk_assessment=ok, critic_reinvocations=critic.MAX_REINVOCATIONS)) == "language_egress"
    # A hard-constraint NO_GO still cancels the Critic rather than skipping it silently.
    hard = {"go_no_go": "NO_GO", "status": "DANGER", "reason": "x"}
    assert g._route_after_reporting(_state(risk_assessment=hard, critic_reinvocations=1)) == "critic_cancelled"
