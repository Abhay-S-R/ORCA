"""CONTEXT-2 (2026-10-09): "answer the same in kannada" translates the earlier answer, it does not run the pipeline again.

The model's reading decides (`language_only`, a follow-up with a reply language); code checks it against the history
(no new place, no new time, an earlier answered turn whose finished answer is held). The facts, the verdict card and the
citations are the earlier answer's, because the SAME answer is translated; the frame carries what the chat remembers about
a turn, so the next follow-up still has its place and intent.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from orca import session
from orca.agents.planning import ROUTING_TABLE
from orca.api import language_rerender
from orca.graph.graph import _route_after_planning, planning_node

ROW = ROUTING_TABLE[0].name
FRAME = {
    "type": "final_response", "query_id": "11111111-1111-1111-1111-111111111111", "outcome": "ANSWERED",
    "final_english_response": "The nearest zone is 49 km WNW of Mangrol.", "final_vernacular_response": "ગુજરાતી",
    "detected_language": "gu", "normalized_english_query": "pfzs near mangrol", "matched_intent_rows": [ROW],
    "user_location": {"place_name": "mangrol", "lat": 21.1, "lon": 70.1, "place_source": "gazetteer"},
    "risk_assessment": {"go_no_go": "GO"}, "vessel_class": "small_fishing", "citations": [{"dataset": "pfz"}],
    "confidence_tier": "HIGH", "confidence_reason": None, "disclosures": ["earlier note"],
}
LAST = session.turn_from_final("answer this in gujarati: pfzs near mangrol", FRAME)


@pytest.fixture(autouse=True)
def _model_off(monkeypatch):
    monkeypatch.setenv("ORCA_LLM_ENABLED", "0")


class _Client:
    engine = "fake-model"

    def __init__(self, body):
        self.text = json.dumps(body)

    def complete(self, messages, **kw):
        return self.text


def _read(**over):
    body = {"kind": "sea_question", "intents": [ROW], "places": [], "when": None, "is_followup": True, "agents": [],
            "english_reading": "PFZs near Mangrol", "reply_language": "kn", "language_only": True}
    body.update(over)
    return body


def _plan(body, query="okay fine answer the same in kannada", history=None):
    history = [LAST] if history is None else history
    with mock.patch("orca.llm.tiers.llm", lambda tier: _Client(body)), mock.patch("orca.llm.tiers.llm_enabled", lambda: True):
        return planning_node({"query_id": "q", "raw_user_query": query, "session_history": history})  # type: ignore[arg-type]


def _translator(text, language):
    return f"[{language}] {text}"


def test_a_language_only_request_translates_the_stored_answer_without_the_pipeline():
    with mock.patch.object(language_rerender, "_translate", _translator), \
            mock.patch.object(language_rerender, "render_query", side_effect=AssertionError("never re-written")):
        update = _plan(_read())
    frame = update["language_rerender"]
    assert update["query_outcome"] == "LANGUAGE_CHANGED"
    assert frame["final_vernacular_response"] == "[kn] The nearest zone is 49 km WNW of Mangrol."
    assert frame["final_english_response"] == FRAME["final_english_response"]  # the same facts
    assert frame["risk_assessment"] == FRAME["risk_assessment"] and frame["citations"] == FRAME["citations"]
    assert frame["detected_language"] == "kn" and frame["language_rerender"] is True
    assert frame["disclosures"] == ["earlier note"]   # nothing is added to the earlier answer's own (2026-10-10: no banner notes)
    assert _route_after_planning({"query_outcome": update["query_outcome"]}) == "__end__"  # no specialist runs


def test_the_next_follow_up_still_has_its_place_and_intent():
    with mock.patch.object(language_rerender, "_translate", _translator):
        frame = _plan(_read())["language_rerender"]
    turn = session.turn_from_final("okay fine answer the same in kannada", frame)
    assert turn["intent_rows"] == [ROW] and turn["user_location"]["place_name"] == "mangrol"
    assert turn["english_query"] == "pfzs near mangrol" and turn["vessel_class"] == "small_fishing" and turn["verdict"] == "GO"
    assert turn["query_id"] == FRAME["query_id"]


def test_english_is_a_valid_target():
    with mock.patch.object(language_rerender, "_translate", lambda text, language: text if language == "en" else None):
        update = _plan(_read(reply_language="en", english_reading="Now in English please"), query="now in english please")
    assert update["language_rerender"]["final_vernacular_response"] == FRAME["final_english_response"]


@pytest.mark.parametrize("over", [
    {"places": [{"raw": "kochi", "normalized": "kochi"}]},   # a new place: a new question
    {"when": {"start": "2026-10-10T00:00:00", "end": "2026-10-10T23:59:00"}},   # another time
    {"language_only": False},                                # the model says it asks more than the language
    {"is_followup": False},
    {"reply_language": None},
])
def test_anything_more_than_the_language_runs_the_normal_pipeline(over):
    with mock.patch.object(language_rerender, "_translate", side_effect=AssertionError("must not translate")):
        update = _plan(_read(**over))
    assert "language_rerender" not in update and update.get("query_outcome") != "LANGUAGE_CHANGED"


def test_with_no_earlier_answer_it_is_not_a_rerender():
    with mock.patch.object(language_rerender, "_translate", side_effect=AssertionError("must not translate")):
        update = _plan(_read(), history=[])
    assert "language_rerender" not in update


def test_when_the_earlier_answer_is_not_held_the_normal_pipeline_runs_and_the_answer_is_never_rewritten():
    without_frame = {k: v for k, v in LAST.items() if k != "frame"}
    with mock.patch.object(language_rerender, "render_query", side_effect=AssertionError("must not re-write")):
        update = _plan(_read(), history=[without_frame])
    assert "language_rerender" not in update and update.get("query_outcome") != "LANGUAGE_CHANGED"


def test_when_translation_fails_the_normal_pipeline_runs():
    with mock.patch.object(language_rerender, "_translate", lambda text, language: None):
        update = _plan(_read())
    assert "language_rerender" not in update


# --- the session keeps the frame for the last turn only ---------------------------------------------------------------------

def test_only_the_last_turn_keeps_its_frame(monkeypatch):
    monkeypatch.setattr(session, "redis_client", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    sid = "ctx2-frames"
    session.append_turn(sid, session.turn_from_final("one", FRAME))
    session.append_turn(sid, session.turn_from_final("two", {**FRAME, "query_id": "22222222-2222-2222-2222-222222222222"}))
    turns = session.get_turns(sid)
    assert "frame" not in turns[0] and turns[1]["frame"]["query_id"].startswith("2222")
    session._local.pop(sid, None)


# --- the older fixed-phrase path shares the builder -------------------------------------------------------------------------

def test_the_p313_phrase_path_uses_the_same_builder_and_may_fall_back_to_the_trace():
    import inspect

    from orca.api import main

    source = inspect.getsource(main._language_change_stream)
    assert "rerender_last_answer(" in source and "rewrite_from_trace=True" in source
    without_frame = {k: v for k, v in LAST.items() if k != "frame"}
    rendered = mock.Mock(query_id="q1", final_english_response="en", final_vernacular_response=None, confidence_tier="HIGH", citations=[])
    with mock.patch.object(language_rerender, "render_query", return_value=rendered):
        assert language_rerender.rerender_last_answer([without_frame], "hi") is None
        frame = language_rerender.rerender_last_answer([without_frame], "hi", rewrite_from_trace=True)
    assert frame is not None and frame["matched_intent_rows"] == [ROW]


def test_the_query_stream_sends_the_prepared_frame():
    import inspect

    from orca.api import main

    assert 'final_state.get("language_rerender")' in inspect.getsource(main._query_stream)
