"""Agent 8 (Visualization) — checkpoint scope: point/polygon/heatmap map
layers, one TimeSeries chart, and validate_payload's mandatory reject path.
"""
from orca.agents.visualization import (
    generate_chart_specs,
    generate_map_layers,
    run,
    validate_payload,
)
from orca.contracts import ChartSpec, MapLayer, SourceProvenance, StyleHints
from orca.state import ORCAState

# Gulf of Mannar / Thoothukudi — same pilot-region point test_geospatial.py uses.
LOCATION = {"lat": 8.70, "lon": 78.50}

_HOURLY = [
    {"time": "2026-09-02T00:00:00Z", "wave_height": 1.2, "wind_speed_10m": 5.0},
    {"time": "2026-09-02T01:00:00Z", "wave_height": 1.3, "wind_speed_10m": 6.0},
]


def _state(**overrides) -> ORCAState:
    base: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "test", "reasoning_depth": "SHALLOW", "user_location": LOCATION,
        "weather_data": {
            "hourly": _HOURLY, "dataset": "Open-Meteo Marine API + Forecast API",
            "acquisition_timestamp": "2026-09-02T00:00:00Z",
        },
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def test_generate_map_layers_returns_point_polygon_and_heatmap() -> None:
    layers = generate_map_layers(_state())
    types = {layer.layer_type for layer in layers}
    assert {"PointMarker", "Polygon", "Heatmap"} <= types


def test_boundary_layer_uses_the_pilot_bbox_and_cites_a_source() -> None:
    from orca.agents.geospatial import PILOT_BBOX_WSEN

    layers = generate_map_layers(_state())
    boundaries = next(l for l in layers if l.layer_id == "boundaries")
    assert boundaries.bounds == PILOT_BBOX_WSEN
    assert boundaries.source_provenance
    assert boundaries.result_refs == ("geospatial",)


def test_generate_chart_specs_builds_a_timeseries_from_hourly_weather() -> None:
    charts = generate_chart_specs(_state())
    assert len(charts) == 1
    assert charts[0].chart_type == "TimeSeries"
    assert len(charts[0].series) == len(_HOURLY)


def test_generate_chart_specs_empty_when_no_weather_data() -> None:
    assert generate_chart_specs(_state(weather_data={})) == []


_WIND_ROSE = {
    "available": True, "port": "Thoothukudi", "hours_counted": 4,
    "bins": ["calm_0_5", "moderate_5_10", "strong_10_plus"],
    "petals": [{"compass": "N", "calm_0_5": 2, "moderate_5_10": 1, "strong_10_plus": 0}],
    "dataset": "Open-Meteo Forecast API (cached, port=Thoothukudi)",
}


def test_generate_chart_specs_builds_a_wind_rose_from_ocean_analytics_data() -> None:
    charts = generate_chart_specs(_state(ocean_data={"wind_rose": _WIND_ROSE}))
    rose = next(c for c in charts if c.chart_type == "WindRose")
    assert rose.series == tuple(_WIND_ROSE["petals"])
    assert rose.x_key == "compass"
    assert rose.y_keys == tuple(_WIND_ROSE["bins"])
    # A practical operating chart, kept off the researcher surface until a
    # real climatological (not forecast-window) source backs it.
    assert rose.persona_visibility == ("fisherman", "commercial_navigator", "coastal_authority")


def test_generate_chart_specs_skips_wind_rose_when_unavailable() -> None:
    charts = generate_chart_specs(_state(ocean_data={"wind_rose": {"available": False}}))
    assert not any(c.chart_type == "WindRose" for c in charts)


def test_bathymetry_raster_layer_restricts_persona_visibility() -> None:
    layers = generate_map_layers(_state())
    bathymetry = [l for l in layers if l.layer_id == "bathymetry"]
    if not bathymetry:  # only present once scripts/generate_tiles.py has run on this checkout
        return
    assert bathymetry[0].persona_visibility == ("commercial_navigator", "researcher", "coastal_authority")


def test_validate_payload_drops_an_unknown_layer_type_but_keeps_the_rest() -> None:
    good = MapLayer(
        layer_id="ok", layer_type="PointMarker", geojson=None, tile_url=None,
        bounds=(77.0, 7.0, 81.0, 11.0), timestamps=None, forecast_frames=None,
        style_hints=StyleHints(palette="x", opacity=1.0, min_zoom=0, max_zoom=10),
        weight="light", persona_visibility=(), source_provenance=(SourceProvenance("d", "", 0),),
        result_refs=(),
    )
    bad = MapLayer(
        layer_id="bad", layer_type="NotARealType", geojson=None, tile_url=None,  # type: ignore[arg-type]
        bounds=(0, 0, 0, 0), timestamps=None, forecast_frames=None,
        style_hints=StyleHints(palette="x", opacity=1.0, min_zoom=0, max_zoom=10),
        weight="light", persona_visibility=(), source_provenance=(SourceProvenance("d", "", 0),),
        result_refs=(),
    )
    kept_layers, _, dropped = validate_payload([good, bad], [])
    assert kept_layers == [good]
    assert dropped == ["layer bad: unknown layer_type 'NotARealType'"]


def test_validate_payload_drops_a_layer_with_no_source_provenance() -> None:
    layer = MapLayer(
        layer_id="no_source", layer_type="PointMarker", geojson=None, tile_url=None,
        bounds=(77.0, 7.0, 81.0, 11.0), timestamps=None, forecast_frames=None,
        style_hints=StyleHints(palette="x", opacity=1.0, min_zoom=0, max_zoom=10),
        weight="light", persona_visibility=(), source_provenance=(), result_refs=(),
    )
    kept_layers, _, dropped = validate_payload([layer], [])
    assert kept_layers == []
    assert "empty source_provenance" in dropped[0]


def test_validate_payload_drops_a_chart_missing_a_declared_y_key() -> None:
    chart = ChartSpec(
        chart_id="broken", chart_type="TimeSeries", series=({"time": "t"},),
        x_key="time", y_keys=("wave_height_m",), unit="m",
        persona_visibility=(), source_provenance=(SourceProvenance("d", "", 0),),
    )
    _, kept_charts, dropped = validate_payload([], [chart])
    assert kept_charts == []
    assert "missing a declared x_key/y_key" in dropped[0]


def test_run_produces_a_clean_agent_result_end_to_end() -> None:
    result = run(_state())
    assert result.agent_name == "visualization"
    assert not result.outputs["validation_dropped"]
    assert result.confidence.score == "HIGH"
    assert {layer.layer_type for layer in result.outputs["map_layers"]} >= {"Polygon", "PointMarker", "Heatmap"}
