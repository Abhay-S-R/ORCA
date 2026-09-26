""""Current time" / "current location" questions, over the real `/query`
route (found 2026-09-26). "current" is real marine vocabulary (an ocean
current) and also an ordinary English adjective; the collision used to run
the full marine pipeline for a plain clock/position question, and answer it
with the pilot region's default position — a real place a caller could
mistake for their own. See `docs/DLC_implementation_log.md`.
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
