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

Both were recorded from real pilot data (`data/tier1/`), not hand-written —
regenerate them with `python -m orca.agents.geospatial` /
`python -m orca.agents.discovery` if the underlying source files change.
