"""G5 verification: IMBL distance and maritime boundaries cite the treaty lines vintage (2026-09-16),
and Agent 3 decides Marine Regions VLIZ for 'boundary', not UNEP-WCMC WDPA (protected areas).

Defect G5 in docs/ORCA_Agent_Trace_and_Audit.md:
The IMBL number cites the boundary vintage 2026-08-30 (the polygon files), but it comes
from the treaty-lines file (timestamp 2026-09-16). Agent 3 decides "boundary" = unep_wcmc_wdpa
(the protected-area file) while the IMBL number is from Marine Regions: the trace line
would say "boundaries from UNEP-WCMC WDPA" for a Marine Regions number.
"""

from orca.agents import geospatial
from orca.agents.discovery import (
    select_source_with_fallback,
)
from orca.graph.graph import geospatial_run, marine_data_discovery_run


def test_boundary_line_vintage_matches_treaty_lines_timestamp():
    vintage = geospatial.boundary_line_vintage()
    assert vintage == "2026-09-16T19:19:33.460Z"


def test_nearest_boundary_line_carries_treaty_lines_vintage():
    line = geospatial.nearest_boundary_line(9.30, 79.45)
    assert line is not None
    assert line.get("vintage") == "2026-09-16T19:19:33.460Z"
    assert line.get("acquisition_timestamp") == "2026-09-16T19:19:33.460Z"
    assert line["source_file"] == "india_maritime_boundary_lines.geojson"


def test_geospatial_run_cites_treaty_lines_vintage_for_imbl():
    state = {
        "query_id": "test-g5",
        "user_location": {"lat": 9.30, "lon": 79.45, "place_source": "gazetteer"},
    }
    result = geospatial_run(state)
    assert result.outputs["imbl_vintage"] == "2026-09-16T19:19:33.460Z"
    assert result.source_provenance.acquisition_timestamp == "2026-09-16T19:19:33.460Z"


def test_agent3_decides_marine_regions_for_boundary():
    decision = select_source_with_fallback("boundary")
    assert decision is not None
    assert decision.chosen.id == "marineregions_eez"
    assert "Marine Regions" in decision.chosen.dataset


def test_agent3_decides_unep_wcmc_for_mpa_only():
    decision = select_source_with_fallback("mpa")
    assert decision is not None
    assert decision.chosen.id == "unep_wcmc_wdpa"
    assert "UNEP-WCMC" in decision.chosen.dataset


def test_trace_line_says_boundaries_from_marine_regions():
    state = {
        "query_id": "test-g5-trace",
        "user_location": {"lat": 9.0, "lon": 79.0, "place_source": "gazetteer"},
        "planned_intents": ["SAFETY"],
        "user_query": "is it safe to fish near rameshwaram",
    }
    result = marine_data_discovery_run(state)
    trace_line = result.outputs["trace_line"]
    assert "boundaries from Marine Regions VLIZ EEZ / IMBL dataset" in trace_line
    assert "boundaries from UNEP-WCMC WDPA" not in trace_line
