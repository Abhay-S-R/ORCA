"""P6.6 (`R-DEMO-1`, orca_final §29.2) — `/demo`'s pinned-fixture rung.

"A one-click run of the production graph on a pinned fixture (the
`backend/tests/fixtures/` pattern), never a video or a hardcoded string." A
scenario's *query* still runs through the real, live, compiled graph — every
node, every span, Reporting and the Critic included — but the four agents
that fetch external data (marine_data_discovery, weather_intelligence,
ocean_analytics, geospatial) are short-circuited to a pinned prior real
reading instead of today's live one, so the scenario's verdict cannot flip
because a monsoon rolled in on demo day. `risk_assessment` itself is
untouched: it still computes the verdict live from whatever inputs it is
handed, pinned or not — the arithmetic that decides GO/CAUTION/NO_GO is never
mocked, only the readings feeding it are.

The fixture file (`backend/tests/fixtures/demo__safe_morning_mannar.json`) is
not hand-authored data — it is a byte-for-byte capture of a real
`GET /query` run's `GET /trace/{query_id}` output at 8.9N 78.5E on
2026-09-24 (`query_id 6cb6c3bf-f80f-4789-9099-f097205ac16e`), the same
"capture a real run, pin it" method `backend/tests/fixtures/`'s existing
files already use. Every `AgentResult` reconstructed from it carries a
`DEMO_ENGINE_SUFFIX`-tagged engine string, so the trace strip and
`/reasoning` both say "pinned demo fixture" rather than silently reading as
a fresh live fetch — the same DEMO provenance tier `Provenance.tsx` has
reserved for this since before this module existed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from orca.contracts import AgentResult, Confidence, SourceProvenance
from orca.state import ORCAState

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

DEMO_ENGINE_SUFFIX = " [pinned demo fixture, not live]"

# scenario_id -> {label, query, lat, lon, persona, fixture_file}. Only
# scenarios whose verdict must survive whatever the weather is doing on
# demo day need a fixture here — a distress query (scenario 5) bypasses
# every one of these four agents by construction (`distress_check_node`
# returns before `marine_data_discovery` ever runs), so it is not listed:
# it runs fully live and is just as reproducible without one.
SCENARIOS: dict[str, dict[str, Any]] = {
    "safe_morning_mannar": {
        "label": "Safe morning — Gulf of Mannar",
        "query": "Is it safe to go out this morning?",
        "lat": 8.9,
        "lon": 78.5,
        "persona": "fisherman",
        "fixture_file": "demo__safe_morning_mannar.json",
    },
}


def _load(fixture_file: str) -> dict[str, Any]:
    return json.loads((_FIXTURE_DIR / fixture_file).read_text(encoding="utf-8"))


def fixture_result(state: ORCAState, agent_name: str) -> AgentResult | None:
    """None on every ordinary query — this is the one branch that has to be
    provably a no-op for every non-demo call, since it sits at the top of
    four live agents. Returns a real `AgentResult` only when `state`
    carries a `demo_scenario` this module actually has a fixture for and
    that fixture covers `agent_name`."""
    scenario_id = state.get("demo_scenario")
    if not scenario_id:
        return None
    scenario = SCENARIOS.get(scenario_id)
    if not scenario:
        return None
    captured = _load(scenario["fixture_file"]).get(agent_name)
    if not captured:
        return None

    detail = captured.get("confidence_detail") or {}
    return AgentResult(
        agent_name=agent_name,
        query_id=state.get("query_id", ""),
        reasoning_depth=state.get("reasoning_depth", "SHALLOW"),  # type: ignore[arg-type]
        inputs_consumed=captured.get("inputs_consumed") or {},
        outputs=captured.get("outputs") or {},
        source_provenance=SourceProvenance(**captured["source_provenance"]) if captured.get("source_provenance") else SourceProvenance(
            dataset="pinned demo fixture", acquisition_timestamp=datetime.now(timezone.utc).isoformat(), freshness_minutes=0
        ),
        confidence=Confidence(
            score=detail.get("label", "MEDIUM"),
            rationale=(detail.get("rule_rationale") or "pinned demo fixture, captured from a real run") + DEMO_ENGINE_SUFFIX,
        ),
        status=captured.get("status", "ok"),
        engine=DEMO_ENGINE_SUFFIX.strip(),
    )


if __name__ == "__main__":
    fixture = _load(SCENARIOS["safe_morning_mannar"]["fixture_file"])
    assert {"marine_data_discovery", "geospatial", "ocean_analytics", "weather_intelligence"} <= set(fixture)

    state: ORCAState = {"demo_scenario": "safe_morning_mannar", "query_id": "t", "reasoning_depth": "SHALLOW"}  # type: ignore[typeddict-item]
    result = fixture_result(state, "geospatial")
    assert result is not None and result.outputs["imbl_distance_nm"] > 0
    assert result.engine == DEMO_ENGINE_SUFFIX.strip()

    assert fixture_result(state, "risk_assessment") is None  # not a fixture-covered agent
    assert fixture_result({"query_id": "t"}, "geospatial") is None  # type: ignore[typeddict-item]  # no demo_scenario at all

    print("demo_fixtures self-check ok")
