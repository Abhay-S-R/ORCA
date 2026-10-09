"""FIX-CONTEXT-1 (2026-10-09): the whole chat stays in view, not just the last five turns.

Found by an audit through the real path: in a seven-turn chat "what was my first question in this chat?" was answered
about the SECOND question (the first had silently fallen out of a five-turn window), with no hint that anything was gone.
Now 30 turns are kept; the last five carry their answers, older turns carry their question; a chat that reaches the
limit tells the model that earlier turns are not available.
"""
from __future__ import annotations

from orca import session
from orca.agents.reporting import _describe_recent_turns, conversation_context
from orca.agents.understand import _build_understand_prompt


def _turns(n):
    return [{"query": f"question {i}", "english_query": f"question {i}", "answer": f"answer {i}", "verdict": "GO",
             "user_location": {"place_name": "kochi"}} for i in range(n)]


def test_the_window_keeps_twenty_turns_and_five_are_recent():
    assert session.MAX_TURNS == 20 and session.RECENT_TURNS == 5


def test_the_understand_prompt_sees_every_question_and_only_the_recent_answers():
    prompt = _build_understand_prompt("and the wind?", _turns(12), None, "2026-10-09T10:00:00+05:30")
    for i in range(12):
        assert f'"question {i}"' in prompt
    assert 'replied: "answer 11"' in prompt and 'replied: "answer 7"' in prompt
    assert 'replied: "answer 6"' not in prompt and 'replied: "answer 0"' not in prompt
    assert "anything earlier is not available" not in prompt  # nothing has been dropped yet


def test_the_reporting_context_sees_every_question_and_only_the_recent_answers():
    text = _describe_recent_turns(_turns(12))
    assert text is not None
    assert '"question 0"' in text and '"question 11"' in text
    assert 'answered: "answer 11"' in text and 'answered: "answer 7"' in text
    assert 'answered: "answer 6"' not in text
    assert "anything earlier is not available" not in text


def test_a_chat_at_the_limit_says_earlier_turns_are_gone():
    full = _turns(session.MAX_TURNS)
    assert "anything earlier is not available" in _build_understand_prompt("x", full, None, "t")
    assert "anything earlier is not available" in (_describe_recent_turns(full) or "")
    assert "anything earlier is not available" in conversation_context(full, None)


def test_the_first_question_of_a_seven_turn_chat_is_still_there(monkeypatch):
    monkeypatch.setattr(session, "redis_client", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    sid = "ctx-window-test"
    for i in range(7):
        session.append_turn(sid, {"query": f"q{i}", "english_query": f"q{i}", "answer": f"a{i}"})
    kept = session.get_turns(sid)
    assert len(kept) == 7 and kept[0]["query"] == "q0"
    assert '"q0"' in _build_understand_prompt("what was my first question?", kept, None, "t")
    session._local.pop(sid, None)


def test_the_window_still_drops_the_oldest_beyond_twenty(monkeypatch):
    monkeypatch.setattr(session, "redis_client", lambda: (_ for _ in ()).throw(ConnectionError("down")))
    sid = "ctx-window-overflow"
    for i in range(session.MAX_TURNS + 3):
        session.append_turn(sid, {"query": f"q{i}", "answer": "a"})
    kept = session.get_turns(sid)
    assert len(kept) == session.MAX_TURNS and kept[0]["query"] == "q3"
    session._local.pop(sid, None)
