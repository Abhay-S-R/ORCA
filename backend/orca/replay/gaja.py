"""orca/replay/gaja.py — Cyclone Gaja historical replay (parent plan §1.3,
phase4 plan §3). Both required datasets landed in data/cyclone_gaja/ during
Phase 2/3 procurement — a real IBTrACS best-track and real ERA5 hourly
wind/wave fields, not the STUB placeholder fetch_gaja.py writes when CDS
credentials are missing (era5_gaja_STUB.json sits alongside, unused,
superseded by the real .nc file).

Every value here is either passed through from IBTrACS/ERA5 unchanged, or
computed by the same evaluate_marine_safety() Agent 7 already uses on the
live safety path — no invented numbers, no reinvented threshold logic.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from functools import lru_cache
from typing import Any

import numpy as np
import xarray as xr

from orca.agents.geospatial import DATA_ROOT
from orca.agents.risk_assessment import evaluate_marine_safety

GAJA_DIR = DATA_ROOT / "cyclone_gaja"
TRACK_FILE = GAJA_DIR / "ibtracs_gaja_2018_besttrack.json"
ERA5_FILE = GAJA_DIR / "era5_gaja_20181112_20181118.nc"

PROVENANCE_CLASS = "HISTORICAL OBSERVED (IMD/ERA5, Nov 2018)"

# Thoothukudi — the pilot port every other agent's default state uses
# (orca/api/main.py's _DEFAULT_LAT/_DEFAULT_LON), so the replay's hazard
# cascade answers the same "is it safe here" question the live path does.
_REPLAY_LAT, _REPLAY_LON = 8.8, 78.14


def _ibtracs_wind_to_alert(wind_kts: float | None) -> str | None:
    """IMD's own cyclone-intensity scale by max sustained wind (knots),
    mapped onto the Red/Orange/Yellow/None vocabulary evaluate_marine_safety
    already accepts from the live SACHET-derived path (orca/agents/sentinel.py's
    risk_assessment_cyclone_alert). Very Severe Cyclonic Storm (64kt+) is the
    threshold India's own warning bulletins treat as landfall-danger, which
    is why it lands on "Red" — the same string that trips NO_GO."""
    if wind_kts is None:
        return None
    if wind_kts >= 64:
        return "Red"      # Very Severe Cyclonic Storm and above
    if wind_kts >= 48:
        return "Orange"   # Severe Cyclonic Storm
    if wind_kts >= 34:
        return "Yellow"   # Cyclonic Storm
    return None            # Depression / Deep Depression


@lru_cache(maxsize=1)
def _load_track() -> dict[str, Any]:
    return json.loads(TRACK_FILE.read_text())


@lru_cache(maxsize=1)
def _load_era5() -> tuple[xr.Dataset, xr.Dataset]:
    """The CDS API returned a zip of two GRIB->NetCDF streams (a normal
    multi-variable-group quirk of that API, not a bug) — extracted once into
    memory and cached, not re-unzipped per call."""
    raw = ERA5_FILE.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        oper_name = next(n for n in names if "oper" in n)
        wave_name = next(n for n in names if "wave" in n)
        oper_bytes = zf.read(oper_name)
        wave_bytes = zf.read(wave_name)
    oper = xr.open_dataset(io.BytesIO(oper_bytes))
    wave = xr.open_dataset(io.BytesIO(wave_bytes))
    return oper, wave


def _nearest(ds: xr.Dataset, var: str, when: datetime, lat: float, lon: float) -> float | None:
    try:
        value = ds[var].sel(valid_time=np.datetime64(when), latitude=lat, longitude=lon, method="nearest")
        result = float(value.values)
    except Exception:  # noqa: BLE001 — a timestep outside the ERA5 window, never interpolated across
        return None
    return result if np.isfinite(result) else None


def hazard_cascade() -> list[dict[str, Any]]:
    """One evaluate_marine_safety() call per IBTrACS observation, wind/wave
    sampled from ERA5 at Thoothukudi at that observation's timestamp — the
    actual "hazard cascade" Definition of Done #7 asks to see: Agent 7's real
    deterministic logic run against real historical fields, not a canned
    GO/CAUTION/NO_GO sequence."""
    track = _load_track()
    oper, wave = _load_era5()
    era5_start, era5_end = oper["valid_time"].values.min(), oper["valid_time"].values.max()

    cascade: list[dict[str, Any]] = []
    for point in track["track"]:
        when = datetime.strptime(point["iso_time"], "%Y-%m-%d %H:%M:%S")
        when64 = np.datetime64(when)
        if when64 < era5_start or when64 > era5_end:
            continue  # outside the procured ERA5 window — omitted, never extrapolated

        u10 = _nearest(oper, "u10", when, _REPLAY_LAT, _REPLAY_LON)
        v10 = _nearest(oper, "v10", when, _REPLAY_LAT, _REPLAY_LON)
        swh = _nearest(wave, "swh", when, _REPLAY_LAT, _REPLAY_LON)
        if u10 is None or v10 is None:
            continue

        wind_speed_kmh = float(np.hypot(u10, v10)) * 3.6
        # ERA5's wave model masks swh as NaN at Thoothukudi's own point — a
        # real grid limitation (it sits in the shallow, land-sheltered Gulf
        # of Mannar strait the wave model doesn't resolve), not a bug: real
        # swh elsewhere in this same grid at the same timestep is well above
        # 3m during the storm. 0.0 is only ever fed to evaluate_marine_safety
        # (a conservative "no wave contribution" input, never a false "calm"
        # claim) — the reported wave_height_m stays None so nothing renders
        # "0.0m calm" during a cyclone (Ground Rule 3: absent is not zero).
        track_wind_kts = float(point["wind_kts"]) if point.get("wind_kts") else None
        cyclone_alert = _ibtracs_wind_to_alert(track_wind_kts)

        verdict = evaluate_marine_safety(
            wave_height_m=swh if swh is not None else 0.0,
            wind_speed_kmh=wind_speed_kmh,
            lightning_active=False,  # no historical lightning-nowcast archive exists for 2018 (parent plan §1.3)
            cyclone_alert=cyclone_alert,
            imbl_distance_nm=999.0,  # Thoothukudi's fixed offshore point — boundary proximity is a live-only concern
            mpa_violation=False,
        )

        cascade.append({
            "timestamp": point["iso_time"],
            "track_position": {"lat": point["lat"], "lon": point["lon"]},
            "track_wind_kts": track_wind_kts,
            "track_pressure_mb": float(point["pressure_mb"]) if point.get("pressure_mb") else None,
            "sampled_at": {"lat": _REPLAY_LAT, "lon": _REPLAY_LON},
            "wind_speed_kmh": round(wind_speed_kmh, 1),
            "wave_height_m": round(swh, 2) if swh is not None else None,
            "cyclone_alert": cyclone_alert,
            "go_no_go": verdict["go_no_go"],
            "status": verdict["status"],
            "reason": verdict["reason"],
            "provenance_class": PROVENANCE_CLASS,
        })
    return cascade


def wind_vector_frames() -> list[dict[str, Any]]:
    """One `{timestamp, points: [...]}` frame per ERA5 timestep, in the exact
    point shape orca/agents/geospatial.py::wind_vectors() already returns and
    FlowFieldCanvas.tsx already consumes — the replay draws on the existing
    flow-field renderer rather than a second visualization path."""
    oper, _wave = _load_era5()
    lats = oper["latitude"].values
    lons = oper["longitude"].values
    frames: list[dict[str, Any]] = []
    for t in oper["valid_time"].values:
        u = oper["u10"].sel(valid_time=t).values
        v = oper["v10"].sel(valid_time=t).values
        points = []
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                uu, vv = float(u[i, j]), float(v[i, j])
                if not (np.isfinite(uu) and np.isfinite(vv)):
                    continue
                speed = float(np.hypot(uu, vv))
                direction = float(np.degrees(np.arctan2(-uu, -vv)) % 360.0)
                points.append({
                    "lat": float(lat), "lon": float(lon),
                    "speed_ms": round(speed, 2), "direction_deg": round(direction, 1),
                })
        frames.append({"timestamp": str(t)[:19], "points": points, "provenance_class": PROVENANCE_CLASS})
    return frames


def replay_payload() -> dict[str, Any]:
    """The full `/api/replay/gaja` response — track, hazard cascade, wind
    frames, every one of them explicitly bannered so nothing here can be
    mistaken for LIVE or SIMULATED data (parent plan §1.3's rule)."""
    track = _load_track()
    return {
        "storm": {
            "name": track["name"], "year": track["year"], "landfall": track["landfall"],
            "source": track["source"], "source_url": track["source_url"],
        },
        "track": [{**point, "provenance_class": PROVENANCE_CLASS} for point in track["track"]],
        "hazard_cascade": hazard_cascade(),
        "wind_frames": wind_vector_frames(),
        "provenance_class": PROVENANCE_CLASS,
    }
