"""AgentResult envelope — the frozen inter-agent hand-off contract (plan §6, Day 3).

Matches Architecture §6. `persona_context` is deliberately absent: specialist
agents never learn who is asking (Ground Rule 1 — intent decides what fires,
persona decides how it's said). Only Agent 1 (ingress/egress) and Agent 9
(Reporting) ever see persona.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class SourceProvenance:
    dataset: str  # e.g. "Open-Meteo Marine API / ECMWF WAM Blend"
    acquisition_timestamp: str  # ISO 8601, UTC
    freshness_minutes: int


@dataclass(frozen=True)
class Confidence:
    # Underscore, not hyphen — matches the confidence_tier Postgres enum
    # (infra/db/001_init.sql). Postgres enums cannot contain hyphens; the
    # architecture doc writes "LOW-DATA" for readability only. LOW_DATA is
    # canonical everywhere in code.
    score: Literal["HIGH", "MEDIUM", "LOW_DATA"]
    rationale: str


@dataclass(frozen=True)
class AgentResult:
    agent_name: str
    query_id: str
    reasoning_depth: Literal["SHALLOW", "STANDARD", "DEEP"]
    inputs_consumed: dict[str, Any]
    outputs: dict[str, Any]
    source_provenance: SourceProvenance
    confidence: Confidence
    status: Literal["ok", "degraded", "failed", "skipped", "cancelled"] = "ok"
    error_detail: str | None = None


@dataclass(frozen=True)
class StyleHints:
    palette: str  # e.g. "risk-red-amber-green", "bathymetry-blue"
    opacity: float
    min_zoom: int
    max_zoom: int
    simplify_tolerance: float = 0.0  # degrees; 0.0 = not simplified (already coarse enough)


@dataclass(frozen=True)
class MapLayer:
    """Agent 8's map-layer envelope (plan §5.9, Architecture §11.1). Frozen
    output contract — D2 (`/zones`, `/trends`) and the frontend map shell
    build against this shape, so it's additive-only from here, same as
    AgentResult above."""
    layer_id: str
    layer_type: Literal[
        "PointMarker", "Polygon", "Polyline", "Heatmap", "Raster",
        "DistressMarker", "SentinelWatch",
    ]
    geojson: dict[str, Any] | None  # FeatureCollection; None for a pure tile_url layer
    tile_url: str | None  # XYZ/WMS template; None for a pure geojson layer
    bounds: tuple[float, float, float, float]  # (west, south, east, north)
    timestamps: tuple[str, ...] | None  # ISO 8601 UTC, one per geojson snapshot
    forecast_frames: tuple[str, ...] | None  # ISO 8601 UTC, tile/frame sequence (Phase 2 later slice)
    style_hints: StyleHints
    weight: Literal["heavy", "light"]  # §4.7 layer-lifecycle budget: heavy layers evict first
    persona_visibility: tuple[str, ...]  # e.g. ("fisherman", "authority"); empty = all personas
    source_provenance: tuple[SourceProvenance, ...]
    result_refs: tuple[str, ...]  # agent_name(s) this layer was derived from — Agent 9 citation hook


@dataclass(frozen=True)
class ChartSpec:
    """Agent 8's chart envelope (plan §5.9, Architecture §11.2). `series` is
    Recharts-ready rows (one dict per x value) so the frontend never
    reshapes data — TimeSeries -> AreaChart/LineChart, BarChart -> BarChart,
    RadarChart -> RadarChart, WindRose -> RadialBarChart."""
    chart_id: str
    chart_type: Literal["TimeSeries", "BarChart", "RadarChart", "WindRose"]
    series: tuple[dict[str, Any], ...]
    x_key: str
    y_keys: tuple[str, ...]
    unit: str
    persona_visibility: tuple[str, ...]
    source_provenance: tuple[SourceProvenance, ...]


_VALID_REASONING_DEPTHS = ("SHALLOW", "STANDARD", "DEEP")


def coerce_reasoning_depth(value: str) -> Literal["SHALLOW", "STANDARD", "DEEP"]:
    """ORCAState.reasoning_depth is a plain `str` (verbatim from Architecture
    §5); AgentResult.reasoning_depth is the stricter Literal these three
    values. Every agent's run() constructs an AgentResult from state, so this
    is the one place that gap gets validated — a typo or a stale value in
    state should fail loud (or degrade to SHALLOW here, logged) rather than
    silently satisfy a type checker that can't see the actual runtime value."""
    if value in _VALID_REASONING_DEPTHS:
        return value  # type: ignore[return-value]  # narrowed by the check above
    return "SHALLOW"


_VALID_CONFIDENCE_SCORES = ("HIGH", "MEDIUM", "LOW_DATA")


def coerce_confidence_score(value: str) -> Literal["HIGH", "MEDIUM", "LOW_DATA"]:
    """Same gap as coerce_reasoning_depth, for confidence_tier — ORCAState
    carries it as a plain `str` (e.g. reconstructing a Confidence from
    state["confidence_tier"] when the graph needs one), Confidence.score is
    the stricter Literal. An invalid/stale value degrades to the most
    conservative reading (LOW_DATA), never the most confident one — the
    failure direction that matters here is never claiming more certainty
    than actually validated."""
    if value in _VALID_CONFIDENCE_SCORES:
        return value  # type: ignore[return-value]  # narrowed by the check above
    return "LOW_DATA"
