"""orca/confidence_score.py — the per-agent score is measured, capped, and never LLM-derived."""
from orca.agents import risk_assessment
from orca.api.trace_routes import _reasoning_summary
from orca.confidence_score import score_agent
from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.data.freshness import past_staleness_ceiling


def _result(label="HIGH", status="ok", **factors):
    return AgentResult(
        agent_name="weather_intelligence", query_id="q", reasoning_depth="SHALLOW",
        inputs_consumed={}, outputs={},
        source_provenance=SourceProvenance(dataset="d", acquisition_timestamp="", freshness_minutes=0),
        confidence=Confidence(score=label, rationale="r"), status=status, **factors,
    )


def test_all_measured_and_perfect_is_100_high():
    s = score_agent(_result(data_age_minutes=0, freshness_class="LIVE", fallback_depth=0, coverage=(2, 2)))
    assert (s["score"], s["label"]) == (100, "HIGH")


def test_unmeasured_factors_are_reported_not_rewarded():
    s = score_agent(_result())
    assert [f["value"] for f in s["factors"]] == [1.0, None, None, None]
    assert all(f["detail"] == "not measured" for f in s["factors"][1:])


def test_stale_cached_read_on_a_fallback_drops_to_low_data():
    # 5-day-old LIVE-class cache on fallback rung 1: 100 × 0.4 × 0.8 = 32
    s = score_agent(_result(label="MEDIUM", data_age_minutes=5 * 24 * 60, freshness_class="LIVE", fallback_depth=1, coverage=(2, 2)))
    assert (s["score"], s["label"]) == (32, "LOW_DATA")


def test_score_never_outranks_the_agents_rule_label():
    s = score_agent(_result(label="MEDIUM", data_age_minutes=0, freshness_class="STATIC", fallback_depth=0, coverage=(2, 2)))
    assert (s["score"], s["label"], s["capped_by_rule_label"]) == (74, "MEDIUM", True)


def test_missing_readings_and_failed_status():
    assert score_agent(_result(coverage=(1, 3)))["label"] == "LOW_DATA"
    assert score_agent(_result(label="LOW_DATA", status="failed"))["score"] == 0


# --- P0.5 staleness ceiling, and the answer tier following the scored label ----

def _risk_state(age_minutes, weather_conf="MEDIUM"):
    return {
        "query_id": "q", "reasoning_depth": "SHALLOW",
        "weather_data": {
            "hourly": [{"wave_height": 0.4, "wind_speed_10m": 2.0}],
            "lightning_active": False, "cyclone_alert": None,
            "freshness_minutes": age_minutes, "dataset": "Open-Meteo (cached)",
            "confidence": Confidence(score=weather_conf, rationale="w"),
        },
        "geospatial_data": {"imbl_distance_nm": 40.0, "mpa_violation": False,
                            "confidence": Confidence(score="MEDIUM", rationale="g")},
    }


def test_live_ceiling_is_two_hours():
    assert not past_staleness_ceiling(120, "LIVE") and past_staleness_ceiling(121, "LIVE")
    assert not past_staleness_ceiling(10**6, "STATIC")


def test_calm_but_50h_old_forecast_is_caution_not_go():
    r = risk_assessment.run(_risk_state(2992))
    assert r.outputs["go_no_go"] == "CAUTION"
    assert r.outputs["status"] == "CAUTION_STALE_DATA"
    assert "49 h old" in r.outputs["reason"]
    assert r.confidence.score == "LOW_DATA"


def test_calm_fresh_forecast_stays_go():
    assert risk_assessment.run(_risk_state(0)).outputs["go_no_go"] == "GO"


def test_weather_summary_reads_hourly_wave_height():
    assert _reasoning_summary("weather_intelligence", {"hourly": [{"wave_height": 1.24}]}, "ok").startswith("Hs 1.2 m")
    assert _reasoning_summary("weather_intelligence", {"hourly": [{"wave_height": float("nan")}]}, "ok").startswith("Hs ? m")
