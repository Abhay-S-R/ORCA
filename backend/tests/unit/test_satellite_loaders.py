"""P5.2 — NOAA CoastWatch ERDDAP loader. Mocked httpx, not a live network
round-trip: this environment's egress to coastwatch.pfeg.noaa.gov was
unreachable when this was written (TLS handshake reset), so the parsing
logic is verified against ERDDAP's own documented griddap JSON table shape
instead of a real response. Re-run against the live endpoint once network
access is confirmed.
"""
from __future__ import annotations

import httpx
import pytest

from orca import resilience
from orca.data import satellite_loaders as sl

BBOX = {"min_lon": 75.0, "min_lat": 8.0, "max_lon": 80.0, "max_lat": 10.0}


def _griddap_response(variable: str, value: float, when: str = "2026-09-22T09:00:00Z") -> dict:
    return {
        "table": {
            "columnNames": ["time", "latitude", "longitude", variable],
            "columnTypes": ["String", "double", "double", "float"],
            "rows": [[when, 8.5, 77.5, value]],
        }
    }


def _ok(json_body: dict) -> httpx.Response:
    return httpx.Response(200, json=json_body, request=httpx.Request("GET", "https://example.test"))


@pytest.fixture(autouse=True)
def _reset_breaker():
    resilience.record_success("noaa_coastwatch")
    yield
    resilience.record_success("noaa_coastwatch")


def test_load_coastwatch_sst_parses_kelvin_to_celsius(monkeypatch):
    def fake_get(url, timeout=None, follow_redirects=None):
        assert "jplMURSST41.json" in url
        assert "analysed_sst" in url
        # bbox actually reaches the URL, not just accepted and ignored.
        assert "(8.0):(10.0)" in url and "(75.0):(80.0)" in url
        return _ok(_griddap_response("analysed_sst", 301.15))  # 28 degC

    monkeypatch.setattr(httpx, "get", fake_get)
    grid = sl.load_coastwatch_sst(BBOX)
    assert grid is not None
    assert grid["units"] == "degC"
    assert grid["frame"] == [{"lon": 77.5, "lat": 8.5, "value": 28.0}]
    assert grid["provenance"]["dataset"].startswith("NOAA CoastWatch ERDDAP")
    assert grid["provenance"]["acquisition_timestamp"] == "2026-09-22T09:00:00Z"


def test_load_coastwatch_chl_parses_mg_m3(monkeypatch):
    def fake_get(url, timeout=None, follow_redirects=None):
        assert "chlor_a" in url
        return _ok(_griddap_response("chlor_a", 0.45))

    monkeypatch.setattr(httpx, "get", fake_get)
    grid = sl.load_coastwatch_chl(BBOX)
    assert grid is not None
    assert grid["frame"] == [{"lon": 77.5, "lat": 8.5, "value": 0.45}]


def test_coastwatch_returns_none_on_transport_failure_not_a_raise(monkeypatch):
    def fake_get(url, timeout=None, follow_redirects=None):
        raise httpx.ConnectError("simulated network failure")

    monkeypatch.setattr(httpx, "get", fake_get)
    assert sl.load_coastwatch_sst(BBOX) is None
    assert sl.load_coastwatch_chl(BBOX) is None


def test_coastwatch_returns_none_on_malformed_json(monkeypatch):
    def fake_get(url, timeout=None, follow_redirects=None):
        return _ok({"unexpected": "shape"})

    monkeypatch.setattr(httpx, "get", fake_get)
    assert sl.load_coastwatch_sst(BBOX) is None


def test_coastwatch_out_of_physical_range_is_dropped_not_kept(monkeypatch):
    def fake_get(url, timeout=None, follow_redirects=None):
        # 500 K is nowhere near a physically possible sea temperature.
        return _ok(_griddap_response("analysed_sst", 500.0))

    monkeypatch.setattr(httpx, "get", fake_get)
    assert sl.load_coastwatch_sst(BBOX) is None


def test_coastwatch_circuit_breaker_skips_the_live_call_once_open(monkeypatch):
    calls = []

    def fake_get(url, timeout=None, follow_redirects=None):
        calls.append(url)
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "get", fake_get)
    for _ in range(3):
        assert sl.load_coastwatch_sst(BBOX) is None
    assert len(calls) == 3  # breaker trips after the 3rd failure

    assert sl.load_coastwatch_sst(BBOX) is None
    assert len(calls) == 3, "circuit_open should have skipped this 4th attempt entirely"
    resilience.record_success("noaa_coastwatch")
