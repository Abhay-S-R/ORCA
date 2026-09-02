"""Model-agnostic LLM layer (plan §3.1).

No file under `orca/agents/` may import a vendor SDK — enforced by CI grep.
Agents call `llm(tier="cheap").complete(...)`; they never name a model or a
vendor. This is the only place that changes.
"""
from orca.llm.tiers import llm

__all__ = ["llm"]
