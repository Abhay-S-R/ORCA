"""HTTP surface for Agent 5 (Ocean Analytics) — Phase 2 plan §4 D2. Separate
APIRouter, one-line include from main.py, so D2's surfaces don't collide with
D1's graph/SSE work.

Endpoints back the `/zones`, `/trends` and `/data` surfaces directly, outside
the main LangGraph pipeline — the same pattern discovery_routes / geospatial_routes
already use for direct map/zone queries.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Response

from orca.agents import ocean_analytics as oa
from orca.agents import reporting
from orca.agents.discovery import (
    FALLBACK_CASCADES,
    SOURCE_REGISTRY,
    load_pfz_advisories,
    select_source_with_fallback,
)
from orca.contracts import ChartSpec, SourceProvenance
from orca.data import analytics_loaders as al

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ocean-analytics"])

_DEFAULT_LAT, _DEFAULT_LON = 8.80, 78.14
_BY_ID = {s.id: s for s in SOURCE_REGISTRY}


def _chart_spec(
    chart_id: str,
    chart_type: str,
    series: list[dict[str, Any]],
    x_key: str,
    y_keys: tuple[str, ...],
    unit: str,
    dataset: str,
    acquisition: str = "",
    freshness_minutes: int = 0,
) -> dict:
    """Build one frozen-contract ChartSpec (plan §5.9 / §4.1 — D3 owns the
    dataclass, D2 emits its shape) and return it json-ready."""
    return asdict(ChartSpec(
        chart_id=chart_id,
        chart_type=chart_type,  # type: ignore[arg-type]  # validated by the Literal at the dataclass
        series=tuple(series),
        x_key=x_key,
        y_keys=y_keys,
        unit=unit,
        persona_visibility=(),
        source_provenance=(SourceProvenance(
            dataset=dataset, acquisition_timestamp=acquisition, freshness_minutes=freshness_minutes
        ),),
    ))


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


def _home_port_from_token(authorization: str | None) -> dict[str, float] | None:
    """Best-effort: if the caller sent a valid bearer token, resolve their
    registered home port (plan §4 D2 Day 12 — "nearest PFZ ... from the
    registered home port"). Anonymous sessions stay first-class (plan §5 D1
    Day 9): no token, bad token, DB down or JWT not configured all fall
    through to None and the surface uses the lat/lon it was given."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        from orca.auth.security import decode_token
        from orca.db.engine import get_sessionmaker
        from orca.db.repositories import get_user_by_id, user_home_port

        payload = decode_token(token, expected_type="access")
        import uuid as _uuid

        db = get_sessionmaker()()
        try:
            user = get_user_by_id(db, _uuid.UUID(payload["sub"]))
            return user_home_port(user) if user is not None else None
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 — anonymous fallback, never a hard failure
        logger.info("home-port resolution skipped (%s: %s)", type(exc).__name__, exc)
        return None


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
def zones(
    lat: float = _DEFAULT_LAT,
    lon: float = _DEFAULT_LON,
    authorization: str | None = Header(default=None),
) -> dict:
    """The `/zones` surface payload — PS #1. Leads with the user's own sector
    status (a cloud-covered sector says so, in INCOIS's words), then the
    nearest advisory node, its persistence, and the thermal-front proxy layer
    that is only valid when INCOIS has published nothing (data audit C-2).

    A logged-in user's nearest-PFZ distance is measured from their registered
    home port; an anonymous caller's from the lat/lon it passed.
    """
    home = _home_port_from_token(authorization)
    origin = "registered home port" if home else "supplied position"
    if home:
        lat, lon = home["lat"], home["lon"]
    near = oa.nearest_pfz(lat, lon)
    user_sector = "SEC006"
    status = oa.sector_status(user_sector)
    persistence = oa.score_pfz_persistence(lat, lon, sector_id=near.sector_id or user_sector)
    status["nearest_advisory_out_of_sector"] = bool(
        near.found and near.sector_id and near.sector_id != user_sector
    )

    proxy = load_pfz_advisories() if status.get("is_data_gap") else {"type": "FeatureCollection", "features": []}
    live_pfz = al.load_pfz_live_geojson()
    combined_features = list(live_pfz.get("features", [])) + list(proxy.get("features", []))

    return {
        "measured_from": origin,
        "origin": {"lat": lat, "lon": lon},
        "sector_status": status,
        # SEC001–SEC014, the whole roster (plan §4 D2 Day 12) — a sector with
        # no advisory still gets a row saying why, never silent omission.
        "all_sectors": oa.all_sector_status(),
        "nearest_pfz": asdict(near),
        "persistence": {k: (asdict(v) if k == "confidence" else v) for k, v in persistence.items()},
        "thermal_front_proxy": proxy,
        "features": combined_features,
        "source_selection": _source_selection("pfz", None),
    }


@router.get("/trends")
def trends(district: str = "Thoothukudi", lat: float = _DEFAULT_LAT, lon: float = _DEFAULT_LON) -> dict:
    """The `/trends` surface — PS #3 (tide axis) and PS #7 (catch decline).

    Emits frozen-contract `ChartSpec` objects (plan §5.9) alongside the
    catch-decline analysis. The ±2σ anomaly band travels next to the spec,
    not inside it — the frozen contract has no slot for it and it is D2's
    surface concern.
    """
    from orca.data import analytics_loaders as al

    station = oa.nearest_station(lat, lon)
    tide_events = sorted(
        (e for e in al.load_soi_tide_events() if e["station_code"] == station["station_code"]),
        key=lambda e: e["when"],
    )
    tide_spec = _chart_spec(
        "tide_height", "TimeSeries",
        [{"t": e["when"].isoformat().replace("+00:00", "Z"), "height_m": e["height_m"]} for e in tide_events],
        x_key="t", y_keys=("height_m",), unit="m above chart datum",
        dataset=f"Survey of India 2026 Tide Tables (station {station['station_code']})",
    )

    diag = oa.diagnose_productivity_decline(district)
    catch_specs: list[dict] = []
    catch_baseline = diag.get("baseline")
    if diag.get("series"):
        catch_specs.append(_chart_spec(
            "catch_landings", "TimeSeries",
            [{"year": str(r["year"]), "total_tonnes": r["total_tonnes"]} for r in diag["series"]],
            x_key="year", y_keys=("total_tonnes",), unit="tonnes",
            dataset="data.gov.in Marine Fish Landings",
        ))

    rose = oa.wind_rose(lat, lon)
    wind_spec = None
    if rose.get("available"):
        wind_spec = _chart_spec(
            "wind_rose", "WindRose", list(rose["petals"]),
            x_key="compass", y_keys=tuple(rose["bins"]),
            unit=f"{rose['hours_counted']} forecast hours",
            dataset=rose.get("dataset", "Open-Meteo Forecast API (cached)"),
        )

    correlation = oa.correlate_sst_chlorophyll(None)

    return {
        "chart_specs": [tide_spec, *catch_specs] + ([wind_spec] if wind_spec else []),
        "catch_baseline": catch_baseline,  # {from,to} band for the catch TimeSeries
        "catch_decline": {k: (asdict(v) if k == "confidence" else v) for k, v in diag.items()},
        "sst_chlorophyll_correlation": {
            k: (asdict(v) if k == "confidence" else v) for k, v in correlation.items()
        },
        "source_selection": _source_selection("catch_statistics", None),
    }


# Declared before /data/{source_id} so "export" is not captured as an id.
@router.get("/data/export")
def data_export(
    q: str = "tide, sea conditions and fishing zones",
    lat: float = _DEFAULT_LAT,
    lon: float = _DEFAULT_LON,
    fmt: str = "csv",
) -> Response:
    """Researcher export — the same underlying facts as the fisherman verdict,
    as a cited table whose every row carries dataset + acquisition timestamp
    + freshness (plan §4 D2 Day 13; exit criterion 2).

    Runs Agent 5 directly and hands the AgentResult to Agent 9's
    `format_export` (D1, plan §4 D1 Day 12) — this surface consumes the
    formatter, it does not reimplement it. NetCDF is out of scope in the
    formatter itself (no agent here produces a gridded array); csv | json.
    """
    if fmt not in ("csv", "json"):
        raise HTTPException(400, "fmt must be 'csv' or 'json' (NetCDF needs gridded arrays no agent produces)")

    state: Any = {
        "query_id": "data-export",
        "raw_user_query": q,
        "normalized_english_query": q,
        "reasoning_depth": "DEEP",  # a researcher export wants the full diagnosis
        "user_location": {"lat": lat, "lon": lon},
    }
    result = oa.run(state)

    # One row per data source Agent 3 selected, so the export is genuinely
    # multi-source (acceptance test A: "the CSV export contains those same
    # sources as metadata columns"), not one opaque blob.
    from orca.contracts import AgentResult, Confidence, SourceProvenance

    source_rows = [
        AgentResult(
            agent_name=f"source:{sel['data_type']}",
            query_id="data-export", reasoning_depth="STANDARD",
            inputs_consumed={"data_type": sel["data_type"]},
            outputs={"chosen": sel["chosen"], "reason": sel["narrative"]},
            source_provenance=SourceProvenance(
                dataset=sel["chosen_dataset"],
                acquisition_timestamp=result.source_provenance.acquisition_timestamp,
                freshness_minutes=0,
            ),
            confidence=Confidence(score="HIGH", rationale="Agent 3 catalog selection"),
        )
        for sel in result.outputs.get("source_selections", [])
    ]
    assembled = reporting.assemble_response("data-export", [result, *source_rows])
    body = reporting.format_export(assembled, fmt)  # type: ignore[arg-type]

    media = "text/csv" if fmt == "csv" else "application/json"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="orca_export.{fmt}"'},
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
