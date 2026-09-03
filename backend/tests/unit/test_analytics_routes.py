"""HTTP surface for Agent 5 / Agent 3 (Phase 2 D2). TestClient over the real
app — no DB and no network needed: /zones, /trends, /tides, /sources and the
researcher export all run off files on disk, and the optional home-port
lookup degrades to anonymous when auth is not configured."""
from __future__ import annotations

import csv
import io

from fastapi.testclient import TestClient

from orca.api.main import app

client = TestClient(app)


def test_zones_measures_from_supplied_position_when_anonymous():
    r = client.get("/api/zones", params={"lat": 8.8, "lon": 78.14})
    assert r.status_code == 200
    body = r.json()
    assert body["measured_from"] == "supplied position"
    assert body["sector_status"]["sector_id"] == "SEC006"
    assert len(body["all_sectors"]) == 14
    assert body["source_selection"]["narrative"]


def test_zones_ignores_a_bad_token_and_stays_anonymous():
    # anonymous sessions are first-class (plan §5 D1 Day 9) — a junk bearer
    # must not 401 this surface, it falls through to the supplied position
    r = client.get("/api/zones", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 200
    assert r.json()["measured_from"] == "supplied position"


def test_trends_emits_frozen_contract_chart_specs():
    r = client.get("/api/trends")
    assert r.status_code == 200
    specs = r.json()["chart_specs"]
    ids = {s["chart_id"] for s in specs}
    assert {"tide_height", "catch_landings", "wind_rose"} <= ids
    for s in specs:
        # every ChartSpec field the frozen contract names is present
        assert set(s) == {
            "chart_id", "chart_type", "series", "x_key", "y_keys",
            "unit", "persona_visibility", "source_provenance",
        }
        assert s["chart_type"] in ("TimeSeries", "BarChart", "RadarChart", "WindRose")
        assert s["source_provenance"][0]["dataset"]


def test_trends_carries_the_anomaly_band_beside_the_spec_not_inside_it():
    body = client.get("/api/trends").json()
    band = body["catch_baseline"]
    assert band["band_low"] < band["mean_tonnes"] < band["band_high"]
    # not smuggled into the ChartSpec (the frozen contract has no slot)
    for s in body["chart_specs"]:
        assert "anomaly_band" not in s


def test_data_export_is_a_cited_csv_every_row_carrying_provenance():
    r = client.get("/api/data/export", params={"fmt": "csv"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert rows, "export must not be empty"
    for row in rows:
        # exit criterion 2 — every column carries dataset + acquisition time
        assert row["dataset"]
        assert "acquisition_timestamp" in row
        assert "freshness_minutes" in row
    # multi-source: the Agent 5 result plus one row per Agent 3 selection
    assert any(row["agent_name"].startswith("source:") for row in rows)


def test_data_export_rejects_netcdf():
    r = client.get("/api/data/export", params={"fmt": "netcdf"})
    assert r.status_code == 400


def test_source_decision_walks_the_declared_cascade():
    r = client.get("/api/source-decision", params={"data_type": "chlorophyll", "down": "mosdac_open_chl"})
    assert r.status_code == 200
    body = r.json()
    assert body["chosen"] == "nasa_ocean_color"
    assert "fallback" in body["narrative"].lower()
