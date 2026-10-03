""""Current time" / "current location" questions, over the real `/query`
route (found 2026-09-26). "current" is real marine vocabulary (an ocean
current) and also an ordinary English adjective; the collision used to run
the full marine pipeline for a plain clock/position question, and answer it
with the pilot region's default position — a real place a caller could
mistake for their own. See `docs/logs/DLC_implementation_log.md`.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from orca import session
from orca.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def redis_down_and_clean_memory(monkeypatch):
    def down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(session, "redis_client", down)
    session._local.clear()
    yield
    session._local.clear()


def _frames(response):
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]


def _echo_facts_client():
    """A fake model that reflects the facts block back, rather than a
    hardcoded time — the real facts read the live clock."""
    fake = MagicMock()
    fake.complete.side_effect = (
        lambda messages, **kw: "Understood — "
        + messages[0]["content"].split("keep every figure in it exactly as written):\n")[1].split("\n\nRULES")[0]
    )
    fake.engine = "gemini · fake"
    return fake


def test_current_time_never_runs_the_marine_pipeline():
    with patch("orca.llm.tiers.llm", return_value=_echo_facts_client()):
        response = client.get("/query", params={"q": "do you know whats current time is"})
    frame = _frames(response)[-1]
    assert frame["outcome"] == "OUT_OF_SCOPE"
    assert "IST" in frame["final_english_response"]
    assert frame.get("risk_assessment") in (None, {})


def test_current_location_with_no_gps_fix_never_claims_the_pilot_default():
    with patch("orca.llm.tiers.llm", return_value=_echo_facts_client()):
        response = client.get("/query", params={"q": "do you know atleast current location"})
    frame = _frames(response)[-1]
    assert frame["outcome"] == "OUT_OF_SCOPE"
    assert "No position has been shared" in frame["final_english_response"]
    # Never the regional-default position that used to be narrated as an answer.
    assert "8.8" not in frame["final_english_response"] and "78.3" not in frame["final_english_response"]


def test_current_location_with_a_real_gps_fix_reports_it_but_not_as_a_place():
    # 8.75N 78.25E: wet water off Thoothukudi (same point test_place_resolution.py's
    # coordinate-parser tests use) — not the on-land Kochi fixture from defect 1's
    # investigation, which _usable_fix would correctly reject and defeat this test.
    with patch("orca.llm.tiers.llm", return_value=_echo_facts_client()):
        response = client.get(
            "/query",
            params={"q": "where am i", "fix_lat": 8.75, "fix_lon": 78.25},
        )
    frame = _frames(response)[-1]
    assert frame["outcome"] == "OUT_OF_SCOPE"
    assert "8.7500, 78.2500" in frame["final_english_response"]
    assert "not a place to answer" in frame["final_english_response"]


def test_a_genuine_ocean_current_question_still_runs_the_marine_pipeline():
    with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no key")):
        response = client.get("/query", params={"q": "ocean current near Chennai"})
    frame = _frames(response)[-1]
    assert frame["outcome"] != "OUT_OF_SCOPE"


def test_with_no_model_a_self_context_reply_still_carries_the_real_facts():
    with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no key")):
        response = client.get("/query", params={"q": "what time is it"})
    frame = _frames(response)[-1]
    assert frame["outcome"] == "OUT_OF_SCOPE"
    assert "IST" in frame["final_english_response"]
    assert frame["response_engine"].startswith("Deterministic")


def test_self_context_in_follow_up_turn_never_inherits_intent_or_place():
    # Found 2026-09-26: turn 1 was "sea conditions at kochi". In turn 2, the user asked
    # "whats my current location? i wanna ask some questions on it". Because turn 1 had
    # intent CONDITIONS and place kochi, the carryover logic previously bypassed out-of-scope,
    # inherited CONDITIONS, carried kochi, and replied with a "Surface Current Outlook at kochi".
    session_id = "test-followup-self-context"
    session.append_turn(
        session_id,
        {
            "query": "sea conditions near Kochi",
            "english_query": "sea conditions near Kochi",
            "intent_rows": ["CONDITIONS"],
            "user_location": {"place_name": "kochi", "lat": 9.9667, "lon": 76.2},
            "place": "kochi",
            "answer": "Wave height is 1.2m.",
        },
    )
    with patch("orca.llm.tiers.llm", return_value=_echo_facts_client()):
        response = client.get(
            "/query",
            params={
                "q": "whats my current location? i wanna ask some questions on it",
                "session_id": session_id,
            },
        )
    frame = _frames(response)[-1]
    assert frame["outcome"] == "OUT_OF_SCOPE"
    assert "No position has been shared" in frame["final_english_response"]
    assert "kochi" not in frame["final_english_response"].lower()
    assert "surface current" not in frame.get("final_english_response", "").lower()



def test_every_model_prompt_gets_the_conversation_and_the_device_position():
    # Found 2026-09-27: guard/small-talk/self-context replies were written from
    # the current message alone, and an inland fix never reached any prompt.
    # Bengaluru is inland: the fix must reach the prompt as context, and must
    # still never become the place the answer is about.
    session_id = "test-context-every-prompt"
    session.append_turn(session_id, {"query": "is it safe near Kochi", "english_query": "is it safe near Kochi",
                                     "intent_rows": ["SAFETY"], "user_location": {"place_name": "kochi"},
                                     "place": "kochi", "answer": "GO: calm."})
    prompts: list[str] = []
    fake = MagicMock()
    fake.complete.side_effect = lambda messages, **kw: prompts.append(messages[0]["content"]) or "[REPLY] Hello."
    fake.engine = "gemini · fake"
    with patch("orca.llm.tiers.llm", return_value=fake):
        response = client.get("/query", params={
            "q": "hi", "session_id": session_id, "fix_lat": 12.9716, "fix_lon": 77.5946,
        })
    frame = _frames(response)[-1]
    assert prompts, "no model was called"
    reply_prompt = prompts[-1]
    assert "is it safe near Kochi" in reply_prompt
    assert "12.9716, 77.5946" in reply_prompt
    assert "not a place the caller named" in reply_prompt
    # "nearest port to me" has a real answer: the closest held port, never a region or open water.
    assert "The nearest port ORCA holds data for is Thalassery" in reply_prompt
    assert frame["outcome"] == "OUT_OF_SCOPE"
