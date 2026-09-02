"""ORCA specialist agents.

No file in this package may import a vendor LLM SDK (orca/llm/ is the only
place that happens — plan §3.1, enforced by CI grep) and no file here may
reference `persona` except Agents 1 and 9 (plan §5.4, enforced by CI grep —
this is the exact bug Architecture v2.0 fixed at the routing layer).

Every agent is a plain function `run(state: ORCAState) -> AgentResult` — no
`langgraph` import here either; only `orca/graph/` wires these into a graph
(plan §3.4). That keeps every agent unit-testable without a graph and
callable directly from Sentinel's background loop later.

What's here as of Phase 1: Agents 2 (planning), 4 (weather_intelligence), 7
(risk_assessment), 12 (distress) — S1/S2/S3 — plus Agents 1 (language), 3
(discovery), 6 (geospatial), 9 (reporting, thin) — S4/S5/S6. Agents 5
(Ocean Analytics), 8 (Visualization), 10 (Critic), 11 (Sentinel) are Phase
2-3 and deliberately absent (plan §7).
"""
