"""Test G7: Depth and shallow hazard checks wired into geospatial output and reporting."""
from __future__ import annotations

import pytest
from orca.agents import geospatial, reporting
from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.graph.graph import geospatial_run


def test_geospatial_run_outputs_depth_and_shallow_hazard() -> None:
    """G7: geospatial_run includes depth_m, on_land, and shallow_hazard in outputs."""
    state = {
        "query_id": "test_g7_1",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 13.35, "lon": 74.66, "place_name": "Malpe"},
    }
    result = geospatial_run(state)  # type: ignore[arg-type]
    outputs = result.outputs

    assert "depth_m" in outputs
    assert isinstance(outputs["depth_m"], float)
    assert outputs["depth_m"] > 0
    assert outputs["on_land"] is False
    assert "shallow_hazard" in outputs
    assert isinstance(outputs["shallow_hazard"], bool)


def test_geospatial_run_on_land_reports_on_land_true() -> None:
    """G7: Points on land report on_land=True and depth_m=None."""
    state = {
        "query_id": "test_g7_land",
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 9.93, "lon": 78.12, "place_name": "Madurai"},
    }
    result = geospatial_run(state)  # type: ignore[arg-type]
    outputs = result.outputs

    assert outputs["on_land"] is True
    assert outputs["depth_m"] is None
    assert outputs["shallow_hazard"] is False


def test_reporting_narrates_shallow_hazard() -> None:
    """G7: facts_paragraph includes shallow water hazard warning when shallow_hazard is True."""
    verdict = {"go_no_go": "CAUTION", "reason": "Shallow water"}
    geo_result = AgentResult(
        agent_name="geospatial",
        query_id="test_g7_narration",
        reasoning_depth="SHALLOW",
        inputs_consumed={},
        outputs={
            "depth_m": 4.5,
            "on_land": False,
            "shallow_hazard": True,
            "imbl_distance_nm": 30.0,
            "mpa_violation": False,
        },
        source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="", freshness_minutes=0),
        confidence=Confidence(score="HIGH", rationale="test"),
    )

    text = reporting.facts_paragraph(verdict, [geo_result])
    assert "Shallow water hazard" in text
    assert "4.5 m" in text
