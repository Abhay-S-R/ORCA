"""HTTP surface for Agent 5 (Ocean Analytics) — Phase 2 plan §4 D2. Separate
APIRouter, one-line include from main.py, so D2's surfaces don't collide with
D1's graph/SSE work.

Endpoints back the `/zones`, `/trends` and `/data` surfaces directly, outside
the main LangGraph pipeline — the same pattern discovery_routes / geospatial_routes
already use for direct map/zone queries.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from orca.agents import ocean_analytics as oa
from orca.agents.discovery import (
    FALLBACK_CASCADES,
    SOURCE_REGISTRY,
    load_pfz_advisories,
    select_source_with_fallback,
)

router = APIRouter(prefix="/api", tags=["ocean-analytics"])

_DEFAULT_LAT, _DEFAULT_LON = 8.80, 78.14
_BY_ID = {s.id: s for s in SOURCE_REGISTRY}


def _source_selection(data_type: str, down: str | None) -> dict | None:
    """Agent 3's decision, rendered for the answer card / activity strip.
    `down` is a comma-separated list of source ids known-unavailable."""
    down_ids = tuple(x.strip() for x in down.split(",") if x.strip()) if down else ()
    decision = select_source_with_fallback(data_type, down=down_ids)
    if decision is None:
        return None
    return {
        "data_type": data_type,
        "chosen": decision.chosen.id,
        "chosen_dataset": decision.chosen.dataset,
        "narrative": decision.narrative,
        "considered": [s.id for s in decision.considered],
        "fallback_chain": list(decision.fallback_chain),
    }


@router.get("/source-decision")
def source_decision(data_type: str, down: str | None = None) -> dict:
    sel = _source_selection(data_type, down)
    if sel is None:
        raise HTTPException(404, f"No source covers data_type={data_type!r}")
    return sel


@router.get("/tides")
def tides(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> dict:
    t = oa.predict_tides(lat, lon)
    return {
        "station_code": t.station_code,
        "station_name": t.station_name,
        "next_high": t.next_high,
        "next_low": t.next_low,
        "tidal_state": t.tidal_state,
        "range_m": t.range_m,
        "spring_neap": t.spring_neap,
        "datum": t.datum,
        "fell_back": t.fell_back,
        "source_provenance": asdict(t.source_provenance),
        "confidence": asdict(t.confidence),
        "source_selection": _source_selection("tide", None),
    }


@router.get("/pfz/nearest")
def pfz_nearest(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> dict:
    near = oa.nearest_pfz(lat, lon)
    persistence = oa.score_pfz_persistence(lat, lon, sector_id=near.sector_id or "SEC006")
    return {
        "nearest": asdict(near),
        "persistence": {k: (asdict(v) if k == "confidence" else v) for k, v in persistence.items()},
        "source_selection": _source_selection("pfz", None),
    }


@router.get("/zones")
def zones(lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> dict:
    """The `/zones` surface payload — PS #1. Leads with the user's own sector
    status (a cloud-covered sector says so, in INCOIS's words), then the
    nearest advisory node, its persistence, and the thermal-front proxy layer
    that is only valid when INCOIS has published nothing (data audit C-2)."""
    near = oa.nearest_pfz(lat, lon)
    user_sector = "SEC006"
    status = oa.sector_status(user_sector)
    persistence = oa.score_pfz_persistence(lat, lon, sector_id=near.sector_id or user_sector)
    status["nearest_advisory_out_of_sector"] = bool(
        near.found and near.sector_id and near.sector_id != user_sector
    )

    proxy = load_pfz_advisories() if status.get("is_data_gap") else {"type": "FeatureCollection", "features": []}

    return {
        "sector_status": status,
        # SEC001–SEC014, the whole roster (plan §4 D2 Day 12) — a sector with
        # no advisory still gets a row saying why, never silent omission.
        "all_sectors": oa.all_sector_status(),
        "nearest_pfz": asdict(near),
        "persistence": {k: (asdict(v) if k == "confidence" else v) for k, v in persistence.items()},
        "thermal_front_proxy": proxy,
        "source_selection": _source_selection("pfz", None),
    }


@router.get("/trends")
def trends(district: str = "Thoothukudi", lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> dict:
    """The `/trends` surface — PS #3 (tide axis) and PS #7 (catch decline).

    Returns plain series the frontend chart wrappers shape into a provisional
    ChartSpec. The frozen §5.9 ChartSpec is D3's to publish (plan §4.1); D2
    does not block on it.
    """
    from orca.data import analytics_loaders as al

    tide_events = sorted(
        (e for e in al.load_soi_tide_events() if e["station_code"] == oa.nearest_station(lat, lon)["station_code"]),
        key=lambda e: e["when"],
    )
    tide_series = [
        {"t": e["when"].isoformat().replace("+00:00", "Z"), "height_m": e["height_m"], "event": e["tide_event"]}
        for e in tide_events
    ]

    diag = oa.diagnose_productivity_decline(district)
    correlation = oa.correlate_sst_chlorophyll(None)
    rose = oa.wind_rose(lat, lon)

    return {
        "tide_series": tide_series,
        "catch_decline": {k: (asdict(v) if k == "confidence" else v) for k, v in diag.items()},
        "sst_chlorophyll_correlation": {
            k: (asdict(v) if k == "confidence" else v) for k, v in correlation.items()
        },
        "wind_rose": {k: (asdict(v) if k == "confidence" else v) for k, v in rose.items()},
        "source_selection": _source_selection("catch_statistics", None),
    }


# Declared before /data/{source_id} so "export" is not captured as an id.
@router.get("/data/export")
def data_export(source_id: str, fmt: str = "csv") -> dict:
    """Researcher CSV / NetCDF export with the full metadata block.

    Deferred: the export formatter is Agent 9's (D1, Phase 2 plan §4 D1 Day
    12 — 'export-formatter mode producing the CSV/NetCDF metadata block').
    This surface consumes it; it does not reimplement it.
    """
    raise HTTPException(
        status_code=501,
        detail="Export formatting is Agent 9's deliverable (D1, Phase 2 plan §4 D1 Day 12). "
        "Wire this to orca.agents.reporting.export_formatted_dataset when it lands.",
    )


@router.get("/data/{source_id}")
def data_source_detail(source_id: str) -> dict:
    src = _BY_ID.get(source_id)
    if src is None:
        raise HTTPException(404, f"Unknown source id {source_id!r}")
    chain = FALLBACK_CASCADES.get(source_id, ())
    return {
        "source": src.__dict__,
        "fallback_chain": [
            {"id": cid, "dataset": _BY_ID[cid].dataset} for cid in chain if cid in _BY_ID
        ],
        "is_fallback_for": [
            primary for primary, c in FALLBACK_CASCADES.items() if source_id in c
        ],
    }
