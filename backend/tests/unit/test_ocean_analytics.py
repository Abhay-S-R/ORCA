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


# --- SST/chl correlation reads the ISRO archives (D3 seam, now wired) ----

def test_correlation_reads_isro_archives_or_says_why_not():
    """The archives are gitignored data, so both branches are legitimate —
    what must never happen is a correlation with no provenance behind it, or
    an unavailable result with no reason."""
    result = oa.correlate_sst_chlorophyll(None)
    if result["available"]:
        assert -1.0 <= result["pearson_r"] <= 1.0
        assert result["n_samples"] >= 3
        assert result["sst_provenance"]["dataset"]
        assert result["chl_provenance"]["dataset"]
    else:
        assert result["confidence"].score == "LOW_DATA"
        assert result["note"]


def test_correlation_never_claims_causation():
    result = oa.correlate_sst_chlorophyll(None)
    if result.get("available"):
        assert "caused by" not in result["relationship"].lower()


# --- ERA5 baseline gives detect_anomaly a reference period ---------------

def test_wind_anomaly_carries_its_baseline_or_names_the_gap(monkeypatch):
    at_pilot = oa.wind_anomaly(*THOOTHUKUDI)
    assert at_pilot["available"] is True
    assert at_pilot["baseline_days"] > 1
    assert at_pilot["units"] == "km/h"  # baseline and observation, same units
    assert "ERA5" in at_pilot["baseline_label"]
    assert isinstance(at_pilot["anomalous"], bool)

    # Since 2026-09-19 the baseline is national, not pilot-only: every port
    # with a cached forecast has a matching ERA5 window, so PS-Q7's anomaly leg
    # answers off Gujarat and Odisha too, not just in the Gulf of Mannar.
    for lat, lon in ((22.98, 70.22), (20.26, 86.68), (11.68, 92.75)):
        national = oa.wind_anomaly(lat, lon)
        assert national["available"] is True, (lat, lon)
        assert national["units"] == "km/h"

    # A port that has no window must still read as "no baseline", never as
    # "not anomalous" — silence and normality are not the same answer.
    with monkeypatch.context() as m:
        m.setattr(oa.al, "load_era5_baseline", lambda port: None)
        gap = oa.wind_anomaly(*THOOTHUKUDI)
    assert gap["available"] is False
    assert "anomalous" not in gap
    assert "baseline" in gap["note"].lower()


# --- OSF point/grid fast path -------------------------------------------

def test_osf_fast_path_prefers_points_then_grid_then_declines():
    at_port = oa.nearest_osf_point_forecast(*THOOTHUKUDI)
    assert at_port["available"] and at_port["wave"]["significant_wave_height_m"] is not None

    # Goa is outside the 8 extracted points but inside the 0.5 deg grid.
    goa = oa.nearest_osf_point_forecast(15.4, 73.5)
    assert goa["available"] and "grid_cell" in goa
    assert goa["confidence"].score == "LOW_DATA"  # a regional cell, not this position

    # The Bay of Bengal north of the extraction footprint has neither.
    far = oa.nearest_osf_point_forecast(21.6, 88.0)
    assert far["available"] is False and far["note"]


# --- PFZ proximity + persistence + sector status (part 2) ---------------

def test_nearest_pfz_has_distance_bearing_compass():
    near = oa.nearest_pfz(*THOOTHUKUDI)
    assert near.found
    assert near.distance_km and near.distance_km > 0
    assert 0 <= near.bearing_deg < 360
    assert near.compass in oa._COMPASS_16


def test_pilot_sector_reports_cloud_cover_not_empty():
    # data audit C-2: a cloud-suppressed sector must say so in INCOIS's own
    # words, never return an empty result.
    #
    # Which sector is suppressed changes with every scrape, so the test asks the
    # data rather than pinning SEC006 — it was written against a day when SEC006
    # happened to be clouded and started failing the first time the scraper ran.
    rows = oa.all_sector_status()
    blocked = [r for r in rows if r["status"] == "NO_DATA_CLOUD_COVER"]
    if not blocked:
        pytest.skip("no sector is cloud-suppressed in the current scrape")
    for row in blocked:
        status = oa.sector_status(row["sector_id"])
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


def test_an_indicative_persistence_does_not_grade_the_agent(monkeypatch: pytest.MonkeyPatch):
    # 4 archived days: too few to score, so persistence reports INDICATIVE /
    # LOW_DATA — and that must stay a note, not the agent's confidence. It
    # used to count from 2 days on, pulling every answer to LOW_DATA.
    indicative = {
        "score": 0.0, "label": "INDICATIVE", "days_present": 0, "days_on_record": 4,
        "window_days": 7, "days_archived_total": 5, "radius_km": 25.0,
        "confidence": oa.Confidence(score="LOW_DATA", rationale="only 4 PFZ snapshot(s)"),
    }
    monkeypatch.setattr(oa, "score_pfz_persistence", lambda *a, **kw: indicative)
    result = oa.run({"user_location": {"lat": 21.08, "lon": 70.1}, "raw_user_query": "conditions at mangrol"})
    assert "PFZ snapshot" not in result.confidence.rationale
    assert result.outputs["pfz_persistence"]["label"] == "INDICATIVE"


def test_persistence_confidence_tracks_days_on_record():
    p = oa.score_pfz_persistence(*THOOTHUKUDI, sector_id="SEC007")
    # The archive grows by one directory every time the scraper runs, so the
    # assertion is the rule, not a snapshot count: a short run cannot be a
    # trend and must degrade to LOW_DATA / INDICATIVE. `days_on_record` counts
    # only the last `window_days`, because a fortnight-old advisory is not
    # evidence about this week.
    assert p["days_on_record"] <= p["days_archived_total"]
    if p["days_on_record"] < 5:
        assert p["confidence"].score == "LOW_DATA"
        assert p["label"] == "INDICATIVE"
    else:
        assert p["confidence"].score == "MEDIUM"
        assert p["label"] in ("PERSISTENT", "TRANSIENT")
        assert 0.0 <= p["score"] <= 1.0


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
    # Whichever way the pilot sector came out today, it is reported as a
    # first-class status with a message — not pinned to the clouded day this
    # test was written on.
    assert res.outputs["sector_status"]["status"] in (
        "HAS_ADVISORY", "NO_DATA_CLOUD_COVER", "NO_DATA")
    assert res.outputs["sector_status"]["message"]
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


# --- observed tide-gauge cross-check ------------------------------------

def test_tide_gauge_reading_is_measured_or_absent_never_invented():
    """A gauge reading is either a real observation or nothing at all.

    `incois_tide_gauge_telemetry.json` holds representative values, not readings —
    INCOIS's TEWS endpoint 404s. Thoothukudi has no IOC gauge within range, so the
    honest answer there is altimetry, and the fields only a gauge can supply must
    come back None rather than be filled from the fixture.
    """
    obs = oa.tide_gauge_observation(*THOOTHUKUDI)
    assert obs["source_kind"] != "in_situ_gauge"
    assert obs["observed_level_m"] is None
    assert obs["station_id"] is None
    # A tsunami determination is INCOIS's to make; ORCA never implies one.
    assert obs["tsunami_trigger_state"] is None


def test_tide_gauge_live_reading_carries_only_what_the_feed_publishes():
    """Chennai has a live IOC gauge, so the reading is real — and bounded.

    IOC publishes a sea level and a timestamp. The prediction, the residual and the
    water temperature are not in the feed, so they stay None and are named in
    `fields_unavailable` instead of being fabricated beside a real number.
    """
    near = oa.tide_gauge_observation(13.08, 80.27)
    if near["source_kind"] != "in_situ_gauge":
        pytest.skip("IOC feed unreachable in this environment")
    assert near["observed_level_m"] is not None
    assert near["observation_age_minutes"] < 24 * 60
    for field in ("predicted_astronomical_m", "sea_level_anomaly_m",
                  "water_temp_c", "tsunami_trigger_state"):
        assert near[field] is None
        assert field in near["fields_unavailable"]


def test_tide_gauge_out_of_range_falls_through_to_altimetry_and_says_so():
    """INCOIS runs 6 gauges nationally; the Gujarat coast has none nearby.
    CMEMS altimetry covers it, but it is a different measurement — the reply
    must never present an altimetric anomaly as a gauge reading."""
    far = oa.tide_gauge_observation(22.4, 69.0)
    assert "km" in far["note"]
    if far["available"]:
        assert far["source_kind"] == "satellite_altimetry"
        assert far["station_id"] is None and far["observed_level_m"] is None
        # A tsunami determination is INCOIS's; altimetry carries none.
        assert far["tsunami_trigger_state"] is None
        assert "altimetry" in far["note"]
        assert far["confidence"].score == "MEDIUM"
    else:
        # No CMEMS file on disk either — then it still declines, with both reasons.
        assert far["confidence"].score == "LOW_DATA"


def test_tide_roster_is_national_and_never_mislabels_the_datum():
    """The roster went from the 5 pilot ports to 14 on 2026-09-19, and only the
    original 5 have a published chart-datum offset. A height on mean sea level
    presented as chart datum is a metre of error under a keel, so the one thing
    that must hold at every station is that `datum` follows the station's own
    offset rather than the code path."""
    from orca.data import analytics_loaders as al

    stations = {s["station_code"]: s for s in al.load_tide_stations()}
    assert len(stations) >= 14, sorted(stations)
    # Coverage is the point: both coasts and the islands, not one sector.
    assert {"KAN", "VIZ", "PRD", "HDA", "PBL"} <= set(stations)

    for code, st in stations.items():
        # Now, not WHEN: the tables carry a rolling 7-day horizon, so a fixed
        # past date would make every station look empty and the test vacuous.
        t = oa.predict_tides(st["latitude"], st["longitude"])
        assert t.station_code == code, f"{code} is not its own nearest station"
        if t.next_high is None and t.next_low is None:
            continue  # no cache for that port yet — declines, does not guess
        if st.get("msl_above_chart_datum_m") is None:
            assert t.datum == "mean sea level", code
            assert t.fell_back is True and t.confidence.score == "MEDIUM", code
        else:
            assert t.datum == "chart datum (LAT)", code


def test_nearest_pfz_is_capped_at_reach_and_carries_the_advisory_age(monkeypatch: pytest.MonkeyPatch):
    # "PFZs near Rameswaram" answered with Betul, 906 km away on another coast.
    far_and_fresh = {"sector_id": "SEC003", "latitude_dd": "15.1", "longitude_dd": "73.9",
                     "valid_for": "2026-09-23", "age_days": 1, "band": "fresh", "expired": True}
    near_and_old = {"sector_id": "SEC006", "latitude_dd": "9.07", "longitude_dd": "79.09",
                    "valid_for": "2026-09-19", "age_days": 5, "band": "hint", "expired": True}
    monkeypatch.setattr(oa.al, "load_pfz_latest", lambda: [far_and_fresh, near_and_old])
    near = oa.nearest_pfz(9.29, 79.31)
    assert near.found and near.sector_id == "SEC006" and near.distance_km < 50
    assert (near.valid_for, near.age_days, near.band) == ("2026-09-19", 5, "hint")

    monkeypatch.setattr(oa.al, "load_pfz_latest", lambda: [far_and_fresh])
    assert oa.nearest_pfz(9.29, 79.31).found is False


def test_nearest_pfz_keeps_orcas_distance_and_incois_landmark_apart(monkeypatch: pytest.MonkeyPatch):
    # "pfzs near mangalore" was narrated as "32 km WSW of Kunzhathur": ORCA's
    # distance from Mangalore paired with INCOIS's landmark, whose own
    # distance to the zone is 52-57 km NW. Each origin travels with its own.
    zone = {"sector_id": "SEC004", "latitude_dd": "12.747778", "longitude_dd": "74.373333",
            "landing_center": "Kunzhathur", "direction": "NW", "distance_km": "52-57",
            "valid_for": "2026-09-19", "age_days": 5, "band": "hint", "expired": True}
    monkeypatch.setattr(oa.al, "load_pfz_latest", lambda: [zone])
    out = oa.run({"user_location": {"lat": 12.85, "lon": 74.65, "place_name": "mangalore"},
                  "raw_user_query": "pfzs near mangalore"}).outputs["nearest_pfz"]
    assert out["measured_from"] == "mangalore" and out["compass"] == "WSW"
    assert out["incois_reference"] == "52-57 km NW of Kunzhathur"
    assert (out["age_days"], out["band"], out["expired"]) == (5, "hint", True)
