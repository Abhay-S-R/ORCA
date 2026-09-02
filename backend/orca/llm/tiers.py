"""Tier -> (provider, model) resolution, from env only, never hardcoded (plan §3.1/§3.3).

Tiers are fixed per agent (plan §3.2): cheap -> Agents 1, 2, 3 · mid -> Agent 9
· reasoning -> Agents 5 (DEEP), 10. Providers are configuration — swapping one
is an env change (`ORCA_LLM_<TIER>_PROVIDER` / `_MODEL` in .env), not a code
change.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from orca.llm.registry import get_provider

Tier = Literal["cheap", "mid", "reasoning"]


@dataclass
class _TieredClient:
    provider_name: str
    model: str

    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        return get_provider(self.provider_name).complete(messages, model=self.model, **kw)

    def stream(self, messages: list[dict[str, str]], **kw: Any) -> Iterator[str]:
        return get_provider(self.provider_name).stream(messages, model=self.model, **kw)


def llm(tier: Tier) -> _TieredClient:
    provider = os.environ.get(f"ORCA_LLM_{tier.upper()}_PROVIDER")
    model = os.environ.get(f"ORCA_LLM_{tier.upper()}_MODEL")
    if not provider or not model:
        raise RuntimeError(
            f"ORCA_LLM_{tier.upper()}_PROVIDER / _MODEL not set. "
            "Not decided yet — bake-off is Phase 2 (plan §3.3). Set both in .env to unblock locally."
        )
    return _TieredClient(provider, model)
