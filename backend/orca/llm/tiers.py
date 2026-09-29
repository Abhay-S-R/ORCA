"""Tier -> (provider, model) resolution, from env only, never hardcoded (plan §3.1/§3.3).

Tiers are fixed per agent (plan §3.2): cheap -> Agents 1, 2, 3 · mid -> Agent 9
· reasoning -> Agents 5 (DEEP), 10. Providers are configuration — swapping one
is an env change (`ORCA_LLM_<TIER>_PROVIDER` / `_MODEL` in .env), not a code
change.
"""
from __future__ import annotations

import logging
import os
import time
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

from orca import local_models
from orca.llm.registry import get_provider, groq_keys

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
    be counted into — a list rather than an int because a ContextVar set on a
    worker thread would not be visible to the caller, whereas a mutation of a
    shared list is. `[answered, failed]`: found 2026-09-29, one question showed
    "12 LLM calls" while making four — each attempt on an overloaded Gemini
    (try, retry, then Groq) was counted as a call. Failed attempts still cost
    quota, so they are counted, just not as calls."""
    counter = [0, 0]
    _call_count.set(counter)
    return counter


def llm_call_count() -> int:
    counter = _call_count.get()
    return counter[0] if counter else 0


def llm_failed_call_count() -> int:
    counter = _call_count.get()
    return counter[1] if counter else 0


def _count_call(*, failed: bool = False) -> None:
    counter = _call_count.get()
    if counter:
        counter[1 if failed else 0] += 1


@dataclass
class _TieredClient:
    provider_name: str
    model: str

    @property
    def engine(self) -> str:
        """What a span should say ran (orca/engines.llm_engine's shape)."""
        return f"{self.provider_name} · {self.model}"

    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        try:
            text = get_provider(self.provider_name).complete(messages, model=self.model, **kw)
        except LLMUnavailable:
            _count_call(failed=True)
            raise
        except Exception as exc:  # a 429 must degrade, not crash
            _count_call(failed=True)
            reason = _classify_provider_failure(exc)
            logger.warning("llm %s/%s: %s", self.provider_name, self.model, reason)
            raise LLMUnavailable(reason) from exc
        _count_call()
        return text

    def stream(self, messages: list[dict[str, str]], **kw: Any) -> Iterator[str]:
        _count_call()
        return get_provider(self.provider_name).stream(messages, model=self.model, **kw)


# --- Chatbot plan C0.2 — a chain of providers per tier ----------------------
#
# One provider on one free-tier key was the whole story before this: when
# gemini-3.5-flash-lite stalled (it returned 504s and 503s all afternoon on
# 2026-09-24), Reporting, Critic and Planning failed together, and /ask showed
# an answer with no written response. A tier is now an ordered list of rungs
# walked until one writes something. The local rung is what makes "every
# prompt gets a written answer" true with the network gone.

# Default second rung: a different Gemini model has its own quota and, as
# measured on 2026-09-24, its own outages — flash-lite-latest answered in
# 5.5 s while 3.5-flash-lite and 3.1-flash-lite were returning 504/503.
_SECOND_GEMINI = "gemini-flash-lite-latest"
_LOCAL_MODEL = "gemma4:e4b"
# Groq joins every tier's default chain, right after the primary, whenever a
# GROQ_API_KEY is in .env: a different company's infrastructure, so it is up
# when Gemini is not. ORCA_LLM_GROQ_MODEL picks the model.
# llama-3.3-70b-versatile (the original default) no longer exists on Groq's
# model list as of 2026-09-26 (a live call 404'd) — found once real keys were
# available to check with. Measured against the real Reporting prompt that
# day: gpt-oss-120b 1.7s, gpt-oss-20b 1.4s, qwen3.8-27b 0.3s, all keeping the
# verdict header intact. gpt-oss-120b is the pick: the largest of the three,
# and still far faster than every Gemini model measured the same day (4.1 s
# best case).
_GROQ_MODEL = "openai/gpt-oss-120b"
# A local model is ALWAYS the last rung and never assumed present: not every
# machine on the team has Ollama, or a GPU. When the startup warm-up finds no
# local model, it is dropped from every chain (`_LOCAL_MISSING`) — so on such
# a machine it reserves no time from the hosted rungs and costs nothing.
_LOCAL_MISSING: set[str] = set()
# Only the writers of the answer (Agent 9 and the guard replies) default to
# the local model. Planning has deterministic tiers 1-2 in front of its model
# and the Critic's review is optional; a local rung there would only add
# latency to a question that already has an answer.
_LOCAL_TIERS = ("mid",)

# Whole-chain time budget per tier, seconds. Reporting's is the largest: it is
# the one call whose failure the user sees.
_BUDGET_S = {"cheap": 15.0, "mid": 45.0, "reasoning": 20.0}
# Most one hosted attempt may take, and what a hosted rung must leave for a
# local rung after it. A warm local answer takes ~5-15 s on the dev GPU.
_HOSTED_CAP_S = 12.0
_LOCAL_RESERVE_S = 20.0
_MIN_ATTEMPT_S = 2.0
_RETRY_BACKOFF_S = 1.0

# A hosted rung that just failed is skipped by every call for this long, then
# tried again. Found 2026-09-28: with gemini-3.5-flash-lite returning 503s,
# every call on every question re-paid 10-20 s of failure before Groq answered
# in ~1 s, because nothing remembered the rung was down. Now the first caller
# pays once and the rest go straight to the next rung. Process-wide on purpose
# (an outage is not per-request); a success clears it early.
_COOLDOWN_S = 120.0
_cooling_until: dict[tuple[str, str], float] = {}

# A failure worth one immediate retry on the same rung: the provider answered
# fast and said "not right now". A timeout is not in here — waiting the same
# 12 s again on the model that just stalled is budget the next rung needs.
# Retried only when no healthy rung comes after it: a different model is a
# better second try than the same overloaded one.
_RETRYABLE = ("429", "resource_exhausted", "rate limit", "500", "502", "503", "unavailable", "overloaded")
_TIMEOUTS = ("timeout", "timed out", "deadline exceeded", "504")


def _retryable(exc: Exception) -> bool:
    text = f"{exc} {exc.__cause__ or ''}".lower()
    return any(m in text for m in _RETRYABLE) and not any(m in text for m in _TIMEOUTS)


def _primary(tier: Tier) -> tuple[str, str]:
    provider = os.environ.get(f"ORCA_LLM_{tier.upper()}_PROVIDER")
    model = os.environ.get(f"ORCA_LLM_{tier.upper()}_MODEL")
    if provider and model:
        return provider, model
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "gemini", "gemini-3.5-flash-lite"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", "claude-3-5-haiku-latest"
    if groq_keys():
        return "groq", os.environ.get("ORCA_LLM_GROQ_MODEL") or _GROQ_MODEL
    return "", ""


def chain_for(tier: Tier) -> list[tuple[str, str]]:
    """The rungs for a tier, in order. `ORCA_LLM_<TIER>_CHAIN` overrides the
    default as `provider:model,provider:model` — a model id may itself hold a
    colon (`ollama:gemma4:e4b`), so each entry splits on its first colon."""
    raw = os.environ.get(f"ORCA_LLM_{tier.upper()}_CHAIN", "").strip()
    if raw:
        rungs = []
        for entry in raw.split(","):
            provider, _, model = entry.strip().partition(":")
            local_off = model in _LOCAL_MISSING or not local_models.enabled()
            if provider and model and not (provider == "ollama" and local_off):
                rungs.append((provider, model))
        return rungs
    rungs = []
    provider, model = _primary(tier)
    if provider:
        rungs.append((provider, model))
    if groq_keys() and provider != "groq":
        rungs.append(("groq", os.environ.get("ORCA_LLM_GROQ_MODEL") or _GROQ_MODEL))
    if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")) and model != _SECOND_GEMINI:
        rungs.append(("gemini", _SECOND_GEMINI))
    local = os.environ.get("ORCA_LLM_LOCAL_MODEL") or _LOCAL_MODEL
    # ORCA_LOCAL_MODELS=0 (orca/local_models.py) drops the Ollama rung like any other local model.
    if tier in _LOCAL_TIERS and local not in _LOCAL_MISSING and local_models.enabled():
        rungs.append(("ollama", local))
    return rungs


@dataclass
class _ChainClient:
    """What `llm(tier)` returns: the same `complete()` every caller already
    uses, walked down the tier's rungs inside one time budget. `engine` names
    the rung that actually wrote the text — `(fallback)` when it was not the
    first — so a span never credits a model that did not answer (P2.1)."""

    tier: Tier
    rungs: list[tuple[str, str]]
    engine: str = ""

    def __post_init__(self) -> None:
        # Until a call succeeds, the label is the rung it will try first.
        if not self.engine and self.rungs:
            self.engine = f"{self.rungs[0][0]} · {self.rungs[0][1]}"

    def complete(self, messages: list[dict[str, str]], **kw: Any) -> str:
        budget = float(os.environ.get(f"ORCA_LLM_{self.tier.upper()}_BUDGET_S") or _BUDGET_S[self.tier])
        deadline = time.monotonic() + budget
        failures: list[str] = []
        # Rungs in their cooldown go to the back, not out: if everything else
        # fails too, one of them may have recovered, and an answer beats none.
        now = time.monotonic()
        order = sorted(self.rungs, key=lambda r: _cooling_until.get(r, 0.0) > now)
        for i, (provider, model) in enumerate(order):
            local = provider == "ollama"
            reserve = sum(_LOCAL_RESERVE_S for p, _ in order[i + 1:] if p == "ollama")
            for attempt in range(1 if local else 2):
                left = deadline - time.monotonic() - reserve
                timeout = left if local else min(_HOSTED_CAP_S, left)
                if timeout < _MIN_ATTEMPT_S:
                    failures.append(f"{provider}/{model}: skipped (budget spent)")
                    break
                try:
                    text = _TieredClient(provider, model).complete(messages, timeout_s=timeout, **kw)
                except LLMUnavailable as exc:
                    failures.append(f"{provider}/{model}: {exc.reason}")
                    if local:
                        break
                    _cooling_until[(provider, model)] = time.monotonic() + _COOLDOWN_S
                    healthy_after = any(_cooling_until.get(r, 0.0) <= time.monotonic() for r in order[i + 1:])
                    if attempt == 0 and _retryable(exc) and not healthy_after:
                        time.sleep(_RETRY_BACKOFF_S)
                        continue
                    break
                if not text.strip():
                    # A safety block or an empty candidate is not an answer.
                    failures.append(f"{provider}/{model}: empty reply")
                    break
                _cooling_until.pop((provider, model), None)
                fallback = (provider, model) != self.rungs[0]
                self.engine = f"{provider} · {model}" + (" (fallback)" if fallback else "")
                return text
        raise LLMUnavailable("; ".join(failures) or f"no provider configured for tier {self.tier!r}")

    def stream(self, messages: list[dict[str, str]], **kw: Any) -> Iterator[str]:
        if not self.rungs:
            raise LLMUnavailable(f"no provider configured for tier {self.tier!r}")
        provider, model = self.rungs[0]
        self.engine = f"{provider} · {model}"
        return _TieredClient(provider, model).stream(messages, **kw)


def llm(tier: Tier) -> _ChainClient:
    if not llm_enabled():
        # P2.11: the one place that has to be switched off, because it is the
        # one place every agent gets a client from. Nothing downstream needs
        # to know — each caller already degrades on an exception here.
        raise LLMUnavailable("LLM providers disabled (ORCA_LLM_ENABLED=0)")
    rungs = chain_for(tier)
    if not rungs:
        raise LLMUnavailable(
            f"ORCA_LLM_{tier.upper()}_PROVIDER / _MODEL not set, and no default API keys found in .env."
        )
    return _ChainClient(tier, rungs)


def warm_local_models() -> None:
    """Load every local rung's weights now rather than on the first fallback
    (a cold load measured 137 s). Best-effort: a machine without Ollama simply
    has no local rung, and its chains end one rung earlier in failure."""
    seen: set[str] = set()
    for tier in ("cheap", "mid", "reasoning"):
        for provider, model in chain_for(tier):  # type: ignore[arg-type]
            if provider == "ollama" and model not in seen:
                seen.add(model)
                try:
                    get_provider("ollama").warm(model)  # type: ignore[attr-defined]
                    _LOCAL_MISSING.discard(model)
                except Exception as exc:  # optional rung: no Ollama means no local rung
                    _LOCAL_MISSING.add(model)
                    logger.info("no local model %s on this machine (%s); chains end at the hosted rungs", model, exc)


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
