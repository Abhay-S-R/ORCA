"""Agent 4 — Weather Intelligence (Architecture §3.1). No LLM calls — API
fetch plus threshold comparison (plan §3.2 table).

Two real, verified sources back this:
  - Open-Meteo Marine API  (wave height, period, swell, currents)
  - Open-Meteo Forecast API (wind, gusts, CAPE / lightning potential)
Both confirmed live against the actual endpoints while writing this, not
assumed from the architecture doc's table alone.

get_lightning_nowcast is honestly labelled: Architecture §1.2 flags the IMD
Damini endpoint as unverified, so this uses Open-Meteo's `lightning_potential`
field (a genuine, verified, live CAPE-based convective proxy) instead of a
Damini integration that doesn't exist yet. Same for get_incois_hazard_alerts
— there is no verified INCOIS-specific hazard endpoint in this codebase, so
it reuses the NDMA SACHET CAP feed get_cyclone_status already fetches,
filtered by area. Both gaps are named in the docstring, not hidden.

PARAMETER ORDER WARNING: every function in this module takes (lat, lon), NOT
(lon, lat) — matching Architecture §3.1's tool table verbatim (e.g.
`get_marine_weather | lat, lon, hours_ahead`). This is deliberately different
from normalize.py's (lon, lat) convention, which governs DATA payloads
(DataFrame columns, GeoJSON), not function call arguments. Every call site as
of writing passes them correctly (see tests), but a (lat, lon) vs (lon, lat)
mismatch fails silently — swapped coordinates still look like plausible
numbers, they just point somewhere else. If you're adding a new caller,
double-check which convention you're matching.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import httpx
import pandas as pd

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.data.loaders import (
    CACHED_MARINE_PORTS,
    CACHED_WEATHER_PORTS,
    cached_lightning_path,
    cached_marine_path,
    cached_ndma_cap_alerts_path,
    cached_weather_path,
    load_json,
)
from orca.data.normalize import SourceDescriptor, normalize_to_common_frame, to_utc_iso
from orca.state import ORCAState

OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NDMA_SACHET_URL = "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails"

# §5.7 — 3s on the safety path, where late is the same as absent.
SAFETY_PATH_TIMEOUT_S = 3.0

# Known port locations, read from the cached fixtures themselves rather than
# a separate hand-maintained registry — each file already carries its own
# latitude/longitude.
_PORT_COORDS: dict[str, tuple[float, float]] | None = None


def _port_coords() -> dict[str, tuple[float, float]]:
    global _PORT_COORDS
    if _PORT_COORDS is None:
        coords = {}
        for port in CACHED_WEATHER_PORTS:
            path = cached_weather_path(port)
            if path.exists():
                d = load_json(path)
                coords[port] = (d["latitude"], d["longitude"])
        _PORT_COORDS = coords
    return _PORT_COORDS


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Nearest-cached-port lookup over ~6 known points — a plain haversine is
    # the right tool here, not scripts/orca_grid_utils.py's wet-cell snapping
    # (that solves a different problem: finding a valid ocean cell in a grid,
    # which doesn't apply to a fixed list of real port coordinates).
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _nearest_port(lat: float, lon: float, candidates: tuple[str, ...]) -> str:
    coords = _port_coords()
    available = [p for p in candidates if p in coords]
    if not available:
        raise RuntimeError("No cached port fixtures available for fallback")
    return min(available, key=lambda p: _haversine_km(lat, lon, *coords[p]))


def _fetch_open_meteo(url: str, lat: float, lon: float, variables: list[str], hours_ahead: int) -> dict:
    """Thin HTTP boundary — the only function tests need to monkeypatch to
    exercise the live path without a network call."""
    resp = httpx.get(
        url,
        params={
            "latitude": lat,
            "longitude": lon,
            "hourly": ",".join(variables),
            "forecast_days": max(1, -(-hours_ahead // 24)),  # ceil division
            "timezone": "UTC",
        },
        timeout=SAFETY_PATH_TIMEOUT_S,
    )
    resp.raise_for_status()
    return resp.json()


def get_marine_weather(lat: float, lon: float, hours_ahead: int = 24) -> dict[str, Any]:
    """Tool per Architecture §3.1 Agent 4. Live Open-Meteo Marine + Forecast
    APIs, cached tier1/ fallback on any failure (plan §5.7 fallback cascade)."""
    now = datetime.now(timezone.utc)
    try:
        marine_raw = _fetch_open_meteo(
            OPEN_METEO_MARINE_URL, lat, lon,
            ["wave_height", "wave_period", "swell_wave_height", "ocean_current_velocity"],
            hours_ahead,
        )
        wind_raw = _fetch_open_meteo(
            OPEN_METEO_FORECAST_URL, lat, lon, ["wind_speed_10m", "wind_gusts_10m"], hours_ahead
        )
        marine_df = pd.DataFrame(marine_raw["hourly"])
        wind_df = pd.DataFrame(wind_raw["hourly"])
        merged = pd.merge(marine_df, wind_df, on="time", how="inner")
        source = SourceDescriptor(
            dataset="Open-Meteo Marine API + Forecast API (live)",
            authority_tier="T1",
            acquisition_timestamp=now.isoformat().replace("+00:00", "Z"),
            native_units={
                "ocean_current_velocity": "km/h", "wind_speed_10m": "km/h", "wind_gusts_10m": "km/h",
            },
            utc_offset_seconds=0,  # requested timezone=UTC explicitly, confirmed live
        )
        normalized = normalize_to_common_frame(
            merged, source=source,
            target_units={"ocean_current_velocity": "m/s", "wind_speed_10m": "m/s", "wind_gusts_10m": "m/s"},
        )
        confidence = Confidence(score="HIGH", rationale="Live Open-Meteo Marine + Forecast APIs, matching target window")
        freshness_minutes = 0
    except (httpx.HTTPError, KeyError, ValueError):
        port = _nearest_port(lat, lon, CACHED_MARINE_PORTS)
        marine_raw = load_json(cached_marine_path(port))
        wind_raw = load_json(cached_weather_path(port))
        marine_df = pd.DataFrame(marine_raw["hourly"])
        wind_df = pd.DataFrame(wind_raw["hourly"])[["time", "wind_speed_10m", "wind_gusts_10m"]]
        merged = pd.merge(marine_df, wind_df, on="time", how="inner")
        offset = wind_raw.get("utc_offset_seconds", 0)
        cached_acquisition_utc = to_utc_iso(wind_raw["hourly"]["time"][0], offset)
        source = SourceDescriptor(
            dataset=f"Open-Meteo Marine/Forecast API (cached tier1 fallback, port={port})",
            authority_tier="T1",
            acquisition_timestamp=cached_acquisition_utc,
            native_units={
                "ocean_current_velocity": "km/h", "wind_speed_10m": "km/h", "wind_gusts_10m": "km/h",
            },
            utc_offset_seconds=offset,
        )
        normalized = normalize_to_common_frame(
            merged, source=source,
            target_units={"ocean_current_velocity": "m/s", "wind_speed_10m": "m/s", "wind_gusts_10m": "m/s"},
        )
        confidence = Confidence(
            score="MEDIUM",
            rationale=f"Live fetch failed; fell back to cached tier1 snapshot for nearest port ({port})",
        )
        cached_dt = datetime.fromisoformat(cached_acquisition_utc.replace("Z", "+00:00"))
        freshness_minutes = max(0, int((now - cached_dt).total_seconds() // 60))

    records = normalized.data.to_dict(orient="records")
    return {
        "hourly": records,
        "source_provenance": SourceProvenance(
            dataset=normalized.provenance["dataset"],
            acquisition_timestamp=normalized.provenance["acquisition_timestamp"],
            freshness_minutes=freshness_minutes,
        ),
        "confidence": confidence,
    }


# --- resolve_temporal_expression -------------------------------------------

_TEMPORAL_PATTERNS: list[tuple[re.Pattern, Any]] = [
    (re.compile(r"\bin (\d+) hours?\b"), "in_n_hours"),
    (re.compile(r"\btomorrow morning\b"), ("days", 1, 6, 12)),
    (re.compile(r"\btomorrow (evening|night)\b"), ("days", 1, 18, 24)),
    (re.compile(r"\btomorrow\b"), ("days", 1, 0, 24)),
    (re.compile(r"\bthis morning\b"), ("days", 0, 6, 12)),
    (re.compile(r"\b(this evening|tonight)\b"), ("days", 0, 18, 24)),
    (re.compile(r"\btoday\b"), ("days", 0, 0, 24)),
]


def resolve_temporal_expression(text: str, *, now: datetime | None = None) -> dict[str, str]:
    """Tool per Architecture §3.1 Agent 4. Deterministic rule-based parser —
    matched against English (Agent 1 normalizes vernacular queries to English
    before Planning/Weather ever see them). Ambiguous phrasing (e.g. "tonight"
    asked at 11pm) resolves to the same day's window rather than guessing
    whether the user means the next occurrence — narrow, documented, not a
    silent guess."""
    now = now or datetime.now(timezone.utc)
    text = text.lower()

    for pattern, action in _TEMPORAL_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        if action == "in_n_hours":
            hours = int(m.group(1))
            start = now + timedelta(hours=hours)
            end = start + timedelta(hours=1)
            return _iso_range(start, end)
        _, day_offset, start_hour, end_hour = action
        day = (now + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        start = day + timedelta(hours=start_hour)
        end = day + timedelta(hours=min(end_hour, 24)) - timedelta(seconds=1) if end_hour == 24 else day + timedelta(hours=end_hour)
        return _iso_range(start, end)

    # No temporal expression found — default to "now, next 3 hours", matching
    # the no-match-fallback discipline (never silently drop, always answer
    # the closest reasonable interpretation).
    return _iso_range(now, now + timedelta(hours=3))


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_range(start: datetime, end: datetime) -> dict[str, str]:
    return {"start": _fmt_utc(start), "end": _fmt_utc(end)}


# --- get_lightning_nowcast ---------------------------------------------------

def _first_non_null(values: list[float | None]) -> float | None:
    # Open-Meteo genuinely returns null for lightning_potential on plenty of
    # hours (confirmed against the real cached fixtures — most of an entire
    # 7-day window can be null). Index [0] alone silently reads as "no risk"
    # when the truth is "no reading" — those are not the same claim.
    for v in values:
        if v is not None:
            return v
    return None


def get_lightning_nowcast(lat: float, lon: float, radius_km: float = 25.0) -> dict[str, Any]:
    """Tool per Architecture §3.1 Agent 4. NOTE: stands in for IMD Damini,
    which §1.2 flags as unverified — uses Open-Meteo's live `lightning_potential`
    (J/kg, CAPE-derived) instead, confirmed live against the real endpoint.
    Swap the source when a real Damini endpoint is confirmed; the output
    shape (lightning_active: bool, source_provenance, confidence) does not
    need to change for that swap."""
    now = datetime.now(timezone.utc)
    try:
        raw = _fetch_open_meteo(OPEN_METEO_FORECAST_URL, lat, lon, ["lightning_potential", "cape"], 1)
        potential = _first_non_null(raw["hourly"]["lightning_potential"])
        dataset = "Open-Meteo lightning_potential (CAPE-derived proxy for IMD Damini, live)"
        confidence = Confidence(score="MEDIUM", rationale="Live proxy source, not the authoritative Damini feed (unverified, §1.2)")
        acquisition = now.isoformat().replace("+00:00", "Z")
    except (httpx.HTTPError, KeyError, IndexError):
        port = _nearest_port(lat, lon, CACHED_WEATHER_PORTS)
        cached = load_json(cached_lightning_path(port))
        potential = _first_non_null(cached["hourly"]["lightning_potential"])
        dataset = f"Open-Meteo lightning_potential (cached tier1 fallback, port={port})"
        confidence = Confidence(
            score="LOW_DATA",
            rationale="Live proxy fetch failed; using cached snapshot"
            + ("" if potential is not None else " (no lightning_potential reading available in the cached window)"),
        )
        acquisition = to_utc_iso(cached["hourly"]["time"][0], cached.get("utc_offset_seconds", 0))

    # J/kg threshold: Open-Meteo's own documentation bands lightning_potential
    # as "moderate risk" above ~1000 J/kg. No official IMD threshold exists to
    # cross-check this against (that's exactly the gap Damini would close).
    lightning_active = potential is not None and potential >= 1000
    return {
        "lightning_active": lightning_active,
        "lightning_potential_j_kg": potential,
        "source_provenance": SourceProvenance(dataset=dataset, acquisition_timestamp=acquisition, freshness_minutes=0),
        "confidence": confidence,
    }


# --- get_cyclone_status / get_incois_hazard_alerts (NDMA SACHET CAP) --------

def _fetch_sachet_alerts() -> tuple[list[dict], str, Confidence]:
    try:
        resp = httpx.get(NDMA_SACHET_URL, timeout=SAFETY_PATH_TIMEOUT_S)
        resp.raise_for_status()
        alerts = resp.json()
        return alerts, "NDMA SACHET CAP feed (live)", Confidence(score="HIGH", rationale="Live government CAP feed")
    except httpx.HTTPError:
        alerts = load_json(cached_ndma_cap_alerts_path())
        return alerts, "NDMA SACHET CAP feed (cached fallback)", Confidence(
            score="MEDIUM", rationale="Live SACHET fetch failed; using cached snapshot"
        )


def _alert_centroid(alert: dict) -> tuple[float, float] | None:
    raw = alert.get("centroid")
    if not raw:
        return None
    try:
        lon_s, lat_s = raw.split(",")
        return float(lat_s), float(lon_s)
    except (ValueError, AttributeError):
        return None


def get_cyclone_status(basin: Literal["BoB", "AS"]) -> dict[str, Any]:
    """Tool per Architecture §3.1 Agent 4. Basin is inferred from each
    alert's centroid longitude — India's east/west coast split, threshold
    77.5°E — because SACHET alerts carry a point centroid, not a basin field.
    This is a coarse geographic heuristic, not authoritative basin geometry;
    the real basin boundary is Agent 6's domain (EEZ/marine-region polygons),
    out of scope for a weather tool."""
    alerts, dataset, confidence = _fetch_sachet_alerts()
    cyclone_alerts = []
    for alert in alerts:
        if "cyclone" not in alert.get("disaster_type", "").lower():
            continue
        centroid = _alert_centroid(alert)
        if centroid is None:
            continue
        _, lon = centroid
        alert_basin = "BoB" if lon >= 77.5 else "AS"
        if alert_basin == basin:
            cyclone_alerts.append(alert)

    return {
        "basin": basin,
        "active_cyclones": cyclone_alerts,
        "source_provenance": SourceProvenance(
            dataset=dataset, acquisition_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,
        ),
        "confidence": confidence,
    }


def _cyclone_alert_severity(active_cyclones: list[dict]) -> str | None:
    """Maps SACHET's severity_color to evaluate_marine_safety's Red/Orange
    scale (Agent 7, Architecture §3.1). UNVERIFIED against a real example:
    the live SACHET feed had zero Cyclone-type entries while this was
    written (checked directly, not assumed) — the disaster_type filter is
    real and tested, but this specific severity mapping has never been
    exercised against an actual cyclone alert. Confirm it the first time one
    is live, before trusting it for a NO_GO decision."""
    if not active_cyclones:
        return None
    colors = {a.get("severity_color", "").lower() for a in active_cyclones}
    if "red" in colors:
        return "Red"
    return "Orange"  # any other active cyclone-type alert — conservative default


def get_incois_hazard_alerts(region: str) -> dict[str, Any]:
    """Tool per Architecture §3.1 Agent 4. HONEST GAP: no verified
    INCOIS-specific tsunami/storm-surge/high-wave endpoint exists in this
    codebase. Reuses the same NDMA SACHET CAP feed get_cyclone_status
    fetches, filtered by area_description containing `region` — the closest
    verified substitute, not a real INCOIS integration. Replace this when a
    real INCOIS hazard endpoint is confirmed live."""
    alerts, dataset, confidence = _fetch_sachet_alerts()
    region_lower = region.lower()
    matching = [a for a in alerts if region_lower in a.get("area_description", "").lower()]
    return {
        "region": region,
        "active_warnings": matching,
        "source_provenance": SourceProvenance(
            dataset=f"{dataset} (substitute for unverified INCOIS hazard endpoint, §1.2)",
            acquisition_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,
        ),
        "confidence": confidence,
    }


# --- Agent entry point -------------------------------------------------------

def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult — no langgraph import, callable directly
    (plan §3.4)."""
    location = state.get("user_location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        bbox = state.get("target_bbox") or {}
        lat = (bbox.get("min_lat", 8.80) + bbox.get("max_lat", 8.80)) / 2
        lon = (bbox.get("min_lon", 78.14) + bbox.get("max_lon", 78.14)) / 2

    weather = get_marine_weather(lat, lon, hours_ahead=24)
    lightning = get_lightning_nowcast(lat, lon)
    basin: Literal["BoB", "AS"] = "BoB" if lon >= 77.5 else "AS"
    cyclone = get_cyclone_status(basin)

    outputs = {
        "hourly": weather["hourly"],
        "lightning_active": lightning["lightning_active"],
        "cyclone_alert": _cyclone_alert_severity(cyclone["active_cyclones"]),
        # Agent 7 reads weather_data (this dict, once the graph stores it in
        # state) and needs its own SourceProvenance for its verdict — the
        # timestamp lived only inside the AgentResult.source_provenance this
        # function returns separately, which the graph node never copies into
        # weather_data. Duplicated here at the top level so Agent 7 can
        # actually reach it instead of silently getting "".
        "acquisition_timestamp": weather["source_provenance"].acquisition_timestamp,
    }
    # Conservative composite: if any input degraded, the whole result did.
    tiers = ["HIGH", "MEDIUM", "LOW_DATA"]
    worst = max(
        weather["confidence"].score, lightning["confidence"].score, cyclone["confidence"].score,
        key=tiers.index,
    )
    confidence = Confidence(
        score=worst,
        rationale=f"weather={weather['confidence'].rationale}; lightning={lightning['confidence'].rationale}; "
        f"cyclone={cyclone['confidence'].rationale}",
    )

    return AgentResult(
        agent_name="weather_intelligence",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"lat": lat, "lon": lon},
        outputs=outputs,
        source_provenance=weather["source_provenance"],
        confidence=confidence,
    )
