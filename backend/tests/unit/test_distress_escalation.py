"""The distress model check (Revamp section 7.4) lives in `distress_escalation.py`.

`distress.py` is a safety-path file and must never gain the means to call a model
(CI guard 4). The escalate-only check is a separate module that the graph hands to
`distress.run`. What is pinned here: it can only raise an alarm, never clear one; any
failure leaves the phrase-list result untouched; and `distress.py` itself stays model-free.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

import pytest

from orca.agents import distress, distress_escalation
from orca.graph.graph import distress_check_node

NO = {"is_distress": False, "distress_type": None, "matched_language": None, "matched_phrase": None}
YES = {"is_distress": True, "distress_type": "phrase_match", "matched_language": "en", "matched_phrase": "sinking"}


class _Client:
    engine = "fake-model"

    def __init__(self, reply=None, boom=False):
        self.reply, self.boom, self.calls = reply, boom, 0

    def complete(self, messages, **kw):
        self.calls += 1
        if self.boom:
            raise RuntimeError("no model")
        return self.reply


def _model(client):
    return mock.patch("orca.llm.tiers.llm", lambda tier: client)


# --- escalate-only ------------------------------------------------------------------------

def test_a_phrase_list_alarm_is_returned_unchanged_and_the_model_is_not_even_asked():
    client = _Client(json.dumps({"is_distress": False}))
    with _model(client):
        assert distress_escalation.escalate_with_model("we are sinking", YES) is YES
    assert client.calls == 0


def test_a_model_yes_raises_the_alarm():
    client = _Client(json.dumps({"is_distress": True, "reason": "engine_failure_adrift"}))
    with _model(client):
        out = distress_escalation.escalate_with_model("engine dead, drifting far from shore", NO)
    assert out["is_distress"] is True and out["distress_type"] == "model_escalated"
    assert out["model_reason"] == "engine_failure_adrift"
    assert out["matched_phrase"] is None and out["matched_language"] is None


@pytest.mark.parametrize("reply", [
    json.dumps({"is_distress": False}),
    json.dumps({"is_distress": "true"}),   # a string is not the boolean the contract asks for
    json.dumps({}),
    "not json at all",
    "[]",
    "",
])
def test_anything_but_a_clear_yes_leaves_the_phrase_list_result_standing(reply):
    with _model(_Client(reply)):
        assert distress_escalation.escalate_with_model("is it safe near pamban", NO) is NO


def test_no_model_leaves_the_phrase_list_result_standing():
    with _model(_Client(boom=True)):
        assert distress_escalation.escalate_with_model("is it safe near pamban", NO) is NO


def test_a_provider_that_cannot_be_built_leaves_it_standing_too():
    def unavailable(tier):
        raise RuntimeError("every provider is off")

    with mock.patch("orca.llm.tiers.llm", unavailable):
        assert distress_escalation.escalate_with_model("is it safe near pamban", NO) is NO


# --- distress.py itself stays deterministic ----------------------------------------------------

def _state(text):
    return {"query_id": "q", "raw_user_query": text, "normalized_english_query": text,
            "reasoning_depth": "SHALLOW", "user_location": None, "distress_flag": False}


def test_run_without_the_hook_never_touches_a_model():
    client = _Client(json.dumps({"is_distress": True}))
    with _model(client):
        result = distress.run(_state("is it safe near pamban"))   # type: ignore[arg-type]
    assert client.calls == 0 and result.outputs["detection"]["is_distress"] is False


def test_run_uses_the_hook_it_is_given_and_still_builds_the_handoff():
    def raise_alarm(text, phrase_detection):
        return {"is_distress": True, "distress_type": "model_escalated", "matched_language": None, "matched_phrase": None}

    result = distress.run(_state("engine dead and drifting"), escalate=raise_alarm)   # type: ignore[arg-type]
    out = result.outputs
    assert out["detection"]["is_distress"] is True
    assert out["handoff"]["distress_type"] == "model_escalated" and out["handoff"]["status"] == "SIMULATED"
    assert out["mrcc_contact"]["nationwide_fallback"]["phone"] == "1554"


def test_the_safety_path_file_has_no_model_import():
    source = (Path(distress.__file__)).read_text(encoding="utf-8")
    pattern = re.compile(r"^\s*(import|from)\s+(orca\.llm|orca\.agents\.distress_escalation|anthropic|openai)", re.MULTILINE)
    assert not pattern.search(source)


# --- the graph node supplies the check ------------------------------------------------------------

def test_the_graph_node_escalates_a_message_the_phrase_list_misses():
    client = _Client(json.dumps({"is_distress": True, "reason": "engine_failure_adrift"}))
    with _model(client):
        update = distress_check_node(_state("engine dead and drifting far from land"))   # type: ignore[arg-type]
    assert update["distress_flag"] is True and update["query_outcome"] == "DISTRESS"
    assert "DISTRESS DETECTED" in update["final_english_response"]


def test_the_graph_node_does_not_raise_an_alarm_when_the_model_says_no():
    with _model(_Client(json.dumps({"is_distress": False}))):
        update = distress_check_node(_state("what is the wave height at pamban"))   # type: ignore[arg-type]
    assert update["distress_flag"] is False and "query_outcome" not in update


def test_the_graph_node_still_catches_a_phrase_list_distress_with_every_model_down():
    with _model(_Client(boom=True)):
        update = distress_check_node(_state("our boat is sinking near thoothukudi"))   # type: ignore[arg-type]
    assert update["distress_flag"] is True
