"""LangGraph wiring — the ONLY place `langgraph` may be imported (plan §3.4).
No agent under orca/agents/ imports it; every node here is a thin wrapper
over a plain `run(state) -> AgentResult` function, via orca.trace.run_traced_node.
"""
from orca.graph.graph import build_graph

__all__ = ["build_graph"]
