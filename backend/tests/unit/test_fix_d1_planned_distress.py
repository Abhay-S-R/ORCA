"""FIX-D1 — a distress reading by planning reaches the distress response.

Found live 2026-10-07/08: "engine failed near pamban" came back from planning as
kind="distress", and the pipeline answered it as a normal sea question ("CAUTION ...
stay near Pamban"). Only the phrase list and the escalate-only check ever reached the
MRCC handoff; the model's own reading was dropped by the router.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from orca.graph.graph import _route_after_planning, build_graph, planned_distress_node


class _Client:
    engine = "fake-model"

    def __init__(self, text):
        self.text = text

    def complete(self, messages, **kw):
        return self.text


def _reading(kind, intents=(), places=()):
    return json.dumps({"kind": kind, "intents": list(intents), "places": [{"raw": p, "normalized": p.title()} for p in places],
                       "when": None, "is_followup": False, "agents": [], "english_reading": "x"})


def _run_graph(query, model_text):
    state = {"query_id": "q-d1", "raw_user_query": query, "session_history": [], "user_language_default": "en"}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(model_text)), \
            mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        return build_graph().invoke(state)


def test_the_router_sends_a_planned_distress_to_the_distress_node():
    assert _route_after_planning({"understood_kind": "distress"}) == "planned_distress"  # type: ignore[typeddict-item]


@pytest.mark.parametrize("kind", ["sea_question", "greeting_or_small_talk", "off_topic", "inland_place", None])
def test_every_other_kind_routes_as_before(kind):
    assert _route_after_planning({"understood_kind": kind, "matched_intent_rows": []}) == "marine_data_discovery"  # type: ignore[typeddict-item]


def test_a_refusal_still_wins_over_the_kind():
    from langgraph.graph import END
    assert _route_after_planning({"understood_kind": "distress", "query_outcome": "NEEDS_PLACE"}) == END  # type: ignore[typeddict-item]


def test_the_node_produces_the_same_response_as_the_sos_button():
    update = planned_distress_node({"query_id": "q", "raw_user_query": "engine failed near pamban", "understood_kind": "distress"})  # type: ignore[typeddict-item]
    assert update["distress_flag"] is True and update["query_outcome"] == "DISTRESS"
    assert update["final_english_response"].startswith("DISTRESS DETECTED. Coast Guard MRCC:")
    assert update["confidence_tier"] == "HIGH" and update["completed_nodes"] == ["planned_distress"]
    assert update["audit_trace_log"][0]["agent_name"] == "distress"


def test_the_whole_graph_answers_a_planned_distress_with_the_handoff_and_runs_no_sea_agent():
    out = _run_graph("engine failed near pamban", _reading("distress", places=["pamban"]))
    assert out["query_outcome"] == "DISTRESS" and out["distress_flag"] is True
    assert out["final_english_response"].startswith("DISTRESS DETECTED")
    ran = set(out["completed_nodes"])
    assert "planned_distress" in ran
    assert not ran & {"weather_intelligence", "geospatial", "risk_assessment", "reporting", "critic"}


def test_a_sea_question_is_untouched():
    out = _run_graph("wave height at kochi", _reading("sea_question", ["CONDITIONS"], ["kochi"]))
    assert out.get("query_outcome") != "DISTRESS" and "planned_distress" not in out["completed_nodes"]
    assert "weather_intelligence" in out["completed_nodes"]


# --- FIX-D3: the English query downstream is the planner's reading for translated messages ----------------------

from orca.graph.graph import planning_node


def _planned(detected_language, reading, query="தூத்துக்குடியில் கடல் பாதுகாப்பானதா"):
    body = json.dumps({"kind": "sea_question", "intents": ["SAFETY_CHECK"], "places": [{"raw": "x", "normalized": "Tuticorin"}],
                       "when": None, "is_followup": False, "agents": [], "english_reading": reading})
    state = {"query_id": "q", "raw_user_query": query, "normalized_english_query": "is the sea safe in new york",
             "detected_language": detected_language, "session_history": []}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(body)), mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        return planning_node(state)  # type: ignore[arg-type]


def test_a_translated_message_uses_the_planners_reading_not_the_translation():
    update = _planned("ta", "Is the sea safe at Thoothukudi?")
    assert update["normalized_english_query"] == "Is the sea safe at Thoothukudi?"


def test_english_text_keeps_its_own_words():
    assert "normalized_english_query" not in _planned("en", "Is the sea safe at Thoothukudi?", query="is sea safe at tuticorin")


def test_no_reading_leaves_the_translation_alone():
    assert "normalized_english_query" not in _planned("ta", "")
