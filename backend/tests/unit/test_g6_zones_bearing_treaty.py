"""Test G6: ZONES_TO_AVOID wiring, spatial_query_zones, bearing, and treaty metadata."""
from __future__ import annotations

from orca.agents import reporting
from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.graph.graph import geospatial_run


def test_geospatial_run_outputs_bearing_treaty_and_nearby_zones() -> None:
    """G6: geospatial_run includes bearing_deg, treaty, treaty_date, and nearby_zones in outputs."""
    state = {
        "query_id": "test_g6_1",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 9.28, "lon": 79.31, "place_name": "Gulf of Mannar"},
    }
    result = geospatial_run(state)  # type: ignore[arg-type]
    outputs = result.outputs

    assert "imbl_bearing_deg" in outputs
    assert isinstance(outputs["imbl_bearing_deg"], float)
    assert 0.0 <= outputs["imbl_bearing_deg"] < 360.0

    assert "imbl_treaty" in outputs
    assert outputs["imbl_treaty"] is not None
    assert "Sri Lanka" in outputs["imbl_treaty"]

    assert "imbl_treaty_date" in outputs
    assert outputs["imbl_treaty_date"] is not None
    assert "1974" in outputs["imbl_treaty_date"]

    assert "nearby_zones" in outputs
    assert isinstance(outputs["nearby_zones"], list)
    assert len(outputs["nearby_zones"]) > 0

    assert "nearby_zone_names" in outputs
    assert isinstance(outputs["nearby_zone_names"], list)
    assert any("Sri Lanka" in name or "Mannar" in name for name in outputs["nearby_zone_names"])


def test_geospatial_run_at_malpe_returns_eez_zone() -> None:
    """G6: At Malpe, spatial_query_zones returns the EEZ zone."""
    state = {
        "query_id": "test_g6_malpe",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 13.35, "lon": 74.66, "place_name": "Malpe"},
    }
    result = geospatial_run(state)  # type: ignore[arg-type]
    outputs = result.outputs

    assert "Indian Exclusive Economic Zone" in outputs["nearby_zone_names"]


def test_reporting_narrates_bearing_and_nearby_zones() -> None:
    """G6: facts_paragraph includes bearing and nearby avoidance zones when present."""
    verdict = {"go_no_go": "GO", "reason": "Safe conditions"}
    geo_result = AgentResult(
        agent_name="geospatial",
        query_id="test_g6_narration",
        reasoning_depth="SHALLOW",
        inputs_consumed={},
        outputs={
            "imbl_distance_nm": 12.6,
            "imbl_bearing_deg": 82.0,
            "imbl_boundary_name": "Sri Lanka - India",
            "imbl_treaty": "1974 Boundary Agreement",
            "nearby_zones": [
                {"name": "Sri Lankan Exclusive Economic Zone", "designation": "Sri Lanka EEZ"},
                {"name": "Adam's Bridge NP", "designation": "Marine National Park"},
            ],
            "mpa_violation": False,
        },
        source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
        confidence=Confidence(score="HIGH", rationale="test"),
    )

    text = reporting.facts_paragraph(verdict, [geo_result])
    assert "12.6 nm" in text
    assert "bearing 82°" in text
    assert "Sri Lankan Exclusive Economic Zone" in text or "Adam's Bridge NP" in text
