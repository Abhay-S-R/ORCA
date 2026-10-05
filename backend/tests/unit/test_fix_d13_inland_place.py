"""D-13 — an inland place is recognised by planning and answered directly.

"hows the weather in bengaluru" was read as off-topic, then the old word list
("weather") sent it to the sea agents, which answered at the pilot default
position under a "names no place" banner. Now the model reads it as an inland
place, no agent runs, and ORCA says plainly that it has no sea data for it.
The gazetteer checks the model's call: a coastal place is never refused.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from orca.agents import planning
from orca.agents.understand import _KIND_VALUES, NON_SEA_KINDS, _parse_understand_output
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


def _reading(kind, place):
    return json.dumps({"kind": kind, "intents": ["CONDITIONS"], "when": None, "is_followup": False, "agents": [],
                       "places": [{"raw": place, "normalized": place}]})


def _plan(kind, place, query="hows the weather in " ):
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(_reading(kind, place))):
        return planning.run({"query_id": "q", "raw_user_query": query + place, "session_history": []})


def test_inland_place_is_a_kind_and_a_non_sea_kind():
    assert "inland_place" in _KIND_VALUES and "inland_place" in NON_SEA_KINDS
    assert _parse_understand_output(_reading("inland_place", "Bengaluru")).kind == "inland_place"


@pytest.mark.parametrize("place", ["Bengaluru", "Delhi", "Hyderabad", "Pune", "Jaipur"])
def test_an_inland_place_runs_no_agent_and_asks_for_no_default_position(place):
    result = _plan("inland_place", place)
    out = result.outputs
    assert out["kind"] == "inland_place"
    assert out["matched_intent_rows"] == [planning.OUT_OF_SCOPE_ROW]
    assert out["execution_plan"] == []


@pytest.mark.parametrize("place", ["Mumbai", "Chennai", "Kochi", "Kolkata", "Mangalore", "Visakhapatnam"])
def test_a_coastal_place_the_model_called_inland_is_overruled_by_the_gazetteer(place):
    result = _plan("inland_place", place)
    assert result.outputs["kind"] == "sea_question"
    assert result.outputs["matched_intent_rows"] != [planning.OUT_OF_SCOPE_ROW]
    assert result.outputs["execution_plan"]  # the sea agents run


@pytest.mark.parametrize("region", ["Goa", "Gujarat", "Kerala"])
def test_a_whole_coastline_called_inland_is_a_sea_question_too(region):
    assert _plan("inland_place", region).outputs["kind"] == "sea_question"


def test_the_reply_is_written_by_the_model_and_is_told_the_place_is_inland():
    fake = _Client("Bengaluru is inland, so I have no sea data for it. Name a coastal place and I can help.")
    with mock.patch("orca.llm.tiers.llm", lambda tier: fake):
        out = out_of_scope_node({"understood_kind": "inland_place", "raw_user_query": "hows the weather in bengaluru"})
    assert out["final_english_response"].startswith("Bengaluru is inland")
    assert out["small_talk"] is True and out["query_outcome"] == "OUT_OF_SCOPE" and out["execution_plan"] == []
    assert "inland, away from the coast" in fake.prompts[0]


def test_no_model_still_says_it_directly_with_no_figure():
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(boom=True)):
        out = out_of_scope_node({"understood_kind": "inland_place", "raw_user_query": "hows the weather in bengaluru"})
    text = out["final_english_response"]
    assert "inland" in text and "no sea data" in text and not any(c.isdigit() for c in text)


def test_a_reply_that_invents_a_temperature_is_discarded():
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client("It is about 27 degrees in Bengaluru.")):
        out = out_of_scope_node({"understood_kind": "inland_place", "raw_user_query": "hows the weather in bengaluru"})
    assert "27" not in out["final_english_response"] and "inland" in out["final_english_response"]
