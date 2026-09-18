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


def test_pfz_layer_never_mixes_advisory_days(tmp_path, monkeypatch):
    """A PFZ advisory is a location for *one* day, and the map draws every
    feature identically, so a collection holding two days reads as one.

    `build_all_india_pfz.py` used to append 54 invented points stamped
    `valid_for: 2026-09-02` under INCOIS's name; the freshness check passed on
    the strength of the fresh half and the whole file was served. The builder no
    longer writes them, but `data/` is gitignored so other clones still hold the
    mixed file — hence the guard sits in the loader, where every consumer passes.
    """
    import json

    from orca.data import analytics_loaders as al

    mixed = {"type": "FeatureCollection", "features": [
        {"properties": {"valid_for": "2026-09-19", "sector_id": "SEC005"}},
        {"properties": {"valid_for": "2026-09-02", "sector_id": "SEC001"}},
    ]}
    national = tmp_path / "all_india_pfz_advisories.geojson"
    national.write_text(json.dumps(mixed), encoding="utf-8")
    (tmp_path / "incois_pfz_live_advisories.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    monkeypatch.setattr(al, "PFZ_DIR", tmp_path)

    served = al.load_pfz_live_geojson()["features"]
    assert [f["properties"]["sector_id"] for f in served] == ["SEC005"]
