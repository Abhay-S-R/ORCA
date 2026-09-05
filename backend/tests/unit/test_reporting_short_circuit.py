"""Cost-based short-circuit (Architecture §9.3, phase4 plan §2.1) — a NO_GO
verdict drops Ocean Analytics' PFZ/tide/trend content from the response
unless the user separately asked for zone or condition data. RAA never reads
ocean_data (confirmed by reading risk_assessment.py), so this is purely a
reporting-layer trim, never a change to the verdict itself.
"""
from __future__ import annotations

from orca.graph.graph import reporting_run

_BASE_STATE = {
    "query_id": "q1",
    "reasoning_depth": "SHALLOW",
    "normalized_english_query": "is it safe to go to sea",
    "stakeholder_persona": "fisherman",
    "weather_data": {
        "lightning_active": False, "cyclone_alert": "Red",
        "dataset": "Open-Meteo", "acquisition_timestamp": "2026-01-01T00:00:00Z", "freshness_minutes": 5,
    },
    "geospatial_data": {"imbl_distance_nm": 10.0, "mpa_violation": False},
    "ocean_data": {"nearest_pfz": {"lat": 8.9, "lon": 78.2}, "tide": {"high": "06:00"}},
    "risk_assessment": {"go_no_go": "NO_GO", "status": "DANGER", "reason": "Severe Weather / Cyclone Threshold Exceeded"},
    "confidence_tier": "HIGH",
}


def test_no_go_without_explicit_ocean_intent_drops_ocean_content():
    state = {**_BASE_STATE, "matched_intent_rows": ["SAFETY_CHECK"]}
    result = reporting_run(state)  # type: ignore[arg-type]
    assert result.outputs["early_exit_triggered"] is True
    assert not any(c["agent_name"] == "ocean_analytics" for c in result.outputs["citations"])


def test_no_go_with_explicit_pfz_intent_keeps_ocean_content():
    state = {**_BASE_STATE, "matched_intent_rows": ["SAFETY_CHECK", "PFZ_NEAREST"]}
    result = reporting_run(state)  # type: ignore[arg-type]
    assert result.outputs["early_exit_triggered"] is False
    assert any(c["agent_name"] == "ocean_analytics" for c in result.outputs["citations"])


def test_go_verdict_never_triggers_early_exit():
    state = {
        **_BASE_STATE,
        "matched_intent_rows": ["SAFETY_CHECK"],
        "weather_data": {**_BASE_STATE["weather_data"], "cyclone_alert": None},
        "risk_assessment": {"go_no_go": "GO", "status": "SAFE", "reason": "All Parameters Within Safe Operational Limits"},
    }
    result = reporting_run(state)  # type: ignore[arg-type]
    assert result.outputs["early_exit_triggered"] is False
    assert any(c["agent_name"] == "ocean_analytics" for c in result.outputs["citations"])
