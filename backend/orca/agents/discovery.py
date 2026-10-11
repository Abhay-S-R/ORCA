"""Agent 3 — Marine Data Discovery (plan §4 S4 / Phase 2 D2 Day 8).

Phase 1 shipped only the seed registry and `select_best_source`. Phase 2 D2
Day 8 grows this into the full catalog across all 25 datasets in
`docs/data/ORCA_Dataset_Master_List.md`, wires in the declared per-source fallback
cascades from Architecture §12.1, and makes `select_source_with_fallback`
return the *comparison narrative* the PS calls "tool selection made visible"
— not a log line, a first-class output the `/data` surface and the answer
card both render:

    "MOSDAC NRT SST chosen over Copernicus CMEMS reanalysis: 6 h old vs
     ~5 d, same Tier-1 authority — freshness decided it."

`select_best_source` (Phase 1 signature) is unchanged so Agent 6 and the
Phase 1 tests keep working; the new cascade-aware picker is additive.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple

from orca import resilience

logger = logging.getLogger(__name__)

AuthorityTier = Literal["TIER1", "TIER2", "TIER3"]

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
PFZ_FALLBACK_FILE = DATA_ROOT / "incois_osf_pfz" / "pfz" / "pfz_fallback_pilot_region.geojson"


@dataclass(frozen=True)
class DataSource:
    id: str
    dataset: str
    authority_tier: AuthorityTier
    typical_freshness_minutes: int  # 0 for static/reference datasets (boundaries, bathymetry)
    covers: tuple[str, ...]  # data_type keys this source can answer
    # AUDIT 4 / A2 (2026-10-10). False = ORCA holds no reader that returns VALUES from this source, so Agent 3 never chooses
    # it: it stays in the catalog (a judge can see it was considered and why it cannot serve), it is not a rung of a cascade.
    # A static declaration (data/ is gitignored, so it cannot be read off the disk: CI has no data).
    readable: bool = True
    why_not_readable: str = ""


@dataclass(frozen=True)
class SelectedSource:
    source: DataSource
    reason: str


# Full catalog — every dataset in docs/data/ORCA_Dataset_Master_List.md that ORCA
# is allowed to cite. `covers` keys are the data_type strings specialist
# agents ask for; `typical_freshness_minutes` is 0 for static reference
# geometry (boundaries, bathymetry). The nine Phase-1 ids are unchanged —
# Agent 6 and the Phase-1 tests pin some of them by id.
SOURCE_REGISTRY: tuple[DataSource, ...] = (
    # --- Tier 1: free & open ---
    DataSource("open_meteo_marine", "Open-Meteo Marine API / ECMWF WAM Blend", "TIER1", 60,
               ("wave_height", "wave_period", "swell_height", "wind_speed", "wind_direction",
                "current_speed", "current_direction")),
    # No "sst": probing the server on 2026-09-18 showed every one of its 17 datasets
    # is a closed historical archive — SST stops in 2011. It was covering "sst" at a
    # 180 min cadence, which is what `select_best_source` ranks on, so ORCA was
    # choosing a 2011 archive as its *primary* sea-surface temperature source ahead
    # of MOSDAC. The cadence below is the archive's real one: it does not update.
    DataSource("incois_erddap", "INCOIS ERDDAP Data Server (historical archive)", "TIER1",
               365 * 24 * 60, ("salinity", "buoy_telemetry", "wave_spectrum"),
               readable=False, why_not_readable="a closed historical archive; ORCA fetches nothing from it"),
    DataSource("incois_osf_ww3", "INCOIS Ocean State Forecast (WaveWatch III)", "TIER1", 360,
               ("wave_height", "wave_period")),
    DataSource("incois_osf_hycom", "INCOIS Ocean State Forecast (HYCOM currents)", "TIER1", 360,
               ("current_speed", "current_direction")),
    DataSource("mosdac_open_sst", "MOSDAC Open Data — INSAT-3DR L3 SST (daily)", "TIER1", 360, ("sst",)),
    DataSource("mosdac_open_chl", "MOSDAC Open Data — EOS-06 OCM-3 Chlorophyll-a", "TIER1", 1440, ("chlorophyll",)),
    DataSource("soi_tide_tables", "Survey of India 2026 Annual Tide Tables", "TIER1", 0, ("tide",)),
    DataSource("incois_tide_gauge", "INCOIS Tide Gauge Network (TEWS)", "TIER1", 15, ("tide_observed", "sea_level_anomaly")),
    DataSource("incois_pfz", "INCOIS Potential Fishing Zone advisories", "TIER1", 1440, ("pfz",)),
    DataSource("incois_hazard_osf", "INCOIS Hazard Alerts & Ocean State Warnings", "TIER1", 10,
               ("hazard", "swell_surge", "high_wave", "kallakkadal")),
    DataSource("ndma_sachet", "NDMA SACHET / IMD CAP alert feed", "TIER1", 15, ("cyclone", "hazard", "cap_alert")),
    # Track + cone geometry only (IMD RSMC has no machine-readable track). Never
    # feeds the verdict — the alert level stays SACHET's.
    DataSource("gdacs_tc", "GDACS tropical cyclone track and cone (EU JRC; JTWC forecast)", "TIER2", 360,
               ("cyclone_track",)),
    # AUDIT 4 / A4 (2026-10-10): there is no Damini feed in ORCA (weather_intelligence.get_lightning_nowcast says so in its own
    # docstring: "stands in for IMD Damini, which §1.2 flags as unverified"). Agent 3 chose "IMD Damini" for lightning and the
    # answer used Open-Meteo's CAPE-derived proxy: the decision named a source that was never read.
    DataSource("damini_lightning", "IMD Damini Lightning Nowcast", "TIER1", 10, ("lightning",),
               readable=False, why_not_readable="no Damini feed is held (unverified endpoint); lightning comes from the Open-Meteo proxy"),
    DataSource("open_meteo_lightning_proxy", "Open-Meteo lightning_potential (CAPE-derived proxy for IMD Damini)", "TIER1", 60,
               ("lightning",)),
    DataSource("datagov_catch", "data.gov.in Marine Fish Landings & species trends", "TIER1", 0, ("catch_statistics",)),
    DataSource("gebco_bathymetry", "GEBCO 2026 15\" Bathymetry Grid", "TIER1", 0, ("bathymetry",)),
    DataSource("marineregions_eez", "Marine Regions VLIZ EEZ / IMBL dataset", "TIER1", 0, ("boundary", "eez", "imbl")),
    DataSource("unep_wcmc_wdpa", "UNEP-WCMC WDPA (marine protected areas)", "TIER1", 0, ("mpa",)),
    DataSource("icg_sar", "Indian Coast Guard SAR station roster (MRCC/MRSC/CGDHQ)", "TIER1", 0,
               ("sar_station", "emergency_contact")),
    DataSource("dof_fishing_ban", "Department of Fisheries uniform annual fishing-ban order", "TIER1", 0,
               ("fishing_ban",)),
    # P5.2 — real gridded values over plain HTTP (no key, no registration),
    # the failover rung after MOSDAC and CMEMS both fail. GIBS is deliberately
    # NOT here: it serves rendered map *imagery*, never a value (2026-09-19
    # stack correction) — a map imagery layer, not a discovery source.
    DataSource("noaa_coastwatch", "NOAA CoastWatch ERDDAP — MUR SST / VIIRS-MODIS chlorophyll", "TIER1", 1440,
               ("sst", "chlorophyll")),
    # The rung weather_intelligence REALLY falls to when the live call fails: the cached Open-Meteo records of the nearest port
    # (data/tier1/ocean + data/tier1/weather, refreshed weekly). It was not in the catalog, so Agent 3 declared INCOIS WW3 and
    # Stormglass as next rungs while the answer used this cache (found 2026-10-09: "cached tier1 fallback, port=gangolli, 192 h old").
    DataSource("open_meteo_port_cache", "Open-Meteo cached port records (offline fixtures, nearest port)", "TIER1", 7 * 24 * 60,
               ("wave_height", "wave_period", "swell_height", "wind_speed", "current_speed")),
    # --- Tier 2: free registration ---
    DataSource("copernicus_cmems", "Copernicus Marine Service (CMEMS) reanalysis", "TIER2", 7200,
               ("sst", "current_speed", "current_direction", "sea_surface_height", "wave_spectrum",
                "chlorophyll", "sea_level_anomaly")),
    DataSource("nasa_ocean_color", "NASA Ocean Color — MODIS-Aqua / VIIRS NRT", "TIER2", 720, ("chlorophyll", "par", "kd490"),
               readable=False, why_not_readable="a listing of granules (`local_catalog` says held_locally=False), no values are read"),
    DataSource("stormglass_tides", "Stormglass.io Marine API — tide extremes", "TIER2", 360, ("tide",)),
    DataSource("gfw_ais", "Global Fishing Watch — AIS fishing effort density", "TIER2", 1440, ("fishing_effort", "ais_presence")),
    # --- Tier 3: gated government portals ---
    # The three MOSDAC "registered NRT" ids point at the SAME files the open products read (data/tier3/mosdac/..., checked in
    # `freshness.SOURCE_FILES`): no separate registered feed is held, so claiming one would be a second name for one dataset.
    DataSource("mosdac_nrt_sst", "MOSDAC Registered NRT — INSAT-3DR/3DS L2/L3 SST", "TIER3", 90, ("sst",),
               readable=False, why_not_readable="the same files as mosdac_open_sst; no separate registered feed is held"),
    DataSource("mosdac_nrt_chl", "MOSDAC Registered NRT — Oceansat-3 OCM Chlorophyll", "TIER3", 360, ("chlorophyll",),
               readable=False, why_not_readable="the same files as mosdac_open_chl; no separate registered feed is held"),
    DataSource("mosdac_nrt_wind", "MOSDAC Registered NRT — Scatterometer ocean winds", "TIER3", 180, ("wind_speed", "wind_direction"),
               readable=False, why_not_readable="archived scatterometer vectors drawn as a map overlay (geospatial.wind_vectors), not a source of the wind reading"),
    DataSource("bhuvan_wms", "Bhuvan / VEDAS (NRSC) WMS thematic layers", "TIER3", 1440, ("wms_layer", "pfz_overlay"),
               readable=False, why_not_readable="a manifest of WMS imagery services, not values"),
    DataSource("icar_cmfri", "ICAR-CMFRI long-term landing archives & stock assessment", "TIER3", 0, ("catch_statistics", "stock_assessment")),
)

_TIER_ORDER: dict[AuthorityTier, int] = {"TIER1": 0, "TIER2": 1, "TIER3": 2}

# Architecture §12.1 — the declared failover chain per primary source. Each
# entry is an ordered list of source ids to try after the primary fails; the
# last rung is almost always a pre-cached local file. A primary absent from
# this map has no declared fallback (a static reference dataset that does not
# go down the same way a live API does).
FALLBACK_CASCADES: dict[str, tuple[str, ...]] = {
    "mosdac_nrt_sst": ("mosdac_open_sst", "copernicus_cmems", "noaa_coastwatch"),
    "mosdac_nrt_chl": ("mosdac_open_chl", "nasa_ocean_color", "copernicus_cmems", "noaa_coastwatch"),
    "mosdac_open_sst": ("copernicus_cmems", "noaa_coastwatch"),
    "mosdac_open_chl": ("nasa_ocean_color", "copernicus_cmems", "noaa_coastwatch"),
    "incois_pfz": ("bhuvan_wms",),  # then the local sector CSV — see load_pfz_advisories
    # weather_intelligence reads Open-Meteo, then the cached port records; it has no reader that returns a weather frame from
    # INCOIS WW3 (that model is read by ocean_analytics as an extra point forecast), so WW3 is not a rung of THIS cascade.
    "open_meteo_marine": ("open_meteo_port_cache",),
    "soi_tide_tables": ("stormglass_tides", "incois_tide_gauge"),
    "incois_erddap": ("copernicus_cmems",),
    "incois_tide_gauge": ("copernicus_cmems",),  # altimetry sea-level anomaly when no gauge is near
    "datagov_catch": ("icar_cmfri",),
    "incois_hazard_osf": ("ndma_sachet",),
}

_BY_ID: dict[str, DataSource] = {s.id: s for s in SOURCE_REGISTRY}


def select_best_source(
    data_type: str, candidates: tuple[DataSource, ...] = SOURCE_REGISTRY
) -> SelectedSource | None:
    """Pick the highest-authority, freshest source covering `data_type`.

    Returns None when nothing in the registry covers the type — callers
    decide whether that's a hard failure or a LOW_DATA confidence signal;
    this function only picks among what exists.
    """
    matches = [s for s in candidates if data_type in s.covers]
    if not matches:
        return None

    best = min(matches, key=lambda s: (_TIER_ORDER[s.authority_tier], s.typical_freshness_minutes))
    same_tier = [s for s in matches if s.authority_tier == best.authority_tier]

    tier_label = best.authority_tier.replace("TIER", "Tier ")
    if len(same_tier) > 1:
        reason = (
            f"{best.dataset} selected: {tier_label} authority, freshest of "
            f"{len(same_tier)} {tier_label} candidates for '{data_type}' "
            f"(typical freshness {best.typical_freshness_minutes} min)."
        )
    else:
        reason = (
            f"{best.dataset} selected: only {tier_label} source for '{data_type}' "
            f"(typical freshness {best.typical_freshness_minutes} min)."
        )
    return SelectedSource(source=best, reason=reason)


@dataclass(frozen=True)
class SourceDecision:
    """The full, renderable account of a source choice — what was picked,
    what it beat, and the one sentence that says why. `narrative` is a
    first-class output (PS "tool selection made visible"), not a log line."""
    chosen: DataSource
    considered: tuple[DataSource, ...]
    fallback_chain: tuple[str, ...]
    narrative: str


def _freshness_phrase(minutes: int) -> str:
    if minutes == 0:
        return "static reference"
    if minutes < 90:
        return f"~{minutes} min old"
    if minutes < 2880:
        return f"~{round(minutes / 60)} h old"
    return f"~{round(minutes / 1440)} d old"


def select_source_with_fallback(
    data_type: str,
    *,
    down: tuple[str, ...] = (),
    candidates: tuple[DataSource, ...] = SOURCE_REGISTRY,
) -> SourceDecision | None:
    """Deterministic priority cascade for `data_type`, honouring both the
    tier/freshness ranking and the Architecture §12.1 fallback chains.

    `down` is the set of source ids currently known-unavailable, explicitly
    passed by the caller. A source whose in-process circuit breaker
    (P5.27, `orca.resilience`) has tripped from repeated failures is skipped
    the same way without the caller having to name it — `validate_arrival`
    feeds that breaker. The picker walks: best-ranked source → its declared
    cascade → next-best source, skipping anything down or breaker-open, and
    narrates the comparison it actually made.

    Returns None only when nothing in the catalog covers `data_type` at all.
    """
    matches = tuple(
        s for s in candidates
        if data_type in s.covers
    )
    if not matches:
        return None

    ranked = sorted(
        matches, key=lambda s: (_TIER_ORDER[s.authority_tier], s.typical_freshness_minutes)
    )
    primary = ranked[0]

    # Build the ordered try-list: each ranked source, with its §12.1 cascade
    # spliced in right after it, de-duplicated, order preserved.
    try_order: list[DataSource] = []
    for src in ranked:
        for sid in (src.id, *FALLBACK_CASCADES.get(src.id, ())):
            s = _BY_ID.get(sid)
            if s is not None and s not in try_order and data_type in s.covers:
                try_order.append(s)

    live = [s for s in try_order if s.id not in down and s.readable and not _breaker_open(s.id)]
    if not live:
        return None
    chosen = live[0]

    if chosen.id == primary.id and len(ranked) == 1:
        narrative = (
            f"{chosen.dataset} selected: only source in the catalog covering "
            f"'{data_type}' ({chosen.authority_tier.replace('TIER', 'Tier ')}, "
            f"{_freshness_phrase(chosen.typical_freshness_minutes)})."
        )
    elif chosen.id == primary.id:
        runner_up = ranked[1]
        same_tier = chosen.authority_tier == runner_up.authority_tier
        basis = "freshness decided it" if same_tier else "higher authority tier"
        narrative = (
            f"{chosen.dataset} chosen over {runner_up.dataset} for '{data_type}': "
            f"{_freshness_phrase(chosen.typical_freshness_minutes)} vs "
            f"{_freshness_phrase(runner_up.typical_freshness_minutes)}, "
            f"{'same ' + chosen.authority_tier.replace('TIER', 'Tier ') + ' authority' if same_tier else 'Tier gap'} — {basis}."
        )
    else:
        why_primary = (
            f"cannot serve values ({primary.why_not_readable})" if not primary.readable
            else f"unavailable ({', '.join(down) or 'no live response'})"
        )
        narrative = (
            f"{chosen.dataset} selected as fallback for '{data_type}': "
            f"{primary.dataset} {why_primary}; "
            f"dropped {try_order.index(chosen)} rung(s) down the declared cascade "
            f"({chosen.authority_tier.replace('TIER', 'Tier ')}, "
            f"{_freshness_phrase(chosen.typical_freshness_minutes)}). Confidence lowered accordingly."
        )

    return SourceDecision(
        chosen=chosen,
        considered=tuple(try_order),
        fallback_chain=(primary.id, *FALLBACK_CASCADES.get(primary.id, ())),
        narrative=narrative,
    )


# --- P2.6 (`R-AGENT-2`, `R-PS-4`): arrival validation ------------------------
#
# orca_final §3.2 says Agent 3 validates what arrives, and nothing in this
# module did: `select_source_with_fallback` picked a source and the cascade
# only ever moved when a caller already *knew* a source was down. An empty
# payload, an all-NaN grid, an out-of-range value or a timestamp stale past
# the source's own class is a failure, and a failure has to fall through the
# cascade like any other — otherwise ORCA cites a Tier-1 dataset for a file
# with nothing in it.
#
# Only the sources ORCA holds on disk can be checked *before* the fetch. Live
# APIs (Open-Meteo, SACHET, Damini) cannot: a probe would be a second request
# per query, and an API that answers a probe can still fail the real call a
# second later. Those come back `checked=False`, which the span reports as
# "unverified" — never as "valid". Claiming a validation that did not happen
# is the same fabrication as claiming a reading that was not taken.

_MAX_LATITUDE, _MAX_LONGITUDE = 90.0, 180.0


@dataclass(frozen=True)
class ArrivalCheck:
    source_id: str
    checked: bool  # False = no local probe exists; `ok` is then meaningless
    ok: bool
    detail: str
    # A source can arrive and still be old (an expired PFZ advisory is still the best information held, so it is NOT
    # rejected). `stale` says so, so the decision, the card and the trace can: "ok" never means "current".
    stale: bool = False


def _finite_number(value: Any) -> bool:
    import math

    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Probe(NamedTuple):
    ok: bool
    detail: str
    stale: bool = False
    # Whether a failure counts against the source's circuit breaker. A source that is UNREADABLE or holds impossible values
    # is broken for everyone; a source that merely does not cover THIS station or THIS time is fine for the next question
    # (found 2026-10-10: one station's gap opened the breaker for every station).
    systemic: bool = True


# A probe returns a `Probe` and is given the question's context: {"lat", "lon", "when"} (any may be missing).
# 2026-10-10 (audit 4): probes used to answer "is the FILE readable", not "can it answer THIS question".

def _check_pfz(ctx: dict[str, Any]) -> Probe:
    """Probe the INCOIS advisory rows the PFZ agent actually reads (`analytics_loaders.load_pfz_latest`, with their age).
    Until 2026-10-10 this probed the cloud-cover FALLBACK geojson (six undated front cells): "6 PFZ features on disk, ok"
    said nothing about the advisory the answer quotes. An old advisory is not rejected (the pointer is still the best
    information there is), it is reported as stale with its date and age."""
    from orca.data.analytics_loaders import load_pfz_latest

    rows = load_pfz_latest()
    if not rows:
        return Probe(False, "no INCOIS PFZ advisory rows on disk")
    newest = min(rows, key=lambda r: float(r["age_days"]) if r.get("age_days") is not None else 1e6)
    age = newest.get("age_days")
    stale = bool(newest.get("expired")) or (isinstance(age, (int, float)) and age >= 1)
    age_txt = f"{age:g} day(s) old" if isinstance(age, (int, float)) else "age unknown"
    state = "expired" if newest.get("expired") else "current"
    return Probe(True, f"{len(rows)} advisory node(s); newest valid for {newest.get('valid_for')}, {age_txt}, {state}", stale)


def _tide_context(ctx: dict[str, Any]) -> tuple[str | None, Any]:
    """(station code, requested time) for the tide probe: the nearest SOI station to the position, and the start of the
    time the question asks about (now when it names none)."""
    from datetime import UTC, datetime

    when = ctx.get("when")
    if isinstance(when, str):
        try:
            when = datetime.fromisoformat(when)
        except ValueError:
            when = None
    when = when or datetime.now(UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    lat, lon = ctx.get("lat"), ctx.get("lon")
    if lat is None or lon is None:
        return None, when
    from orca.agents.ocean_analytics import nearest_station

    return nearest_station(float(lat), float(lon))["station_code"], when


def _check_tide_tables(ctx: dict[str, Any]) -> Probe:
    from orca.data.analytics_loaders import load_soi_tide_events

    events = load_soi_tide_events()
    if not events:
        return Probe(False, "Survey of India tide table is empty")
    # Per STATION and per REQUESTED TIME. "137 tide events, heights within range" was true of the whole file while the
    # station the question was about had no rows, or its rows ended before the time asked for, and the answer then said
    # "tide table ends before the requested time".
    code, when = _tide_context(ctx)
    if code is not None:
        mine = [e for e in events if e["station_code"] == code]
        if not mine:
            return Probe(False, f"no Survey of India rows for station {code}", systemic=False)
        last = max(e["when"] for e in mine)
        if last < when:
            return Probe(False, f"Survey of India table for {code} ends {last.date()}, before the requested {when.date()}", systemic=False)
        events = mine
    heights = [e.get("height_m") for e in events]
    if not any(_finite_number(h) for h in heights):
        return Probe(False, f"{len(events)} tide events, none with a readable height")
    # A tide height outside this band is a parse failure, not a tide — the
    # largest range anywhere on the Indian coast (Gulf of Khambhat) is ~11 m.
    out_of_range = [h for h in heights if isinstance(h, (int, float)) and _finite_number(h) and not (-2.0 <= float(h) <= 15.0)]
    if out_of_range:
        return Probe(False, f"tide height out of physical range: {out_of_range[0]} m")
    where = f" for station {code}, covering {when.date()}" if code is not None else ""
    return Probe(True, f"{len(events)} tide events{where}, heights within range")


def _check_stormglass_tides(ctx: dict[str, Any]) -> Probe:
    """The second tide rung is a CACHE of Stormglass extremes on disk (`refresh_tide_tables.py` writes it), not a live call:
    it was labelled "live source, validated on fetch" and never checked, although it is exactly what a station with no
    Survey of India rows falls back to."""
    from orca.data.analytics_loaders import load_stormglass_tide_events

    code, when = _tide_context(ctx)
    if code is None:
        return Probe(True, "Stormglass cache present (no position to check a station against)")
    events = load_stormglass_tide_events(code)
    if not events:
        return Probe(False, f"no cached Stormglass extremes for station {code}", systemic=False)
    last = max(e["when"] for e in events)
    if last < when:
        return Probe(False, f"cached Stormglass extremes for {code} end {last.date()}, before the requested {when.date()}", systemic=False)
    return Probe(True, f"{len(events)} cached Stormglass extremes for station {code}, covering {when.date()}")


_PORT_CACHE_MAX_KM = 300.0   # a cached port further than this is not "the data for this place" (weather used any nearest one, silently)
_PORT_CACHE_STALE_HOURS = 24.0


def _check_open_meteo_port_cache(ctx: dict[str, Any]) -> Probe:
    """Is there a cached Open-Meteo record near the position, and how old is it?"""
    from datetime import UTC, datetime

    from orca.agents import weather_intelligence as wi
    from orca.data.loaders import cached_weather_path, load_json
    from orca.data.normalize import to_utc_iso

    lat, lon = ctx.get("lat"), ctx.get("lon")
    try:
        coords = wi.port_coordinates()
        if lat is None or lon is None:
            port = next(iter(coords)) if coords else None
            if port is None:
                raise RuntimeError("no cached ports")
            km = 0.0
        else:
            port = wi._nearest_port(float(lat), float(lon), wi.CACHED_MARINE_PORTS)
            km = wi._haversine_km(float(lat), float(lon), *coords[port])
    except RuntimeError:
        return Probe(False, "no cached Open-Meteo port records on disk")
    if km > _PORT_CACHE_MAX_KM:
        return Probe(False, f"the nearest cached port ({port}) is {km:.0f} km away, beyond {_PORT_CACHE_MAX_KM:.0f} km", systemic=False)
    raw = load_json(cached_weather_path(port))
    acquired = datetime.fromisoformat(to_utc_iso(raw["hourly"]["time"][0], raw.get("utc_offset_seconds", 0)))
    age_h = max(0.0, (datetime.now(UTC) - acquired).total_seconds() / 3600)
    stale = age_h >= _PORT_CACHE_STALE_HOURS
    return Probe(True, f"cached record for port {port}, {km:.0f} km away, {age_h:.0f} h old", stale)


_GRID_STALE_DAYS = 3.0   # freshness.RECENCY_BANDS: the daily satellite products are "fresh" up to 3 days


def _grid_probe(source_id: str):
    """A probe for a satellite grid ORCA reads from disk (INSAT SST, EOS-06 chlorophyll, CMEMS): is there a cell within reach of
    THIS position, and how old is the granule? Until 2026-10-10 these were "live source, validated on fetch" although they are
    files, so Agent 3's pick said nothing about whether the place had any reading (A5)."""

    def probe(ctx: dict[str, Any]) -> Probe | None:
        dtype = ctx.get("data_type")
        if dtype not in ("sst", "chlorophyll"):
            return None
        lat, lon = ctx.get("lat"), ctx.get("lon")
        if lat is None or lon is None:
            return None
        from orca.agents import ocean_analytics as oa

        reading = oa.grid_reading(source_id, dtype, float(lat), float(lon))
        if reading is None:
            return Probe(False, f"{source_id} holds no {dtype} cell within {oa._READING_MAX_KM:.0f} km of the position", systemic=False)
        age = reading.get("age_days")
        stale = isinstance(age, (int, float)) and age > _GRID_STALE_DAYS
        age_txt = f"{age:g} d old" if isinstance(age, (int, float)) else "age unknown"
        return Probe(True, f"{reading['source']}: cell {reading['cell_distance_km']} km away, observed {reading.get('observed')}, {age_txt}", stale)

    return probe


def source_report_entry(decision: dict[str, Any] | None, used: str | list[str] | None) -> dict[str, Any]:
    """{decided, used, obeyed} for one data type. obeyed: `used` is the decided rung, or a LATER rung of the declared cascade
    (the decided one failed at fetch). `used` may be a list when an agent really reads several sources for one data type
    (geospatial reads the treaty lines AND the protected-area file for "boundary"): the decision is obeyed when it is among them.
    None, never True, when no decision was in state."""
    if not decision:
        return {"decided": None, "used": used, "obeyed": None}
    decided = decision.get("chosen")
    considered = decision.get("considered") or []
    used_all: list[str] = [u for u in used if u is not None] if isinstance(used, list) else ([used] if used is not None else [])
    obeyed = decided in used_all or any(
        u in considered and decided in considered and considered.index(u) > considered.index(decided) for u in used_all
    )
    return {"decided": decided, "used": used, "obeyed": obeyed}


def source_check(reports: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    """The run-level answer to "did every specialist use what marine_data_discovery decided?" (A6, 2026-10-10).
    `reports` maps an agent name to its `source_report`. A difference is never hidden: it is listed, logged at WARNING, and the
    line says so; an entry with no decision to compare against is `unknown`, not counted as obeyed."""
    checked = obeyed = 0
    unknown: list[str] = []
    mismatches: list[dict[str, Any]] = []
    for agent, report in reports.items():
        for dtype, entry in (report or {}).items():
            flag = entry.get("obeyed")
            if flag is None:
                unknown.append(f"{agent}:{dtype}")
                continue
            checked += 1
            if flag:
                obeyed += 1
            else:
                mismatches.append({"agent": agent, "data_type": dtype, "decided": entry.get("decided"), "used": entry.get("used")})
    if mismatches:
        logger.warning("source mismatch: %s", mismatches)
        line = "; ".join(f"{m['agent']} used {m['used']} for {m['data_type']} but marine data discovery decided {m['decided']}" for m in mismatches)
    elif checked:
        line = f"Every source used matches what marine data discovery decided ({checked} checks)."
    else:
        line = "No source decisions were available to compare."
    return {"checked": checked, "obeyed": obeyed, "mismatches": mismatches, "unknown": unknown, "line": line}


_DATA_TYPE_LABEL = {
    "wave_height": "wave height", "wind_speed": "wind speed", "lightning": "lightning", "cyclone": "cyclone alerts",
    "boundary": "boundaries", "pfz": "fishing zones", "tide": "tides", "catch_statistics": "catch statistics",
    "current_speed": "currents", "sst": "sea surface temperature", "chlorophyll": "chlorophyll", "bathymetry": "depth",
    "eez": "the maritime boundary", "mpa": "protected areas", "hazard": "hazard alerts", "fishing_ban": "the fishing ban",
}


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def discovery_trace_line(selections: list[dict[str, Any]], unusable: list[str] | None = None) -> str:
    """One plain sentence for the trace, built from the real decisions: "Chose data sources: wave height and wind speed from
    Open-Meteo ...; tides from ... (Survey of India covers none of this: fell back); no usable source for: ..." Data types
    that share a source are grouped. Stale data and a fall down the cascade are said, never left out."""
    groups: dict[str, dict[str, Any]] = {}
    for s in selections:
        if not s.get("chosen"):
            continue
        g = groups.setdefault(s["chosen"], {"dataset": s.get("chosen_dataset") or s["chosen"], "labels": [], "stale": False, "fell": None})
        g["labels"].append(_DATA_TYPE_LABEL.get(s["data_type"], str(s["data_type"]).replace("_", " ")))
        if (s.get("arrival") or {}).get("stale"):
            g["stale"] = True
        if s.get("fell_through") and s.get("rejected"):
            g["fell"] = s["rejected"][0]["reason"]
    parts = []
    for g in groups.values():
        text = f"{_join(g['labels'])} from {g['dataset']}"
        notes = []
        if g["fell"]:
            notes.append(f"fell back: {g['fell']}")
        if g["stale"]:
            notes.append("not current")
        parts.append(text + (f" ({'; '.join(notes)})" if notes else ""))
    line = "Chose data sources: " + "; ".join(parts) + "." if parts else "No data source was needed."
    if unusable:
        line += " No usable source for: " + ", ".join(_DATA_TYPE_LABEL.get(u, u.replace("_", " ")) for u in unusable) + "."
    return line


def _check_osf_points(product: str) -> Probe:
    from orca.data.analytics_loaders import load_osf_point_forecasts

    points = load_osf_point_forecasts(product)
    if not points:
        return Probe(False, f"no INCOIS OSF {product.upper()} point series extracted")
    placed = [
        p for p in points
        if _finite_number(p.get("lat")) and _finite_number(p.get("lon"))
        and abs(float(p["lat"])) <= _MAX_LATITUDE and abs(float(p["lon"])) <= _MAX_LONGITUDE
    ]
    if not placed:
        return Probe(False, f"{len(points)} OSF {product.upper()} points, none with usable coordinates")
    return Probe(True, f"{len(placed)} OSF {product.upper()} point series")


def _check_boundaries(ctx: dict[str, Any]) -> Probe:
    from orca.agents import geospatial

    dtype = ctx.get("data_type")
    if dtype in ("boundary", "imbl"):
        vintage = geospatial.boundary_line_vintage() or geospatial.boundary_data_vintage()
    else:
        vintage = geospatial.boundary_data_vintage()
    if not vintage:
        return Probe(False, "boundary geometry has no recorded acquisition date")
    return Probe(True, f"boundary geometry acquired {vintage}")


# source_id -> a probe over what is actually on disk. A source absent from
# this map is unverifiable before the fetch, not assumed good.
_ARRIVAL_PROBES: dict[str, Any] = {
    "incois_pfz": _check_pfz,
    "soi_tide_tables": _check_tide_tables,
    "stormglass_tides": _check_stormglass_tides,
    "open_meteo_port_cache": _check_open_meteo_port_cache,
    "mosdac_open_sst": _grid_probe("mosdac_open_sst"),
    "mosdac_open_chl": _grid_probe("mosdac_open_chl"),
    "copernicus_cmems": _grid_probe("copernicus_cmems"),
    "incois_osf_ww3": lambda ctx: _check_osf_points("ww3"),
    "incois_osf_hycom": lambda ctx: _check_osf_points("hycom"),
    "marineregions_eez": _check_boundaries,
    "unep_wcmc_wdpa": _check_boundaries,
}

# The breaker keys the SPECIALISTS record failures under, where they differ from this catalog's ids (weather_intelligence
# trips "open_meteo" and "incois_hazard_bulletins"). Agent 3 asked the breaker about "open_meteo_marine", which nothing ever
# trips, so a source the specialists had already given up on still looked healthy to it (audit 4, 2026-10-10).
_BREAKER_KEY: dict[str, str] = {"open_meteo_marine": "open_meteo", "incois_hazard_osf": "incois_hazard_bulletins"}


def _breaker_open(source_id: str) -> bool:
    return resilience.circuit_open(source_id) or resilience.circuit_open(_BREAKER_KEY.get(source_id, source_id))


def validate_arrival(source_id: str, ctx: dict[str, Any] | None = None) -> ArrivalCheck:
    """Did this source's data actually arrive in a usable state?

    A probe that raises is a failed arrival, not a crashed query — the whole
    point is to fall through the cascade rather than take the request down.
    Every result (pass or fail) feeds the P5.27 circuit breaker, so a source
    that keeps failing its arrival check stops being re-tried as the primary
    pick on every query once it has tripped — `select_source_with_fallback`
    reads the same breaker.
    """
    probe = _ARRIVAL_PROBES.get(source_id)
    if probe is None:
        return ArrivalCheck(source_id, checked=False, ok=True, detail="live source — validated on fetch, not before it")
    try:
        result = probe(ctx or {})
    except Exception as exc:  # an unreadable file IS the failure being detected
        result = Probe(False, f"unreadable: {type(exc).__name__}: {exc}")
    if result is None:   # the probe has nothing to say about this data type
        return ArrivalCheck(source_id, checked=False, ok=True, detail="no probe for this data type: validated on fetch, not before it")
    if result.ok:
        resilience.record_success(source_id)
    elif result.systemic:
        resilience.record_failure(source_id)
    return ArrivalCheck(source_id, checked=True, ok=result.ok, detail=result.detail, stale=result.stale)


def select_validated_source(
    data_type: str, *, down: tuple[str, ...] = (), ctx: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """`select_source_with_fallback`, plus the arrival check — and the cascade
    fall-through that failing it is supposed to cause.

    Walks the declared §12.1 cascade, validating each rung, and returns the
    first one whose data is actually there. Every rung it rejected is named in
    `rejected`, because "we tried INCOIS first and its advisory file was empty"
    is the sentence that makes the fallback honest.

    Returns None only when nothing in the catalog covers `data_type` at all.
    """
    tried: list[dict[str, str]] = []
    unavailable = list(down)
    for _ in range(len(SOURCE_REGISTRY)):  # bounded: each pass marks one more source down
        decision = select_source_with_fallback(data_type, down=tuple(unavailable))
        if decision is None:
            break
        check = validate_arrival(decision.chosen.id, {**(ctx or {}), "data_type": data_type})
        if check.ok:
            return {
                "data_type": data_type,
                "chosen": decision.chosen.id,
                "chosen_dataset": decision.chosen.dataset,
                "narrative": decision.narrative,
                "considered": [s.id for s in decision.considered],
                "fallback_chain": list(decision.fallback_chain),
                "arrival": {"checked": check.checked, "ok": True, "detail": check.detail, "stale": check.stale},
                "rejected": tried,
                "fell_through": bool(tried),
            }
        tried.append({"source_id": check.source_id, "reason": check.detail})
        unavailable.append(decision.chosen.id)

    if not tried:
        return None
    # Every rung of the cascade failed its arrival check. That is a real
    # outcome and it is reported as one — a data_type with no usable source
    # is LOW_DATA downstream, never a quietly-omitted line.
    return {
        "data_type": data_type,
        "chosen": None,
        "chosen_dataset": None,
        "narrative": (
            f"No usable source for '{data_type}': every rung of the declared cascade failed its "
            f"arrival check ({'; '.join(t['reason'] for t in tried)})."
        ),
        "considered": [t["source_id"] for t in tried],
        "fallback_chain": [],
        "arrival": {"checked": True, "ok": False, "detail": "all rungs failed", "stale": False},
        "rejected": tried,
        "fell_through": True,
    }


def local_catalog(source_id: str) -> list[dict[str, Any]]:
    """What ORCA holds locally *about* a registry source, for the sources whose
    on-disk file is an index rather than the data itself.

    `nasa_ocean_color` is the case that matters: the file on disk is a NASA CMR
    granule listing — it names granules, it does not contain chlorophyll. Every
    entry it returns carries `held_locally: False` so the distinction survives
    into whatever renders it. Without this the cascade advertised a rung whose
    only evidence nobody could see.

    An empty list means "no local index for this source", never "this source
    has no data".
    """
    from orca.data.analytics_loaders import (
        load_bhuvan_wms_services,
        load_gfw_vessel_sample,
        load_nasa_chl_granules,
        load_osf_dataset_manifest,
    )

    if source_id == "nasa_ocean_color":
        return load_nasa_chl_granules()
    if source_id == "bhuvan_wms":
        return [{**svc, "held_locally": False} for svc in load_bhuvan_wms_services()]
    if source_id == "gfw_ais":
        return load_gfw_vessel_sample()
    # The INCOIS manifest is keyed by folder, not by registry id; this is the
    # one mapping between the two, kept here rather than in the loader so the
    # loader stays a plain read of the file as written.
    manifest_key = {
        "incois_osf_ww3": "osf_ww3",
        "incois_osf_hycom": "osf_hycom",
        "incois_pfz": "pfz",
    }.get(source_id)
    if manifest_key:
        entry = (load_osf_dataset_manifest().get("sources") or {}).get(manifest_key)
        # `held_locally: True` here, unlike every other branch: these ARE the
        # grids on disk, and this is their licence and provenance record.
        return [{**entry, "folder": manifest_key, "held_locally": True}] if entry else []
    return []


def load_pfz_advisories() -> dict[str, Any]:
    """Cached Potential Fishing Zone advisories for the pilot region (plan
    §4 S4 Day 6 — "`/zones` surface scaffold rendering PFZ from cached
    advisories"). Live INCOIS scraping is `scripts/scrape_pfz_advisories.py`;
    this reads its already-fetched fallback output, matching the fixture
    strategy — the surface renders from what's on disk, not from a live
    call every request.

    Returns an empty FeatureCollection with a warning if the file is missing
    (plan §5.7 item 6 — "no number is ever invented to fill a hole").
    """
    try:
        return json.loads(PFZ_FALLBACK_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning(
            "PFZ fallback file not found at %s — returning empty FeatureCollection. "
            "Ensure data/incois_osf_pfz/pfz/pfz_fallback_pilot_region.geojson is present.",
            PFZ_FALLBACK_FILE,
        )
        return {"type": "FeatureCollection", "features": []}


if __name__ == "__main__":
    picked = select_best_source("wave_height")
    assert picked is not None
    assert picked.source.id == "open_meteo_marine", picked.source.id
    assert "Tier 1" in picked.reason and "min)" in picked.reason
    assert select_best_source("nonexistent_type") is None

    # cascade-aware picker: MOSDAC NRT SST beats Copernicus on the ranking,
    # and falls to the open MOSDAC product when NRT is down.
    d = select_source_with_fallback("sst")
    assert d is not None
    # TIER1 MOSDAC Open beats the TIER3 registered NRT stream on authority,
    # which is the intended order: same instrument, open licence.
    assert d.chosen.id == "mosdac_open_sst", d.chosen.id
    d_down = select_source_with_fallback("sst", down=("mosdac_nrt_sst", "mosdac_open_sst"))
    assert d_down is not None
    assert d_down.chosen.id == "copernicus_cmems", d_down.chosen.id
    assert "fallback" in d_down.narrative.lower()
    assert select_source_with_fallback("nonexistent_type") is None

    pfz = load_pfz_advisories()
    assert pfz["type"] == "FeatureCollection" and pfz["features"]

    # P2.6 arrival validation. A live source cannot be probed before the
    # fetch, and says so rather than claiming a check it did not run.
    live = validate_arrival("open_meteo_marine")
    assert live.checked is False, "a live API must never report a pre-fetch validation"
    on_disk = validate_arrival("incois_pfz")
    assert on_disk.checked is True and on_disk.ok is True, on_disk
    missing = validate_arrival("not_a_source")
    assert missing.checked is False

    validated_pfz = select_validated_source("pfz")
    assert validated_pfz is not None and validated_pfz["chosen"] == "incois_pfz", validated_pfz
    assert validated_pfz["fell_through"] is False and validated_pfz["rejected"] == []
    assert select_validated_source("nonexistent_type") is None

    # Forcing the validated primary down must move to the next rung that
    # actually covers the type. `incois_pfz`'s declared §12.1 fallback is
    # `bhuvan_wms`, which covers "pfz_overlay" and NOT "pfz" — so with INCOIS
    # down there is genuinely no source for "pfz", and the honest answer is
    # None rather than a rung that cannot answer the question.
    assert select_validated_source("pfz", down=("incois_pfz",)) is None

    # "tide" does have a real second rung (Stormglass), so it is the one that
    # proves the fall-through rather than the absence of one.
    fell = select_validated_source("tide", down=("soi_tide_tables",))
    assert fell is not None and fell["chosen"] == "stormglass_tides", fell

    # Local catalogs: an index, explicitly not the data.
    nasa = local_catalog("nasa_ocean_color")
    assert nasa and all(g["held_locally"] is False for g in nasa), nasa[:1]
    assert local_catalog("bhuvan_wms"), "Bhuvan manifest should list WMS services"
    assert local_catalog("soi_tide_tables") == []
    ww3_cat = local_catalog("incois_osf_ww3")
    assert ww3_cat and "license" in ww3_cat[0], ww3_cat
    print("discovery self-check ok:", d.narrative)

    # D2 fixture — Agent 3's cascade decision when the primary SST source is
    # down, recorded in the AgentResult shape the fixture harness expects.
    from orca.contracts import AgentResult, Confidence, SourceProvenance
    from orca.testing.fixtures import record_fixture

    fixture = AgentResult(
        agent_name="discovery",
        query_id="fixture-sst-fallback",
        reasoning_depth="STANDARD",
        inputs_consumed={"data_type": "sst", "down": ["mosdac_nrt_sst", "mosdac_open_sst"]},
        outputs={
            "source_id": d_down.chosen.id,
            "dataset": d_down.chosen.dataset,
            "reason": d_down.narrative,
            "considered": [s.id for s in d_down.considered],
            "fallback_chain": list(d_down.fallback_chain),
        },
        source_provenance=SourceProvenance(
            dataset=d_down.chosen.dataset, acquisition_timestamp="", freshness_minutes=0
        ),
        confidence=Confidence(score="MEDIUM", rationale="fell to a declared §12.1 fallback rung"),
    )
    record_fixture(fixture, "sst_fallback_cascade")
    print("discovery fixture written: discovery__sst_fallback_cascade.json")

    # ... and the healthy primary-pick shape, so consumers have both branches.
    d_chl = select_source_with_fallback("chlorophyll")
    assert d_chl is not None
    record_fixture(
        AgentResult(
            agent_name="discovery",
            query_id="fixture-chlorophyll-primary",
            reasoning_depth="STANDARD",
            inputs_consumed={"data_type": "chlorophyll", "down": []},
            outputs={
                "source_id": d_chl.chosen.id,
                "dataset": d_chl.chosen.dataset,
                "reason": d_chl.narrative,
                "considered": [s.id for s in d_chl.considered],
                "fallback_chain": list(d_chl.fallback_chain),
            },
            source_provenance=SourceProvenance(
                dataset=d_chl.chosen.dataset, acquisition_timestamp="", freshness_minutes=0
            ),
            confidence=Confidence(score="HIGH", rationale="primary source available"),
        ),
        "chlorophyll_primary",
    )
    print("discovery fixture written: discovery__chlorophyll_primary.json")
