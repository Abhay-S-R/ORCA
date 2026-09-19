"""HTTP surface for Agent 6 (Geospatial) — plan §4 S5. A separate APIRouter,
included from `main.py` with one line, so this slice's endpoints don't
collide with S1's graph/SSE work in that file.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from orca.agents.geospatial import (
    DATA_ROOT,
    PAN_INDIA_BBOX_WSEN,
    PILOT_BBOX_WSEN,
    bearing_and_distance,
    boundary_data_vintage,
    check_boundary_proximity,
    current_vectors,
    depth_at_point,
    district_at_point,
    generate_map_layers,
    nearest_boundary_line,
    point_in_polygon,
    fishing_ban_status,
    hycom_nearest_step,
    spatial_query_zones,
    wind_vectors,
)
from orca.agents.visualization import generate_map_layers as agent8_generate_map_layers
from orca.data.analytics_loaders import load_boundary_provenance
from orca.data.freshness import max_age_minutes, read_json_if_fresh

# Derived-cache windows, taken from the class of the source each is derived from
# (docs/ORCA_Data_Freshness_Contract.md): HYCOM currents are DAILY, scatterometer
# wind is WEEKLY. A derived artefact may never claim to be fresher than its input.
CURRENT_VECTOR_TTL_MINUTES = max_age_minutes("DAILY")
WIND_VECTOR_TTL_MINUTES = max_age_minutes("WEEKLY")
from orca.trace import record_layer_metric
from orca.api.params import Lat, Lon, OptLat, OptLon

router = APIRouter(prefix="/api", tags=["geospatial"])

def _feature_summary(f) -> dict:
    return {"name": f.name, "designation": f.designation, "geofence_usable": f.geofence_usable}


@router.get("/map-layers")
def map_layers(lat: OptLat = None, lon: OptLon = None, zoom: int = 11) -> dict:
    return generate_map_layers(user_lat=lat, user_lon=lon, zoom=zoom)


@router.get("/raster-layers")
def raster_layers(lat: OptLat = None, lon: OptLon = None) -> dict:
    """Agent 8's Heatmap/Raster map layers (plan §5.10 Day 13 `/map`
    explorer) — a standalone REST surface, separate from `/map-layers`
    above (Agent 6's own boundaries/position, an older, narrower shape kept
    unchanged for its existing callers). Agent 8 normally only runs inside
    the `/query` SSE graph; its `generate_map_layers(state)` is a pure
    transform of `user_location` (bathymetry/tile-pyramid layers need
    nothing else), so a minimal state built here — with no weather/ocean
    data run through the graph — is a legitimate, cheap call, not a
    shortcut around Agent 8's contract.
    """
    state = {"user_location": {"lat": lat, "lon": lon} if lat is not None and lon is not None else None}
    layers = agent8_generate_map_layers(state)  # type: ignore[arg-type]
    return {"layers": [asdict(layer) for layer in layers if layer.layer_type in ("Raster", "Heatmap")]}


@router.get("/current-vectors")
def current_vectors_route(pan_india: bool = True) -> dict:
    """Real HYCOM surface current vectors (plan's revised D3 stack — the
    flow particle layer). Points, not a MapLayer: a vector field the frontend
    turns into an animated flow field client-side.

    The cache expires (R-FRESH-2). It used to be returned whenever the file
    existed, which meant a field computed on 2026-09-09 was still being served
    nine days later while a newer HYCOM run sat unread on the same disk. HYCOM is
    a DAILY-class source, so the window is a day.
    """
    cache_path = DATA_ROOT / "tier1" / "vectors" / "pan_india_currents_v2.json"
    # `valid_time` is the HYCOM step the field is for (P4.15): the time slider
    # greys this layer out when it is more than half a step away. A cached
    # field for a step that is no longer the nearest one is stale too.
    step, valid_time = hycom_nearest_step()
    if pan_india:
        cached = read_json_if_fresh(cache_path, CURRENT_VECTOR_TTL_MINUTES)
        if cached is not None and cached.get("valid_time") == valid_time:
            return cached
    if pan_india:
        pts = current_vectors(bbox=PAN_INDIA_BBOX_WSEN, stride=3, step=step)
        result = {"points": pts, "bounds": list(PAN_INDIA_BBOX_WSEN), "valid_time": valid_time, "step_hours": 3}
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                import json
                json.dump(result, f)
        except Exception:
            pass
        return result
    return {"points": current_vectors(step=step), "bounds": list(PILOT_BBOX_WSEN), "valid_time": valid_time, "step_hours": 3}


@router.get("/wind-vectors")
def wind_vectors_route(pan_india: bool = True) -> dict:
    """Archived ScatSat 10m wind. NOT live — one snapshot per day —
    so `acquisition_date` ships in the response for the frontend to render
    as an honest freshness label, never silently presented as 'now'.

    Scatterometer wind is WEEKLY-class, so the derived cache expires weekly
    (R-FRESH-2); before this it never expired at all and served a field built
    on 2026-09-04 from an 2026-08-27 pass. Note that rebuilding only helps once
    someone has downloaded a newer granule — the honest label carried by
    `acquisition_date` is what covers the gap in between.
    """
    cache_path = DATA_ROOT / "tier1" / "vectors" / "pan_india_wind.json"
    if pan_india:
        cached = read_json_if_fresh(cache_path, WIND_VECTOR_TTL_MINUTES)
        if cached is not None and "valid_time" in cached:
            return cached
    if pan_india:
        res = wind_vectors(bbox=PAN_INDIA_BBOX_WSEN, stride=4)
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                import json
                json.dump(res, f)
        except Exception:
            pass
        return res
    return wind_vectors()


class LayerMetricIn(BaseModel):
    layer_id: str
    layer_load_ms: float
    render_ms: float
    payload_bytes: int
    dropped_frames: int


@router.post("/layer-metrics")
def layer_metrics_route(metric: LayerMetricIn) -> dict:
    """§4.7 instrumentation sink — staging half of "console in dev, OTel
    stream in staging". The frontend only calls this outside dev."""
    record_layer_metric(
        metric.layer_id, metric.layer_load_ms, metric.render_ms, metric.payload_bytes, metric.dropped_frames
    )
    return {"ok": True}


@router.get("/boundary-proximity")
def boundary_proximity(lat: Lat, lon: Lon, boundary_name: str) -> dict:
    try:
        result = check_boundary_proximity(lat, lon, boundary_name)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return asdict(result)


_CYCLONE_MEMO: dict[str, tuple[float, dict]] = {}
_CYCLONE_MEMO_S = 600  # GDACS updates every ~6 h; one fetch per 10 min is plenty


@router.get("/cyclone-track")
def cyclone_track() -> dict:
    """Active North Indian Ocean cyclones — track, positions (observed and
    forecast) and uncertainty cone — as GeoJSON for the map (P5.30). Source is
    GDACS, labelled as such; it never feeds the verdict."""
    import time

    from orca.agents.weather_intelligence import get_cyclone_tracks

    hit = _CYCLONE_MEMO.get("nio")
    if hit and time.monotonic() - hit[0] < _CYCLONE_MEMO_S:
        return hit[1]
    result = get_cyclone_tracks()
    if not result.get("cached") and result.get("available"):
        _CYCLONE_MEMO["nio"] = (time.monotonic(), result)
    return result


@router.get("/boundary-line")
def boundary_line(lat: Lat, lon: Lon) -> dict:
    """Nearest DELIMITED maritime boundary line and the treaty that drew it.

    Distinct from /boundary-proximity, which measures to an EEZ polygon's
    edge — along the Palk Bay that edge is the IMBL, but off Gujarat it is
    the 200 NM limit, a different thing to cross.
    """
    line = nearest_boundary_line(lat, lon)
    if line is None:
        raise HTTPException(404, "no maritime boundary line dataset on disk")
    return line


@router.get("/district")
def district(lat: Lat, lon: Lon) -> dict:
    """Census-2011 district containing a position; `found: false` at sea."""
    hit = district_at_point(lat, lon)
    if hit is None:
        return {"found": False,
                "note": "position is outside every Census 2011 district polygon "
                        "(at sea, or outside India)"}
    return {"found": True, **hit}


@router.get("/boundary-provenance")
def boundary_provenance() -> dict:
    """The evidence behind every boundary answer: the audited per-MPA record
    (WDPA site ids, why each polygon is or is not geofence-usable) and the
    VLIZ EEZ gazetteer entries (MRGID, citation) the EEZ polygons came from.

    PS-C10 requires citations. These sidecars were on disk and only their
    timestamps were read (`geospatial.boundary_data_vintage`), so the citation
    a boundary distance rests on could not actually be shown to anyone — this
    is the endpoint the citation panel reads.
    """
    prov = load_boundary_provenance()
    return {
        **prov,
        "boundary_data_vintage": boundary_data_vintage(),
        "note": "Static reference geometry. The vintage is the OLDEST of the contributing sources.",
    }


@router.get("/point-in-polygon")
def point_in_polygon_route(lat: Lat, lon: Lon) -> dict:
    return {"boundaries": [_feature_summary(f) for f in point_in_polygon(lat, lon)]}


@router.get("/depth")
def depth(lat: Lat, lon: Lon) -> dict:
    return asdict(depth_at_point(lat, lon))


@router.get("/bearing")
def bearing(from_lat: Lat, from_lon: Lon, to_lat: Lat, to_lon: Lon) -> dict:
    bearing_deg, distance_nm = bearing_and_distance(from_lat, from_lon, to_lat, to_lon)
    return {"bearing_deg": bearing_deg, "distance_nm": distance_nm}


@router.get("/fishing-ban")
def fishing_ban(lat: Lat, lon: Lon) -> dict:
    """Seasonal fishing-ban status at a position today (runbook C4, PS-C8).

    Regulatory, never a sail/no-sail verdict — the risk cascade does not read
    it, and a closed season is not a weather hazard.
    """
    return fishing_ban_status(lat, lon)


@router.get("/zones-nearby")
def zones_nearby(lat: Lat, lon: Lon, radius_nm: float = 25.0) -> dict:
    return {"boundaries": [_feature_summary(f) for f in spatial_query_zones(lat, lon, radius_nm)]}
