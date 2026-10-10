"""2026-10-10 (the user): this is a chatbot. Nothing is drawn above an answer, and a message that refers to a place without
naming it is read from the chat's 20 turns, not flagged and not re-asked.

(1) no "Same answer in X: no new forecast was fetched" note; (2) a language-only claim is checked against the previous
question ("now in english: SST and chlorophyll of the same place" is a NEW question); (3) the planner sees the place each
turn was answered for and may return the place a message refers to, which counts when a recent turn was answered for it.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

from orca import session
from orca.agents.understand import _build_understand_prompt
from orca.api import language_rerender
from orca.graph.graph import planning_node
from orca.place_resolution import adopt_model_place, resolve_or_ask

DEFAULT = {"lat": 8.8, "lon": 78.3, "place_name": None, "place_source": "regional_default"}
FRAME = {"type": "final_response", "query_id": "11111111-1111-1111-1111-111111111111", "outcome": "ANSWERED",
         "final_english_response": "The sea near Mangalore is calm.", "normalized_english_query": "is it safe near mangalore",
         "matched_intent_rows": ["SAFETY_CHECK"], "disclosures": [],
         "user_location": {"lat": 12.9, "lon": 74.8, "place_name": "mangalore", "place_source": "gazetteer"}}
LAST = session.turn_from_final("is it safe near mangalore", FRAME)


# --- (1) no note -------------------------------------------------------------------------------------------------------------

def test_a_language_rerender_adds_no_note_to_the_answer():
    with mock.patch.object(language_rerender, "_translate", lambda text, lang: f"[{lang}] {text}"):
        frame = language_rerender.rerender_last_answer([LAST], "hi")
    assert frame is not None and frame["disclosures"] == []


def test_the_trace_rewrite_adds_no_note_either():
    rendered = mock.Mock(query_id="q1", final_english_response="en", final_vernacular_response=None, confidence_tier="HIGH", citations=[])
    without_frame = {k: v for k, v in LAST.items() if k != "frame"}
    with mock.patch.object(language_rerender, "render_query", return_value=rendered):
        frame = language_rerender.rerender_last_answer([without_frame], "hi", rewrite_from_trace=True)
    assert frame is not None and frame["disclosures"] == []


def test_the_source_has_no_same_answer_or_switched_replies_sentence():
    import inspect

    from orca.api import main

    for source in (inspect.getsource(language_rerender), inspect.getsource(main._language_change_stream)):
        assert "no new forecast was fetched" not in source and "Switched replies to" not in source


# --- (2) a language-only claim is checked ------------------------------------------------------------------------------------

class _Client:
    engine = "fake-model"

    def __init__(self, body):
        self.text = json.dumps(body)

    def complete(self, messages, **kw):
        return self.text


def _plan(query, intents, history=None, **over):
    body = {"kind": "sea_question", "intents": intents, "places": [], "when": None, "is_followup": True, "agents": [],
            "english_reading": query, "reply_language": "en", "language_only": True}
    body.update(over)
    state = {"query_id": "q", "raw_user_query": query, "session_history": [LAST] if history is None else history,
             "user_location": {"lat": 12.9, "lon": 74.8, "place_name": "mangalore", "place_source": "session_carried"},
             "place_resolution": resolve_or_ask(query).as_dict()}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(body)), mock.patch("orca.llm.tiers.llm_enabled", lambda: True), \
            mock.patch.object(language_rerender, "_translate", lambda text, lang: f"[{lang}] {text}"):
        return planning_node(state)  # type: ignore[arg-type]


def test_a_real_language_only_request_is_still_a_rerender():
    update = _plan("okay fine answer the same in english", ["SAFETY_CHECK"])
    assert update["query_outcome"] == "LANGUAGE_CHANGED"


def test_the_user_message_that_also_asks_for_sst_and_chlorophyll_is_a_new_question():
    update = _plan("okay fine now answer in english: SST and chlorophyll of the same place", ["CONDITIONS"])
    assert update.get("query_outcome") != "LANGUAGE_CHANGED" and "language_rerender" not in update


def test_a_new_ocean_data_subject_is_a_new_question_even_if_the_model_returns_no_intent():
    update = _plan("now in english: the chlorophyll", [])
    assert "language_rerender" not in update


def test_a_different_intent_from_the_previous_turn_is_a_new_question():
    update = _plan("in hindi, any hazard alerts?", ["HAZARD_ALERTS"])
    assert "language_rerender" not in update


# --- (3) the model estimates the place a message refers to ---------------------------------------------------------------------

def test_the_planner_prompt_shows_the_place_each_turn_was_answered_for_and_the_rule_for_references():
    prompt = " ".join(_build_understand_prompt("and the wind there", [LAST], None, "2026-10-10T10:00:00+05:30").split())
    assert '"is it safe near mangalore" [answered for: mangalore]' in prompt
    assert "A MESSAGE THAT REFERS TO A PLACE WITHOUT NAMING IT" in prompt and "Never invent a place that is not in RECENT TURNS" in prompt


def test_a_referred_to_place_counts_when_a_recent_turn_was_answered_for_it():
    got = adopt_model_place([{"raw": "the same place", "normalized": "mangalore"}], DEFAULT, ["okay same place in hindi"], ["mangalore"])
    assert got is not None and got[0]["place_name"] == "mangalore" and got[0]["place_source"] == "gazetteer"


def test_the_model_cannot_name_a_place_no_turn_was_answered_for():
    assert adopt_model_place([{"raw": "the same place", "normalized": "kochi"}], DEFAULT, ["okay same place in hindi"], ["mangalore"]) is None
    assert adopt_model_place([{"raw": "the same place", "normalized": "kochi"}], DEFAULT, ["okay same place in hindi"], None) is None


def test_planning_sets_the_position_from_the_chat_for_a_message_that_names_no_place():
    body = {"kind": "sea_question", "intents": ["CONDITIONS"], "places": [{"raw": "the same place", "normalized": "mangalore"}], "when": None,
            "is_followup": True, "agents": [], "english_reading": "SST and chlorophyll of the same place"}
    query = "okay fine, SST and chlorophyll of the same place"
    state = {"query_id": "q", "raw_user_query": query, "session_history": [LAST],
             "user_location": dict(DEFAULT), "place_resolution": resolve_or_ask(query).as_dict()}
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(body)), mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        update = planning_node(state)  # type: ignore[arg-type]
    assert update["user_location"]["place_name"] == "mangalore" and update.get("query_outcome") is None
    assert not update.get("disclosures")


# --- (4) the frontend draws nothing above an answer ---------------------------------------------------------------------------

def test_the_chat_turn_renders_no_banner_and_no_carried_over_chips():
    root = Path(__file__).resolve().parents[3] / "frontend" / "app" / "ask"
    chat = (root / "ChatTurn.tsx").read_text(encoding="utf-8")
    assert "<DisclosureBanner" not in chat and "<InheritedChips" not in chat and "onDropInherited" not in chat
    assert "export function InheritedChips" not in (root / "ReasoningEvidence.tsx").read_text(encoding="utf-8")
    assert "export function DisclosureBanner" not in (root / "Disclosures.tsx").read_text(encoding="utf-8")
