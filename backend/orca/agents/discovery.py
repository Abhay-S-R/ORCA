"""Agent 3 — Marine Data Discovery (plan §4 S4 / Phase 2 D2 Day 8).

Phase 1 shipped only the seed registry and `select_best_source`. Phase 2 D2
Day 8 grows this into the full catalog across all 25 datasets in
`docs/ORCA_Dataset_Master_List.md`, wires in the declared per-source fallback
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
from typing import Any, Literal

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


@dataclass(frozen=True)
class SelectedSource:
    source: DataSource
    reason: str


# Full catalog — every dataset in docs/ORCA_Dataset_Master_List.md that ORCA
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
               365 * 24 * 60, ("salinity", "buoy_telemetry", "wave_spectrum")),
    DataSource("incois_osf_ww3", "INCOIS Ocean State Forecast (WaveWatch III)", "TIER1", 360,
               ("wave_height", "wave_period")),
    DataSource("incois_osf_hycom", "INCOIS Ocean State Forecast (HYCOM currents)", "TIER1", 360,
               ("current_speed", "current_direction")),
    DataSource("mosdac_open_sst", "MOSDAC Open Data — INSAT-3DR L3 SST (daily)", "TIER1", 360, ("sst",)),
    DataSource("mosdac_open_chl", "MOSDAC Open Data — EOS-06 OCM-3 Chlorophyll-a", "TIER1", 1440, ("chlorophyll",)),
    DataSource("soi_tide_tables", "Survey of India 2026 Annual Tide Tables", "TIER1", 0, ("tide",)),
    DataSource("incois_tide_gauge", "INCOIS Tide Gauge Network (TEWS)", "TIER1", 15, ("tide_observed", "sea_level_anomaly")),
    DataSource("incois_pfz", "INCOIS Potential Fishing Zone advisories", "TIER1", 1440, ("pfz",)),
    DataSource("incois_hazard_osf", "INCOIS Hazard Alerts & Ocean State Warnings", "TIER1", 30,
               ("hazard", "swell_surge", "high_wave", "kallakkadal")),
    DataSource("ndma_sachet", "NDMA SACHET / IMD CAP alert feed", "TIER1", 15, ("cyclone", "hazard", "cap_alert")),
    # Track + cone geometry only (IMD RSMC has no machine-readable track). Never
    # feeds the verdict — the alert level stays SACHET's.
    DataSource("gdacs_tc", "GDACS tropical cyclone track and cone (EU JRC; JTWC forecast)", "TIER2", 360,
               ("cyclone_track",)),
    DataSource("damini_lightning", "IMD Damini Lightning Nowcast", "TIER1", 10, ("lightning",)),
    DataSource("datagov_catch", "data.gov.in Marine Fish Landings & species trends", "TIER1", 0, ("catch_statistics",)),
    DataSource("gebco_bathymetry", "GEBCO 2026 15\" Bathymetry Grid", "TIER1", 0, ("bathymetry",)),
    DataSource("unep_wcmc_wdpa", "UNEP-WCMC WDPA / OSM (marine boundaries)", "TIER1", 0, ("boundary", "mpa")),
    DataSource("marineregions_eez", "Marine Regions VLIZ EEZ / IMBL dataset", "TIER1", 0, ("eez", "imbl", "boundary")),
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
    # --- Tier 2: free registration ---
    DataSource("copernicus_cmems", "Copernicus Marine Service (CMEMS) reanalysis", "TIER2", 7200,
               ("sst", "current_speed", "current_direction", "sea_surface_height", "wave_spectrum",
                "chlorophyll", "sea_level_anomaly")),
    DataSource("nasa_ocean_color", "NASA Ocean Color — MODIS-Aqua / VIIRS NRT", "TIER2", 720, ("chlorophyll", "par", "kd490")),
    DataSource("stormglass_tides", "Stormglass.io Marine API — tide extremes", "TIER2", 360, ("tide",)),
    DataSource("gfw_ais", "Global Fishing Watch — AIS fishing effort density", "TIER2", 1440, ("fishing_effort", "ais_presence")),
    # --- Tier 3: gated government portals ---
    DataSource("mosdac_nrt_sst", "MOSDAC Registered NRT — INSAT-3DR/3DS L2/L3 SST", "TIER3", 90, ("sst",)),
    DataSource("mosdac_nrt_chl", "MOSDAC Registered NRT — Oceansat-3 OCM Chlorophyll", "TIER3", 360, ("chlorophyll",)),
    DataSource("mosdac_nrt_wind", "MOSDAC Registered NRT — Scatterometer ocean winds", "TIER3", 180, ("wind_speed", "wind_direction")),
    DataSource("bhuvan_wms", "Bhuvan / VEDAS (NRSC) WMS thematic layers", "TIER3", 1440, ("wms_layer", "pfz_overlay")),
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
    "open_meteo_marine": ("incois_osf_ww3", "stormglass_tides"),
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

    live = [s for s in try_order if s.id not in down and not resilience.circuit_open(s.id)]
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
        narrative = (
            f"{chosen.dataset} selected as fallback for '{data_type}': "
            f"{primary.dataset} unavailable ({', '.join(down) or 'no live response'}); "
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


def _finite_number(value: Any) -> bool:
    import math

    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _check_pfz() -> tuple[bool, str]:
    doc = load_pfz_advisories()
    features = doc.get("features") or []
    if not features:
        return False, "PFZ advisory file holds no features"
    return True, f"{len(features)} PFZ advisory feature(s) on disk"


def _check_tide_tables() -> tuple[bool, str]:
    from orca.data.analytics_loaders import load_soi_tide_events

    events = load_soi_tide_events()
    if not events:
        return False, "Survey of India tide table is empty"
    heights = [e.get("height_m") for e in events]
    if not any(_finite_number(h) for h in heights):
        return False, f"{len(events)} tide events, none with a readable height"
    # A tide height outside this band is a parse failure, not a tide — the
    # largest range anywhere on the Indian coast (Gulf of Khambhat) is ~11 m.
    out_of_range = [h for h in heights if isinstance(h, (int, float)) and _finite_number(h) and not (-2.0 <= float(h) <= 15.0)]
    if out_of_range:
        return False, f"tide height out of physical range: {out_of_range[0]} m"
    return True, f"{len(events)} tide events, heights within range"


def _check_osf_points(product: str) -> tuple[bool, str]:
    from orca.data.analytics_loaders import load_osf_point_forecasts

    points = load_osf_point_forecasts(product)
    if not points:
        return False, f"no INCOIS OSF {product.upper()} point series extracted"
    placed = [
        p for p in points
        if _finite_number(p.get("lat")) and _finite_number(p.get("lon"))
        and abs(float(p["lat"])) <= _MAX_LATITUDE and abs(float(p["lon"])) <= _MAX_LONGITUDE
    ]
    if not placed:
        return False, f"{len(points)} OSF {product.upper()} points, none with usable coordinates"
    return True, f"{len(placed)} OSF {product.upper()} point series"


def _check_boundaries() -> tuple[bool, str]:
    from orca.agents import geospatial

    vintage = geospatial.boundary_data_vintage()
    if not vintage:
        return False, "boundary geometry has no recorded acquisition date"
    return True, f"boundary geometry acquired {vintage}"


# source_id -> a probe over what is actually on disk. A source absent from
# this map is unverifiable before the fetch, not assumed good.
_ARRIVAL_PROBES: dict[str, Any] = {
    "incois_pfz": _check_pfz,
    "soi_tide_tables": _check_tide_tables,
    "incois_osf_ww3": lambda: _check_osf_points("ww3"),
    "incois_osf_hycom": lambda: _check_osf_points("hycom"),
    "marineregions_eez": _check_boundaries,
    "unep_wcmc_wdpa": _check_boundaries,
}


def validate_arrival(source_id: str) -> ArrivalCheck:
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
        ok, detail = probe()
    except Exception as exc:  # an unreadable file IS the failure being detected
        ok, detail = False, f"unreadable: {type(exc).__name__}: {exc}"
    if ok:
        resilience.record_success(source_id)
    else:
        resilience.record_failure(source_id)
    return ArrivalCheck(source_id, checked=True, ok=ok, detail=detail)


def select_validated_source(
    data_type: str, *, down: tuple[str, ...] = ()
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
        check = validate_arrival(decision.chosen.id)
        if check.ok:
            return {
                "data_type": data_type,
                "chosen": decision.chosen.id,
                "chosen_dataset": decision.chosen.dataset,
                "narrative": decision.narrative,
                "considered": [s.id for s in decision.considered],
                "fallback_chain": list(decision.fallback_chain),
                "arrival": {"checked": check.checked, "ok": True, "detail": check.detail},
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
        "arrival": {"checked": True, "ok": False, "detail": "all rungs failed"},
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
