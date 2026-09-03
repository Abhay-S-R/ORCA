# Fixture convention (plan §6)

Every slice records one JSON fixture of its agent's output the day it first
works. S1 wires the LangGraph skeleton against these before real agents
exist; real integration on Day 6-7 becomes a swap, not a discovery, because
the shapes already matched.

## Naming

```
<agent_name>__<scenario>.json
```

`agent_name` matches `AgentResult.agent_name` exactly (e.g.
`weather_intelligence`, `geospatial`, `risk_assessment`). `scenario` is
lowercase snake_case describing the *case*, not the query verbatim:
`risk_assessment__caution_verdict`, not `risk_assessment__is_it_safe`.

## Recording

Use `orca.testing.fixtures.record_fixture(result, scenario)` — it writes
`dataclasses.asdict(AgentResult)` as pretty-printed, key-sorted JSON so diffs
stay small when a fixture is regenerated.

```python
from orca.testing.fixtures import record_fixture

result = my_agent.run(state)  # an AgentResult
record_fixture(result, "thoothukudi_caution")
```

## Replaying

```python
from orca.testing.fixtures import load_fixture

data = load_fixture("geospatial", "thoothukudi_gulf_of_mannar")
```

`load_fixture` returns the plain dict — reconstruct dataclasses from it only
where a test needs the frozen/typed form back; most consumers (the SSE mock,
frontend fixtures) just need the dict.

## What's already here

- `geospatial__thoothukudi_gulf_of_mannar.json` — `check_boundary_proximity`
  + `point_in_polygon` at the pilot query's coordinates.
- `discovery__wave_height.json` — `select_best_source` picking between the
  two Tier 1 wave-height sources.

Agent 3 (Phase 2 D2), regenerate with `python -m orca.agents.discovery`:

- `discovery__chlorophyll_primary.json` — the healthy primary pick.
- `discovery__sst_fallback_cascade.json` — the same picker after the primary
  is declared down, walking the Architecture §12.1 chain.

Agent 5 (Phase 2 D2), regenerate with `python -m orca.agents.ocean_analytics`:

- `ocean_analytics__thoothukudi_deep_multi_intent.json` — the full `run()`
  envelope at DEEP depth (tide + PFZ + sector + diagnosis).
- `ocean_analytics__tide_soi_primary.json` / `__tide_stormglass_fallback.json`
  — both rungs of the tide cascade. Note the `datum` field differs between
  them; the heights are not comparable across the two.
- `ocean_analytics__sector_cloud_cover.json` — the suppressed pilot sector
  plus the full SEC001–SEC014 roster.
- `ocean_analytics__wind_rose_thoothukudi.json` — 16-point directional bins.
- `ocean_analytics__catch_diagnosis_mumbai.json` — the no-recent-decline
  branch of `diagnose_productivity_decline`.
- `ocean_analytics__sst_chl_awaiting_d3.json` — the LOW_DATA shape returned
  while D3's gridded fixtures (§4.2) are absent, so consumers can build
  against the degraded path before the real one exists.

All were recorded from real pilot data (`data/`), not hand-written —
regenerate them with the module commands above if the source files change.
