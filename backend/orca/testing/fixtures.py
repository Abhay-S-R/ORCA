"""Fixture record/replay harness (plan §6, S4 Day 5).

Every slice records one JSON fixture of its agent's output the day it first
works. S1 wires the LangGraph skeleton against these fixtures before real
agents exist; integration on Day 6-7 becomes a swap, not a discovery,
because the shapes already matched.

Convention: `backend/tests/fixtures/<agent_name>__<scenario>.json`, holding
`dataclasses.asdict(AgentResult)`. Scenario names are lowercase snake_case
describing the case, not the query verbatim
(`risk_assessment__caution_verdict`, not `risk_assessment__is_it_safe`).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from orca.contracts import AgentResult

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"


def fixture_path(agent_name: str, scenario: str) -> Path:
    return FIXTURES_DIR / f"{agent_name}__{scenario}.json"


def record_fixture(result: AgentResult, scenario: str) -> Path:
    path = fixture_path(result.agent_name, scenario)
    path.write_text(json.dumps(asdict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_fixture(agent_name: str, scenario: str) -> dict:
    return json.loads(fixture_path(agent_name, scenario).read_text(encoding="utf-8"))


if __name__ == "__main__":
    from orca.contracts import Confidence, SourceProvenance

    sample = AgentResult(
        agent_name="_selfcheck",
        query_id="q-selfcheck",
        reasoning_depth="SHALLOW",
        inputs_consumed={"lat": 8.70, "lon": 78.50},
        outputs={"ok": True},
        source_provenance=SourceProvenance(dataset="test", acquisition_timestamp="2026-09-02T00:00:00Z", freshness_minutes=0),
        confidence=Confidence(score="HIGH", rationale="self-check"),
    )
    path = record_fixture(sample, "roundtrip")
    reloaded = load_fixture("_selfcheck", "roundtrip")
    assert reloaded["query_id"] == "q-selfcheck"
    path.unlink()
    print("fixtures self-check ok")
