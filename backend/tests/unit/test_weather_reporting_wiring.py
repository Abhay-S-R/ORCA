"""Tests for defects W1, W2, and W3:
- W1: IMD nowcast alerts narrated in reporting (when active/non-expired)
- W2: lightning_source_agreement surfaced in reporting / facts_paragraph
- W3: reporting_run forwards full weather_data outputs in reconstructed AgentResult
"""
from __future__ import annotations

from orca.agents import reporting
from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.graph.graph import reporting_run
from orca.state import ORCAState


def test_reporting_run_forwards_w1_w2_w3_weather_outputs() -> None:
    """Verify W3: reporting_run does not drop imd_nowcast, agreement, or other weather outputs."""
    weather_data = {
        "lightning_active": False,
        "cyclone_alert": "Orange",
        "imd_nowcast": {
            "alerts": [
                {
                    "district": "Ernakulam",
                    "event_category": "Lightning",
                    "severity": "Alert",
                    "severity_color": "orange",
                    "events": "Thunder with Lightning",
                    "distance_km": 15.2,
                }
            ],
            "alert_count": 1,
            "lightning_flagged": True,
            "expired": False,
            "window_end": "2026-10-10T15:00:00Z",
            "radius_km": 150.0,
        },
        "imd_nowcast_dataset": "IMD district convective nowcast",
        "lightning_source_agreement": "disagree",
        "source_report": {
            "wave_height": {"chosen": "open_meteo", "used": "open_meteo", "obeyed": True},
        },
        "dataset": "Open-Meteo Marine API + Forecast API",
        "acquisition_timestamp": "2026-10-10T12:00:00Z",
        "freshness_minutes": 10,
        "confidence": Confidence(score="MEDIUM", rationale="test weather confidence"),
    }

    state: ORCAState = {
        "query_id": "test-w-q1",
        "reasoning_depth": "SHALLOW",
        "weather_data": weather_data,
        "risk_assessment": {"go_no_go": "GO", "reason": "Safe conditions", "readings": {}},
        "ocean_data": {},
        "geospatial_data": {},
        "raw_user_query": "is it safe to sail from kochi",
    }

    # Run reporting_run to produce the reporting AgentResult
    res = reporting_run(state)
    assert res.agent_name == "reporting"

    # Assemble response directly with a reconstructed result matching reporting_run
    assembled = reporting.assemble_response(
        "test-w-q1",
        [
            AgentResult(
                agent_name="weather_intelligence",
                query_id="test-w-q1",
                reasoning_depth="SHALLOW",
                inputs_consumed={},
                outputs={k: v for k, v in weather_data.items() if k != "confidence"},
                source_provenance=SourceProvenance(
                    dataset="Open-Meteo Marine API",
                    acquisition_timestamp="2026-10-10T12:00:00Z",
                    freshness_minutes=10,
                ),
                confidence=Confidence(score="MEDIUM", rationale="test"),
            )
        ],
    )
    # Check that result_refs preserves the full weather outputs (W3)
    ref = next(r for r in assembled.result_refs if r["agent_name"] == "weather_intelligence")
    assert "imd_nowcast" in ref["outputs"]
    assert "lightning_source_agreement" in ref["outputs"]
    assert ref["outputs"]["lightning_source_agreement"] == "disagree"
    assert ref["outputs"]["imd_nowcast"]["alert_count"] == 1


def test_facts_paragraph_narrates_active_imd_nowcast_w1() -> None:
    """Verify W1: facts_paragraph narrates active, non-expired IMD nowcast district alerts."""
    weather_out = {
        "lightning_active": False,
        "cyclone_alert": None,
        "imd_nowcast": {
            "alerts": [
                {
                    "district": "Ernakulam",
                    "event_category": "Thunderstorm / Lightning",
                    "severity": "Alert",
                    "severity_color": "orange",
                    "events": "Thunder with Lightning and Moderate Rain",
                    "distance_km": 12.0,
                },
                {
                    "district": "Alappuzha",
                    "event_category": "Squall",
                    "severity": "Warning",
                    "severity_color": "yellow",
                    "events": "Gusty wind with Rain",
                    "distance_km": 28.5,
                },
            ],
            "alert_count": 2,
            "lightning_flagged": True,
            "expired": False,
        },
    }

    results = [
        AgentResult(
            agent_name="weather_intelligence",
            query_id="q1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs=weather_out,
            source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
            confidence=Confidence(score="HIGH", rationale="test"),
        )
    ]

    verdict = {"go_no_go": "GO", "reason": "Conditions safe", "readings": {}}
    facts = reporting.facts_paragraph(verdict, results, user_location={"place_name": "kochi"})

    assert "IMD convective nowcast in force:" in facts
    assert "Ernakulam (Orange alert: Thunderstorm / Lightning)" in facts
    assert "Alappuzha (Yellow alert: Squall)" in facts


def test_facts_paragraph_suppresses_expired_imd_nowcast_w1() -> None:
    """Verify W1: facts_paragraph never presents an expired IMD nowcast as active."""
    weather_out = {
        "lightning_active": False,
        "cyclone_alert": None,
        "imd_nowcast": {
            "alerts": [
                {
                    "district": "Ernakulam",
                    "event_category": "Lightning",
                    "severity": "Alert",
                    "severity_color": "orange",
                }
            ],
            "alert_count": 1,
            "lightning_flagged": True,
            "expired": True,  # Historical / closed window!
        },
    }

    results = [
        AgentResult(
            agent_name="weather_intelligence",
            query_id="q1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs=weather_out,
            source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
            confidence=Confidence(score="LOW_DATA", rationale="expired"),
        )
    ]

    verdict = {"go_no_go": "GO", "reason": "Conditions safe", "readings": {}}
    facts = reporting.facts_paragraph(verdict, results, user_location={"place_name": "kochi"})

    assert "IMD convective nowcast in force" not in facts


def test_facts_paragraph_discloses_lightning_disagreement_w2() -> None:
    """Verify W2: facts_paragraph explicitly discloses when sources disagree on lightning."""
    weather_out = {
        "lightning_active": False,  # Open-Meteo proxy says clear
        "cyclone_alert": None,
        "imd_nowcast": {
            "alerts": [
                {
                    "district": "Ernakulam",
                    "event_category": "Lightning",
                    "severity": "Alert",
                    "severity_color": "orange",
                }
            ],
            "alert_count": 1,
            "lightning_flagged": True,  # IMD says lightning
            "expired": False,
        },
        "lightning_source_agreement": "disagree",
    }

    results = [
        AgentResult(
            agent_name="weather_intelligence",
            query_id="q1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs=weather_out,
            source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
            confidence=Confidence(score="MEDIUM", rationale="diverged"),
        )
    ]

    verdict = {"go_no_go": "CAUTION", "reason": "Convective risk active", "readings": {}}
    facts = reporting.facts_paragraph(verdict, results, user_location={"place_name": "kochi"})

    assert "Note: IMD district nowcast and Open-Meteo lightning indicators disagree on convective risk" in facts
    assert "convective conditions are treated conservatively as active" in facts


def test_facts_paragraph_no_disclosure_when_sources_agree_w2() -> None:
    """Verify W2: facts_paragraph does not add disagreement disclosure when agreement is 'agree'."""
    weather_out = {
        "lightning_active": True,
        "cyclone_alert": None,
        "imd_nowcast": {
            "alerts": [{"district": "Ernakulam", "event_category": "Lightning"}],
            "alert_count": 1,
            "lightning_flagged": True,
            "expired": False,
        },
        "lightning_source_agreement": "agree",
    }

    results = [
        AgentResult(
            agent_name="weather_intelligence",
            query_id="q1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs=weather_out,
            source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
            confidence=Confidence(score="HIGH", rationale="agree"),
        )
    ]

    verdict = {"go_no_go": "NO_GO", "reason": "Lightning active", "readings": {}}
    facts = reporting.facts_paragraph(verdict, results, user_location={"place_name": "kochi"})

    assert "Lightning is active in the area." in facts
    assert "disagree on convective risk" not in facts


def test_narration_view_and_format_outputs_prune_hourly() -> None:
    """Ensure bulky 48-hour arrays are pruned from prompt context and summary lines."""
    outputs = {
        "lightning_active": True,
        "hourly": {
            "time": ["2026-10-10T00:00:00Z"] * 48,
            "wave_height": [1.5] * 48,
            "wind_speed": [12.0] * 48,
        },
        "lightning_source_agreement": "agree",
    }

    # narration_view used for LLM prompt facts block
    cleaned = reporting.narration_view(outputs)
    assert "hourly" not in cleaned
    assert "lightning_active" in cleaned
    assert "lightning_source_agreement" in cleaned

    # _format_outputs used for AssembledResponse summary_lines
    fmt = reporting._format_outputs(outputs)
    assert "hourly" not in fmt
    assert "lightning_active=True" in fmt


def test_facts_paragraph_narrates_active_incois_hazard_warnings_w4() -> None:
    """Verify W4: facts_paragraph narrates active INCOIS ocean state hazard warnings (HWA/SSA)."""
    weather_out = {
        "lightning_active": False,
        "cyclone_alert": None,
        "incois_hazard": {
            "region": "kochi",
            "active_warnings": [
                {
                    "hazard_type": "high_wave",
                    "district": "Ernakulam",
                    "state": "Kerala",
                    "message": "High waves in the range of 3.0 - 3.5 meters forecasted along the coast",
                },
                {
                    "hazard_type": "swell_surge",
                    "district": "Alappuzha",
                    "state": "Kerala",
                    "message": "Swell surge warning",
                },
            ],
            "warning_count": 2,
            "source_used": "incois_hazard_osf",
        },
    }

    results = [
        AgentResult(
            agent_name="weather_intelligence",
            query_id="q1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs=weather_out,
            source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
            confidence=Confidence(score="HIGH", rationale="test"),
        )
    ]

    verdict = {"go_no_go": "NO_GO", "reason": "High waves", "readings": {}}
    facts = reporting.facts_paragraph(verdict, results, user_location={"place_name": "kochi"})

    assert "INCOIS ocean state warning in force:" in facts
    assert "Ernakulam (High Wave)" in facts
    assert "Alappuzha (Swell Surge)" in facts
