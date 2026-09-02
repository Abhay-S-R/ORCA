"""End-to-end graph test (plan §5.8 skeleton) — the regression net for the
whole Phase 1 slice. Every upstream call is mocked or reads a real recorded
fixture; nothing here touches the network, matching the plan's own
requirement that CI stays green with an upstream down.
"""
import httpx
import pytest

from orca.agents import weather_intelligence as wia
from orca.graph.graph import build_graph
from orca.state import ORCAState


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    """Nobody in this test file may make a real HTTP call — enforced, not
    just intended. Anything that reaches httpx.get/_fetch_open_meteo without
    an explicit per-test override fails loudly instead of silently hitting
    the network."""
    def blocked(*a, **kw):
        raise AssertionError("e2e test attempted a real network call — mock the boundary instead")

    monkeypatch.setattr(httpx, "get", blocked)
    monkeypatch.setattr(wia, "_fetch_open_meteo", lambda *a, **kw: blocked())


def _base_state(query: str) -> ORCAState:
    return {  # type: ignore[typeddict-item]
        "query_id": "e2e-1",
        "raw_user_query": query,
        "normalized_english_query": query,
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 8.822495, "lon": 78.119064},
        "distress_flag": False,
    }


def test_safety_query_end_to_end_produces_a_go_verdict(monkeypatch):
    # All-safe fixture: calm sea, no wind, no lightning, no cyclone alerts.
    monkeypatch.setattr(
        wia, "get_marine_weather",
        lambda lat, lon, hours_ahead=24: {
            # get_marine_weather() normally returns wind_speed_10m already
            # converted to m/s (normalize.py convention) — these mocks skip
            # that conversion by construction, so the units below ARE m/s,
            # not Open-Meteo's native km/h. 2.0 m/s = 7.2 km/h (calm).
            "hourly": [{"wave_height": 0.5, "wind_speed_10m": 2.0}],
            "source_provenance": wia.SourceProvenance(dataset="fixture", acquisition_timestamp="2026-09-02T00:00:00Z", freshness_minutes=0),
            "confidence": wia.Confidence(score="HIGH", rationale="fixture"),
        },
    )
    monkeypatch.setattr(
        wia, "get_lightning_nowcast",
        lambda lat, lon, radius_km=25.0: {
            "lightning_active": False, "lightning_potential_j_kg": 0,
            "source_provenance": None, "confidence": wia.Confidence(score="HIGH", rationale="fixture"),
        },
    )
    monkeypatch.setattr(
        wia, "get_cyclone_status",
        lambda basin: {
            "basin": basin, "active_cyclones": [],
            "source_provenance": None, "confidence": wia.Confidence(score="HIGH", rationale="fixture"),
        },
    )

    graph = build_graph()
    result = graph.invoke(_base_state("Is it safe to go to sea tomorrow morning near Thoothukudi?"))

    assert result["risk_assessment"]["go_no_go"] == "GO"
    assert "SAFETY_CHECK" in result["matched_intent_rows"]
    assert result["distress_flag"] is False
    # Every node actually ran — this is the regression net. Order between
    # weather_intelligence/geospatial_stub isn't asserted: they're a real
    # parallel fan-out (langgraph doesn't guarantee which completes first).
    assert set(result["completed_nodes"]) == {
        "distress_check", "planning", "weather_intelligence", "geospatial_stub", "risk_assessment", "reporting_stub",
    }
    assert result["completed_nodes"][0] == "distress_check"
    assert result["completed_nodes"][-1] == "reporting_stub"
    assert len(result["audit_trace_log"]) == 6  # one entry per node visited
    assert "GO" in result["final_english_response"]


def test_severe_weather_end_to_end_produces_no_go(monkeypatch):
    monkeypatch.setattr(
        wia, "get_marine_weather",
        lambda lat, lon, hours_ahead=24: {
            # 20.0 m/s = 72 km/h — also past the 55 km/h DANGER band on its own,
            # but 4.5m Hs is already the dominant trigger here.
            "hourly": [{"wave_height": 4.5, "wind_speed_10m": 20.0}],  # 4.5m Hs — well past 3.5m DANGER
            "source_provenance": wia.SourceProvenance(dataset="fixture", acquisition_timestamp="2026-09-02T00:00:00Z", freshness_minutes=0),
            "confidence": wia.Confidence(score="HIGH", rationale="fixture"),
        },
    )
    monkeypatch.setattr(
        wia, "get_lightning_nowcast",
        lambda lat, lon, radius_km=25.0: {
            "lightning_active": False, "lightning_potential_j_kg": 0,
            "source_provenance": None, "confidence": wia.Confidence(score="HIGH", rationale="fixture"),
        },
    )
    monkeypatch.setattr(
        wia, "get_cyclone_status",
        lambda basin: {
            "basin": basin, "active_cyclones": [],
            "source_provenance": None, "confidence": wia.Confidence(score="HIGH", rationale="fixture"),
        },
    )

    graph = build_graph()
    result = graph.invoke(_base_state("Is it safe to go to sea tomorrow morning near Thoothukudi?"))

    assert result["risk_assessment"]["go_no_go"] == "NO_GO"
    assert "NO_GO" in result["final_english_response"]


def test_distress_query_bypasses_planning_and_weather_entirely():
    state = _base_state("எங்கள் படகு மூழ்குகிறது")  # "our boat is sinking"
    graph = build_graph()
    result = graph.invoke(state)

    assert result["distress_flag"] is True
    assert "MRCC" in result["final_english_response"]
    assert "1554" in result["final_english_response"]
    # Never touched Planning/Weather/RiskAssessment — the bypass is real, not cosmetic.
    # And Agent 12 runs exactly once, not twice — one node, one trace entry,
    # which matters most on exactly this path (SOS, <2s requirement).
    assert result["completed_nodes"] == ["distress_check"]
    assert len(result["audit_trace_log"]) == 1
    assert result["audit_trace_log"][0]["agent_name"] == "distress"


def test_ui_sos_control_also_bypasses_even_with_calm_text():
    state = _base_state("is it safe to go to sea")
    state["distress_flag"] = True  # simulates the persistent SOS button tap
    graph = build_graph()
    result = graph.invoke(state)
    assert "MRCC" in result["final_english_response"]
    assert result["completed_nodes"] == ["distress_check"]
    assert len(result["audit_trace_log"]) == 1


def test_missing_upstream_source_degrades_rather_than_crashes(monkeypatch):
    # §5.7 degradation variant: weather's live fetch fails AND its cached
    # fallback port lookup also fails — the graph must still complete with a
    # forced-conservative answer, never a stack trace reaching the user.
    def raise_error(*a, **kw):
        raise RuntimeError("simulated total weather outage")

    monkeypatch.setattr(wia, "get_marine_weather", raise_error)

    graph = build_graph()
    result = graph.invoke(_base_state("is it safe to go to sea"))

    # The weather node's exception boundary (trace.run_traced_node) caught
    # it — the graph still reaches reporting_stub rather than crashing.
    assert result["completed_nodes"][-1] == "reporting_stub"
    weather_trace = next(e for e in result["audit_trace_log"] if e["agent_name"] == "weather_intelligence")
    assert weather_trace["status"] == "failed"
