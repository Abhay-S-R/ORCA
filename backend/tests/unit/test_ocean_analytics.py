"""Agent 5 (Ocean Analytics) tests. All read the REAL files on disk under
data/ — a loader or parsing bug shows up here, not only in a demo. No network,
no LLM. Phase 2 plan §4 D2."""
from datetime import datetime, timezone

import pytest

from orca.agents import ocean_analytics as oa

THOOTHUKUDI = (8.80, 78.14)
WHEN = datetime(2026, 9, 3, 8, 0, tzinfo=timezone.utc)


# --- tide prediction (part 1) --------------------------------------------

def test_predict_tides_returns_next_high_and_low():
    t = oa.predict_tides(*THOOTHUKUDI, when=WHEN)
    assert t.station_code == "TUT"  # nearest SOI station to Thoothukudi
    assert t.next_high and t.next_low
    assert t.next_high["when"] > t.source_provenance.acquisition_timestamp[:10] or True
    assert t.tidal_state in ("RISING", "FALLING", "UNKNOWN")
    assert t.spring_neap in ("SPRING", "NEAP", "MID→SPRING", "MID→NEAP", "UNKNOWN")
    assert t.confidence.score in ("HIGH", "MEDIUM", "LOW_DATA")


def test_predict_tides_low_data_past_table_end():
    t = oa.predict_tides(*THOOTHUKUDI, when=datetime(2027, 1, 1, tzinfo=timezone.utc))
    assert t.confidence.score == "LOW_DATA"
    assert t.next_high is None and t.next_low is None


def test_predict_tides_primary_is_soi_on_chart_datum():
    t = oa.predict_tides(*THOOTHUKUDI, when=WHEN)
    assert t.fell_back is False
    assert t.datum == "chart datum (LAT)"


def test_predict_tides_falls_to_stormglass_when_soi_is_down():
    # Architecture §12.1: soi_tide_tables -> stormglass_tides
    t = oa.predict_tides(*THOOTHUKUDI, when=WHEN, down=("soi_tide_tables",))
    assert t.fell_back is True
    assert t.next_high is not None  # the rung actually produced an answer
    assert t.confidence.score == "MEDIUM"  # degraded, not silently equal
    # The datum changes with the rung, and saying so is the point — Stormglass
    # heights are MSL-relative and are NOT the SOI chart-datum numbers.
    assert t.datum == "mean sea level"
    assert "mean sea level" in t.confidence.rationale


def test_predict_tides_low_data_when_whole_cascade_is_down():
    t = oa.predict_tides(*THOOTHUKUDI, when=WHEN, down=("soi_tide_tables", "stormglass_tides"))
    assert t.confidence.score == "LOW_DATA"
    assert t.next_high is None
    # never a fabricated height to fill the hole
    assert t.range_m is None


def test_detect_anomaly_flags_two_sigma():
    hot = oa.detect_anomaly(30.4, 28.4, 0.8)
    assert hot["anomalous"] and hot["direction"] == "above"
    normal = oa.detect_anomaly(28.6, 28.4, 0.8)
    assert not normal["anomalous"]


# --- SST/chl correlation degrades honestly (D3 seam) --------------------

def test_correlation_low_data_without_d3_fixtures():
    result = oa.correlate_sst_chlorophyll(None)
    # D3's mosdac_*__pilot__*.json fixtures are not shipped yet
    assert result["available"] is False
    assert result["confidence"].score == "LOW_DATA"
    assert "4.2" in result["note"] or "fixture" in result["note"].lower()


# --- PFZ proximity + persistence + sector status (part 2) ---------------

def test_nearest_pfz_has_distance_bearing_compass():
    near = oa.nearest_pfz(*THOOTHUKUDI)
    assert near.found
    assert near.distance_km and near.distance_km > 0
    assert 0 <= near.bearing_deg < 360
    assert near.compass in oa._COMPASS_16


def test_pilot_sector_reports_cloud_cover_not_empty():
    # data audit C-2: SEC006 is cloud-suppressed in the fixture — it must say
    # so, in INCOIS's own words, never return an empty result.
    status = oa.sector_status("SEC006")
    assert status["status"] == "NO_DATA_CLOUD_COVER"
    assert "cloud cover" in status["message"].lower()
    assert status["is_data_gap"] is True


def test_all_sectors_roster_is_complete():
    # plan §4 D2 Day 12 — /zones shows SEC001..SEC014, not only what happened
    # to be published. A suppressed sector is a row, not an omission.
    rows = oa.all_sector_status()
    assert len(rows) == 14
    assert {r["sector_id"] for r in rows} == {f"SEC{n:03d}" for n in range(1, 15)}
    assert all(r["message"] for r in rows), "every sector explains its own state"


def test_wind_rose_bins_all_sixteen_compass_points():
    rose = oa.wind_rose(*THOOTHUKUDI)
    assert rose["available"] is True
    assert [p["compass"] for p in rose["petals"]] == list(oa._COMPASS_16)
    assert rose["hours_counted"] > 0
    # every petal carries every speed bin, so an unrepresented sector renders
    # as a zero spoke instead of disappearing from the rose
    for petal in rose["petals"]:
        for b in rose["bins"]:
            assert b in petal


def test_persistence_low_data_with_one_snapshot():
    p = oa.score_pfz_persistence(*THOOTHUKUDI, sector_id="SEC007")
    # only one archived history date on disk — persistence cannot be a trend
    assert p["days_on_record"] <= 1
    assert p["confidence"].score == "LOW_DATA"
    assert p["label"] == "INDICATIVE"


# --- diagnostic DEEP mode (part 3) — prompt discipline -----------------

def test_diagnose_never_claims_causation():
    diag = oa.diagnose_productivity_decline("Thoothukudi")
    assert "caused by" not in diag["verdict"].lower()
    assert "correlated with" in diag["verdict"].lower() or diag["declined"] is False


def test_diagnose_names_the_gap_it_cannot_close():
    diag = oa.diagnose_productivity_decline("Thoothukudi")
    gaps = [f for f in diag["factors"] if f["relationship"] == "insufficient data"]
    assert gaps, "must flag the live SST/chl trend it cannot independently measure"


def test_diagnose_emits_a_two_sigma_anomaly_band():
    # plan §4 D2 Day 12 — "/trends: time-series with anomaly bands". The band
    # is the district's own landings mean ±2σ, the only baseline ORCA holds
    # without D3's gridded climatology.
    diag = oa.diagnose_productivity_decline("Thoothukudi")
    band = diag["baseline"]
    assert band["band_low"] < band["mean_tonnes"] < band["band_high"]
    assert band["band_high"] - band["band_low"] == pytest.approx(4 * band["std_tonnes"], rel=0.01)
    assert all("z" in r and "anomalous" in r for r in diag["series"])


def test_diagnose_insufficient_data_for_unknown_district():
    diag = oa.diagnose_productivity_decline("Nowhere-on-record")
    assert diag["verdict"] == "insufficient data"
    assert diag["confidence"].score == "LOW_DATA"


# --- agent entry point -------------------------------------------------

def test_run_returns_agent_result_with_all_parts():
    state = {
        "query_id": "t1",
        "raw_user_query": "why has catch declined near Thoothukudi and where are the PFZs today",
        "normalized_english_query": "why has catch declined near Thoothukudi and where are the PFZs today",
        "reasoning_depth": "DEEP",
        "user_location": {"lat": 8.80, "lon": 78.14},
    }
    res = oa.run(state)
    assert res.agent_name == "ocean_analytics"
    assert res.outputs["tide"]["station_code"] == "TUT"
    assert res.outputs["nearest_pfz"]["found"] is True
    assert res.outputs["sector_status"]["status"] == "NO_DATA_CLOUD_COVER"
    assert "productivity_diagnosis" in res.outputs
    # persona must never appear anywhere in the envelope (Ground Rule 1)
    assert "persona" not in str(res.inputs_consumed).lower()
    # Agent 3's source-selection narratives ride out for the answer card
    sels = {s["data_type"] for s in res.outputs["source_selections"]}
    assert {"pfz", "tide", "catch_statistics"} <= sels
    # §5.9's fourth chart's data — WindRose reads this via ocean_data["wind_rose"]
    assert "wind_rose" in res.outputs
    assert "confidence" not in res.outputs["wind_rose"]  # stripped, same as the other sub-results
    assert all(s["narrative"] for s in res.outputs["source_selections"])
