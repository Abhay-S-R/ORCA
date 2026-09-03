"""orca/resilience.py — plan §5.7, D1 Day 13."""
from __future__ import annotations

import time

import pytest

from orca.contracts import AgentResult
from orca.resilience import (
    CascadeRung,
    TimeoutExceeded,
    agent_boundary,
    conservative_or,
    safety_floor_for_missing_inputs,
    validate_arrival,
    walk_fallback_cascade,
    with_timeout,
)


def test_with_timeout_passes_through_a_fast_call():
    @with_timeout(1.0)
    def fast() -> int:
        return 42

    assert fast() == 42


def test_with_timeout_raises_on_a_slow_call():
    @with_timeout(0.05)
    def slow() -> int:
        time.sleep(1)
        return 1

    with pytest.raises(TimeoutExceeded):
        slow()


def test_agent_boundary_catches_and_returns_failed_status():
    @agent_boundary("test_agent")
    def raises() -> AgentResult:
        raise RuntimeError("boom")

    result = raises()
    assert result.status == "failed"
    assert result.confidence.score == "LOW_DATA"
    assert result.error_detail == "boom"


def test_agent_boundary_passes_through_success():
    @agent_boundary("test_agent")
    def ok() -> str:
        return "fine"

    assert ok() == "fine"


def test_walk_fallback_cascade_uses_first_working_rung():
    rungs = [
        CascadeRung("primary", lambda: {"v": 1}),
        CascadeRung("secondary", lambda: {"v": 2}),
    ]
    payload, rung_name, confidence = walk_fallback_cascade(rungs)
    assert payload == {"v": 1}
    assert rung_name == "primary"
    assert confidence.score == "HIGH"


def test_walk_fallback_cascade_falls_back_and_downgrades_confidence():
    def boom():
        raise RuntimeError("primary source down")

    rungs = [
        CascadeRung("primary", boom),
        CascadeRung("cached_fixture", lambda: {"v": 2}),
    ]
    payload, rung_name, confidence = walk_fallback_cascade(rungs)
    assert payload == {"v": 2}
    assert rung_name == "cached_fixture"
    assert confidence.score == "MEDIUM"
    assert "rung 1" in confidence.rationale


def test_walk_fallback_cascade_raises_when_every_rung_fails():
    def boom():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        walk_fallback_cascade([CascadeRung("only", boom)])


def test_validate_arrival_rejects_empty_payload():
    ok, reason = validate_arrival({})
    assert ok is False
    assert reason == "empty payload"


def test_validate_arrival_rejects_missing_required_key():
    ok, reason = validate_arrival({"a": 1}, required_keys=["a", "b"])
    assert ok is False
    assert "b" in reason


def test_validate_arrival_rejects_stale_payload():
    ok, reason = validate_arrival({"freshness_minutes": 500}, max_staleness_minutes=60)
    assert ok is False
    assert "stale" in reason


def test_validate_arrival_accepts_a_fresh_complete_payload():
    ok, reason = validate_arrival({"a": 1, "freshness_minutes": 5}, required_keys=["a"], max_staleness_minutes=60)
    assert ok is True
    assert reason is None


def test_conservative_or_records_missing_field_without_altering_value():
    missing: list[str] = []
    assert conservative_or(None, missing_field_name="wave_height_m", missing=missing) is None
    assert missing == ["wave_height_m"]
    assert conservative_or(1.5, missing_field_name="wind_speed", missing=missing) == 1.5
    assert missing == ["wave_height_m"]  # unchanged — the present field is never added


def test_safety_floor_is_none_when_nothing_missing():
    assert safety_floor_for_missing_inputs([]) is None


def test_safety_floor_forces_caution_naming_the_missing_input():
    go_no_go, reason = safety_floor_for_missing_inputs(["wave_height_m"])
    assert go_no_go == "CAUTION"
    assert "wave_height_m" in reason
