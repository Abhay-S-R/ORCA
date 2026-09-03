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
    DataSource("incois_erddap", "INCOIS ERDDAP Data Server", "TIER1", 180,
               ("sst", "salinity", "buoy_telemetry", "wave_spectrum")),
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
    DataSource("damini_lightning", "IMD Damini Lightning Nowcast", "TIER1", 10, ("lightning",)),
    DataSource("datagov_catch", "data.gov.in Marine Fish Landings & species trends", "TIER1", 0, ("catch_statistics",)),
    DataSource("gebco_bathymetry", "GEBCO 2026 15\" Bathymetry Grid", "TIER1", 0, ("bathymetry",)),
    DataSource("unep_wcmc_wdpa", "UNEP-WCMC WDPA / OSM (marine boundaries)", "TIER1", 0, ("boundary", "mpa")),
    DataSource("marineregions_eez", "Marine Regions VLIZ EEZ / IMBL dataset", "TIER1", 0, ("eez", "imbl", "boundary")),
    # --- Tier 2: free registration ---
    DataSource("copernicus_cmems", "Copernicus Marine Service (CMEMS) reanalysis", "TIER2", 7200,
               ("sst", "current_speed", "current_direction", "sea_surface_height", "wave_spectrum")),
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
    "mosdac_nrt_sst": ("mosdac_open_sst", "copernicus_cmems", "incois_erddap"),
    "mosdac_nrt_chl": ("mosdac_open_chl", "nasa_ocean_color"),
    "mosdac_open_sst": ("copernicus_cmems", "incois_erddap"),
    "mosdac_open_chl": ("nasa_ocean_color",),
    "incois_pfz": ("bhuvan_wms",),  # then the local sector CSV — see load_pfz_advisories
    "open_meteo_marine": ("incois_osf_ww3", "stormglass_tides"),
    "soi_tide_tables": ("stormglass_tides", "incois_tide_gauge"),
    "incois_erddap": ("copernicus_cmems",),
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

    `down` is the set of source ids currently known-unavailable (circuit
    breaker tripped, live fetch failed). The picker walks: best-ranked
    source → its declared cascade → next-best source, skipping anything in
    `down`, and narrates the comparison it actually made.

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

    live = [s for s in try_order if s.id not in down]
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
    assert d.chosen.id == "incois_erddap", d.chosen.id
    d_down = select_source_with_fallback("sst", down=("incois_erddap", "mosdac_open_sst"))
    assert d_down is not None
    assert d_down.chosen.id == "copernicus_cmems", d_down.chosen.id
    assert "fallback" in d_down.narrative.lower()
    assert select_source_with_fallback("nonexistent_type") is None

    pfz = load_pfz_advisories()
    assert pfz["type"] == "FeatureCollection" and pfz["features"]
    print("discovery self-check ok:", d.narrative)

    # D2 fixture — Agent 3's cascade decision when the primary SST source is
    # down, recorded in the AgentResult shape the fixture harness expects.
    from orca.contracts import AgentResult, Confidence, SourceProvenance
    from orca.testing.fixtures import record_fixture

    fixture = AgentResult(
        agent_name="discovery",
        query_id="fixture-sst-fallback",
        reasoning_depth="STANDARD",
        inputs_consumed={"data_type": "sst", "down": ["incois_erddap", "mosdac_open_sst"]},
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
