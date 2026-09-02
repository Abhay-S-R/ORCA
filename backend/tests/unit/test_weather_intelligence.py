"""Agent 4 tests. Live-path tests monkeypatch the one HTTP boundary
(_fetch_open_meteo / httpx.get) rather than hitting the network — matching
plan §5.8's fixture-replay philosophy: CI stays green with no live key and
no network. Fallback-path tests read the REAL cached files on disk, so a
loader bug shows up here, not only in a demo."""
from datetime import datetime, timezone

import httpx
import pytest

from orca.agents import weather_intelligence as wia
from orca.state import ORCAState

THOOTHUKUDI = (8.822495, 78.119064)  # real coordinate from the cached fixture


# --- resolve_temporal_expression --------------------------------------------

NOW = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)  # a Wednesday, 10:00 UTC


def test_tomorrow_morning():
    r = wia.resolve_temporal_expression("Is it safe to go to sea tomorrow morning?", now=NOW)
    assert r == {"start": "2026-09-03T06:00:00Z", "end": "2026-09-03T12:00:00Z"}


def test_tonight():
    r = wia.resolve_temporal_expression("any lightning tonight", now=NOW)
    assert r == {"start": "2026-09-02T18:00:00Z", "end": "2026-09-02T23:59:59Z"}


def test_in_n_hours():
    r = wia.resolve_temporal_expression("conditions in 5 hours", now=NOW)
    assert r["start"] == "2026-09-02T15:00:00Z"


def test_today_defaults_to_full_day():
    r = wia.resolve_temporal_expression("weather today", now=NOW)
    assert r["start"] == "2026-09-02T00:00:00Z"


def test_no_temporal_expression_defaults_to_next_three_hours():
    r = wia.resolve_temporal_expression("is it safe near Thoothukudi", now=NOW)
    assert r == {"start": "2026-09-02T10:00:00Z", "end": "2026-09-02T13:00:00Z"}


def test_more_specific_pattern_wins_over_generic_tomorrow():
    # "tomorrow morning" must not fall through to the bare "tomorrow" (full-day) rule
    r = wia.resolve_temporal_expression("tomorrow morning please", now=NOW)
    assert r["end"] == "2026-09-03T12:00:00Z"


# --- get_marine_weather: live path (mocked) ---------------------------------

def _fake_hourly(**cols):
    return {"hourly": cols}


def test_get_marine_weather_live_path_merges_marine_and_wind(monkeypatch):
    def fake_fetch(url, lat, lon, variables, hours_ahead):
        if "marine" in url:
            return _fake_hourly(
                time=["2026-09-02T00:00", "2026-09-02T01:00"],
                wave_height=[1.2, 1.3], wave_period=[7.0, 7.1],
                swell_wave_height=[0.8, 0.9], ocean_current_velocity=[3.6, 7.2],
            )
        return _fake_hourly(
            time=["2026-09-02T00:00", "2026-09-02T01:00"],
            wind_speed_10m=[18.0, 36.0], wind_gusts_10m=[25.0, 40.0],
        )

    monkeypatch.setattr(wia, "_fetch_open_meteo", fake_fetch)
    result = wia.get_marine_weather(*THOOTHUKUDI)

    assert result["confidence"].score == "HIGH"
    assert len(result["hourly"]) == 2
    # 36 km/h -> 10 m/s, converted by normalize_to_common_frame, not left in km/h
    assert result["hourly"][1]["wind_speed_10m"] == pytest.approx(10.0)
    assert result["hourly"][0]["time"] == "2026-09-02T00:00:00Z"


def test_get_marine_weather_falls_back_to_cache_on_live_failure(monkeypatch):
    def raising_fetch(*a, **kw):
        raise httpx.ConnectTimeout("simulated network failure")

    monkeypatch.setattr(wia, "_fetch_open_meteo", raising_fetch)
    result = wia.get_marine_weather(*THOOTHUKUDI)

    assert result["confidence"].score == "MEDIUM"
    assert "cached tier1 fallback" in result["source_provenance"].dataset
    assert len(result["hourly"]) > 0
    # units still converted on the fallback path, not just the live one
    assert all(h["wind_speed_10m"] < 60 for h in result["hourly"])  # sane m/s, not raw km/h


def test_nearest_port_picks_pamban_for_a_rameswaram_coordinate():
    # Pamban is the island at Rameswaram itself — genuinely closer than
    # Thoothukudi to a Palk Bay coordinate this far north.
    port = wia._nearest_port(9.28, 79.30, wia.CACHED_MARINE_PORTS)
    assert port == "pamban"


# --- get_lightning_nowcast ---------------------------------------------------

def test_lightning_nowcast_live_high_potential_flags_active(monkeypatch):
    monkeypatch.setattr(
        wia, "_fetch_open_meteo",
        lambda *a, **kw: {"hourly": {"time": ["2026-09-02T00:00"], "lightning_potential": [1500], "cape": [2000]}},
    )
    result = wia.get_lightning_nowcast(*THOOTHUKUDI)
    assert result["lightning_active"] is True
    assert result["confidence"].score == "MEDIUM"  # proxy source, never HIGH — not the real Damini feed


def test_lightning_nowcast_low_potential_not_active(monkeypatch):
    monkeypatch.setattr(
        wia, "_fetch_open_meteo",
        lambda *a, **kw: {"hourly": {"time": ["2026-09-02T00:00"], "lightning_potential": [50], "cape": [100]}},
    )
    result = wia.get_lightning_nowcast(*THOOTHUKUDI)
    assert result["lightning_active"] is False


def test_lightning_nowcast_falls_back_to_cache_on_failure(monkeypatch):
    # REAL DATA GAP, confirmed by checking every cached port: lightning_potential
    # is null for all 168 cached hours, every port (chennai/kochi/mumbai/pamban/
    # thoothukudi). This is not a code bug — it's what the cached fixture
    # actually contains, and the correct behaviour is LOW_DATA + a named-missing
    # reading, never a silent "no lightning" false. Flagged for S3 to re-fetch
    # a cache that actually has values before the demo.
    monkeypatch.setattr(wia, "_fetch_open_meteo", lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectTimeout("x")))
    result = wia.get_lightning_nowcast(*THOOTHUKUDI)
    assert result["confidence"].score == "LOW_DATA"
    assert result["lightning_potential_j_kg"] is None
    assert "no lightning_potential reading available" in result["confidence"].rationale
    assert result["lightning_active"] is False  # unknown collapses to not-proven-active, never invented True


def test_lightning_nowcast_uses_first_real_reading_when_one_exists(monkeypatch):
    # Same all-null cache, but proves the scan-for-non-null logic works when
    # a real reading DOES exist somewhere in the window (guards against a
    # future cache refresh silently going back to the index-[0] bug).
    monkeypatch.setattr(wia, "_fetch_open_meteo", lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectTimeout("x")))
    port = wia._nearest_port(*THOOTHUKUDI, wia.CACHED_WEATHER_PORTS)
    import orca.agents.weather_intelligence as wia_mod
    from orca.data.loaders import cached_lightning_path, load_json

    real_cached = load_json(cached_lightning_path(port))
    patched = {**real_cached, "hourly": {**real_cached["hourly"], "lightning_potential": [None, None, 1250.0]}}
    monkeypatch.setattr(wia_mod, "load_json", lambda path: patched if "lightning_nowcast" in str(path) else load_json(path))
    result = wia.get_lightning_nowcast(*THOOTHUKUDI)
    assert result["lightning_potential_j_kg"] == 1250.0
    assert result["lightning_active"] is True


# --- get_cyclone_status / get_incois_hazard_alerts (SACHET) -----------------

def test_cyclone_status_filters_by_basin_from_centroid_longitude(monkeypatch):
    fake_alerts = [
        {"disaster_type": "Cyclone", "centroid": "88.0,20.0"},  # BoB (east coast)
        {"disaster_type": "Cyclone", "centroid": "70.0,20.0"},  # AS (west coast)
        {"disaster_type": "Heavy Rain", "centroid": "88.0,20.0"},  # not a cyclone, excluded
    ]
    monkeypatch.setattr(wia, "_fetch_sachet_alerts", lambda: (fake_alerts, "fake", wia.Confidence(score="HIGH", rationale="x")))
    result = wia.get_cyclone_status("BoB")
    assert len(result["active_cyclones"]) == 1
    assert result["active_cyclones"][0]["centroid"] == "88.0,20.0"


def test_incois_hazard_alerts_filters_by_region_substring(monkeypatch):
    fake_alerts = [
        {"disaster_type": "Flood", "area_description": "Thoothukudi coastal taluk"},
        {"disaster_type": "Flood", "area_description": "Mumbai suburban"},
    ]
    monkeypatch.setattr(wia, "_fetch_sachet_alerts", lambda: (fake_alerts, "fake", wia.Confidence(score="HIGH", rationale="x")))
    result = wia.get_incois_hazard_alerts("thoothukudi")
    assert len(result["active_warnings"]) == 1


def test_sachet_falls_back_to_real_cached_file_on_live_failure(monkeypatch):
    def raise_error(*a, **kw):
        raise httpx.ConnectTimeout("simulated")

    monkeypatch.setattr(httpx, "get", raise_error)
    alerts, dataset, confidence = wia._fetch_sachet_alerts()
    assert isinstance(alerts, list) and len(alerts) > 0  # real ndma_cap_alerts.json on disk
    assert "cached" in dataset
    assert confidence.score == "MEDIUM"


# --- run() — the (ORCAState) -> AgentResult entry point ---------------------

def test_run_returns_agent_result_with_no_persona_field(monkeypatch):
    # Must stay fully offline (plan §5.8) — mock both HTTP boundaries this
    # touches, not just the weather one, or CI silently depends on a live
    # network path nobody noticed.
    monkeypatch.setattr(wia, "_fetch_open_meteo", lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectTimeout("x")))
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: (_ for _ in ()).throw(httpx.ConnectTimeout("x")))
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-1", "reasoning_depth": "SHALLOW",
        "user_location": {"lat": THOOTHUKUDI[0], "lon": THOOTHUKUDI[1]},
    }
    result = wia.run(state)
    assert result.agent_name == "weather_intelligence"
    assert result.query_id == "q-1"
    assert not hasattr(result, "persona")  # AgentResult has no persona field at all
    assert "lightning_active" in result.outputs
    assert "cyclone_alert" in result.outputs
    # Regression: acquisition_timestamp must be reachable from outputs
    # directly — Agent 7 reads state["weather_data"]["acquisition_timestamp"],
    # not the AgentResult.source_provenance this function returns separately,
    # so it has to actually be in outputs, not just in the envelope.
    assert result.outputs["acquisition_timestamp"] != ""
    assert result.outputs["acquisition_timestamp"] == result.source_provenance.acquisition_timestamp
