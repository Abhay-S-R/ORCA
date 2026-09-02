"""Agent 3 (Data Discovery) skeleton — plan §4 S4, Day 3.

Phase 1 builds only the registry and `select_best_source`; ranking novel
external catalogs is Phase 2 (plan §7 — "Agent 3 (full)"). The reason string
exists from day one even though nothing surfaces it yet this week: Phase 2's
`/data` provenance popover reads it directly, and retrofitting a
human-readable reason onto a bare source id later is exactly the churn the
plan warns against.
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


# Seeded from the pilot's known tier1 datasets (data audit). Phase 2 grows
# this into a real catalog; Phase 1 needs only what the safety query touches.
SOURCE_REGISTRY: tuple[DataSource, ...] = (
    DataSource("open_meteo_marine", "Open-Meteo Marine API / ECMWF WAM Blend", "TIER1", 60,
               ("wave_height", "wave_period", "wind_speed", "wind_direction")),
    DataSource("incois_osf_ww3", "INCOIS Ocean State Forecast (WaveWatch III)", "TIER1", 360,
               ("wave_height", "wave_period")),
    DataSource("incois_osf_hycom", "INCOIS Ocean State Forecast (HYCOM currents)", "TIER1", 360,
               ("current_speed", "current_direction")),
    DataSource("incois_pfz", "INCOIS Potential Fishing Zone advisories", "TIER1", 1440, ("pfz",)),
    DataSource("ndma_sachet", "NDMA SACHET CAP alerts", "TIER1", 15, ("cyclone", "hazard")),
    DataSource("damini_lightning", "Damini Lightning Nowcast", "TIER1", 10, ("lightning",)),
    DataSource("gebco_bathymetry", "GEBCO 2026 Grid", "TIER1", 0, ("bathymetry",)),
    DataSource("unep_wcmc_wdpa", "UNEP-WCMC WDPA / OSM (marine boundaries)", "TIER1", 0, ("boundary",)),
    DataSource("marineregions_eez", "Marine Regions VLIZ EEZ dataset", "TIER1", 0, ("eez",)),
)

_TIER_ORDER: dict[AuthorityTier, int] = {"TIER1": 0, "TIER2": 1, "TIER3": 2}


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
    pfz = load_pfz_advisories()
    assert pfz["type"] == "FeatureCollection" and pfz["features"]
    print("discovery self-check ok:", picked.reason)
