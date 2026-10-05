"""D-10 — every message gets one kind, and conversation about ORCA's last reply is answered, not refused.

Found on /ask 2026-10-05: "i need more detailed description" after "what all can
you do", and "so you cant give me any land based forcast?" after a Bengaluru
answer, were both met with the same fixed capability sentence. Two causes: the
classifier was shown only the user's earlier questions (never what ORCA replied)
and had no kind for "conversation about the last reply"; and the guard reply
made the model repeat a fixed sentence verbatim.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from orca.agents import planning, reporting
from orca.agents.understand import (
    _KIND_VALUES,
    NON_SEA_KINDS,
    _build_understand_prompt,
    _parse_understand_output,
)
from orca.graph.graph import out_of_scope_node


class _Client:
    engine = "fake-model"

    def __init__(self, text=None, boom=False):
        self.text, self.boom, self.prompts = text, boom, []

    def complete(self, messages, **kw):
        self.prompts.append(messages[0]["content"])
        if self.boom:
            raise RuntimeError("no model")
        return self.text


def _llm_returning(*texts):
    """One fake client per `llm()` call, in order; the last repeats."""
    clients = [_Client(t) for t in texts]
    calls = {"n": 0}

    def factory(tier):
        c = clients[min(calls["n"], len(clients) - 1)]
        calls["n"] += 1
        return c

    return factory, clients


def _reading(kind, intents=(), followup=False, places=()):
    return json.dumps({"kind": kind, "intents": list(intents), "places": list(places), "when": None,
                       "is_followup": followup, "agents": []})


PFZ_TURN = {"query": "pfzs near mangrol", "english_query": "pfzs near mangrol",
            "answer": "The nearest potential fishing zone is about 49 km WNW of Mangrol.",
            "intent_rows": ["PFZ_NEAREST"]}
CAPABILITY_TURN = {"query": "what all can you do", "english_query": "what all can you do",
                   "answer": "I answer questions about conditions at sea off India.", "intent_rows": []}


# --- the kind exists, and the one list of non-sea kinds contains it -------------------

def test_chat_followup_is_a_kind_and_is_not_a_sea_question():
    assert "chat_followup" in _KIND_VALUES and "chat_followup" in NON_SEA_KINDS
    assert "sea_question" not in NON_SEA_KINDS
    assert NON_SEA_KINDS == set(_KIND_VALUES) - {"sea_question"}


def test_the_parser_accepts_it_and_still_rejects_unknown_kinds():
    assert _parse_understand_output(_reading("chat_followup")).kind == "chat_followup"
    assert _parse_understand_output(_reading("made_up_kind")) is None


# --- the classifier is shown what ORCA replied -----------------------------------------

def test_the_classifier_prompt_carries_orcas_previous_reply_and_the_follow_up_rule():
    prompt = _build_understand_prompt("i need more detailed description", [CAPABILITY_TURN], None, "2026-10-05T12:00")
    assert 'User: "what all can you do"' in prompt
    assert 'ORCA replied: "I answer questions about conditions at sea off India."' in prompt
    assert "chat_followup" in prompt and "MESSAGES THAT REFER TO THE CONVERSATION" in prompt


def test_a_turn_without_an_answer_still_renders():
    prompt = _build_understand_prompt("and tomorrow?", [{"query": "wave height at pamban"}], None, "t")
    assert 'User: "wave height at pamban"' in prompt and '   ORCA replied: "' not in prompt


# --- planning routes it as a non-sea message, and a sea follow-up still runs agents ------

def test_planning_routes_chat_followup_to_out_of_scope_without_place_validation():
    factory, _ = _llm_returning(_reading("chat_followup"))
    with mock.patch("orca.llm.tiers.llm", factory):
        out = planning.run({"query_id": "q", "raw_user_query": "so you cant give me any land based forcast?",
                            "session_history": [CAPABILITY_TURN]}).outputs
    assert out["matched_intent_rows"] == [planning.OUT_OF_SCOPE_ROW] and out["execution_plan"] == []


def test_more_detail_after_a_fishing_zone_answer_stays_a_sea_question_and_carries_the_intent():
    factory, _ = _llm_returning(_reading("sea_question", followup=True))
    with mock.patch("orca.llm.tiers.llm", factory):
        out = planning.run({"query_id": "q", "raw_user_query": "i need more detailed description",
                            "session_history": [PFZ_TURN]}).outputs
    assert out["matched_intent_rows"] == ["PFZ_NEAREST"]
    assert "ocean_analytics" in out["execution_plan"]


# --- the reply is written by the model from what ORCA can do, with a safe fallback --------

def _node_state(kind, query):
    return {"understood_kind": kind, "raw_user_query": query, "session_history": [CAPABILITY_TURN]}


@pytest.mark.parametrize("kind", ["what_can_orca_do", "chat_followup"])
def test_the_model_reply_is_used_and_is_shown_as_chat_not_a_refusal(kind):
    fake = _Client("I only cover the sea, so I cannot give a land forecast, but name a port and I can tell you the waves.")
    with mock.patch("orca.llm.tiers.llm", lambda tier: fake):
        out = out_of_scope_node(_node_state(kind, "so you cant give me any land based forcast?"))
    assert out["final_english_response"].startswith("I only cover the sea")
    assert out["small_talk"] is True and out["response_engine"] == "fake-model"
    assert "land-based weather" in fake.prompts[0] and "so you cant give me any land based forcast?" in fake.prompts[0]


def test_it_is_not_forced_to_repeat_a_fixed_sentence():
    # The old guard prompt demanded "keep EVERY sentence ... exactly as written".
    fake = _Client("Sure. I can check safety, waves, wind, tides and fishing zones for a coastal place.")
    with mock.patch("orca.llm.tiers.llm", lambda tier: fake):
        out = out_of_scope_node(_node_state("chat_followup", "i need more detailed description"))
    assert out["final_english_response"] == "Sure. I can check safety, waves, wind, tides and fishing zones for a coastal place."
    assert "EVERY sentence" not in fake.prompts[0]


def test_no_model_falls_back_to_the_fixed_capability_text():
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(boom=True)):
        out = out_of_scope_node(_node_state("chat_followup", "why not?"))
    assert out["final_english_response"].startswith("I answer questions about conditions at sea off India")
    assert out["small_talk"] is True


def test_a_reply_that_invents_a_figure_is_discarded():
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client("It is 31 degrees in Bengaluru today.")):
        reply, engine = reporting.write_chat_reply("what is it like there", reporting.CAPABILITY_FACTS, "FALLBACK")
    assert reply == "FALLBACK" and "figure" in engine


def test_a_figure_already_in_the_facts_or_the_message_is_allowed():
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client("I can look up to 7 days ahead, so 5 days is fine.")):
        reply, _ = reporting.write_chat_reply("can you do 5 days", reporting.CAPABILITY_FACTS, "FALLBACK")
    assert reply != "FALLBACK"


# --- the kind decides: a word list and the follow-up flag cannot send a chat message to the sea agents

@pytest.mark.parametrize("query", [
    "so you cant give me any land based forcast?",
    "why cant you give me a weather forecast for the land?",   # says "weather" and "forecast"
    "i need more detailed description",
])
def test_a_chat_followup_never_runs_the_sea_agents_even_with_marine_words_or_the_followup_flag(query):
    factory, _ = _llm_returning(_reading("chat_followup", intents=["CONDITIONS"], followup=True))
    with mock.patch("orca.llm.tiers.llm", factory):
        out = planning.run({"query_id": "q", "raw_user_query": query, "session_history": [PFZ_TURN]}).outputs
    assert out["matched_intent_rows"] == [planning.OUT_OF_SCOPE_ROW]
    assert out["execution_plan"] == []


def test_distress_read_by_the_model_is_not_turned_into_a_refusal_here():
    factory, _ = _llm_returning(_reading("distress"))
    with mock.patch("orca.llm.tiers.llm", factory):
        out = planning.run({"query_id": "q", "raw_user_query": "engine failed near pamban", "session_history": []}).outputs
    assert out["matched_intent_rows"] != [planning.OUT_OF_SCOPE_ROW]
