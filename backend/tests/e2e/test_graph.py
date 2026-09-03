"""End-to-end graph test (plan §5.8 skeleton) — the regression net for the
whole Phase 1 slice. Every upstream call is mocked or reads a real recorded
fixture except geospatial (real, in-memory, no network — cheap enough to run
for real rather than mock) and the explicitly-marked IndicTrans2 test, which
skips itself where the gated weights aren't present. Nothing here touches
the network by default, matching the plan's own requirement that CI stays
green with an upstream down.
"""
from pathlib import Path

import httpx
import pytest

from orca.agents import language
from orca.agents import weather_intelligence as wia
from orca.graph.graph import build_graph
from orca.state import ORCAState

ALL_NODES = {
    "distress_check", "language_ingress", "planning", "weather_intelligence",
    "geospatial", "ocean_analytics", "risk_assessment", "visualization",
    "reporting", "language_egress",
}

import importlib.util

_TOOLKIT_PRESENT = importlib.util.find_spec("IndicTransToolkit") is not None

_HF_HUB = Path.home() / ".cache" / "huggingface" / "hub"
_INDICTRANS2_WEIGHTS_PRESENT = (
    _TOOLKIT_PRESENT
    and any(_HF_HUB.glob("models--ai4bharat--indictrans2-indic-en*"))
    and any(_HF_HUB.glob("models--ai4bharat--indictrans2-en-indic*"))
)


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


@pytest.fixture(autouse=True)
def no_translation_backend_leaks_between_tests(monkeypatch):
    # register_translation_backend is module-global state; make sure no test
    # leaves a backend registered for the next one to accidentally depend on.
    monkeypatch.setattr(language, "_backend", None)


def _base_state(query: str) -> ORCAState:
    return {  # type: ignore[typeddict-item]
        "query_id": "e2e-1",
        "raw_user_query": query,
        "normalized_english_query": query,
        "reasoning_depth": "SHALLOW",
        "user_location": {"lat": 8.822495, "lon": 78.119064},
        "distress_flag": False,
    }


def _mock_calm_weather(monkeypatch):
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


def test_safety_query_end_to_end_produces_a_go_verdict(monkeypatch):
    _mock_calm_weather(monkeypatch)

    graph = build_graph()
    result = graph.invoke(_base_state("Is it safe to go to sea tomorrow morning near Thoothukudi?"))

    assert result["risk_assessment"]["go_no_go"] == "GO"
    assert "SAFETY_CHECK" in result["matched_intent_rows"]
    assert result["distress_flag"] is False
    # Every node actually ran — this is the regression net. Order between
    # weather_intelligence/geospatial isn't asserted: they're a real
    # parallel fan-out (langgraph doesn't guarantee which completes first).
    assert set(result["completed_nodes"]) == ALL_NODES
    assert result["completed_nodes"][0] == "distress_check"
    assert result["completed_nodes"][1] == "language_ingress"
    assert result["completed_nodes"][-1] == "language_egress"
    assert len(result["audit_trace_log"]) == len(ALL_NODES)  # one entry per node visited
    assert "GO" in result["final_english_response"]
    # Real geospatial ran (not a stub) — a real distance came back for a
    # known-far-from-the-boundary coordinate.
    assert result["geospatial_data"]["imbl_distance_nm"] > 3.0
    assert result["geospatial_data"]["mpa_violation"] is False
    # Real citations reached the top level, not a stub's empty/plain string.
    assert len(result["evidence_citations"]) >= 2
    # English query — vernacular response is the same as English (no
    # backend registered in this test, and English short-circuits anyway).
    assert result["final_vernacular_response"] == result["final_english_response"]


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


def test_distress_query_bypasses_everything_else():
    state = _base_state("எங்கள் படகு மூழ்குகிறது")  # "our boat is sinking"
    graph = build_graph()
    result = graph.invoke(state)

    assert result["distress_flag"] is True
    assert "MRCC" in result["final_english_response"]
    assert "1554" in result["final_english_response"]
    # Never touched language/Planning/Weather/RiskAssessment/Reporting — the
    # bypass is real, not cosmetic. And Agent 12 runs exactly once, not
    # twice — one node, one trace entry, which matters most on exactly this
    # path (SOS, <2s requirement).
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
    # it — the graph still reaches the end rather than crashing.
    assert result["completed_nodes"][-1] == "language_egress"
    weather_trace = next(e for e in result["audit_trace_log"] if e["agent_name"] == "weather_intelligence")
    assert weather_trace["status"] == "failed"


def test_tamil_query_translates_in_and_out_with_a_mocked_backend(monkeypatch):
    """Proves the translation WIRING is correct without paying for real
    model inference — a fast, deterministic, CI-safe stand-in for the real
    IndicTrans2 round trip below."""
    class _EchoBackend:
        def translate(self, text: str, source: str, target: str) -> str:
            return f"[{source}->{target}] {text}"

    monkeypatch.setattr(language, "_backend", _EchoBackend())
    _mock_calm_weather(monkeypatch)

    graph = build_graph()
    result = graph.invoke(_base_state("எங்களுக்கு பாதுகாப்பானதா?"))

    assert result["detected_language"] == "ta"
    # normalized_english_query was translated before Planning ever saw it
    # (proven by the echo prefix surviving into the routing decision — a
    # real Tamil string would never match Planning's English keyword table).
    assert result["normalized_english_query"].startswith("[ta->en]")
    # And the final response was translated back to Tamil on the way out.
    assert result["final_vernacular_response"].startswith("[en->ta]")
    assert result["final_english_response"] != result["final_vernacular_response"]


@pytest.mark.skipif(not _INDICTRANS2_WEIGHTS_PRESENT, reason="IndicTrans2 weights not downloaded on this machine")
def test_real_tamil_safety_query_end_to_end(monkeypatch):
    """The actual Phase 1 acceptance query (plan §1), through the real
    IndicTrans2 models, not a mock. Slow (real model inference twice) —
    that's expected and correct for the one test whose entire point is
    proving the real thing works, not just the wiring around it."""
    from orca.agents.language import IndicTrans2Backend, register_translation_backend

    register_translation_backend(IndicTrans2Backend())
    _mock_calm_weather(monkeypatch)

    graph = build_graph()
    result = graph.invoke(
        _base_state("நாளை காலை தூத்துக்குடி அருகே கடலுக்குச் செல்வது பாதுகாப்பானதா?")
    )

    assert result["detected_language"] == "ta"
    assert "GO" in result["final_english_response"]
    # Real Tamil script came back, not an untranslated passthrough.
    assert any(0x0B80 <= ord(ch) <= 0x0BFF for ch in result["final_vernacular_response"])
    assert result["final_vernacular_response"] != result["final_english_response"]


def test_network_cut_returns_a_verdict_forced_to_low_data(monkeypatch):
    # Plan §8 hardening check 2. The autouse offline_only fixture is the
    # network cut, so every weather tool takes its cached-fixture fallback
    # with no mocking beyond turning the block into the connection error a
    # real cut raises. A verdict must still come back, the tier must be
    # forced to LOW-DATA, and the citation must admit the data is cached and
    # stale rather than describing it as a live fetch.
    def cut(*a, **kw):
        raise httpx.ConnectError("network cut")

    monkeypatch.setattr(httpx, "get", cut)
    monkeypatch.setattr(wia, "_fetch_open_meteo", cut)

    graph = build_graph()
    result = graph.invoke(_base_state("is it safe to go to sea"))

    assert result["risk_assessment"]["go_no_go"] in {"GO", "CAUTION", "NO_GO"}
    assert result["confidence_tier"] == "LOW_DATA"

    weather_citation = next(
        c for c in result["evidence_citations"] if "Open-Meteo" in c["dataset"]
    )
    assert "cached" in weather_citation["dataset"]
    assert weather_citation["freshness_minutes"] > 0
