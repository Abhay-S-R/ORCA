import json
from unittest.mock import MagicMock, patch

from orca.agents.critic import (
    _REINVOKE_MAP,
    _RUBRIC,
    MAX_ITERATIONS,
    _parse_judge_response,
    _verdict_header,
    build_facts_block,
    run,
    run_critic_pass,
)

_NARRATIVE = "GO: conditions within safe thresholds. Wave height 0.8m, well below the 2.0m caution band."


def _deep_state(matched_intent_rows: list[str] | None = None) -> dict:
    return {
        "query_id": "q-1",
        "reasoning_depth": "DEEP",
        "normalized_english_query": "why has catch declined",
        "final_english_response": _NARRATIVE,
        "matched_intent_rows": matched_intent_rows or [],
        "risk_assessment": {"go_no_go": "GO"},
        "weather_data": {"wave_height": 0.8},
        "geospatial_data": {"imbl_distance_nm": 16.3},
        "ocean_data": {},
    }


def test_rubric_and_reinvoke_map_cover_the_same_five_items():
    assert set(_REINVOKE_MAP) == set(_RUBRIC)
    assert len(_RUBRIC) == 5


def test_clean_narrative_passes_on_first_iteration():
    fake_client = MagicMock()
    fake_client.complete.return_value = "[]"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        final, passed, iterations, issues = run_critic_pass(
            "q", _NARRATIVE, "wave_height_m: 0.8", is_safety_check=True,
        )
    assert passed is True
    assert iterations == 1
    assert issues == []
    assert final == _NARRATIVE
    fake_client.complete.assert_called_once()  # judge only, no revise call needed


def test_flagged_narrative_gets_revised_and_verdict_header_survives():
    fake_client = MagicMock()
    judge_response = json.dumps([{"rubric_item": "causal_claim_strength", "description": "overclaims causation"}])
    fake_client.complete.side_effect = [
        judge_response,
        "GO: conditions within safe thresholds. Catch decline correlates with, but is not proven caused by, SST rise.",
        "[]",
    ]
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        final, passed, iterations, _issues = run_critic_pass(
            "q", _NARRATIVE, "wave_height_m: 0.8", is_safety_check=False,
        )
    assert final.startswith("GO:")
    assert passed is True
    assert iterations == 2


def test_revision_that_drops_the_verdict_header_is_rejected():
    fake_client = MagicMock()
    judge_response = json.dumps([{"rubric_item": "spatial_accuracy", "description": "wrong distance"}])
    fake_client.complete.side_effect = [judge_response, "conditions are fine, no verdict here"]
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        final, passed, _iterations, _issues = run_critic_pass(
            "q", _NARRATIVE, "imbl_distance_nm: 16.3", is_safety_check=False,
        )
    assert final == _NARRATIVE  # kept the pre-revision text
    assert passed is False


def test_never_exceeds_max_iterations():
    fake_client = MagicMock()
    always_flag = json.dumps([{"rubric_item": "temporal_coherence", "description": "tense mismatch"}])
    fake_client.complete.side_effect = [
        always_flag, "GO: conditions within safe thresholds. revised.",
    ] * MAX_ITERATIONS
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        _, passed, iterations, _ = run_critic_pass("q", _NARRATIVE, "facts", is_safety_check=False)
    assert iterations == MAX_ITERATIONS
    assert passed is False


def test_run_never_alters_the_verdict_header_even_on_llm_failure():
    with patch("orca.llm.tiers.llm", side_effect=RuntimeError("no key")):
        result = run(_deep_state())
    assert result.status == "degraded"
    assert result.outputs["final_english_response"] == _NARRATIVE
    assert result.outputs["critic_pass"] is False


def test_run_on_safety_check_reviews_prose_only_never_the_verdict():
    fake_client = MagicMock()
    fake_client.complete.return_value = "[]"
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        result = run(_deep_state(matched_intent_rows=["SAFETY_CHECK"]))
    assert _verdict_header(result.outputs["final_english_response"]) == "GO:"
    assert result.outputs["critic_pass"] is True


def test_run_never_references_persona_the_ci_guard_would_catch():
    import re

    from orca import agents

    guard_pattern = re.compile(r"\bstakeholder_persona\b|\bpersona['\"]?\s*[:=]|\[['\"]persona['\"]]|\.get\(['\"]persona")
    critic_path = f"{agents.__path__[0]}/critic.py"
    with open(critic_path, encoding="utf-8") as f:
        code_only = "\n".join(line for line in f if not line.strip().startswith("#"))
    # Strip the module/function docstrings (triple-quoted blocks) before
    # checking, the same way a human reviewer reads code vs. comments — the
    # guard's own regex has no docstring awareness, so this mirrors what CI
    # actually executes rather than a laxer approximation of it.
    code_only = re.sub(r'"""[\s\S]*?"""', "", code_only)
    assert not guard_pattern.search(code_only)


def test_build_facts_block_includes_hazard_nowcasts_and_cyclone_tracks():
    state = {
        "weather_data": {
            "hourly": [{"wave_height": 1.2, "wind_speed_10m": 8.0}],
            "incois_hazard": {
                "active_warnings": [
                    {"hazard_type": "high_wave", "district": "Ernakulam", "message": "Waves up to 3.2m"}
                ]
            },
            "imd_nowcast": {
                "expired": False,
                "alerts": [
                    {"district": "Kollam", "severity_color": "orange", "event_category": "thunderstorm"}
                ]
            },
            "lightning_source_agreement": "disagree",
            "cyclone_tracks": [
                {"name": "MANDOUS", "basin": "BOB", "distance_km": 150.0, "max_wind_kmh": 85.0}
            ],
        },
        "risk_assessment": {"go_no_go": "CAUTION", "reason": "Elevated waves"},
        "geospatial_data": {},
        "ocean_data": {},
    }
    facts = build_facts_block(state)
    assert "incois_hazard_warnings: Ernakulam (High Wave): Waves up to 3.2m" in facts
    assert "imd_convective_nowcast_alerts: Kollam (Orange alert: thunderstorm)" in facts
    assert "lightning_source_agreement: disagree" in facts
    assert "active_cyclone_tracks: MANDOUS (basin BOB, 150 km away, winds 85 km/h)" in facts


def test_build_facts_block_includes_geospatial_depth_bearing_and_zones():
    state = {
        "geospatial_data": {
            "imbl_distance_nm": 12.5,
            "imbl_bearing_deg": 185.0,
            "imbl_boundary_name": "Sri Lanka IMBL",
            "imbl_boundary_band": "CAUTION",
            "shallow_hazard": True,
            "depth_m": 6.4,
            "mpa_regulatory": [{"name": "Gulf of Mannar", "designation": "National Park"}],
            "nearby_zones": [{"name": "Palk Bay Zone", "designation": "Restricted", "distance_nm": 8.2}],
        },
        "weather_data": {},
        "risk_assessment": {},
        "ocean_data": {},
    }
    facts = build_facts_block(state)
    assert "maritime_boundary_bearing_deg: 185.0" in facts
    assert "maritime_boundary_name: Sri Lanka IMBL" in facts
    assert "maritime_boundary_band: CAUTION" in facts
    assert "shallow_water_hazard: True" in facts
    assert "bathymetric_depth_m: 6.4" in facts
    assert "inside_regulatory_mpa: Gulf of Mannar (National Park)" in facts
    assert "nearby_avoidance_zones_within_50nm: Palk Bay Zone (Restricted) 8.2 nm" in facts


def test_build_facts_block_includes_ocean_fishing_ban_species_and_stats():
    state = {
        "ocean_data": {
            "nearest_pfz": {
                "found": True,
                "distance_km": 25.0,
                "fishing_ban": {
                    "available": True,
                    "in_ban_period": True,
                    "coast": "west",
                    "window": "10 June to 31 July",
                    "exemptions": "traditional craft",
                },
                "top_species": [
                    {"name": "Indian Mackerel", "scientific_name": "Rastrelliger kanagurta"},
                    {"name": "Oil Sardine", "scientific_name": "Sardinella longiceps"},
                ],
                "boundary_note": "Within territorial waters",
            },
            "sector_disclosure": "Advisory mapped from Kerala sector",
            "tide": {
                "tidal_state": "Ebb",
                "station_name": "Kochi",
                "next_high": {"height_m": 1.1, "in_hours": 3.5, "when": "2026-10-11T09:30:00Z"},
            },
            "sst_chlorophyll_correlation": {
                "available": True,
                "pearson_r": 0.45,
                "relationship": "moderate positive",
                "n_samples": 40,
            },
            "wind_anomaly": {
                "available": True,
                "anomalous": True,
                "observed_peak": 42.0,
                "units": "km/h",
                "direction": "high",
                "baseline_days": 30,
                "nearest_port": "Cochin",
            },
            "historical_comparison": {
                "available": True,
                "statement": "Wind speeds are in the 90th percentile of October observations.",
            },
        },
        "weather_data": {},
        "geospatial_data": {},
        "risk_assessment": {},
    }
    facts = build_facts_block(state)
    assert "seasonal_fishing_ban: annual uniform fishing ban in force on west coast; window 10 June to 31 July; exemptions: traditional craft" in facts
    assert "top_target_fish_species: Indian Mackerel (Rastrelliger kanagurta), Oil Sardine (Sardinella longiceps)" in facts
    assert "nearest_fishing_zone_boundary_note: Within territorial waters" in facts
    assert "sector_fallback_disclosure: Advisory mapped from Kerala sector" in facts
    assert "tide_station_name: Kochi" in facts
    assert "next_high_tide_time: 15:00 IST (2026-10-11T09:30:00Z)" in facts
    assert "sst_chlorophyll_correlation: r=0.45 (moderate positive), 40 samples" in facts
    assert "wind_anomaly_against_era5: peak 42.0 km/h is anomalous (high) vs 30-day ERA5 baseline at Cochin" in facts
    assert "historical_climate_comparison: Wind speeds are in the 90th percentile of October observations." in facts


def test_parse_judge_response_handles_fenced_markdown_and_prose():
    fenced_raw = """Here is my review:
```json
[
    {"rubric_item": "Spatial Accuracy", "description": "boundary distance discrepancy"},
    {"rubric_item": "factual consistency", "description": "contradicts wave height"}
]
```
Please let me know if you need more details."""
    issues = _parse_judge_response(fenced_raw)
    assert len(issues) == 2
    assert issues[0].rubric_item == "spatial_accuracy"
    assert issues[0].reinvoke_agent == "geospatial"
    assert issues[1].rubric_item == "factual_consistency"
    assert issues[1].reinvoke_agent == "reporting"


def test_standard_depth_skips_redundant_revise_when_specialist_reinvocation_targeted():
    fake_client = MagicMock()
    judge_response = json.dumps([{"rubric_item": "spatial_accuracy", "description": "wrong distance to boundary"}])
    fake_client.complete.return_value = judge_response

    with patch("orca.llm.tiers.llm", return_value=fake_client):
        final, passed, iterations, issues = run_critic_pass(
            "q", _NARRATIVE, "facts", is_safety_check=False,
            max_iterations=1, can_reinvoke=True,
        )

    # D3: The revise call was skipped to save LLM tokens since specialist will be re-invoked
    assert fake_client.complete.call_count == 1
    assert passed is False
    assert iterations == 1
    assert len(issues) == 1
    assert issues[0].reinvoke_agent == "geospatial"
    assert final == _NARRATIVE


def test_standard_depth_safe_prose_revision_passes_clean():
    fake_client = MagicMock()
    judge_response = json.dumps([{"rubric_item": "citation_completeness", "description": "unsourced claim"}])
    revised_text = "GO: conditions within safe thresholds. Wave height 0.8m reported by buoy."
    fake_client.complete.side_effect = [judge_response, revised_text]

    with patch("orca.llm.tiers.llm", return_value=fake_client):
        final, passed, iterations, issues = run_critic_pass(
            "q", _NARRATIVE, "facts", is_safety_check=False,
            max_iterations=1, can_reinvoke=True,
        )

    # 1 judge call + 1 revise call; since citation_completeness maps to reporting (non-reinvocable),
    # the safe revision passes clean on 1 iteration
    assert fake_client.complete.call_count == 2
    assert passed is True
    assert iterations == 1
    assert len(issues) == 1
    assert final == revised_text


def test_run_clears_reinvoke_agent_when_critic_passes():
    fake_client = MagicMock()
    fake_client.complete.return_value = "[]"  # passes clean
    with patch("orca.llm.tiers.llm", return_value=fake_client):
        result = run(_deep_state())
    assert result.outputs["critic_pass"] is True
    assert result.outputs["reinvoke_agent"] is None


if __name__ == "__main__":
    print("run via pytest: pytest backend/tests/unit/test_critic.py")

