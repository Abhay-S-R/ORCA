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


def test_pfz_layer_keeps_every_sectors_latest_advisory_labelled_by_age(tmp_path, monkeypatch):
    """docs/ORCA_Stale_Data_Policy.md. A sector cloud-covered today keeps its
    last clear day's zones on the map, each labelled with its own age — it used
    to be dropped, which emptied the east coast whenever only Maharashtra and
    Goa were cloud-free. Archive snapshots are grouped by `valid_for`, so a
    folder named by scrape day and a re-scrape of one advisory count once."""
    from datetime import date

    from orca.data import analytics_loaders as al

    header = ["sector_id,latitude_dd,longitude_dd,valid_for"]

    def csv_text(*rows: str) -> str:
        return "\n".join(header + list(rows)) + "\n"

    (tmp_path / "incois_pfz_live_advisories_master.csv").write_text(
        csv_text("SEC002,19.0,72.5,2026-09-23"), encoding="utf-8")
    for folder, rows in {
        "20260922": ("SEC002,19.0,72.5,2026-09-23",),  # scrape-day name, same advisory
        "20260918": ("SEC002,18.0,72.6,2026-09-19", "SEC006,9.07,79.09,2026-09-19"),
        "20260901": ("SEC006,9.5,79.4,2026-09-02",),
    }.items():
        (tmp_path / "history" / folder).mkdir(parents=True)
        (tmp_path / "history" / folder / "advisories.csv").write_text(csv_text(*rows), encoding="utf-8")
    monkeypatch.setattr(al, "PFZ_DIR", tmp_path)
    monkeypatch.setattr(al, "PFZ_HISTORY_DIR", tmp_path / "history")

    assert list(al.pfz_advisories_by_date()) == ["2026-09-02", "2026-09-19", "2026-09-23"]
    served = {
        f["properties"]["sector_id"]: f["properties"]
        for f in al.load_pfz_live_geojson(today=date(2026, 9, 24))["features"]
    }
    assert served["SEC002"]["valid_for"] == "2026-09-23" and served["SEC002"]["band"] == "fresh"
    assert served["SEC006"]["valid_for"] == "2026-09-19" and served["SEC006"]["band"] == "hint"
    assert served["SEC006"]["expired"] is True and served["SEC006"]["age_days"] == 5
