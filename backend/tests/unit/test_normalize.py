"""Round-trip check for normalize_to_common_frame (plan §5.6 — the two bugs
this exists to catch: axis-order transposition and unit mismatches reaching
the safety math undetected).
"""
from typing import Any

import pandas as pd
import pytest

from orca.data.normalize import SourceDescriptor, normalize_to_common_frame


def _thoothukudi_source(**overrides: Any) -> SourceDescriptor:
    defaults: dict[str, Any] = {
        "dataset": "Open-Meteo Marine API",
        "authority_tier": "T1",
        "acquisition_timestamp": "2026-08-30T00:00:00Z",
        "native_units": {"wind_speed_10m": "km/h"},
        "utc_offset_seconds": 19800,  # IST, +5:30 — matches the real cached fixtures
    }
    defaults.update(overrides)
    return SourceDescriptor(**defaults)  # type: ignore[arg-type]


def test_axis_order_survives_normalization():
    # Real Thoothukudi coordinate from data/tier1/weather/openmeteo_weather_thoothukudi.json
    df = pd.DataFrame({"latitude": [8.822495], "longitude": [78.119064]})
    result = normalize_to_common_frame(df, source=_thoothukudi_source())
    assert result.data["lon"].iloc[0] == pytest.approx(78.119064)
    assert result.data["lat"].iloc[0] == pytest.approx(8.822495)
    assert "axis_order" in result.provenance["operations"]


def test_hycom_style_longitude_wraps_to_correct_hemisphere():
    # 281.86 == -78.14 (Thoothukudi) in a 0..360 grid, e.g. HYCOM
    df = pd.DataFrame({"lon": [281.86], "lat": [8.80]})
    result = normalize_to_common_frame(df, source=_thoothukudi_source())
    assert result.data["lon"].iloc[0] == pytest.approx(-78.14)
    assert "longitude_wrap" in result.provenance["operations"]


def test_naive_local_time_converts_to_utc_with_z_suffix():
    # Real value from the cached fixture: 2026-08-30T00:00 IST == 2026-08-29T18:30 UTC
    df = pd.DataFrame({"time": ["2026-08-30T00:00"]})
    result = normalize_to_common_frame(df, source=_thoothukudi_source())
    assert result.data["time"].iloc[0] == "2026-08-29T18:30:00Z"
    assert "utc_time" in result.provenance["operations"]


def test_wind_speed_kmh_converts_to_ms():
    df = pd.DataFrame({"wind_speed_10m": [36.0]})  # 36 km/h == 10 m/s exactly
    result = normalize_to_common_frame(
        df, source=_thoothukudi_source(), target_units={"wind_speed_10m": "m/s"}
    )
    assert result.data["wind_speed_10m"].iloc[0] == pytest.approx(10.0)
    assert "unit_convert:wind_speed_10m" in result.provenance["operations"]


def test_missing_values_counted_not_replaced_with_a_sentinel():
    df = pd.DataFrame({"wave_height": [1.2, None, 0.9]})
    result = normalize_to_common_frame(df, source=_thoothukudi_source())
    assert result.provenance["missing_value_count"] == 1
    assert result.data["wave_height"].isna().sum() == 1  # still NaN, never -999/0


def test_upsampling_past_native_cadence_is_refused():
    df = pd.DataFrame(
        {"time": pd.date_range("2026-09-01", periods=3, freq="3h").astype(str), "hs": [1, 2, 3]}
    )
    with pytest.raises(ValueError, match="Refusing to resample"):
        normalize_to_common_frame(df, source=_thoothukudi_source(), target_time_resolution="1h")


def test_bbox_clip_drops_points_outside_pilot_region():
    df = pd.DataFrame({"lon": [78.14, 20.0], "lat": [8.80, 50.0]})
    pilot_bbox = {"min_lon": 77.5, "max_lon": 80.5, "min_lat": 7.5, "max_lat": 10.5}
    result = normalize_to_common_frame(df, source=_thoothukudi_source(), bbox=pilot_bbox)
    assert len(result.data) == 1
    assert result.data["lon"].iloc[0] == pytest.approx(78.14)


def test_unsupported_input_type_fails_loudly_not_silently():
    with pytest.raises(NotImplementedError, match="dict"):
        normalize_to_common_frame({"type": "FeatureCollection"}, source=_thoothukudi_source())


def test_provenance_carries_dataset_identity_forward():
    df = pd.DataFrame({"lon": [78.14], "lat": [8.80]})
    result = normalize_to_common_frame(df, source=_thoothukudi_source())
    assert result.provenance["dataset"] == "Open-Meteo Marine API"
    assert result.provenance["acquisition_timestamp"] == "2026-08-30T00:00:00Z"
