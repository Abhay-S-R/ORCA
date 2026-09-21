"""Tier -> (provider, model) resolution, from env only, never hardcoded (plan §3.1/§3.3).

Tiers are fixed per agent (plan §3.2): cheap -> Agents 1, 2, 3 · mid -> Agent 9
· reasoning -> Agents 5 (DEEP), 10. Providers are configuration — swapping one
is an env change (`ORCA_LLM_<TIER>_PROVIDER` / `_MODEL` in .env), not a code
change.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

# Auto-load .env from repository root or backend folder
for _p in [Path(__file__).resolve().parents[3] / ".env", Path(__file__).resolve().parents[2] / ".env"]:
    if _p.exists():
        load_dotenv(_p)

from orca.llm.registry import get_provider

Tier = Literal["cheap", "mid", "reasoning"]

logger = logging.getLogger("orca.llm")


class LLMUnavailable(RuntimeError):
    """Every reason a tier cannot be reached, as one exception type: no
    provider configured, the demo switch off (P2.11), or the provider itself
    refusing (a 429 or a timeout — P2.13).

    It is deliberately a `RuntimeError` subclass: every call site already
    caught broad exceptions around `llm()` and degraded to its deterministic
    path, so this reaches all of them without touching one of them. `reason`
    is the short phrase that goes on the span (orca/engines.deterministic)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# P2.11 (`R-NEW-3`) — the per-request override, so a judge can watch the same
# question re-answered with every provider off without restarting the API.
# A ContextVar rather than a module global because two queries can be in
# flight at once and one of them must not silently disable the other's.
_llm_enabled_override: ContextVar[bool | None] = ContextVar("orca_llm_enabled", default=None)

_OFF = ("0", "false", "no", "off")


def llm_enabled() -> bool:
    """Whether any LLM tier may be reached at all. The per-request override
    wins over the environment; `ORCA_LLM_ENABLED=0` is the env form
    `docs/orca_final.md` §5.5/§28 already names."""
    override = _llm_enabled_override.get()
    if override is not None:
        return override
    return os.environ.get("ORCA_LLM_ENABLED", "1").strip().lower() not in _OFF


@contextmanager
def llm_switch(enabled: bool | None):
    """Scopes an override to one request. `None` means "don't override" — the
    ordinary path, so callers can pass the query parameter straight through
    without branching on it."""
    token = _llm_enabled_override.set(enabled)
    try:
        yield
    finally:
        _llm_enabled_override.reset(token)


def set_llm_override(enabled: bool | None) -> None:
    """The same override for code that cannot wrap a `with` block around the
    work — a LangGraph node may run on a worker thread whose context was
    copied before the request set anything, so `_query_stream` also sets it
    directly on the thread that runs the graph."""
    _llm_enabled_override.set(enabled)


# P2.13 — a provider that answers "not right now" is *unavailable*, not an
# error worth failing an answer over. Gemini's free tier returns 429 well
# inside a demo's question rate, and the wrong behaviour is a crashed span.
_UNAVAILABLE_MARKERS = (
    "429", "resource_exhausted", "resource exhausted", "rate limit", "ratelimit",
    "quota", "timeout", "timed out", "deadline exceeded", "503", "unavailable",
)


def _classify_provider_failure(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    for marker in _UNAVAILABLE_MARKERS:
        if marker in text:
            return f"provider unavailable ({marker})"
    return f"provider error ({type(exc).__name__})"


# P2.13 (3) — how many provider calls this query actually made, so §6.2's cost
# number is measured rather than asserted. Per-request, same reason as the
# switch above.
_call_count: ContextVar[list[int] | None] = ContextVar("orca_llm_calls", default=None)


def reset_llm_call_count() -> list[int]:
    """Starts a fresh counter for this request and returns the list it will
    be counted into — a one-element list rather than an int because a
    ContextVar set on a worker thread would not be visible to the caller,
    whereas a mutation of a shared list is."""
    counter = [0]
    _call_count.set(counter)
    return counter


def llm_call_count() -> int:
    counter = _call_count.get()
    return counter[0] if counter else 0


def _count_call() -> None:
    counter = _call_count.get()
    if counter:
        counter[0] += 1


@dataclass
class _TieredClient:
    provider_name: str
    model: str

    @property
    def engine(self) -> str:
        """What a span should say ran (orca/engines.llm_engine's shape)."""
        return f"{self.provider_name} · {self.model}"

    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        _count_call()
        try:
            return get_provider(self.provider_name).complete(messages, model=self.model, **kw)
        except LLMUnavailable:
            raise
        except Exception as exc:  # a 429 must degrade, not crash
            reason = _classify_provider_failure(exc)
            logger.warning("llm %s/%s: %s", self.provider_name, self.model, reason)
            raise LLMUnavailable(reason) from exc

    def stream(self, messages: list[dict[str, str]], **kw: Any) -> Iterator[str]:
        _count_call()
        return get_provider(self.provider_name).stream(messages, model=self.model, **kw)


def llm(tier: Tier) -> _TieredClient:
    if not llm_enabled():
        # P2.11: the one place that has to be switched off, because it is the
        # one place every agent gets a client from. Nothing downstream needs
        # to know — each caller already degrades on an exception here.
        raise LLMUnavailable("LLM providers disabled (ORCA_LLM_ENABLED=0)")
    provider = os.environ.get(f"ORCA_LLM_{tier.upper()}_PROVIDER")
    model = os.environ.get(f"ORCA_LLM_{tier.upper()}_MODEL")
    if not provider or not model:
        if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
            provider = "gemini"
            model = "gemini-3.5-flash-lite"
        elif os.environ.get("ANTHROPIC_API_KEY"):
            provider = "anthropic"
            model = "claude-3-5-haiku-latest"
        else:
            raise LLMUnavailable(
                f"ORCA_LLM_{tier.upper()}_PROVIDER / _MODEL not set, and no default API keys found in .env."
            )
    return _TieredClient(provider, model)


if __name__ == "__main__":
    # No network: the switch, the counter and the failure classifier only.
    import os as _os

    _os.environ.pop("ORCA_LLM_ENABLED", None)
    assert llm_enabled() is True
    with llm_switch(False):
        assert llm_enabled() is False
        try:
            llm("mid")
        except LLMUnavailable as exc:
            assert "disabled" in exc.reason
        else:  # pragma: no cover - the assert above is the check
            raise AssertionError("llm() must refuse while the switch is off")
    assert llm_enabled() is True, "the override must not leak out of its scope"

    _os.environ["ORCA_LLM_ENABLED"] = "0"
    assert llm_enabled() is False
    with llm_switch(True):
        assert llm_enabled() is True, "an explicit per-request ON overrides the env OFF"
    _os.environ.pop("ORCA_LLM_ENABLED")

    assert "429" in _classify_provider_failure(Exception("503 RESOURCE_EXHAUSTED: 429 quota"))
    assert "provider error" in _classify_provider_failure(ValueError("bad shape"))

    counter = reset_llm_call_count()
    assert llm_call_count() == 0
    _count_call()
    _count_call()
    assert llm_call_count() == 2 and counter[0] == 2
    print("tiers self-check ok")
