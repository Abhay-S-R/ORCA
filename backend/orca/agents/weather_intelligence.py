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

import json
import math
import os
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

_IST = timezone(timedelta(hours=5, minutes=30))

import httpx
import pandas as pd

from orca import resilience
from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.data.analytics_loaders import load_imd_nowcast_alerts
from orca.data.loaders import (
    CACHED_MARINE_PORTS,
    CACHED_WEATHER_PORTS,
    cached_gdacs_tc_path,
    cached_lightning_path,
    cached_marine_path,
    cached_ndma_cap_alerts_path,
    cached_weather_path,
    load_json,
    port_coordinates,
)
from orca.data.loaders import DEFAULT_LAT as _DEFAULT_LAT
from orca.data.loaders import DEFAULT_LON as _DEFAULT_LON
from orca.data.normalize import SourceDescriptor, normalize_to_common_frame, to_utc_iso
from orca.state import ORCAState

OPEN_METEO_MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
NDMA_SACHET_URL = "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails"
# INCOIS's public multi-hazard endpoints (high wave + swell surge, ocean currents).
INCOIS_HWASSA_URL = "https://sarat.incois.gov.in/incoismobileappdata/rest/incois/hwassalatestdata"
INCOIS_CURRENTS_URL = "https://samudra.incois.gov.in/incoismobileappdata/rest/incois/currentslatestdata"

# §5.7 — 3s on the safety path, where late is the same as absent.
SAFETY_PATH_TIMEOUT_S = 3.0

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
    coords = port_coordinates()
    available = [p for p in candidates if p in coords]
    if not available:
        raise RuntimeError("No cached port fixtures available for fallback")
    return min(available, key=lambda p: _haversine_km(lat, lon, *coords[p]))


def _fetch_open_meteo(url: str, lat: float, lon: float, variables: list[str], hours_ahead: int) -> dict:
    """Thin HTTP boundary — the only function tests need to monkeypatch to
    exercise the live path without a network call.

    P5.27: gated by the "open_meteo" in-process circuit breaker. Once it has
    tripped, this raises immediately instead of paying another timeout —
    every caller already has a cached-fallback except branch for exactly
    this exception, so the cascade drops a rung with no behaviour change
    beyond no longer waiting out a dead upstream on every single query.
    """
    if resilience.circuit_open("open_meteo"):
        raise httpx.ConnectError("circuit_open: open_meteo is in its cool-down, skipping live attempt")
    # OPEN_METEO_PROXY_URL (infra/cloudflare/open-meteo-proxy.js): on a host whose outbound IP is
    # shared, Open-Meteo's per-IP free quota is spent by other tenants and it answers 429. The
    # Worker forwards the same request with its own quota. Unset, Open-Meteo is called directly.
    headers = None
    proxy = os.environ.get("OPEN_METEO_PROXY_URL")
    if proxy:
        url = proxy.rstrip("/") + urlsplit(url).path
        headers = {"X-Orca-Key": os.environ.get("OPEN_METEO_PROXY_KEY") or ""}
    try:
        resp = httpx.get(
            url,
            headers=headers,
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(variables),
                "forecast_days": max(3, -(-hours_ahead // 24)),  # at least 3 days for complete coverage
                "timezone": "UTC",
            },
            timeout=SAFETY_PATH_TIMEOUT_S,
        )
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError:
        resilience.record_failure("open_meteo")
        raise
    resilience.record_success("open_meteo")
    return payload


def get_marine_weather(lat: float, lon: float, hours_ahead: int = 48, *, skip_live: bool = False) -> dict[str, Any]:
    """Tool per Architecture §3.1 Agent 4. Live Open-Meteo Marine + Forecast
    APIs, cached tier1/ fallback on any failure (plan §5.7 fallback cascade)."""
    now = datetime.now(UTC)
    port: str | None = None
    port_km: float | None = None
    try:
        if skip_live:
            # Agent 3 decided the cached rung (the live source's breaker is open): do not pay the 3 s timeout again (A4)
            raise httpx.ConnectError("skipped: marine_data_discovery decided the cached rung")
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
        if merged.empty:
            raise ValueError("Live Open-Meteo marine and wind streams had no overlapping timestamps")
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
        fallback_depth = 0
    except (httpx.HTTPError, KeyError, ValueError):
        port = _nearest_port(lat, lon, CACHED_MARINE_PORTS)
        port_km = _haversine_km(lat, lon, *port_coordinates()[port])
        marine_raw = load_json(cached_marine_path(port))
        wind_raw = load_json(cached_weather_path(port))
        marine_df = pd.DataFrame(marine_raw["hourly"])
        wind_df = pd.DataFrame(wind_raw["hourly"])[["time", "wind_speed_10m", "wind_gusts_10m"]]
        merged = pd.merge(marine_df, wind_df, on="time", how="inner")
        offset = wind_raw.get("utc_offset_seconds", 0)
        cached_acquisition_utc = to_utc_iso(wind_raw["hourly"]["time"][0], offset)
        circuit_note = ", circuit_open" if resilience.circuit_open("open_meteo") else ""
        source = SourceDescriptor(
            dataset=f"Open-Meteo Marine/Forecast API (cached tier1 fallback, port={port}, {port_km:.0f} km away{circuit_note})",
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
        cached_dt = datetime.fromisoformat(cached_acquisition_utc)
        freshness_minutes = max(0, int((now - cached_dt).total_seconds() // 60))
        fallback_depth = 1

    records = normalized.data.to_dict(orient="records")
    return {
        "hourly": records,
        "source_provenance": SourceProvenance(
            dataset=normalized.provenance["dataset"],
            acquisition_timestamp=normalized.provenance["acquisition_timestamp"],
            freshness_minutes=freshness_minutes,
        ),
        "confidence": confidence,
        "fallback_depth": fallback_depth,
        # which catalog source really served (A4): compared with Agent 3's decision in `run`
        "source_used": "open_meteo_port_cache" if fallback_depth else "open_meteo_marine",
        "port": port,
        "port_km": port_km,
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
    now = now or datetime.now(UTC)
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
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


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
    now = datetime.now(UTC)
    try:
        raw = _fetch_open_meteo(OPEN_METEO_FORECAST_URL, lat, lon, ["lightning_potential", "cape"], 1)
        potential = _first_non_null(raw["hourly"]["lightning_potential"])
        dataset = "Open-Meteo lightning_potential (CAPE-derived proxy for IMD Damini, live)"
        used = "open_meteo_lightning_proxy"
        confidence = Confidence(score="MEDIUM", rationale="Live proxy source, not the authoritative Damini feed (unverified, §1.2)")
        acquisition = now.isoformat().replace("+00:00", "Z")
    except (httpx.HTTPError, KeyError, IndexError):
        port = _nearest_port(lat, lon, CACHED_WEATHER_PORTS)
        cached = load_json(cached_lightning_path(port))
        potential = _first_non_null(cached["hourly"]["lightning_potential"])
        dataset = f"Open-Meteo lightning_potential (cached tier1 fallback, port={port})"
        used = "open_meteo_lightning_cache"
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
        "source_used": used,
        "lightning_active": lightning_active,
        "lightning_potential_j_kg": potential,
        "source_provenance": SourceProvenance(dataset=dataset, acquisition_timestamp=acquisition, freshness_minutes=0),
        "confidence": confidence,
    }


# --- get_imd_nowcast_alerts (cached IMD district convective nowcast) -------

# IMD publishes district nowcasts, not marine ones: the nearest issuing
# district centroid to an offshore position is inland, so the radius has to be
# wide enough to reach the coast from a district seat. 150 km is roughly the
# span of a coastal district plus the shelf a day-boat works.
_IMD_NOWCAST_RADIUS_KM = 150.0
# "Sun Aug 30 19:30:00 IST 2026" — IMD's own stamp format. %Z will not parse
# "IST" on most platforms, so the literal is matched and the offset applied by
# hand rather than trusted to the C library's timezone table.
_IMD_TIME_FMT = "%a %b %d %H:%M:%S IST %Y"
_IST = timezone(timedelta(hours=5, minutes=30))


def _imd_time(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, _IMD_TIME_FMT).replace(tzinfo=_IST)
    except (ValueError, TypeError):
        return None


def get_imd_nowcast_alerts(
    lat: float, lon: float, radius_km: float = _IMD_NOWCAST_RADIUS_KM
) -> dict[str, Any]:
    """Cached IMD district convective nowcast entries in force near a point.

    This is a genuine IMD-sourced hazard surface — the only one on disk — and
    it exists alongside the Open-Meteo lightning proxy rather than replacing
    it, so the two can be compared. Two independent sources disagreeing is
    information the user should see, not a conflict to silently resolve.

    The cache is a snapshot with a fixed validity window, so `expired` is
    reported rather than hidden: an out-of-window nowcast is evidence about
    the past, never a claim about now.
    """
    entries = load_imd_nowcast_alerts()
    now = datetime.now(UTC)
    nearby: list[dict[str, Any]] = []
    window_end: datetime | None = None
    for e in entries:
        coords = (e.get("location") or {}).get("coordinates") or []
        if len(coords) < 2:
            continue
        e_lon, e_lat = float(coords[0]), float(coords[1])
        km = _haversine_km(lat, lon, e_lat, e_lon)
        if km > radius_km:
            continue
        end = _imd_time(e.get("effective_end_time", ""))
        if end is not None and (window_end is None or end > window_end):
            window_end = end
        nearby.append({
            "district": e.get("area_description"),
            "event_category": e.get("event_category"),
            "severity": e.get("severity"),
            "severity_color": e.get("severity_color"),
            "events": e.get("events"),
            "distance_km": round(km, 1),
            "effective_start_time": e.get("effective_start_time"),
            "effective_end_time": e.get("effective_end_time"),
        })
    nearby.sort(key=lambda a: a["distance_km"])

    expired = window_end is not None and window_end < now
    lightning_flagged = any(
        "lightning" in (a.get("event_category") or "").lower() for a in nearby
    )
    if not nearby:
        confidence = Confidence(
            score="LOW_DATA",
            rationale=f"no cached IMD nowcast district within {radius_km:.0f} km of this position",
        )
    elif expired and window_end is not None:
        confidence = Confidence(
            score="LOW_DATA",
            rationale=f"cached IMD nowcast window closed {window_end.astimezone(_IST):%Y-%m-%d %H:%M IST} — historical, not current",
        )
    else:
        confidence = Confidence(score="MEDIUM", rationale=f"{len(nearby)} cached IMD district nowcast(s) in force nearby")

    return {
        "alerts": nearby[:10],
        "alert_count": len(nearby),
        "lightning_flagged": lightning_flagged,
        "expired": expired,
        "window_end": window_end.isoformat() if window_end else None,
        "radius_km": radius_km,
        "source_provenance": SourceProvenance(
            dataset="IMD district convective nowcast (cached snapshot, tier1/hazards)",
            acquisition_timestamp=_fmt_utc(window_end) if window_end else "",
            freshness_minutes=0,
        ),
        "confidence": confidence,
    }


# --- get_cyclone_status / get_incois_hazard_alerts (NDMA SACHET CAP) --------

def _fetch_sachet_alerts() -> tuple[list[dict], str, Confidence]:
    # P5.27: same breaker discipline as _fetch_open_meteo — a tripped SACHET
    # skips the live attempt and goes straight to the cached CAP snapshot.
    if resilience.circuit_open("ndma_sachet"):
        alerts = load_json(cached_ndma_cap_alerts_path())
        return alerts, "NDMA SACHET CAP feed (cached fallback, circuit_open)", Confidence(
            score="MEDIUM", rationale="ndma_sachet circuit open — skipping live attempt during cool-down"
        )
    try:
        resp = httpx.get(NDMA_SACHET_URL, timeout=SAFETY_PATH_TIMEOUT_S)
        resp.raise_for_status()
        alerts = resp.json()
        # Guard against 200-with-empty-body or unexpected non-list payloads
        if not isinstance(alerts, list):
            raise ValueError(f"SACHET returned non-list payload: {type(alerts).__name__}")  # noqa: TRY004
        resilience.record_success("ndma_sachet")
        return alerts, "NDMA SACHET CAP feed (live)", Confidence(score="HIGH", rationale="Live government CAP feed")
    except (httpx.HTTPError, ValueError):
        # ValueError covers JSONDecodeError (its subclass) and the guard above
        resilience.record_failure("ndma_sachet")
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
            dataset=dataset, acquisition_timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,
        ),
        "confidence": confidence,
    }


# --- get_cyclone_tracks (GDACS) — the live track and cone, for the map ------
#
# IMD RSMC New Delhi publishes its track only as PDF/text bulletins, so the
# geometry comes from GDACS (EU JRC), which republishes each agency's forecast
# (JTWC for the North Indian Ocean) as GeoJSON. It is drawn and labelled as
# GDACS — never as IMD — and it never reaches the verdict: the cyclone alert
# level evaluate_marine_safety reads still comes from NDMA SACHET above.

GDACS_EVENTS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
GDACS_GEOMETRY_URL = "https://www.gdacs.org/gdacsapi/api/polygons/getgeometry"
# North Indian Ocean: Arabian Sea, Bay of Bengal and the southern reach of the EEZ.
NIO_BBOX_WSEN = (40.0, -10.0, 100.0, 30.0)
# Not the safety path — this draws a layer, the verdict never waits on it.
GDACS_TIMEOUT_S = 5.0
_GDACS_POSITION_RE = re.compile(r"(\d{2})/(\d{2}) (\d{2}):(\d{2})")


def _in_nio(lon: float, lat: float) -> bool:
    west, south, east, north = NIO_BBOX_WSEN
    return west <= lon <= east and south <= lat <= north


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float]:
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def _position_time(label: str, year: int) -> str | None:
    """GDACS labels a track position "15/09 12:00 UTC" — day/month, no year."""
    m = _GDACS_POSITION_RE.search(label or "")
    if not m:
        return None
    day, month, hour, minute = (int(g) for g in m.groups())
    return datetime(year, month, day, hour, minute, tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _tc_features(geometry: dict, event: dict) -> list[dict]:
    """Keep the track (lines), the timed positions and the uncertainty cone;
    drop GDACS's wind-buffer polygons, which are a different product."""
    props = event.get("properties", {})
    year = int(str(props.get("fromdate", "1970"))[:4])
    last_observed = props.get("todate")  # positions after this are forecast
    base = {"event_id": props.get("eventid"), "name": props.get("eventname"),
            "alert_level": props.get("alertlevel"), "forecast_agency": props.get("source")}
    out: list[dict] = []
    for f in geometry.get("features", []):
        cls = (f.get("properties") or {}).get("Class", "")
        label = (f.get("properties") or {}).get("polygonlabel", "")
        geom = f.get("geometry") or {}
        if cls.startswith("Line_Line"):
            out.append({"type": "Feature", "geometry": geom, "properties": {**base, "kind": "track", "status": label}})
        elif cls == "Poly_Cones":
            out.append({"type": "Feature", "geometry": geom, "properties": {**base, "kind": "cone"}})
        elif cls.startswith("Point_Polygon_Point") and geom.get("type") == "Polygon":
            lon, lat = _ring_centroid(geom["coordinates"][0])
            t = _position_time(label, year)
            forecast = bool(t and last_observed and t > f"{last_observed}Z")
            out.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, 3), round(lat, 3)]},
                        "properties": {**base, "kind": "position", "time": t, "forecast": forecast}})
    return out


def _fetch_gdacs_tracks() -> dict[str, Any]:
    # P5.27 — same in-process breaker as open_meteo/ndma_sachet: once GDACS
    # has flapped, skip straight to the cached-fixture fallback in
    # get_cyclone_tracks rather than paying a timeout per query.
    if resilience.circuit_open("gdacs_tc"):
        raise httpx.ConnectError("circuit_open: gdacs_tc is in its cool-down, skipping live attempt")
    try:
        events = httpx.get(GDACS_EVENTS_URL, params={"eventlist": "TC"}, timeout=GDACS_TIMEOUT_S)
        events.raise_for_status()
        systems: list[dict] = []
        features: list[dict] = []
        for ev in events.json().get("features", []):
            props = ev.get("properties", {})
            lon, lat = (ev.get("geometry") or {}).get("coordinates", [None, None])[:2]
            if str(props.get("iscurrent")).lower() != "true" or lon is None or not _in_nio(lon, lat):
                continue
            geo = httpx.get(GDACS_GEOMETRY_URL, timeout=GDACS_TIMEOUT_S, params={
                "eventtype": "TC", "eventid": props.get("eventid"), "episodeid": props.get("episodeid")})
            geo.raise_for_status()
            features.extend(_tc_features(geo.json(), ev))
            systems.append({
                "event_id": props.get("eventid"), "name": props.get("eventname"), "alert_level": props.get("alertlevel"),
                "forecast_agency": props.get("source"), "severity": (props.get("severitydata") or {}).get("severitytext"),
                "last_observed": props.get("todate"), "report_url": (props.get("url") or {}).get("report"),
            })
    except httpx.HTTPError:
        resilience.record_failure("gdacs_tc")
        raise
    resilience.record_success("gdacs_tc")
    return {"systems": systems, "geojson": {"type": "FeatureCollection", "features": features}}


def get_cyclone_tracks() -> dict[str, Any]:
    """Active North Indian Ocean cyclones as a map layer: track, timed positions
    (observed vs forecast) and the uncertainty cone. Live from GDACS; on failure
    the last successful fetch is served with its own timestamp and `cached`
    set; with no fetch ever made, `available` is False — never an invented track."""
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    try:
        result = {**_fetch_gdacs_tracks(), "fetched_at": now, "cached": False}
        try:
            path = cached_gdacs_tc_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result), encoding="utf-8")
        except OSError:
            pass  # a failed cache write must not cost the live answer
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        try:
            result = {**load_json(cached_gdacs_tc_path()), "cached": True}
        except (OSError, ValueError):
            return {"available": False, "systems": [], "geojson": {"type": "FeatureCollection", "features": []},
                    "cached": False, "note": "GDACS unreachable and no earlier fetch on disk — cyclone track unavailable.",
                    "source": "GDACS (EU JRC)"}
    systems = result["systems"]
    active = len(systems) if isinstance(systems, list) else 0
    result.update({
        "available": True,
        "source": "GDACS (EU JRC)",
        "note": (f"{active} active system(s) in the North Indian Ocean" if active
                 else "No active cyclone in the North Indian Ocean") + f" — GDACS, checked {result['fetched_at']}"
                + (" (cached — live fetch failed)" if result["cached"] else "") + ".",
    })
    return result


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


def _fetch_incois_hazard_bulletins() -> tuple[list[dict], str] | None:
    """INCOIS's own district-level HWA / SSA / ocean-current bulletins, or None.

    These are the JSON endpoints behind incois.gov.in's public multi-hazard map
    (`site/services/Alerts.html`) — the same ones the INCOIS mobile app reads. No
    key, no whitelisting, unlike IMD's nowcast API which answers 401 "Your IP needs
    to be whitelisted". Each payload wraps its rows as a JSON *string* under a
    sibling key, with the literal "None" standing in for "nothing issued today".
    """
    # P5.27 — same in-process breaker as open_meteo/gdacs_tc: once INCOIS's
    # hazard endpoints have flapped, skip straight to the NDMA SACHET fallback
    # get_incois_hazard_alerts already has, instead of paying a timeout per query.
    if resilience.circuit_open("incois_hazard_bulletins"):
        return None
    out: list[dict] = []
    for url, pairs in (
        (INCOIS_HWASSA_URL, (("LatestHWADate", "HWAJson", "high_wave"),
                             ("LatestSSADate", "SSAJson", "swell_surge"))),
        (INCOIS_CURRENTS_URL, (("LatestCurrentsDate", "CurrentsJson", "ocean_current"),)),
    ):
        try:
            resp = httpx.get(url, timeout=SAFETY_PATH_TIMEOUT_S,
                             headers={"User-Agent": "ORCA/1.0 (SIH26176)"})
            resp.raise_for_status()
            payload = resp.json()
            for date_key, json_key, kind in pairs:
                issued = payload.get(date_key)
                if not issued or issued == "None":
                    continue  # INCOIS issued no bulletin of this kind today
                for row in json.loads(payload[json_key]):
                    out.append({
                        "hazard_type": kind,
                        "district": row.get("District"),
                        "state": row.get("STATE"),
                        "message": row.get("Message"),
                        "issued_date": issued,
                    })
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            resilience.record_failure("incois_hazard_bulletins")
            return None  # partial hazard data is worse than none — fall back whole
    resilience.record_success("incois_hazard_bulletins")
    return (out, "INCOIS multi-hazard bulletins — HWA/SSA/currents (live)")


def get_incois_hazard_alerts(region: str) -> dict[str, Any]:
    """Tool per Architecture §3.1 Agent 4. Live INCOIS high-wave, swell-surge and
    ocean-current bulletins for `region`, matched against district or state.

    Falls back to the NDMA SACHET CAP feed — `discovery.py`'s declared fallback for
    this source — when INCOIS is unreachable, and says which one it used. An empty
    list from INCOIS means "no hazard issued", which is a real answer; only a
    transport or parse failure triggers the fallback.
    """
    region_lower = region.lower()
    live = _fetch_incois_hazard_bulletins()
    if live is not None:
        bulletins, dataset = live
        matching = [b for b in bulletins
                    if region_lower in (b["district"] or "").lower()
                    or region_lower in (b["state"] or "").lower()]
        confidence = Confidence(score="HIGH", rationale="Live INCOIS hazard bulletin feed")
    else:
        alerts, dataset, confidence = _fetch_sachet_alerts()
        dataset = f"{dataset} (INCOIS hazard feed unreachable — SACHET fallback)"
        matching = [a for a in alerts if region_lower in a.get("area_description", "").lower()]

    return {
        "region": region,
        "active_warnings": matching,
        "source_provenance": SourceProvenance(
            dataset=dataset,
            acquisition_timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,
        ),
        "confidence": confidence,
    }


# --- Agent entry point -------------------------------------------------------

def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult — no langgraph import, callable directly
    (plan §3.4)."""
    from orca import demo_fixtures

    pinned = demo_fixtures.fixture_result(state, "weather_intelligence")
    if pinned is not None:
        return pinned

    location = state.get("user_location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    if lat is None or lon is None:
        bbox = state.get("target_bbox") or {}
        lat = (bbox.get("min_lat", _DEFAULT_LAT) + bbox.get("max_lat", _DEFAULT_LAT)) / 2
        lon = (bbox.get("min_lon", _DEFAULT_LON) + bbox.get("max_lon", _DEFAULT_LON)) / 2

    # A4 (2026-10-10): the wave/wind source is the one marine_data_discovery decided. It can pre-decide only what is knowable
    # before the call: when the live source's breaker is open it names the cached rung and this agent skips the live attempt (a
    # 3 s wait) instead of making its own choice. A live call that fails AT FETCH still falls to the declared next rung.
    decisions = (state.get("discovery_sources") or {}).get("by_data_type") or {}
    wave_decision = decisions.get("wave_height") or {}
    weather = get_marine_weather(lat, lon, hours_ahead=48, skip_live=wave_decision.get("chosen") == "open_meteo_port_cache")
    lightning = get_lightning_nowcast(lat, lon)
    basin: Literal["BoB", "AS"] = "BoB" if lon >= 77.5 else "AS"
    cyclone = get_cyclone_status(basin)
    imd = get_imd_nowcast_alerts(lat, lon)

    # Cross-source agreement on convective risk (differentiator: ORCA shows
    # when two independent sources disagree instead of picking one silently).
    # Only meaningful while the IMD snapshot is still in its validity window —
    # an expired nowcast "disagreeing" with a live proxy is not a
    # disagreement, it is two statements about different days.
    if imd["expired"] or imd["alert_count"] == 0:
        agreement = "single_source"
    elif imd["lightning_flagged"] == lightning["lightning_active"]:
        agreement = "agree"
    else:
        agreement = "disagree"

    used_by_type = {
        "wave_height": weather["source_used"], "wind_speed": weather["source_used"], "lightning": lightning["source_used"],
    }
    from orca.agents.discovery import source_report_entry

    source_report = {dtype: source_report_entry(decisions.get(dtype), used) for dtype, used in used_by_type.items()}
    outputs = {
        "source_report": source_report,
        "hourly": weather["hourly"],
        "lightning_active": lightning["lightning_active"],
        "imd_nowcast": {k: v for k, v in imd.items() if k not in ("confidence", "source_provenance")},
        "imd_nowcast_dataset": imd["source_provenance"].dataset,
        "lightning_source_agreement": agreement,
        "cyclone_alert": _cyclone_alert_severity(cyclone["active_cyclones"]),
        # Agent 7 reads weather_data (this dict, once the graph stores it in
        # state) and needs its own SourceProvenance for its verdict — the
        # timestamp lived only inside the AgentResult.source_provenance this
        # function returns separately, which the graph node never copies into
        # weather_data. Duplicated here at the top level so Agent 7 can
        # actually reach it instead of silently getting "".
        "acquisition_timestamp": weather["source_provenance"].acquisition_timestamp,
        # Same reason: the reporting agent cites weather_data, and hardcoding a
        # live dataset name with freshness 0 there described a 5-day-old cached
        # snapshot as a live fetch.
        "dataset": weather["source_provenance"].dataset,
        "freshness_minutes": weather["source_provenance"].freshness_minutes,
    }
    # Conservative composite: if any input degraded, the whole result did.
    # The IMD nowcast is deliberately NOT in this max(): it is a corroborating
    # second source, and its cached snapshot is LOW_DATA by construction once
    # its window closes. Letting that drag a live forecast down would mean a
    # perfectly good safety answer degrades because a *bonus* source is stale.
    tiers = ["HIGH", "MEDIUM", "LOW_DATA"]
    worst = max(
        weather["confidence"].score, lightning["confidence"].score, cyclone["confidence"].score,
        key=tiers.index,
    )
    confidence = Confidence(
        score=worst,  # type: ignore[arg-type]  # max() over Literal values returns str
        rationale=f"weather={weather['confidence'].rationale}; lightning={lightning['confidence'].rationale}; "
        f"cyclone={cyclone['confidence'].rationale}; imd_nowcast={imd['confidence'].rationale}",
    )

    return AgentResult(
        agent_name="weather_intelligence",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"lat": lat, "lon": lon},
        outputs=outputs,
        source_provenance=weather["source_provenance"],
        confidence=confidence,
        # Measured factors for orca/confidence_score.py. Open-Meteo is LIVE-class
        # (data/freshness.py SOURCE_CLASS["open_meteo_marine"]); a cached read is
        # rung 1 and its real age is what the freshness factor judges.
        data_age_minutes=weather["source_provenance"].freshness_minutes,
        freshness_class="LIVE",
        fallback_depth=weather.get("fallback_depth"),
        coverage=_reading_coverage((weather["hourly"] or [{}])[0], ("wave_height", "wind_speed_10m")),
    )


def _reading_coverage(record: dict, keys: tuple[str, ...]) -> tuple[int, int]:
    """(present, expected) — a reading counts only if it is a real number, not None/NaN."""
    present = sum(1 for k in keys if isinstance(record.get(k), (int, float)) and record[k] == record[k])
    return present, len(keys)
