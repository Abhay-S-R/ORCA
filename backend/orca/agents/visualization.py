"""Agent 8 — Visualization (Architecture §11, plan §5.9). Zero LLM calls,
zero raw-dataset reasoning (Ground Rule 2) — every function here shapes
something a specialist agent (or Agent 6's own map helper) already
computed into the frozen MapLayer/ChartSpec envelope (orca/contracts.py).
It never fetches, never scores, never decides GO/CAUTION/NO_GO.

Checkpoint scope (Phase 2 D3, reordered ahead of the tile pyramid per team
sign-off): PointMarker/Polygon/Heatmap map layers, one TimeSeries chart, and
the mandatory validate_payload gate. Polyline (routes), Raster (WMS tiles),
DistressMarker and SentinelWatch layer types, and BarChart/RadarChart/
WindRose chart types are real Architecture §11 types this module's Literal
already allows — just not populated by any generator yet. Next checkpoint.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from shapely.geometry import shape
from shapely.validation import explain_validity

from orca.agents import geospatial
from orca.contracts import (
    AgentResult,
    ChartSpec,
    Confidence,
    MapLayer,
    SourceProvenance,
    StyleHints,
    coerce_reasoning_depth,
)
from orca.state import ORCAState

# §4.7 layer-lifecycle budget: over this many features, a layer must be
# simplified/tiled before shipping, never sent as-is. The tile pyramid is
# what "simplify/tile" means for a Heatmap/Raster this size — until that
# exists (next checkpoint), over-budget is a validate_payload rejection,
# not a lossy on-the-fly reshape invented here.
_MAX_FEATURES = 5000

# Generous plausibility box around the pilot bbox — wide enough that a real
# boundary or heatmap point never trips it, tight enough to catch a genuine
# sign-flip or wrong-hemisphere coordinate (validate_payload's job, not a
# second geofence check).
_PLAUSIBLE_LON = (60.0, 100.0)
_PLAUSIBLE_LAT = (-10.0, 30.0)

_VALID_LAYER_TYPES = {
    "PointMarker", "Polygon", "Polyline", "Heatmap", "Raster",
    "DistressMarker", "SentinelWatch",
}
_VALID_CHART_TYPES = {"TimeSeries", "BarChart", "RadarChart", "WindRose"}


# --- generate_map_layers ------------------------------------------------------

def generate_map_layers(state: ORCAState) -> list[MapLayer]:
    """PointMarker (user position), Polygon (boundaries), Heatmap
    (bathymetry) — the checkpoint's three layer types, each wrapping data a
    specialist already computed (Agent 6's own generate_map_layers/
    bathymetry_heatmap_points)."""
    location = state.get("user_location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    raw = geospatial.generate_map_layers(user_lat=lat, user_lon=lon)
    boundary_provenance = (SourceProvenance(
        dataset="Marine Regions VLIZ EEZ + UNEP-WCMC WDPA (via Agent 6)",
        acquisition_timestamp=geospatial.boundary_data_vintage(), freshness_minutes=0,
    ),)

    layers = [MapLayer(
        layer_id="boundaries", layer_type="Polygon", geojson=raw["boundaries"], tile_url=None,
        bounds=geospatial.PILOT_BBOX_WSEN, timestamps=None, forecast_frames=None,
        style_hints=StyleHints(
            palette="boundary-amber", opacity=0.35, min_zoom=4, max_zoom=14,
            simplify_tolerance=geospatial._MAP_SIMPLIFY_TOLERANCE_DEG,
        ),
        weight="light", persona_visibility=(), source_provenance=boundary_provenance,
        result_refs=("geospatial",),
    )]

    if "user_position" in raw:
        layers.append(MapLayer(
            layer_id="user_position", layer_type="PointMarker", geojson=raw["user_position"], tile_url=None,
            bounds=geospatial.PILOT_BBOX_WSEN, timestamps=None, forecast_frames=None,
            style_hints=StyleHints(palette="vessel-blue", opacity=1.0, min_zoom=0, max_zoom=18),
            weight="light", persona_visibility=(), source_provenance=boundary_provenance,
            result_refs=("geospatial",),
        ))

    depth_points = geospatial.bathymetry_heatmap_points()
    if depth_points:
        heatmap_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
                    "properties": {"depth_m": p["depth_m"]},
                }
                for p in depth_points
            ],
        }
        layers.append(MapLayer(
            layer_id="bathymetry_heatmap", layer_type="Heatmap", geojson=heatmap_geojson, tile_url=None,
            bounds=geospatial.PILOT_BBOX_WSEN, timestamps=None, forecast_frames=None,
            style_hints=StyleHints(palette="bathymetry-blue", opacity=0.6, min_zoom=4, max_zoom=12),
            weight="heavy", persona_visibility=(),
            source_provenance=(SourceProvenance(dataset="GEBCO 2026 (via Agent 6)", acquisition_timestamp="", freshness_minutes=0),),
            result_refs=("geospatial",),
        ))

    return layers


# --- generate_chart_specs -----------------------------------------------------

def generate_chart_specs(state: ORCAState) -> list[ChartSpec]:
    """TimeSeries wave-height/wind-speed chart from Agent 4's hourly
    forecast — the checkpoint's one chart type. BarChart/RadarChart/
    WindRose need data this codebase doesn't compute yet (catch stats,
    multi-parameter safety score, wind direction distribution); adding
    those here now would mean fabricating input, not shaping real output."""
    weather = state.get("weather_data") or {}
    hourly = weather.get("hourly") or []
    if not hourly:
        return []

    series = tuple(
        {"time": h.get("time"), "wave_height_m": h.get("wave_height"), "wind_speed_ms": h.get("wind_speed_10m")}
        for h in hourly
    )
    provenance = (SourceProvenance(
        dataset=weather.get("dataset", "Open-Meteo Marine API + Forecast API"),
        acquisition_timestamp=weather.get("acquisition_timestamp", ""),
        freshness_minutes=weather.get("freshness_minutes", 0),
    ),)
    return [ChartSpec(
        chart_id="wave_wind_timeseries", chart_type="TimeSeries", series=series,
        x_key="time", y_keys=("wave_height_m", "wind_speed_ms"), unit="m | m/s",
        persona_visibility=(), source_provenance=provenance,
    )]


# --- validate_payload (mandatory) ---------------------------------------------

def _geometry_valid_and_plausible(geojson: dict[str, Any] | None) -> str | None:
    """None if OK, else the rejection reason."""
    if not geojson:
        return None
    for feat in geojson.get("features", []):
        geom = feat.get("geometry")
        if not geom:
            continue
        g = shape(geom)
        if not g.is_valid:
            return f"invalid/mis-wound geometry: {explain_validity(g)}"
        minx, miny, maxx, maxy = g.bounds
        if not (_PLAUSIBLE_LON[0] <= minx and maxx <= _PLAUSIBLE_LON[1] and _PLAUSIBLE_LAT[0] <= miny and maxy <= _PLAUSIBLE_LAT[1]):
            return f"coordinates outside plausible India-region bounds: {g.bounds}"
    return None


def _timestamps_ok(timestamps: tuple[str, ...] | None) -> bool:
    if not timestamps:
        return True
    parsed = []
    for t in timestamps:
        try:
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
        except ValueError:
            return False
        if dt.tzinfo is None:
            return False
        parsed.append(dt)
    return parsed == sorted(parsed)


def _reject_layer(layer: MapLayer) -> str | None:
    if layer.layer_type not in _VALID_LAYER_TYPES:
        return f"unknown layer_type {layer.layer_type!r}"
    if not layer.source_provenance:
        return "empty source_provenance"
    count = len((layer.geojson or {}).get("features", []))
    if count > _MAX_FEATURES:
        return f"{count} features exceeds §4.7 budget of {_MAX_FEATURES}"
    geometry_problem = _geometry_valid_and_plausible(layer.geojson)
    if geometry_problem:
        return geometry_problem
    if not _timestamps_ok(layer.timestamps):
        return "timestamps not tz-aware/monotonic"
    return None


def _reject_chart(chart: ChartSpec) -> str | None:
    if chart.chart_type not in _VALID_CHART_TYPES:
        return f"unknown chart_type {chart.chart_type!r}"
    if not chart.source_provenance:
        return "empty source_provenance"
    if not chart.series:
        return "empty series"
    needed = (chart.x_key, *chart.y_keys)
    if any(k not in row for row in chart.series for k in needed):
        return "series rows missing a declared x_key/y_key"
    return None


def validate_payload(
    layers: list[MapLayer], charts: list[ChartSpec]
) -> tuple[list[MapLayer], list[ChartSpec], list[str]]:
    """Mandatory gate (plan §5.9) between "Agent 8 built this" and "a client
    receives this". Anything that fails ANY check is dropped and logged —
    the response degrades (fewer layers/charts), it never ships a malformed
    one. Returns (kept_layers, kept_charts, dropped_reasons)."""
    kept_layers, kept_charts, dropped = [], [], []

    for layer in layers:
        reason = _reject_layer(layer)
        (dropped.append(f"layer {layer.layer_id}: {reason}") if reason else kept_layers.append(layer))

    for chart in charts:
        reason = _reject_chart(chart)
        (dropped.append(f"chart {chart.chart_id}: {reason}") if reason else kept_charts.append(chart))

    return kept_layers, kept_charts, dropped


# --- Agent entry point -------------------------------------------------------

def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Reads weather_data/geospatial_data/
    user_location from state — never fetches, never LLM-calls."""
    layers = generate_map_layers(state)
    charts = generate_chart_specs(state)
    kept_layers, kept_charts, dropped = validate_payload(layers, charts)

    if not kept_layers and not kept_charts:
        score, rationale = "LOW_DATA", "No layer or chart survived validate_payload"
    elif dropped:
        score, rationale = "MEDIUM", f"{len(kept_layers)} layer(s)/{len(kept_charts)} chart(s) kept; {len(dropped)} dropped: {dropped}"
    else:
        score, rationale = "HIGH", f"{len(kept_layers)} layer(s)/{len(kept_charts)} chart(s), all validated clean"

    return AgentResult(
        agent_name="visualization",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={
            "has_weather_data": bool(state.get("weather_data")),
            "has_geospatial_data": bool(state.get("geospatial_data")),
        },
        outputs={"map_layers": kept_layers, "chart_specs": kept_charts, "validation_dropped": dropped},
        source_provenance=SourceProvenance(
            dataset="ORCA visualization (Agent 8 — transforms specialist outputs, no LLM/no raw-dataset reasoning)",
            acquisition_timestamp="", freshness_minutes=0,
        ),
        confidence=Confidence(score=score, rationale=rationale),  # type: ignore[arg-type]
    )


if __name__ == "__main__":
    demo_state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "demo", "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 8.80, "lon": 78.14},
        "weather_data": {
            "hourly": [
                {"time": "2026-09-02T00:00:00Z", "wave_height": 1.2, "wind_speed_10m": 5.0},
                {"time": "2026-09-02T01:00:00Z", "wave_height": 1.3, "wind_speed_10m": 6.0},
            ],
            "dataset": "Open-Meteo Marine API + Forecast API", "acquisition_timestamp": "2026-09-02T00:00:00Z",
        },
    }
    result = run(demo_state)
    assert result.agent_name == "visualization"
    layer_types = {layer.layer_type for layer in result.outputs["map_layers"]}
    assert {"Polygon", "PointMarker", "Heatmap"} <= layer_types, layer_types
    assert result.outputs["chart_specs"][0].chart_type == "TimeSeries"
    assert not result.outputs["validation_dropped"], result.outputs["validation_dropped"]
    print("visualization self-check OK:", layer_types, len(result.outputs["chart_specs"]), "chart(s)")
