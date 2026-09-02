"""ORCA specialist agents.

No file in this package may import a vendor LLM SDK (orca/llm/ is the only
place that happens — plan §3.1, enforced by CI grep) and no file here may
reference `persona` except Agents 1 and 9 (plan §5.4, enforced by CI grep —
this is the exact bug Architecture v2.0 fixed at the routing layer).

Every agent is a plain function `run(state: ORCAState) -> AgentResult` — no
`langgraph` import here either; only `orca/graph/` wires these into a graph
(plan §3.4). That keeps every agent unit-testable without a graph and
callable directly from Sentinel's background loop later.
"""
