"""FIX-FOLLOWLANG-1 (2026-10-09): "okay fine answer the same in kannada" after a Gujarati answer re-answers.

Found by the user: "answer this in gujarati: pfzs near mangrol" was right; the next message "okay fine answer the
same in kannada" got "Sure thing — just let me know what you'd like to change." Cause: prompt rule 5 sent "switch to
Tamil / talk in Hindi" to `reset_or_language_switch`, a terminal kind (fixed sentence, no agent), and rule 17 (a reply
language on a sea question) never covered a message that carries only the language. The offline fallback had the same
gap (any "language" in the text was a reset).
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from orca.agents.planning import ROUTING_TABLE
from orca.agents.understand import (
    _build_understand_prompt,
    _fallback_understand,
    requested_reply_language,
)
from orca.graph.graph import planning_node

ROW = ROUTING_TABLE[0].name
HISTORY = [{"role": "user", "content": "pfzs near mangrol", "intent_rows": [ROW]}]


@pytest.fixture(autouse=True)
def _model_off(monkeypatch):
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")


class _Client:
    engine = "fake-model"

    def __init__(self, text):
        self.text = text

    def complete(self, messages, **kw):
        return self.text


def _plan(body: dict, query="okay fine answer the same in kannada", history=HISTORY):
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(json.dumps(body))), \
            mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        return planning_node({"query_id": "q", "raw_user_query": query, "session_history": history})  # type: ignore[arg-type]


# --- the prompt: reset means reset; a language for the earlier answer is its own rule ----------------------------------

def test_the_prompt_no_longer_sends_a_language_for_an_answer_to_reset():
    prompt = _build_understand_prompt("x", [], None, "2026-10-09T10:00:00+05:30")
    rule5 = next(line for line in prompt.splitlines() if line.startswith("5. "))
    assert "ONLY" in rule5 and "start over" in rule5
    assert '"talk in Hindi"' in rule5 and "NOT a reset" in rule5  # the old triggers are named as NOT resets


def test_the_prompt_has_the_rule_for_the_earlier_answer_in_another_language():
    prompt = _build_understand_prompt("x", [], None, "2026-10-09T10:00:00+05:30")
    rule = next(line for line in prompt.splitlines() if line.startswith("18. "))
    assert "answer the same in Kannada" in rule and 'kind = "sea_question"' in rule and "reply_language" in rule
    assert 'never "reset_or_language_switch"' in rule


# --- the code validates what the model proposes -----------------------------------------------------------------------

def test_a_reset_kind_with_a_reply_language_after_a_sea_answer_becomes_the_earlier_question_again():
    body = {"kind": "reset_or_language_switch", "intents": [], "places": [], "when": None, "is_followup": False,
            "agents": [], "english_reading": "answer the same", "reply_language": "kn"}
    result = _plan(body)
    plan = result
    assert plan["understood_kind"] == "sea_question" and plan["understood_is_followup"] is True
    assert plan["reply_language"] == "kn"
    assert plan["execution_plan"] and plan.get("query_outcome") is None  # the sea agents run again


def test_a_genuine_reset_stays_a_reset():
    body = {"kind": "reset_or_language_switch", "intents": [], "places": [], "when": None, "is_followup": False,
            "agents": [], "english_reading": "reset", "reply_language": None}
    assert _plan(body, query="clear the conversation")["understood_kind"] == "reset_or_language_switch"


def test_with_nothing_to_repeat_the_override_does_not_invent_a_question():
    body = {"kind": "reset_or_language_switch", "intents": [], "places": [], "when": None, "is_followup": False,
            "agents": [], "english_reading": "answer in kannada", "reply_language": "kn"}
    assert _plan(body, query="answer in kannada", history=[])["understood_kind"] == "reset_or_language_switch"


# --- the offline reading ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "message,code",
    [("okay fine answer the same in kannada", "kn"), ("in hindi please", "hi"), ("Kannada", "kn"), ("say that again in tamizh", "ta"),
     ("give me that in Gujarati", "gu"), ("reply in Odia", "or"), ("answer in kannda", "kn")],
)
def test_the_offline_reading_finds_the_requested_language(message, code):
    assert requested_reply_language(message) == code


@pytest.mark.parametrize("message", ["is it safe near kochi", "change language", "what is the wave height", "hello", ""])
def test_ordinary_messages_request_no_language(message):
    assert requested_reply_language(message) is None


@pytest.mark.parametrize("message,code", [("okay fine answer the same in kannada", "kn"), ("in hindi please", "hi"), ("kannada", "kn")])
def test_offline_a_language_request_after_a_sea_answer_is_a_followup_not_a_reset(message, code):
    u = _fallback_understand(message, HISTORY)
    assert (u.kind, u.is_followup, u.reply_language) == ("sea_question", True, code)


def test_offline_the_language_word_alone_still_means_a_reset_when_no_language_is_named():
    assert _fallback_understand("change language", HISTORY).kind == "reset_or_language_switch"


def test_offline_a_fresh_question_still_requests_no_language():
    # PC5.8's rule: the word list never requests a language on a new question; only the follow-up case uses it
    u = _fallback_understand("answer in kannada: pfzs near mangrol", [])
    assert u.kind == "sea_question" and u.reply_language is None
