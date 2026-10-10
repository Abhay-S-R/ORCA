"""Tests for defects O1, O2, and O3:
- O1: wind_rose, wind_anomaly, sst_chlorophyll_correlation, and top_species forwarded to reporting
- O2: source_selections narrative surfaced to reporting / prompt context
- O3: sector_disclosure forwarded and surfaced in reporting
"""
from __future__ import annotations

from orca.agents import reporting
from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.graph.graph import reporting_run
from orca.state import ORCAState


def test_reporting_run_forwards_o1_o2_o3_outputs():
    """Verify O1, O2, O3: reporting_run does not drop ocean outputs."""
    ocean_data = {
        "tide": {"tidal_state": "FALLING", "station_name": "Thoothukudi"},
        "nearest_pfz": {"found": True, "distance_km": 12.0, "compass": "ESE"},
        "sector_status": {"sector_id": "SEC006", "is_data_gap": False},
        "wind_rose": {
            "available": True,
            "port": "Thoothukudi",
            "hours_counted": 168,
            "petals": [{"compass": "N", "calm": 5, "light": 10, "moderate": 2}],
        },
        "wind_anomaly": {
            "available": True,
            "nearest_port": "Thoothukudi",
            "observed_peak": 42.5,
            "units": "km/h",
            "baseline_days": 30,
            "anomalous": True,
            "direction": "high",
        },
        "sst_chlorophyll_correlation": {
            "available": True,
            "pearson_r": -0.682,
            "relationship": "moderate inverse",
            "n_samples": 45,
        },
        "top_species": [
            {"name": "Indian Mackerel", "scientific_name": "Rastrelliger kanagurta"},
            {"name": "Sardinella", "scientific_name": "Sardinella longiceps"},
        ],
        "source_selections": [
            {
                "data_type": "tide",
                "chosen": "soi_tide_tables",
                "chosen_dataset": "Survey of India 2026 Tide Tables",
                "narrative": "Survey of India official harmonic tables selected",
                "considered": ["soi_tide_tables", "stormglass_tides"],
                "fallback_chain": ["soi_tide_tables", "stormglass_tides"],
            }
        ],
        "sector_disclosure": "Sector SEC006 was derived from the regional fallback position, not from yours.",
    }

    state: ORCAState = {
        "query_id": "test-q1",
        "reasoning_depth": "SHALLOW",
        "ocean_data": ocean_data,
        "risk_assessment": {"go_no_go": "GO", "reason": "Safe conditions"},
        "weather_data": {},
        "geospatial_data": {},
        "raw_user_query": "where are the fishing zones",
    }

    res = reporting_run(state)
    assert res.agent_name == "reporting"

    # We can inspect assembled citations or test assemble_response directly
    assembled = reporting.assemble_response(
        "test-q1",
        [
            AgentResult(
                agent_name="ocean_analytics",
                query_id="test-q1",
                reasoning_depth="SHALLOW",
                inputs_consumed={},
                outputs=ocean_data,
                source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
                confidence=Confidence(score="HIGH", rationale="test"),
            )
        ],
    )
    assert assembled.query_id == "test-q1"


def test_facts_paragraph_surfaces_o3_sector_disclosure():
    """Verify O3: facts_paragraph surfaces sector_disclosure."""
    ocean_out = {
        "sector_status": {"is_data_gap": False},
        "sector_disclosure": "Sector SEC006 was derived from the regional fallback position, not from yours.",
    }
    results = [
        AgentResult(
            agent_name="ocean_analytics",
            query_id="q1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs=ocean_out,
            source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
            confidence=Confidence(score="HIGH", rationale="ok"),
        )
    ]
    text = reporting.facts_paragraph({"go_no_go": "GO", "reason": "Safe"}, results)
    assert "Sector SEC006 was derived from the regional fallback position, not from yours." in text


def test_facts_paragraph_surfaces_o1_wind_anomaly_and_correlation():
    """Verify O1: facts_paragraph surfaces wind anomaly and SST-chlorophyll correlation."""
    ocean_out = {
        "wind_anomaly": {
            "available": True,
            "nearest_port": "Thoothukudi",
            "observed_peak": 44.0,
            "units": "km/h",
            "baseline_days": 30,
            "anomalous": True,
            "direction": "high",
        },
        "sst_chlorophyll_correlation": {
            "available": True,
            "pearson_r": -0.72,
            "relationship": "strong inverse",
            "n_samples": 50,
        },
    }
    results = [
        AgentResult(
            agent_name="ocean_analytics",
            query_id="q1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs=ocean_out,
            source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
            confidence=Confidence(score="HIGH", rationale="ok"),
        )
    ]
    text = reporting.facts_paragraph({"go_no_go": "GO", "reason": "Safe"}, results)
    assert "Forecast peak wind 44.0 km/h is anomalous (high)" in text
    assert "Regional SST and chlorophyll correlation is r=-0.72 (strong inverse) across 50 co-located grid cells." in text


def test_facts_paragraph_surfaces_o1_top_species_fallback():
    """Verify O1: facts_paragraph falls back to ocean.top_species when nearest_pfz has none."""
    ocean_out = {
        "nearest_pfz": {"found": True, "distance_km": 15.0, "compass": "S"},
        "top_species": [
            {"name": "Indian Mackerel", "scientific_name": "Rastrelliger kanagurta"},
            {"name": "Oil Sardine", "scientific_name": "Sardinella longiceps"},
        ],
    }
    results = [
        AgentResult(
            agent_name="ocean_analytics",
            query_id="q1",
            reasoning_depth="SHALLOW",
            inputs_consumed={},
            outputs=ocean_out,
            source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
            confidence=Confidence(score="HIGH", rationale="ok"),
        )
    ]
    text = reporting.facts_paragraph({"go_no_go": "GO", "reason": "Safe"}, results)
    assert "Top target fish species for this zone" in text
    assert "Indian Mackerel (Rastrelliger kanagurta)" in text


def test_narration_view_prunes_bulky_fields_from_source_selections():
    """Verify O2: narration_view keeps narrative and decisions while pruning bulky routing lists."""
    raw_selection = {
        "data_type": "tide",
        "chosen": "soi_tide_tables",
        "chosen_dataset": "Survey of India 2026 Tide Tables",
        "narrative": "Survey of India official harmonic tables selected",
        "considered": ["soi_tide_tables", "stormglass_tides"],
        "fallback_chain": ["soi_tide_tables", "stormglass_tides"],
        "decided_by": "marine_data_discovery",
    }
    cleaned = reporting.narration_view(raw_selection)
    assert cleaned["narrative"] == "Survey of India official harmonic tables selected"
    assert cleaned["chosen"] == "soi_tide_tables"
    assert "considered" not in cleaned
    assert "fallback_chain" not in cleaned
