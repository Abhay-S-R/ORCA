"""Agent 8 — Visualization (Architecture §11, plan §5.9). Zero LLM calls,
zero raw-dataset reasoning (Ground Rule 2) — every function here shapes
something a specialist agent (or Agent 6's own map helper) already
computed into the frozen MapLayer/ChartSpec envelope (orca/contracts.py).
It never fetches, never scores, never decides GO/CAUTION/NO_GO.


Checkpoint scope (Phase 2 D3): PointMarker/Polygon/Heatmap/Raster map
layers (including forecast_frames tile pyramids), TimeSeries + WindRose
charts, persona_visibility on layers/charts, and the mandatory
validate_payload gate. Polyline (routes), DistressMarker and SentinelWatch
layer types, and BarChart/RadarChart chart types are real Architecture §11
types this module's Literal already allows — just not populated by any
generator yet (no route-planning or catch-statistics agent output exists
to shape). Next checkpoint.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from shapely.geometry import shape
from shapely.validation import explain_validity

from orca.agents import geospatial
from orca.contracts import (
    AgentResult,
    ChartSpec,
    ColorRamp,
    Confidence,
    MapLayer,
    SourceProvenance,
    StyleHints,
    coerce_reasoning_depth,
)
from orca.state import ORCAState

# scripts/generate_tiles.py writes {layer_id}/meta.json under here — same
# data/ root geospatial.py's own DATA_ROOT points at (gitignored; a fresh
# checkout has none until that script has been run once).
_TILES_ROOT = geospatial.DATA_ROOT / "tier1" / "tiles"

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

def _raster_layers() -> list[MapLayer]:
    """Raster map layers from pre-built tile pyramids (orca/tiles.py). Reads
    only each layer's meta.json sidecar — never rasterio, never the source
    NetCDF — so this stays cheap enough to call on every request. No tiles
    generated yet on this checkout (scripts/generate_tiles.py not run) means
    an empty list, not an error, matching every other generator's
    degrade-gracefully posture in this module."""
    layers: list[MapLayer] = []
    if not _TILES_ROOT.is_dir():
        return layers
    for layer_dir in sorted(_TILES_ROOT.iterdir()):
        meta_path = layer_dir / "meta.json"
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text())
        ramp = meta["color_ramp"]
        # `timestamps` present (scripts/generate_tiles.py's
        # generate_forecast_tiles output) means this is a forecast_frames
        # layer (plan §5.10 Day 12) — the same Raster type, just carrying a
        # frame sequence instead of one static pyramid.
        frame_timestamps = meta.get("timestamps")
        # The full-precision bathymetry grid is a technical planning layer —
        # the fisherman surface already carries the same depth fact via the
        # bathymetry_heatmap (coarse points) and the Sounding readout's
        # shallow-hazard flag, so this raster doesn't need to compete for
        # their screen space. Forecast/other layers stay open to everyone
        # (empty tuple): safety-relevant data is never persona-gated.
        visibility = ("commercial_navigator", "researcher", "coastal_authority") if meta["layer_id"] == "bathymetry" else ()
        layers.append(MapLayer(
            layer_id=meta["layer_id"], layer_type="Raster", geojson=None,
            tile_url=meta["tile_url_template"], bounds=tuple(meta["bounds"]),
            timestamps=None,
            forecast_frames=tuple(frame_timestamps) if frame_timestamps else None,
            style_hints=StyleHints(
                palette=ramp["palette"], opacity=0.85,
                min_zoom=meta["min_zoom"], max_zoom=meta["max_zoom"],
                color_ramp=ColorRamp(**ramp),
            ),
            weight="heavy", persona_visibility=visibility,
            source_provenance=(SourceProvenance(
                dataset=f"{meta['layer_id']} raster tile pyramid (via orca/tiles.py)",
                acquisition_timestamp="", freshness_minutes=0,
            ),),
            result_refs=("geospatial",),
        ))
    return layers


def generate_map_layers(state: ORCAState) -> list[MapLayer]:
    """PointMarker (user position), Polygon (boundaries), Heatmap
    (bathymetry), Raster (pre-built tile pyramids) — each wrapping data a
    specialist already computed (Agent 6's own generate_map_layers/
    bathymetry_heatmap_points, or orca/tiles.py's offline pyramid build)."""
    location = state.get("user_location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    # The initial payload is built for the whole-basin view (z<=7's coarsest
    # bucket) — MapView re-requests this same endpoint at the finer buckets
    # as the user zooms in (plan §5.10 Day 10), never simplifying in the
    # browser itself.
    zoom = 7
    raw = geospatial.generate_map_layers(user_lat=lat, user_lon=lon, zoom=zoom)
    boundary_provenance = (SourceProvenance(
        dataset="Marine Regions VLIZ EEZ + UNEP-WCMC WDPA (via Agent 6)",
        acquisition_timestamp=geospatial.boundary_data_vintage(), freshness_minutes=0,
    ),)

    layers = [MapLayer(
        layer_id="boundaries", layer_type="Polygon", geojson=raw["boundaries"], tile_url=None,
        bounds=geospatial.PILOT_BBOX_WSEN, timestamps=None, forecast_frames=None,
        style_hints=StyleHints(
            palette="boundary-amber", opacity=0.35, min_zoom=4, max_zoom=14,
            simplify_tolerance=geospatial._simplify_tolerance_for_zoom(zoom),
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

    layers.extend(_raster_layers())
    return layers


# --- generate_chart_specs -----------------------------------------------------

def generate_chart_specs(state: ORCAState) -> list[ChartSpec]:
    """TimeSeries wave-height/wind-speed chart from Agent 4's hourly
    forecast, WindRose from Agent 5's directional wind frequency
    (`ocean_analytics.wind_rose`, already real cached Open-Meteo data — see
    `ocean_data["wind_rose"]`). BarChart/RadarChart still need data this
    codebase doesn't compute yet (catch stats, multi-parameter safety
    score); adding those now would mean fabricating input, not shaping
    real output."""
    charts: list[ChartSpec] = []

    weather = state.get("weather_data") or {}
    hourly = weather.get("hourly") or []
    if hourly:
        series = tuple(
            {"time": h.get("time"), "wave_height_m": h.get("wave_height"), "wind_speed_ms": h.get("wind_speed_10m")}
            for h in hourly
        )
        provenance = (SourceProvenance(
            dataset=weather.get("dataset", "Open-Meteo Marine API + Forecast API"),
            acquisition_timestamp=weather.get("acquisition_timestamp", ""),
            freshness_minutes=weather.get("freshness_minutes", 0),
        ),)
        charts.append(ChartSpec(
            chart_id="wave_wind_timeseries", chart_type="TimeSeries", series=series,
            x_key="time", y_keys=("wave_height_m", "wind_speed_ms"), unit="m | m/s",
            persona_visibility=(), source_provenance=provenance,
        ))

    rose = (state.get("ocean_data") or {}).get("wind_rose") or {}
    if rose.get("available"):
        charts.append(ChartSpec(
            chart_id="wind_rose", chart_type="WindRose", series=tuple(rose["petals"]),
            x_key="compass", y_keys=tuple(rose["bins"]), unit="hourly readings",
            # A practical operating chart, not a research-grade climatology
            # (§5.9's own note: "a forecast window, not a climatology") —
            # kept off the researcher surface until a real climatological
            # source backs it.
            persona_visibility=("fisherman", "commercial_navigator", "coastal_authority"),
            source_provenance=(SourceProvenance(
                dataset=rose.get("dataset", "Open-Meteo Forecast API (cached)"),
                acquisition_timestamp="", freshness_minutes=0,
            ),),
        ))

    return charts


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
        "ocean_data": {
            "wind_rose": {
                "available": True, "port": "Thoothukudi", "hours_counted": 12,
                "bins": ["calm_0_5", "moderate_5_10", "strong_10_plus"],
                "petals": [{"compass": "N", "calm_0_5": 3, "moderate_5_10": 1, "strong_10_plus": 0}],
                "dataset": "Open-Meteo Forecast API (cached, port=Thoothukudi)",
            },
        },
    }
    result = run(demo_state)
    assert result.agent_name == "visualization"
    layer_types = {layer.layer_type for layer in result.outputs["map_layers"]}
    assert {"Polygon", "PointMarker", "Heatmap"} <= layer_types, layer_types
    raster_layers = [layer for layer in result.outputs["map_layers"] if layer.layer_type == "Raster"]
    if raster_layers:  # only present once scripts/generate_tiles.py has run on this checkout
        forecast_layers = [layer for layer in raster_layers if layer.forecast_frames]
        assert all(len(layer.forecast_frames) > 1 for layer in forecast_layers)
        assert all("{time}" in layer.tile_url for layer in forecast_layers)
        bathymetry = [layer for layer in raster_layers if layer.layer_id == "bathymetry"]
        assert all(layer.persona_visibility == ("commercial_navigator", "researcher", "coastal_authority")
                   for layer in bathymetry)
    chart_types = {chart.chart_type for chart in result.outputs["chart_specs"]}
    assert {"TimeSeries", "WindRose"} <= chart_types, chart_types
    wind_rose_chart = next(c for c in result.outputs["chart_specs"] if c.chart_type == "WindRose")
    assert wind_rose_chart.persona_visibility == ("fisherman", "commercial_navigator", "coastal_authority")
    assert not result.outputs["validation_dropped"], result.outputs["validation_dropped"]
    print("visualization self-check OK:", layer_types, len(result.outputs["chart_specs"]), "chart(s)")
