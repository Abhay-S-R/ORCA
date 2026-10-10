"""Test G8: Dynamic confidence and coverage reporting for geospatial agent."""
from __future__ import annotations

import pytest

from orca.agents import geospatial
from orca.graph.graph import geospatial_run


def test_geospatial_confidence_and_coverage_on_complete_data() -> None:
    """G8: When treaty lines and all 4 checks are available, coverage is (4, 4) and score is HIGH."""
    state = {
        "query_id": "test_g8_complete",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 9.28, "lon": 79.31, "place_name": "Gulf of Mannar"},
    }
    result = geospatial_run(state)  # type: ignore[arg-type]

    assert result.fallback_depth == 0
    assert result.coverage == (4, 4)
    assert result.confidence.score == "HIGH"
    assert "Authoritative treaty line check" in result.confidence.rationale


def test_geospatial_confidence_when_ban_order_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """G8: When fishing ban order is unavailable, coverage is (3, 4) and confidence degrades to MEDIUM."""
    def fake_ban(lat: float, lon: float) -> dict:
        return {"available": False, "reason": "No order on disk"}

    monkeypatch.setattr(geospatial, "fishing_ban_status", fake_ban)

    state = {
        "query_id": "test_g8_no_ban",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 9.28, "lon": 79.31, "place_name": "Gulf of Mannar"},
    }
    result = geospatial_run(state)  # type: ignore[arg-type]

    assert result.coverage == (3, 4)
    assert result.confidence.score == "MEDIUM"
    assert "coverage: 3/4" in result.confidence.rationale


def test_geospatial_confidence_when_fallback_proxy_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """G8: When treaty line dataset is missing and fallback proxy is used, fallback_depth is 1 and score is MEDIUM."""
    monkeypatch.setattr(geospatial, "nearest_boundary_line", lambda lat, lon: None)

    state = {
        "query_id": "test_g8_proxy",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 9.28, "lon": 79.31, "place_name": "Gulf of Mannar"},
    }
    result = geospatial_run(state)  # type: ignore[arg-type]

    assert result.fallback_depth == 1
    assert result.confidence.score == "MEDIUM"
    assert "EEZ proxy" in result.confidence.rationale
