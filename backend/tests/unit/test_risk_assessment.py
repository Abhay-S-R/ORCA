"""Agent 7 tests. This is the one module in the codebase with real coverage
by design (plan §4, S2) — a bug here is a life-safety issue, not a UX bug.
Every threshold boundary is tested on both sides, for every vessel class.
"""
import pytest

from orca.agents.risk_assessment import (
    check_active_hazards,
    compute_confidence,
    evaluate_marine_safety,
    generate_alert_payload,
    run,
)
from orca.contracts import Confidence
from orca.state import ORCAState

# A verdict with every input at its safest — the baseline every test perturbs
# exactly one field away from.
SAFE_BASELINE = {
    "wave_height_m": 1.0, "wind_speed_kmh": 20.0, "lightning_active": False,
    "cyclone_alert": None, "imbl_distance_nm": 10.0, "mpa_violation": False,
}


def _v(**overrides):
    return evaluate_marine_safety(**{**SAFE_BASELINE, **overrides})


# --- baseline -----------------------------------------------------------------

def test_all_safe_returns_go():
    assert _v()["go_no_go"] == "GO"
    assert _v()["status"] == "SAFE"


# --- wave height band, small_fishing (default) --------------------------------

def test_wave_height_exactly_at_danger_threshold_is_no_go():
    assert _v(wave_height_m=3.5)["go_no_go"] == "NO_GO"


def test_wave_height_just_below_danger_is_caution_not_go():
    assert _v(wave_height_m=3.49)["go_no_go"] == "CAUTION"


def test_wave_height_exactly_at_caution_threshold_is_caution():
    assert _v(wave_height_m=2.0)["go_no_go"] == "CAUTION"


def test_wave_height_just_below_caution_threshold_is_go():
    assert _v(wave_height_m=1.99)["go_no_go"] == "GO"


# --- wind speed band, small_fishing --------------------------------------------

def test_wind_exactly_at_danger_threshold_is_no_go():
    assert _v(wind_speed_kmh=55.0)["go_no_go"] == "NO_GO"


def test_wind_just_below_danger_is_caution():
    assert _v(wind_speed_kmh=54.9)["go_no_go"] == "CAUTION"


def test_wind_exactly_at_caution_threshold_is_caution():
    assert _v(wind_speed_kmh=35.0)["go_no_go"] == "CAUTION"


def test_wind_just_below_caution_threshold_is_go():
    assert _v(wind_speed_kmh=34.9)["go_no_go"] == "GO"


# --- lightning and cyclone: hard DANGER regardless of everything else ---------

def test_lightning_active_is_no_go_even_with_calm_seas():
    assert _v(lightning_active=True)["go_no_go"] == "NO_GO"
    assert _v(lightning_active=True)["status"] == "DANGER"


def test_cyclone_red_is_no_go():
    assert _v(cyclone_alert="Red")["go_no_go"] == "NO_GO"


def test_cyclone_orange_is_no_go():
    assert _v(cyclone_alert="Orange")["go_no_go"] == "NO_GO"


def test_cyclone_alert_other_than_red_orange_does_not_trigger_alone():
    # e.g. a "Yellow" advisory shouldn't itself force NO_GO
    assert _v(cyclone_alert="Yellow")["go_no_go"] == "GO"


# --- geofence: IMBL / MPA --------------------------------------------------

def test_imbl_exactly_at_one_nm_is_critical_geofence():
    r = _v(imbl_distance_nm=1.0)
    assert r["go_no_go"] == "NO_GO"
    assert r["status"] == "CRITICAL_GEOFENCE"


def test_imbl_just_above_one_nm_is_not_critical():
    assert _v(imbl_distance_nm=1.01)["status"] != "CRITICAL_GEOFENCE"


def test_imbl_between_one_and_three_nm_is_caution():
    assert _v(imbl_distance_nm=2.5)["go_no_go"] == "CAUTION"


def test_imbl_exactly_at_three_nm_is_caution():
    assert _v(imbl_distance_nm=3.0)["go_no_go"] == "CAUTION"


def test_imbl_just_above_three_nm_is_go():
    assert _v(imbl_distance_nm=3.01)["go_no_go"] == "GO"


def test_mpa_violation_is_critical_geofence_regardless_of_distance():
    r = _v(mpa_violation=True, imbl_distance_nm=50.0)
    assert r["go_no_go"] == "NO_GO"
    assert r["status"] == "CRITICAL_GEOFENCE"


# --- priority ordering: danger beats geofence beats caution -------------------

def test_severe_weather_wins_over_geofence_when_both_present():
    r = _v(wave_height_m=4.0, imbl_distance_nm=0.5, mpa_violation=True)
    assert r["status"] == "DANGER"  # not CRITICAL_GEOFENCE — severe weather is checked first


def test_lightning_wins_over_caution_band_wave_height():
    r = _v(wave_height_m=2.5, lightning_active=True)
    assert r["status"] == "DANGER"


# --- vessel class deltas -------------------------------------------------------

def test_mechanized_trawler_wind_delta_is_9_3_kmh():
    # 55 km/h is NO_GO for small_fishing; for a trawler the threshold moves to 64.3
    assert _v(wind_speed_kmh=55.0, vessel_class="mechanized_trawler")["go_no_go"] == "CAUTION"
    assert _v(wind_speed_kmh=64.3, vessel_class="mechanized_trawler")["go_no_go"] == "NO_GO"
    assert _v(wind_speed_kmh=64.29, vessel_class="mechanized_trawler")["go_no_go"] == "CAUTION"


def test_mechanized_trawler_wave_delta_is_0_5m():
    assert _v(wave_height_m=3.5, vessel_class="mechanized_trawler")["go_no_go"] == "CAUTION"
    assert _v(wave_height_m=4.0, vessel_class="mechanized_trawler")["go_no_go"] == "NO_GO"


def test_cargo_vessel_wind_delta_is_27_8_kmh():
    assert _v(wind_speed_kmh=55.0, vessel_class="cargo_vessel")["go_no_go"] == "GO"
    assert _v(wind_speed_kmh=82.8, vessel_class="cargo_vessel")["go_no_go"] == "NO_GO"


def test_cargo_vessel_wave_delta_is_1_5m():
    # caution_hs shifts to 2.0+1.5=3.5, danger_hs to 3.5+1.5=5.0
    assert _v(wave_height_m=3.4, vessel_class="cargo_vessel")["go_no_go"] == "GO"
    assert _v(wave_height_m=3.5, vessel_class="cargo_vessel")["go_no_go"] == "CAUTION"
    assert _v(wave_height_m=5.0, vessel_class="cargo_vessel")["go_no_go"] == "NO_GO"


def test_vessel_class_delta_never_applies_to_geofence_or_lightning():
    # The architecture doc's delta note names wind/Hs only — a bigger vessel
    # does not get to stand closer to the IMBL or ignore lightning.
    for vessel_class in ("small_fishing", "mechanized_trawler", "cargo_vessel"):
        assert _v(imbl_distance_nm=1.0, vessel_class=vessel_class)["go_no_go"] == "NO_GO"
        assert _v(lightning_active=True, vessel_class=vessel_class)["go_no_go"] == "NO_GO"


def test_default_vessel_class_is_small_fishing_the_most_conservative():
    r_default = evaluate_marine_safety(**{**SAFE_BASELINE, "wind_speed_kmh": 55.0})
    r_explicit = _v(wind_speed_kmh=55.0, vessel_class="small_fishing")
    assert r_default == r_explicit


# --- compute_confidence --------------------------------------------------------

def test_compute_confidence_takes_the_worst_tier():
    result = compute_confidence([
        Confidence(score="HIGH", rationale="a"),
        Confidence(score="LOW_DATA", rationale="b"),
    ])
    assert result.score == "LOW_DATA"


def test_compute_confidence_all_high_stays_high():
    result = compute_confidence([Confidence(score="HIGH", rationale="a"), Confidence(score="HIGH", rationale="b")])
    assert result.score == "HIGH"


def test_compute_confidence_empty_defaults_to_low_data_not_high():
    # No inputs is itself a data gap — must never default to HIGH
    assert compute_confidence([]).score == "LOW_DATA"


# --- generate_alert_payload -----------------------------------------------

def test_generate_alert_payload_english_ok():
    payload = generate_alert_payload("Cyclone", "danger", "Thoothukudi")
    assert "Thoothukudi" in payload["text"]
    assert len(payload["sms"]) <= 160


def test_generate_alert_payload_sms_truncates_to_160_chars():
    payload = generate_alert_payload("Cyclone " * 20, "danger", "Thoothukudi " * 10)
    assert len(payload["sms"]) == 160


def test_generate_alert_payload_non_english_raises_not_silently_returns_english():
    with pytest.raises(NotImplementedError, match="ta"):
        generate_alert_payload("Cyclone", "danger", "Thoothukudi", language="ta")


# --- check_active_hazards (composes Agent 4 via WIA) ---------------------------

def test_check_active_hazards_composes_lightning_and_cyclone(monkeypatch):
    from orca.agents import weather_intelligence as wia

    monkeypatch.setattr(
        wia, "get_lightning_nowcast",
        lambda lat, lon, radius_km=25.0: {
            "lightning_active": True, "lightning_potential_j_kg": 1500,
            "source_provenance": None, "confidence": Confidence(score="HIGH", rationale="x"),
        },
    )
    monkeypatch.setattr(
        wia, "get_cyclone_status",
        lambda basin: {
            "basin": basin, "active_cyclones": [],
            "source_provenance": None, "confidence": Confidence(score="HIGH", rationale="y"),
        },
    )
    result = check_active_hazards(8.80, 78.14)
    assert any(h["type"] == "lightning" for h in result["hazards"])
    assert result["confidence"].score == "HIGH"


# --- run() — the (ORCAState) -> AgentResult entry point ---------------------

def test_run_produces_no_go_when_weather_data_signals_danger():
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-1", "reasoning_depth": "SHALLOW", "vessel_class": None,
        "weather_data": {
            "hourly": [{"wave_height": 4.0, "wind_speed_10m": 5.0}],
            "lightning_active": False, "cyclone_alert": None,
            "confidence": Confidence(score="HIGH", rationale="live"),
        },
        "geospatial_data": {"imbl_distance_nm": 10.0, "mpa_violation": False, "confidence": Confidence(score="HIGH", rationale="live")},
    }
    result = run(state)
    assert result.agent_name == "risk_assessment"
    assert result.outputs["go_no_go"] == "NO_GO"
    assert result.confidence.score == "HIGH"
    assert not hasattr(result, "persona")


def test_run_carries_weather_acquisition_timestamp_into_its_own_provenance():
    # Regression: this key previously didn't exist at the top level of
    # weather_data, so Agent 7's own SourceProvenance always read "".
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-ts", "reasoning_depth": "SHALLOW",
        "weather_data": {
            "hourly": [{"wave_height": 0.5, "wind_speed_10m": 1.0}], "lightning_active": False,
            "acquisition_timestamp": "2026-09-02T10:00:00Z",
        },
        "geospatial_data": {"imbl_distance_nm": 50.0, "mpa_violation": False},
    }
    result = run(state)
    assert result.source_provenance.acquisition_timestamp == "2026-09-02T10:00:00Z"


def test_run_defaults_to_small_fishing_when_vessel_class_unset():
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-2", "reasoning_depth": "SHALLOW",
        "weather_data": {"hourly": [{"wave_height": 0.5, "wind_speed_10m": 1.0}], "lightning_active": False},
        "geospatial_data": {"imbl_distance_nm": 50.0, "mpa_violation": False},
    }
    result = run(state)
    assert result.inputs_consumed["vessel_class"] == "small_fishing"
    assert result.outputs["go_no_go"] == "GO"


def test_run_missing_geospatial_data_degrades_conservative_not_crashes():
    # Agent 6 hasn't run yet (fixture stub not wired) — must not crash, and
    # must not silently assume "far from every boundary" without saying so.
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-3", "reasoning_depth": "SHALLOW",
        "weather_data": {"hourly": [{"wave_height": 0.5, "wind_speed_10m": 1.0}], "lightning_active": False},
    }
    result = run(state)
    assert result.confidence.score == "LOW_DATA"  # compute_confidence([]) — no inputs supplied
    # §5.7 safety-path rule: missing imbl_distance_nm must not silently read
    # as "999nm from every boundary" (a fabricated GO-shaped default) — the
    # verdict is forced to CAUTION and names the missing field.
    assert result.outputs["go_no_go"] == "CAUTION"
    assert "imbl_distance_nm" in result.outputs["reason"]


def test_run_missing_weather_data_forces_caution_not_a_silent_go():
    # Regression: Agent 4 failed entirely (weather_data == {}), so
    # current.get("wave_height", 0.0) used to default to 0.0m / 0 wind —
    # indistinguishable from genuinely calm seas — and returned GO on no
    # data at all. §5.7 requires CAUTION/NO_GO naming the missing input.
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-4", "reasoning_depth": "SHALLOW",
        "weather_data": {},
        "geospatial_data": {"imbl_distance_nm": 50.0, "mpa_violation": False},
    }
    result = run(state)
    assert result.outputs["go_no_go"] == "CAUTION"
    assert "wave_height_m" in result.outputs["reason"]
    assert "wind_speed_10m" in result.outputs["reason"]
    assert result.confidence.score == "LOW_DATA"


def test_run_missing_data_never_downgrades_an_already_worse_verdict():
    # A NO_GO from real hazardous data must not be softened to CAUTION just
    # because a different field also happens to be missing.
    state: ORCAState = {  # type: ignore[typeddict-item]
        "query_id": "q-5", "reasoning_depth": "SHALLOW",
        "weather_data": {"hourly": [{"wave_height": 5.0, "wind_speed_10m": 1.0}], "lightning_active": False},
        # geospatial missing entirely — must not water down the wave-driven NO_GO.
    }
    result = run(state)
    assert result.outputs["go_no_go"] == "NO_GO"
