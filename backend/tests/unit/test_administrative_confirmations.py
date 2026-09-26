"""The reset and language-switch confirmations, over the real `/query` route
(chatbot plan defect 4, fixed 2026-09-25). Both short-circuit before
`_query_stream` — a query-cache/session test mocking that function never
reaches them — so they need their own coverage.
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


def test_a_reset_is_worded_by_a_model_and_still_clears_the_session():
    fake_client = MagicMock()
    fake_client.complete.return_value = "All set — I've cleared this conversation."
    fake_client.engine = "gemini · fake"
    session.append_turn("chat-reset", {
        "query": "is it safe today", "english_query": "is it safe today", "verdict": "GO",
        "intent_rows": ["SAFETY_CHECK"], "answer": "GO: calm",
        "user_location": {"lat": 9.28, "lon": 79.2, "place_name": "pamban", "place_source": "gazetteer"},
    })
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        response = client.get("/query", params={"q": "forget everything", "session_id": "chat-reset"})
    (frame,) = _frames(response)
    assert frame["outcome"] == "RESET"
    assert frame["final_english_response"] == "All set — I've cleared this conversation."
    assert frame["response_engine"] == "gemini · fake"
    assert session.get_turns("chat-reset") == []


def test_a_reset_still_confirms_with_its_own_text_when_no_model_answers():
    with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no API key")):
        response = client.get("/query", params={"q": "forget everything"})
    (frame,) = _frames(response)
    assert frame["outcome"] == "RESET"
    assert frame["final_english_response"] == session.RESET_CONFIRMATION
    assert frame["response_engine"].startswith("Deterministic")


def test_a_language_switch_with_no_earlier_turn_is_worded_by_a_model_and_translated():
    fake_client = MagicMock()
    fake_client.complete.return_value = "Sure thing — Tamil from here on."
    fake_client.engine = "gemini · fake"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        response = client.get("/query", params={"q": "speak to me in tamil", "session_id": "chat-lang"})
    (frame,) = _frames(response)
    assert frame["outcome"] == "LANGUAGE_CHANGED"
    assert frame["final_english_response"] == "Sure thing — Tamil from here on."
    assert frame["response_engine"] == "gemini · fake"
    assert frame["detected_language"] == "ta"
    # The reply is translated for delivery, English kept only in the English field.
    assert frame["final_vernacular_response"] != frame["final_english_response"]


def test_a_language_switch_still_confirms_with_its_own_text_when_no_model_answers():
    with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no API key")):
        response = client.get("/query", params={"q": "speak to me in hindi", "session_id": "chat-lang-2"})
    (frame,) = _frames(response)
    assert frame["outcome"] == "LANGUAGE_CHANGED"
    assert frame["final_english_response"] == "Done — I'll reply in this language from now on."
    assert frame["response_engine"].startswith("Deterministic")
