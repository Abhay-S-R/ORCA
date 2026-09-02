"""The common data frame — every loader exits through this (plan §5.6, hard
Day 3-4 gate). Axis order, units, and time zone bugs here are silent and only
surface as a wrong safety verdict, which is why this has its own round-trip
test rather than trusting call sites to get it right individually.

ORCA convention, enforced here:
  - CRS: EPSG:4326 internally
  - Axis order: (lon, lat) everywhere — the single most likely silent bug
  - Longitude: -180..180
  - Timestamps: tz-aware UTC, ISO-8601 with a trailing 'Z'
  - Units: m, m/s, degC, hPa — never km/h, knots, or degF past this point
  - Missing values: NaN, never a sentinel (-999/9999/0), and the count is recorded
  - Resampling: explicit and downsample-only, never interpolated finer than native

Only the pandas.DataFrame branch is implemented — it's what Agent 4's point
time-series data (Open-Meteo, cached tier1/ JSON) actually needs. The
xr.Dataset / GeoDataFrame / GeoJSON-dict branches raise NotImplementedError
with a pointer to who owns them (Agent 5's gridded NetCDF, Agent 6's boundary
polygons) — building untested behaviour for data this slice never touches
would be guessing, not correctness.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

# Single source of truth for km/h <-> m/s — evaluate_marine_safety's
# reference signature (Architecture §3.1) is fixed in km/h, but ORCAState's
# own convention (this module) is m/s, so Agent 7 has to convert back at
# that one boundary. Both directions share this constant rather than each
# hardcoding 3.6 independently, which is exactly the kind of drift that
# turns a round-trip conversion into a silent unit bug.
KM_PER_HOUR_PER_MS = 3.6


def kmh_to_ms(x: float) -> float:
    return x / KM_PER_HOUR_PER_MS


def ms_to_kmh(x: float) -> float:
    return x * KM_PER_HOUR_PER_MS


# km/h -> m/s is the only unit conversion Phase 1 actually exercises
# (Open-Meteo's wind_speed_10m, wind_gusts_10m, ocean_current_velocity are
# all km/h; ORCA's internal convention is m/s). Extend this table, don't
# special-case call sites, when a second conversion is actually needed.
_UNIT_CONVERTERS = {
    ("km/h", "m/s"): kmh_to_ms,
}


@dataclass(frozen=True)
class SourceDescriptor:
    dataset: str  # e.g. "Open-Meteo Marine API"
    authority_tier: str  # e.g. "T1" — matches the Dataset Master List tiers
    acquisition_timestamp: str  # ISO 8601 UTC — when this payload was fetched
    native_crs: str = "EPSG:4326"
    native_units: dict[str, str] = field(default_factory=dict)
    utc_offset_seconds: int = 0  # for sources whose timestamps are naive-local


@dataclass(frozen=True)
class NormalizedFrame:
    data: Any
    provenance: dict[str, Any]


def to_utc_iso(naive_local: str, utc_offset_seconds: int) -> str:
    """Open-Meteo timestamps are naive local time ('2026-08-30T00:00', no
    'Z', no offset) with the offset given separately as utc_offset_seconds.
    Confirmed against the actual cached fixtures, not assumed."""
    local_dt = datetime.fromisoformat(naive_local)
    utc_dt = local_dt - timedelta(seconds=utc_offset_seconds)
    return utc_dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_to_common_frame(
    data: Any,
    *,
    source: SourceDescriptor,
    target_crs: str = "EPSG:4326",
    target_time_resolution: str | None = None,
    target_units: dict[str, str] | None = None,
    bbox: dict[str, float] | None = None,  # {"min_lon","min_lat","max_lon","max_lat"}
) -> NormalizedFrame:
    if isinstance(data, pd.DataFrame):
        return _normalize_dataframe(
            data, source=source, target_time_resolution=target_time_resolution,
            target_units=target_units or {}, bbox=bbox,
        )
    type_name = type(data).__name__
    raise NotImplementedError(
        f"normalize_to_common_frame has no branch for {type_name} yet. "
        "xr.Dataset (gridded NetCDF) belongs to whoever builds Agent 5's ocean "
        "grids; GeoDataFrame/GeoJSON boundary polygons belong to Agent 6 (S5). "
        "Add the branch when that data actually needs normalizing — don't guess "
        "the transform ahead of a real fixture to test it against."
    )


def _normalize_dataframe(
    df: pd.DataFrame,
    *,
    source: SourceDescriptor,
    target_time_resolution: str | None,
    target_units: dict[str, str],
    bbox: dict[str, float] | None,
) -> NormalizedFrame:
    df = df.copy()
    operations: list[str] = []

    # --- axis order: (lon, lat), never (lat, lon) ---
    rename = {}
    if "longitude" in df.columns and "lon" not in df.columns:
        rename["longitude"] = "lon"
    if "latitude" in df.columns and "lat" not in df.columns:
        rename["latitude"] = "lat"
    if rename:
        df = df.rename(columns=rename)
        operations.append("axis_order")
    if "lon" in df.columns:
        # HYCOM-style 0..360 longitude -> -180..180. No source in this slice
        # produces it, but the convention is enforced here, once, rather than
        # left for whichever loader is first to hit it.
        wrapped = df["lon"] > 180
        if wrapped.any():
            df.loc[wrapped, "lon"] = df.loc[wrapped, "lon"] - 360
            operations.append("longitude_wrap")

    # --- time: naive local -> tz-aware UTC ISO-8601 with 'Z' ---
    if "time" in df.columns:
        df["time"] = df["time"].apply(lambda t: to_utc_iso(t, source.utc_offset_seconds))
        operations.append("utc_time")

    # --- units: only the conversions actually declared ---
    for column, target_unit in target_units.items():
        native_unit = source.native_units.get(column)
        if native_unit is None or native_unit == target_unit or column not in df.columns:
            continue
        converter = _UNIT_CONVERTERS.get((native_unit, target_unit))
        if converter is None:
            raise NotImplementedError(
                f"No unit converter registered for {native_unit!r} -> {target_unit!r} "
                f"(column {column!r}). Add it to _UNIT_CONVERTERS rather than "
                "converting inline at the call site."
            )
        df[column] = df[column].apply(converter)
        operations.append(f"unit_convert:{column}")

    # --- missing values: NaN, count recorded, no sentinel guessing ---
    missing_value_count = int(df.isna().sum().sum())

    # --- resampling: explicit, downsample-only ---
    if target_time_resolution is not None:
        if "time" not in df.columns:
            raise ValueError("target_time_resolution requires a 'time' column")
        indexed = df.set_index(pd.to_datetime(df["time"]))
        native_step = indexed.index.to_series().diff().median()
        target_step = pd.Timedelta(target_time_resolution)
        if target_step < native_step:
            raise ValueError(
                f"Refusing to resample to {target_time_resolution}, finer than the "
                f"source's native ~{native_step} cadence — that would be interpolation, "
                "which the ORCA convention forbids (never invent a forecast value)."
            )
        df = indexed.resample(target_time_resolution).mean(numeric_only=True).reset_index(
            names="time"
        )
        df["time"] = df["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        operations.append(f"resample:{target_time_resolution}")

    # --- extent clip ---
    if bbox is not None and {"lon", "lat"}.issubset(df.columns):
        df = df[
            df["lon"].between(bbox["min_lon"], bbox["max_lon"])
            & df["lat"].between(bbox["min_lat"], bbox["max_lat"])
        ]
        operations.append("clip")

    provenance = {
        "dataset": source.dataset,
        "authority_tier": source.authority_tier,
        "acquisition_timestamp": source.acquisition_timestamp,
        "native_crs": source.native_crs,
        "native_units": dict(source.native_units),
        "operations": operations,
        "missing_value_count": missing_value_count,
    }
    return NormalizedFrame(data=df, provenance=provenance)
