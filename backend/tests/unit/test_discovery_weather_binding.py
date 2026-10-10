"""AGENT-AUDIT 4, phase A4 (2026-10-10): weather_intelligence obeys marine_data_discovery on wave, wind and lightning.

Found by the audit: Agent 3 chose "IMD Damini" for lightning (no Damini feed exists: the answer used Open-Meteo's CAPE proxy),
declared INCOIS WW3 as the wave fallback (weather has no reader for it: it used its own cached port records), and weather
never read the decision at all. Now: the catalog says what is read, weather follows the decided rung (the cached one when
Agent 3 names it, skipping a pointless 3 s live attempt), and the output carries decided / used / obeyed per data type.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest import mock

import httpx
import pytest

from orca import resilience
from orca.agents import weather_intelligence as wi
from orca.agents.discovery import FALLBACK_CASCADES, SOURCE_REGISTRY, select_source_with_fallback


@pytest.fixture(autouse=True)
def _clean_breakers():
    for i in ("open_meteo", "open_meteo_marine", "open_meteo_port_cache"):
        resilience._breaker_opened_at.pop(i, None)
        resilience._breaker_failures.pop(i, None)
    yield


# --- the catalog -------------------------------------------------------------------------------------------------------------------

def test_lightning_is_decided_as_the_proxy_that_is_really_read_not_a_feed_that_does_not_exist():
    damini = next(s for s in SOURCE_REGISTRY if s.id == "damini_lightning")
    assert damini.readable is False and "no Damini feed" in damini.why_not_readable
    d = select_source_with_fallback("lightning")
    assert d is not None and d.chosen.id == "open_meteo_lightning_proxy" and "Damini" in d.chosen.dataset and "proxy" in d.chosen.dataset


def test_the_wave_fallback_is_the_rung_weather_can_serve():
    assert FALLBACK_CASCADES["open_meteo_marine"] == ("open_meteo_port_cache",)
    d = select_source_with_fallback("wave_height", down=("open_meteo_marine",))
    assert d is not None and d.chosen.id == "open_meteo_port_cache"      # not INCOIS WW3, which weather cannot read as a weather frame


def test_agent_3_names_the_cache_once_the_breaker_the_specialists_trip_is_open():
    assert select_source_with_fallback("wave_height").chosen.id == "open_meteo_marine"  # type: ignore[union-attr]
    for _ in range(6):
        resilience.record_failure("open_meteo")
    assert select_source_with_fallback("wave_height").chosen.id == "open_meteo_port_cache"  # type: ignore[union-attr]


# --- weather follows the decision -----------------------------------------------------------------------------------------------------

def _frame(n=3):
    t0 = datetime.now(UTC).strftime("%Y-%m-%dT%H:00")
    return {"hourly": {"time": [t0] * n, "wave_height": [0.5] * n, "wave_period": [6.0] * n, "swell_wave_height": [0.4] * n,
                       "ocean_current_velocity": [1.0] * n, "wind_speed_10m": [7.0] * n, "wind_gusts_10m": [9.0] * n}, "utc_offset_seconds": 0}


def _cache_patches():
    raw = _frame()
    return (
        mock.patch.object(wi, "load_json", lambda path: raw),
        mock.patch.object(wi, "_nearest_port", lambda lat, lon, c: "kochi"),
        mock.patch.object(wi, "port_coordinates", lambda: {"kochi": (9.96, 76.27)}),
    )


def test_a_live_success_is_reported_as_the_decided_primary():
    live = _frame()

    def fetch(url, lat, lon, variables, hours):
        return live

    with mock.patch.object(wi, "_fetch_open_meteo", fetch):
        w = wi.get_marine_weather(9.96, 76.27)
    assert w["source_used"] == "open_meteo_marine" and w["fallback_depth"] == 0 and w["port"] is None


def test_skip_live_goes_straight_to_the_cache_without_calling_the_network():
    called = []

    def fetch(*a, **k):
        called.append(1)
        raise AssertionError("the live source must not be called when Agent 3 decided the cached rung")

    a, b, c = _cache_patches()
    with mock.patch.object(wi, "_fetch_open_meteo", fetch), a, b, c:
        w = wi.get_marine_weather(9.96, 76.27, skip_live=True)
    assert called == [] and w["source_used"] == "open_meteo_port_cache" and w["port"] == "kochi"
    assert "port=kochi" in w["source_provenance"].dataset and "km away" in w["source_provenance"].dataset


def test_a_live_failure_at_fetch_still_falls_to_the_cache_and_says_how_far_it_is():
    def fetch(*a, **k):
        raise httpx.ConnectTimeout("slow")

    a, b, c = _cache_patches()
    with mock.patch.object(wi, "_fetch_open_meteo", fetch), a, b, c:
        w = wi.get_marine_weather(9.96, 76.27)
    assert w["source_used"] == "open_meteo_port_cache" and w["fallback_depth"] == 1 and w["port_km"] is not None


def _state(decisions):
    return {"query_id": "q", "user_location": {"lat": 9.96, "lon": 76.27}, "discovery_sources": {"by_data_type": decisions}}


def _decision(chosen, considered):
    return {"chosen": chosen, "considered": considered}


def _run_with(weather_used, lightning_used, state, skip_seen=None):
    from orca.contracts import Confidence, SourceProvenance

    hourly = [{"wave_height": 0.5, "wind_speed_10m": 7.0}]
    prov = SourceProvenance(dataset="d", acquisition_timestamp="2026-10-10T00:00:00Z", freshness_minutes=0)
    conf = Confidence(score="HIGH", rationale="r")
    weather = {"hourly": hourly, "source_provenance": prov, "confidence": conf, "fallback_depth": 0 if weather_used == "open_meteo_marine" else 1,
               "source_used": weather_used, "port": None, "port_km": None}
    lightning = {"lightning_active": False, "source_provenance": prov, "confidence": conf, "source_used": lightning_used}
    imd = {"expired": True, "alert_count": 0, "lightning_flagged": False, "confidence": conf, "source_provenance": prov}
    cyc = {"active_cyclones": [], "confidence": conf}

    def gmw(lat, lon, hours_ahead=48, *, skip_live=False):
        if skip_seen is not None:
            skip_seen.append(skip_live)
        return weather

    with mock.patch.object(wi, "get_marine_weather", gmw), mock.patch.object(wi, "get_lightning_nowcast", lambda lat, lon: lightning),             mock.patch.object(wi, "get_cyclone_status", lambda basin: cyc), mock.patch.object(wi, "get_imd_nowcast_alerts", lambda lat, lon: imd),             mock.patch("orca.demo_fixtures.fixture_result", lambda state, name: None):
        return wi.run(state)  # type: ignore[arg-type]


def test_obeyed_when_the_used_source_is_the_decided_one():
    state = _state({"wave_height": _decision("open_meteo_marine", ["open_meteo_marine", "open_meteo_port_cache"]),
                    "wind_speed": _decision("open_meteo_marine", ["open_meteo_marine", "open_meteo_port_cache"]),
                    "lightning": _decision("open_meteo_lightning_proxy", ["open_meteo_lightning_proxy"])})
    report = _run_with("open_meteo_marine", "open_meteo_lightning_proxy", state).outputs["source_report"]
    assert report["wave_height"] == {"decided": "open_meteo_marine", "used": "open_meteo_marine", "obeyed": True}
    assert report["lightning"]["obeyed"] is True


def test_a_live_failure_at_fetch_is_a_later_declared_rung_so_still_obeyed():
    state = _state({"wave_height": _decision("open_meteo_marine", ["open_meteo_marine", "open_meteo_port_cache"]),
                    "wind_speed": _decision("open_meteo_marine", ["open_meteo_marine", "open_meteo_port_cache"])})
    report = _run_with("open_meteo_port_cache", "open_meteo_lightning_proxy", state).outputs["source_report"]
    assert report["wave_height"]["obeyed"] is True and report["wave_height"]["used"] == "open_meteo_port_cache"


def test_using_something_other_than_the_decision_or_its_cascade_is_reported_as_not_obeyed():
    state = _state({"wave_height": _decision("open_meteo_port_cache", ["open_meteo_port_cache"]),
                    "wind_speed": _decision("open_meteo_port_cache", ["open_meteo_port_cache"])})
    report = _run_with("open_meteo_marine", "open_meteo_lightning_proxy", state).outputs["source_report"]
    assert report["wave_height"]["obeyed"] is False and report["wave_height"]["decided"] == "open_meteo_port_cache"


def test_no_decision_in_state_is_unknown_not_obeyed():
    report = _run_with("open_meteo_marine", "open_meteo_lightning_proxy", _state({})).outputs["source_report"]
    assert all(v["obeyed"] is None and v["decided"] is None for v in report.values())


def test_the_cached_decision_tells_weather_to_skip_the_live_attempt_and_other_decisions_do_not():
    seen: list[bool] = []
    _run_with("open_meteo_port_cache", "open_meteo_lightning_proxy", _state({"wave_height": _decision("open_meteo_port_cache", ["open_meteo_port_cache"])}), seen)
    _run_with("open_meteo_marine", "open_meteo_lightning_proxy", _state({"wave_height": _decision("open_meteo_marine", ["open_meteo_marine"])}), seen)
    _run_with("open_meteo_marine", "open_meteo_lightning_proxy", _state({}), seen)
    assert seen == [True, False, False]


def test_the_lightning_nowcast_names_which_source_served():
    def live(url, lat, lon, variables, hours):
        return {"hourly": {"lightning_potential": [10.0], "cape": [100.0]}}

    with mock.patch.object(wi, "_fetch_open_meteo", live):
        assert wi.get_lightning_nowcast(9.96, 76.27)["source_used"] == "open_meteo_lightning_proxy"
