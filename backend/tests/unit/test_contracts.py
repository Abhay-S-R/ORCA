"""Runnable check for the frozen contracts (Ground Rule 6). Also doubles as
the "CI green on an empty test" Phase 0 exit criterion until Phase 1 adds
real coverage.
"""
from orca.contracts import AgentResult, Confidence, SourceProvenance


def test_agent_result_round_trip() -> None:
    result = AgentResult(
        agent_name="weather_intelligence",
        query_id="q-1",
        reasoning_depth="STANDARD",
        inputs_consumed={"lat": 8.80, "lon": 78.14},
        outputs={"significant_wave_height_m": 1.4},
        source_provenance=SourceProvenance(
            dataset="Open-Meteo Marine API",
            acquisition_timestamp="2026-09-02T01:00:00Z",
            freshness_minutes=75,
        ),
        confidence=Confidence(score="HIGH", rationale="Direct NWP grid match"),
    )
    assert result.confidence.score == "HIGH"
    assert result.status == "ok"
    # frozen — this must raise, not silently accept a mutation
    try:
        result.status = "failed"  # type: ignore[misc]
        raise AssertionError("AgentResult must be frozen")
    except AttributeError:
        pass


def test_confidence_uses_underscore_not_hyphen() -> None:
    # Matches the confidence_tier Postgres enum (infra/db/001_init.sql) —
    # Postgres enums cannot contain hyphens. Regression check for that fix.
    c = Confidence(score="LOW_DATA", rationale="stale cache")
    assert c.score == "LOW_DATA"
