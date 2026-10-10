"""AGENT-AUDIT 4, phases A2 and A3 (2026-10-10): the catalog tells the truth, and ocean_analytics obeys Agent 3 on tide.

A2: a source ORCA cannot read values from is never chosen (the three MOSDAC "registered NRT" ids are the same files as the open
products, NASA is a granule listing, Bhuvan a WMS manifest, ERDDAP a closed archive, the scatterometer wind an overlay); the real
last-resort rung weather falls to (cached Open-Meteo port records) is in the catalog with a probe.
A3: the tide source is the one Agent 3 decided; `source_used` says what really served; `obeyed` compares the two.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest

from orca import resilience
from orca.agents import ocean_analytics as oa
from orca.agents.discovery import (
    FALLBACK_CASCADES,
    SOURCE_REGISTRY,
    select_source_with_fallback,
    select_validated_source,
    validate_arrival,
)
from orca.data import analytics_loaders as al

UNREADABLE = {"incois_erddap", "mosdac_nrt_sst", "mosdac_nrt_chl", "mosdac_nrt_wind", "bhuvan_wms", "nasa_ocean_color"}


@pytest.fixture(autouse=True)
def _clean_breakers():
    for i in ("open_meteo", "open_meteo_marine", "soi_tide_tables", "stormglass_tides", "open_meteo_port_cache"):
        resilience._breaker_opened_at.pop(i, None)
        resilience._breaker_failures.pop(i, None)
    yield


# --- A2: the catalog ---------------------------------------------------------------------------------------------------------------

def test_exactly_these_sources_are_declared_unreadable_and_each_says_why():
    assert {s.id for s in SOURCE_REGISTRY if not s.readable} == UNREADABLE
    assert all(s.why_not_readable for s in SOURCE_REGISTRY if not s.readable)
    assert all(not s.why_not_readable for s in SOURCE_REGISTRY if s.readable)


@pytest.mark.parametrize("dtype", ["sst", "chlorophyll", "wind_speed", "wind_direction", "wave_height", "tide", "pfz", "boundary"])
def test_an_unreadable_source_is_never_chosen_even_with_everything_else_down(dtype):
    every_readable = tuple(s.id for s in SOURCE_REGISTRY if s.readable)
    assert select_source_with_fallback(dtype, down=every_readable) is None   # no readable source left: "no source", never an unreadable one


def test_chlorophyll_and_sst_fall_to_sources_that_can_serve_values():
    assert select_source_with_fallback("chlorophyll", down=("mosdac_open_chl",)).chosen.id == "copernicus_cmems"  # type: ignore[union-attr]
    assert select_source_with_fallback("sst", down=("mosdac_open_sst",)).chosen.id == "copernicus_cmems"  # type: ignore[union-attr]


def test_a_type_with_only_unreadable_sources_has_no_decision_and_wind_skips_the_overlay():
    assert select_source_with_fallback("wms_layer") is None
    d = select_source_with_fallback("wind_speed", down=("open_meteo_marine",))
    assert d is not None and d.chosen.id == "open_meteo_port_cache" and "mosdac_nrt_wind" not in d.narrative


def test_the_real_last_resort_rung_is_in_the_catalog_and_the_cascade():
    assert any(s.id == "open_meteo_port_cache" for s in SOURCE_REGISTRY)
    assert FALLBACK_CASCADES["open_meteo_marine"] == ("incois_osf_ww3", "open_meteo_port_cache")
    d = select_source_with_fallback("wave_height", down=("open_meteo_marine", "incois_osf_ww3"))
    assert d is not None and d.chosen.id == "open_meteo_port_cache" and d.chosen.authority_tier == "TIER1"


def test_the_ranking_of_live_sources_is_unchanged():
    assert select_source_with_fallback("wave_height").chosen.id == "open_meteo_marine"  # type: ignore[union-attr]
    assert select_source_with_fallback("sst").chosen.id == "mosdac_open_sst"  # type: ignore[union-attr]


def _port_cache(ports, nearest, km, acquired):
    from orca.agents import weather_intelligence as wi

    coords = {p: (9.0 + i, 76.0) for i, p in enumerate(ports)}
    raw = {"hourly": {"time": [acquired.strftime("%Y-%m-%dT%H:%M")]}, "utc_offset_seconds": 0}
    return (
        mock.patch.multiple(wi, port_coordinates=lambda: coords, _nearest_port=lambda lat, lon, c: nearest, _haversine_km=lambda *a: km),
        mock.patch("orca.data.loaders.load_json", lambda path: raw),
    )


def test_the_port_cache_probe_reports_the_port_its_distance_and_its_age():
    a, b = _port_cache(["kochi", "gangolli"], "gangolli", 21.0, datetime.now(UTC) - timedelta(hours=192))
    with a, b:
        check = validate_arrival("open_meteo_port_cache", {"lat": 13.6, "lon": 74.6})
    assert check.ok is True and check.stale is True
    assert "port gangolli" in check.detail and "21 km away" in check.detail and "192 h old" in check.detail


def test_a_fresh_cache_is_not_stale():
    a, b = _port_cache(["kochi"], "kochi", 4.0, datetime.now(UTC) - timedelta(hours=3))
    with a, b:
        assert validate_arrival("open_meteo_port_cache", {"lat": 9.9, "lon": 76.2}).stale is False


def test_a_cache_far_from_the_position_is_not_data_for_it_and_does_not_trip_the_breaker():
    a, b = _port_cache(["kochi"], "kochi", 900.0, datetime.now(UTC))
    with a, b:
        for _ in range(6):
            check = validate_arrival("open_meteo_port_cache", {"lat": 20.0, "lon": 86.0})
            assert check.ok is False and "beyond 300 km" in check.detail
    assert not resilience.circuit_open("open_meteo_port_cache")


def test_no_cache_on_disk_is_a_failure():
    from orca.agents import weather_intelligence as wi

    with mock.patch.object(wi, "port_coordinates", dict):
        assert validate_arrival("open_meteo_port_cache", {"lat": 9.9, "lon": 76.2}).ok is False


def test_when_open_meteo_is_down_agent_3_names_the_cache_not_a_rung_weather_cannot_serve():
    for _ in range(6):
        resilience.record_failure("open_meteo")      # weather gave up on the live feed
    a, b = _port_cache(["kochi"], "kochi", 4.0, datetime.now(UTC) - timedelta(hours=5))
    with a, b:
        d = select_validated_source("wind_speed", ctx={"lat": 9.9, "lon": 76.2})
    assert d is not None and d["chosen"] == "open_meteo_port_cache"
    assert "fallback" in d["narrative"].lower()


# --- A3: tide binding ----------------------------------------------------------------------------------------------------------------

def test_the_down_list_follows_the_decision():
    assert oa.tide_down_from_decision({"chosen": "soi_tide_tables"}) == (("stormglass_tides",), None)
    assert oa.tide_down_from_decision({"chosen": "stormglass_tides"}) == (("soi_tide_tables",), None)
    assert oa.tide_down_from_decision(None) == ((), None)
    decision = {"chosen": None, "rejected": [{"source_id": "soi_tide_tables", "reason": "ends 2026-10-16, before the requested 2026-10-30"}]}
    down, why = oa.tide_down_from_decision(decision)
    assert set(down) == {"soi_tide_tables", "stormglass_tides"} and "ends 2026-10-16" in (why or "")


def _ev(code, day, kind="HIGH TIDE", h=1.0):
    return {"station_code": code, "station_name": code, "when": datetime(2026, 10, day, 6, 0, tzinfo=UTC), "tide_event": kind, "height_m": h, "source": "t"}


def _tide(decision, soi, storm, station="NMP", when=datetime(2026, 10, 11, 6, 0, tzinfo=UTC)):
    down, why = oa.tide_down_from_decision(decision)
    with mock.patch.object(al, "load_soi_tide_events", lambda: list(soi)), mock.patch.object(al, "load_stormglass_tide_events", lambda c: list(storm)), \
            mock.patch.object(al, "load_stormglass_cache_date", lambda c: None), \
            mock.patch.object(oa, "nearest_station", lambda lat, lon: {"station_code": station, "station_name": station}):
        return oa.predict_tides(9.9, 76.2, when=when, down=down, unusable_reason=why)


def test_a_decision_for_soi_is_served_by_soi_and_reported_as_used():
    t = _tide({"chosen": "soi_tide_tables"}, [_ev("NMP", 12), _ev("NMP", 13, "LOW TIDE")], [_ev("NMP", 12, h=9.0)])
    assert t.source_used == "soi_tide_tables" and t.fell_back is False and t.next_high["height_m"] == 1.0


def test_a_decision_for_stormglass_is_obeyed_even_though_soi_has_rows():
    # SOI has rows for the station but they end before the requested time; Agent 3 chose the cache; the old order kept SOI
    t = _tide({"chosen": "stormglass_tides"}, [_ev("NMP", 9)], [_ev("NMP", 12, h=2.5), _ev("NMP", 13, "LOW TIDE", h=0.4)])
    assert t.source_used == "stormglass_tides" and t.fell_back is True and t.datum == "mean sea level" and t.next_high["height_m"] == 2.5


def test_no_usable_source_is_reported_with_agent_3s_own_reasons():
    decision = {"chosen": None, "rejected": [{"source_id": "soi_tide_tables", "reason": "Survey of India table for NMP ends 2026-10-16, before the requested 2026-10-30"}]}
    t = _tide(decision, [_ev("NMP", 12)], [_ev("NMP", 12)], when=datetime(2026, 10, 30, tzinfo=UTC))
    assert t.source_used is None and t.confidence.score == "LOW_DATA" and "ends 2026-10-16" in t.confidence.rationale


def test_without_a_decision_the_old_behaviour_stands():
    t = _tide(None, [_ev("NMP", 12), _ev("NMP", 13, "LOW TIDE")], [])
    assert t.source_used == "soi_tide_tables"


def _state(decision_chosen):
    return {"query_id": "q", "raw_user_query": "tide at mangalore", "normalized_english_query": "tide at mangalore",
            "user_location": {"lat": 12.9, "lon": 74.8, "place_name": "mangalore", "place_source": "gazetteer"},
            "discovery_sources": {"by_data_type": {"tide": {"data_type": "tide", "chosen": decision_chosen, "chosen_dataset": "x", "narrative": "n",
                                                          "considered": [], "fallback_chain": [], "rejected": []}}}}


def test_the_agent_output_says_decided_used_and_obeyed():
    real = oa.predict_tides
    seen = {}

    def spy(lat=0, lon=0, *, when=None, down=(), unusable_reason=None):
        seen["down"] = down
        return real(lat, lon, when=when, down=down, unusable_reason=unusable_reason)

    with mock.patch.object(oa, "predict_tides", spy):
        out = oa.run(_state("stormglass_tides")).outputs  # type: ignore[arg-type]
    assert seen["down"] == ("soi_tide_tables",)                           # the decision reached the fetch
    assert out["tide"]["source_decided"] == "stormglass_tides"
    assert out["tide"]["source_used"] in ("stormglass_tides", None)       # None when the cache holds no rows for that station
    assert out["tide"]["obeyed"] == (out["tide"]["source_used"] == "stormglass_tides")
    tide_sel = next(s for s in out["source_selections"] if s["data_type"] == "tide")
    assert "used" in tide_sel and tide_sel["decided_by"] == "marine_data_discovery"


def test_with_no_decision_in_state_obeyed_is_unknown_not_true():
    st = _state("soi_tide_tables")
    st["discovery_sources"] = {}
    out = oa.run(st).outputs  # type: ignore[arg-type]
    assert out["tide"]["source_decided"] is None and out["tide"]["obeyed"] is None
