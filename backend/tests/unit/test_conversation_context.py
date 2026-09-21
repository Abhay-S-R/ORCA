"""The Ask chat's context window (checklist P0 #1, Architecture §8.8): the last
MAX_TURNS turns of one chat are remembered and fed to Planning (a follow-up
continues the previous intent) and Agent 9 (the narrative reads the
conversation). No Redis or Postgres needed — Redis is forced down so the
in-process mirror carries the memory, which is itself one of the behaviours
under test.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from orca import session
from orca.agents import planning, reporting
from orca.api import main


@pytest.fixture(autouse=True)
def redis_down_and_clean_memory(monkeypatch):
    def down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(session, "redis_client", down)
    session._local.clear()
    yield
    session._local.clear()


def _turn(query="is it safe to go to sea today", rows=("SAFETY_CHECK",), place="Pamban", answer="GO: calm seas"):
    return {
        "query": query, "english_query": query, "verdict": "GO", "intent_rows": list(rows), "answer": answer,
        "user_location": {"lat": 9.28, "lon": 79.2, "place_name": place, "place_source": "gazetteer"},
    }


# --- store ------------------------------------------------------------------

def test_redis_outage_keeps_the_conversation_instead_of_silently_forgetting_it():
    session.append_turn("chat-1", _turn())
    assert [t["query"] for t in session.get_turns("chat-1")] == ["is it safe to go to sea today"]


def test_window_keeps_only_the_last_max_turns_oldest_first():
    for i in range(session.MAX_TURNS + 3):
        session.append_turn("chat-1", _turn(query=f"q{i}"))
    turns = session.get_turns("chat-1")
    assert len(turns) == session.MAX_TURNS
    assert turns[0]["query"] == "q3" and turns[-1]["query"] == f"q{session.MAX_TURNS + 2}"


def test_chats_never_share_context():
    session.append_turn("chat-1", _turn())
    assert session.get_turns("chat-2") == []
    assert session.get_turns(None) == []


def test_turn_from_final_keeps_english_query_intent_and_a_bounded_answer():
    final = {
        "normalized_english_query": "is it safe near pamban",
        "matched_intent_rows": ["SAFETY_CHECK"],
        "risk_assessment": {"go_no_go": "CAUTION"},
        "final_english_response": "x" * 2000,
        "user_location": {"lat": 9.28, "lon": 79.2},
    }
    turn = session.turn_from_final("பாம்பன் அருகே பாதுகாப்பானதா", final)
    assert turn["english_query"] == "is it safe near pamban"
    assert turn["intent_rows"] == ["SAFETY_CHECK"]
    assert turn["verdict"] == "CAUTION"
    assert len(turn["answer"]) == session.ANSWER_CHARS


def test_a_carried_place_survives_the_turn_that_named_it_rolling_out_of_the_window():
    turns = [_turn()] + [
        {**_turn(query=f"and q{i}"), "user_location": {"lat": 9.28, "lon": 79.2, "place_name": "Pamban", "place_source": "session_carried"}}
        for i in range(session.MAX_TURNS)
    ]
    window = turns[-session.MAX_TURNS:]
    assert all(t["user_location"]["place_source"] == "session_carried" for t in window)
    assert session.last_place(window) == (9.28, 79.2, "Pamban")


# --- Planning ---------------------------------------------------------------

def test_follow_up_with_no_routing_match_continues_the_previous_intent(monkeypatch):
    monkeypatch.setattr(planning, "_tier3_llm_fallback", lambda q, history=None: [])
    result = planning.run({
        "query_id": "q", "normalized_english_query": "what about tomorrow evening?",
        "session_history": [_turn()],
    })
    assert result.outputs["matched_intent_rows"] == ["SAFETY_CHECK"]
    assert "risk_assessment" in result.outputs["execution_plan"]
    assert result.confidence.score == "MEDIUM"
    assert "previous turn" in result.confidence.rationale


def test_follow_up_that_matches_on_its_own_is_not_overridden(monkeypatch):
    monkeypatch.setattr(planning, "_tier3_llm_fallback", lambda q, history=None: [])
    result = planning.run({
        "query_id": "q", "normalized_english_query": "what is the wave height",
        "session_history": [_turn()],
    })
    assert result.outputs["matched_intent_rows"] == ["CONDITIONS"]


def test_only_the_immediately_previous_turn_is_carried():
    history = [_turn(), _turn(query="tell me something", rows=())]
    assert planning.carry_intent(history) == []
    assert planning.carry_intent([]) == []
    assert planning.carry_intent([_turn(rows=("NOT_A_REAL_ROW",))]) == []


def test_tier3_llm_reads_a_follow_up_in_the_context_of_the_previous_question():
    client = MagicMock()
    client.complete.return_value = "SAFETY_CHECK"
    with patch("orca.llm.tiers.llm", return_value=client):
        matches = planning.classify_intent("what about tomorrow evening?", [_turn(query="is it safe near pamban")])
    assert matches == [("SAFETY_CHECK", 0.7)]
    prompt = client.complete.call_args.args[0][0]["content"]
    assert 'previous question in the conversation was: "is it safe near pamban"' in prompt


def test_priority_lane_agrees_with_a_carried_safety_intent(monkeypatch):
    monkeypatch.setattr(planning, "_tier3_llm_fallback", lambda q, history=None: [])
    assert main._is_priority_shaped("what about tomorrow evening?", None, [_turn()]) is True
    assert main._is_priority_shaped("what about tomorrow evening?", None) is False


# --- Agent 9 prompt -----------------------------------------------------------

def test_narrative_prompt_carries_every_turn_in_the_window_with_answers():
    history = [_turn(query=f"question {i}", answer=f"answer {i}") for i in range(session.MAX_TURNS)]
    block = reporting._describe_recent_turns(history)
    for i in range(session.MAX_TURNS):
        assert f'"question {i}"' in block and f'"answer {i}"' in block
    assert block.index("question 0") < block.index("question 4")


def test_narrative_prompt_includes_the_conversation_but_keeps_the_verdict_fixed():
    client = MagicMock()
    client.complete.return_value = "CAUTION: swell building. Unlike earlier, hold off."
    with patch("orca.llm.tiers.llm", return_value=client):
        reporting.synthesize_narrative(
            "why?", {"go_no_go": "CAUTION", "reason": "swell building"}, [],
            session_history=[_turn(answer="GO: calm seas")],
        )
    prompt = client.complete.call_args.args[0][0]["content"]
    assert "EARLIER IN THIS CONVERSATION" in prompt
    assert 'ORCA answered: "GO: calm seas"' in prompt
    assert "VERDICT: CAUTION" in prompt


def test_old_history_entries_without_answers_still_render():
    assert reporting._describe_recent_turns([{"query": "is it safe", "verdict": "GO"}]) == (
        '1. User asked: "is it safe" -> verdict then: GO'
    )


# --- /query route -------------------------------------------------------------

def _final(user_location, english="is it safe to go to sea today"):
    return {
        "type": "final_response", "query_id": "qid-1",
        "final_english_response": "GO: calm seas", "normalized_english_query": english,
        "matched_intent_rows": ["SAFETY_CHECK"], "risk_assessment": {"go_no_go": "GO", "reason": "calm"},
        "user_location": user_location,
    }


@pytest.fixture
def api(monkeypatch):
    """/query with the graph replaced by a stub that records what it was given
    — the route's own cache / coalescing / memory wiring is what's under test."""
    seen: list[dict] = []
    stored: dict[str, dict] = {}

    async def fake_stream(q, lat, lon, vessel_class, distress=False, persona=None, depth=None,
                          place=(None, "explicit"), on_final=None, session_id=None, session_history=None,
                          resolution=None, **kwargs):
        # **kwargs, not a growing parameter list: this double stands in for
        # the graph so the *route's* cache / coalescing / memory wiring can be
        # tested, and it has no opinion about arguments that only the real
        # stream reads (P2.11's `llm=`, and whatever comes after it). Captured
        # rather than dropped, so a test that does care can assert on them.
        seen.append({"q": q, "place": place, "history": list(session_history or []), "on_final": on_final,
                     "vessel_class": vessel_class, **kwargs})
        # Echo the position the route really resolved, as the graph does. A
        # hardcoded place_source here is how the allowlist's "pilot_gazetteer"
        # — a source the resolver never produces — went unnoticed.
        final = _final({"lat": lat, "lon": lon, "place_name": place[0], "place_source": place[1]})
        if on_final is not None:
            on_final(final)
        yield main._sse(final)

    monkeypatch.setattr(main, "_query_stream", fake_stream)
    monkeypatch.setattr(main, "query_cache_get", lambda key: stored.get(key))
    monkeypatch.setattr(main, "query_cache_store", lambda key, value: stored.__setitem__(key, value))
    monkeypatch.setattr(planning, "_tier3_llm_fallback", lambda q, history=None: [])
    return TestClient(main.app), seen, stored


def _frames(response):
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]


def test_each_answered_turn_is_remembered_and_fed_to_the_next(api):
    client, seen, _ = api
    client.get("/query", params={"q": "is it safe to go to sea near Pamban", "session_id": "chat-1"})
    client.get("/query", params={"q": "what about tomorrow evening?", "session_id": "chat-1"})
    assert seen[0]["history"] == []
    assert [t["english_query"] for t in seen[1]["history"]] == ["is it safe to go to sea today"]
    # The follow-up named no place, so it continues the one the chat was about.
    assert seen[0]["place"][1] == "gazetteer"
    assert seen[1]["place"] == (seen[0]["place"][0], "session_carried")
    assert len(session.get_turns("chat-1")) == 2


def test_a_query_cache_hit_is_still_remembered(api):
    client, seen, _ = api
    client.get("/query", params={"q": "is it safe to go to sea near Pamban", "session_id": "chat-1"})
    client.get("/query", params={"q": "is it safe to go to sea near Pamban", "session_id": "chat-2"})
    assert len(seen) == 1, "second chat's first turn should be served from the cache"
    assert len(session.get_turns("chat-2")) == 1


def test_follow_ups_never_touch_the_shared_query_cache(api):
    client, seen, stored = api
    client.get("/query", params={"q": "is it safe to go to sea near Pamban", "session_id": "chat-1"})
    cached_before = dict(stored)
    client.get("/query", params={"q": "is it safe to go to sea near Pamban", "session_id": "chat-1"})
    assert len(seen) == 2, "a follow-up must run fresh, not replay another conversation's answer"
    assert seen[1]["on_final"] is None
    assert stored == cached_before


def test_callers_without_a_session_are_unchanged(api):
    client, seen, _ = api
    response = client.get("/query", params={"q": "is it safe to go to sea near Pamban"})
    assert _frames(response)[-1]["type"] == "final_response"
    assert seen[0]["history"] == []
    assert session._local == {}


# --- P2.9: the ✕ on a "Carried over" chip ------------------------------------

def test_drop_place_refuses_to_inherit_the_chats_place(api):
    """The first version of the chip's ✕ re-asked "(not Kannur — I have not said
    where yet)", which put the name back into the text and resolved Kannur again;
    without the name, the session handed it back anyway. Only a parameter that
    reaches `session.last_place` can refuse the carry-over."""
    client, seen, _ = api
    client.get("/query", params={"q": "is it safe to go to sea near Pamban", "session_id": "chip-1"})
    client.get("/query", params={"q": "what about tomorrow evening?", "session_id": "chip-1"})
    client.get("/query", params={"q": "what about tomorrow evening?", "session_id": "chip-1", "drop": "place"})
    assert seen[1]["place"][1] == "session_carried", "control: without drop it IS inherited"
    assert seen[2]["place"][1] != "session_carried"
    assert seen[2]["place"][0] is None, "the place is not silently kept under another source name"


def test_drop_intent_withholds_the_previous_intent_from_planning(api):
    client, seen, _ = api
    client.get("/query", params={"q": "is it safe to go to sea near Pamban", "session_id": "chip-2"})
    client.get("/query", params={"q": "what about tomorrow evening?", "session_id": "chip-2"})
    client.get("/query", params={"q": "what about tomorrow evening?", "session_id": "chip-2", "drop": "intent"})
    assert any(t.get("intent_rows") for t in seen[1]["history"]), "control: the intent is carried"
    assert all(not t.get("intent_rows") for t in seen[2]["history"])
    # The conversation itself is still there for Agent 9 to read.
    # ... and by the third request the chat legitimately holds BOTH earlier turns.
    assert len(seen[2]["history"]) == 2


def test_drop_vessel_class_refuses_to_inherit_the_chats_vessel(api):
    from orca import session as session_memory

    client, seen, _ = api
    session_memory.append_turn("chip-3", {
        "query": "is it safe near Pamban", "english_query": "is it safe near Pamban",
        "user_location": {"lat": 9.27, "lon": 79.2, "place_name": "pamban", "place_source": "gazetteer"},
        "vessel_class": "mechanized_trawler", "intent_rows": ["SAFETY_CHECK"],
    })
    client.get("/query", params={"q": "what about tomorrow evening?", "session_id": "chip-3"})
    client.get("/query", params={"q": "what about tomorrow evening?", "session_id": "chip-3", "drop": "vessel_class"})
    assert seen[0]["vessel_class"] == "mechanized_trawler", "control: inherited without drop"
    assert seen[1]["vessel_class"] is None


def test_an_unknown_drop_value_is_ignored_not_an_error(api):
    client, seen, _ = api
    response = client.get("/query", params={"q": "is it safe to go to sea near Pamban", "drop": "bogus,,"})
    assert response.status_code == 200 and seen
