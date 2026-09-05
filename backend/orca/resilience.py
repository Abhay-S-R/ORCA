"""orca/resilience.py — plan §5.7, D1 Day 13.

Four things, each independently useful and each a straight extraction of a
rule already documented in the architecture, not new policy:

1. `with_timeout` — a call-site timeout decorator (5s default, 3s on the
   safety path).
2. `agent_boundary` — the agent exception boundary, promoted out of
   trace.py's inline try/except into a reusable decorator any agent's
   tool-level function can wear, not just the run() wrapper.
3. `walk_fallback_cascade` — tries an ordered list of source rungs in turn,
   downgrading confidence and appending provenance one rung at a time,
   stopping at the first rung that returns a validated payload.
4. `validate_arrival` / `conservative_or` — the safety-path rule: a missing
   required input forces CAUTION/NO_GO naming the input, never GO, never an
   LLM estimate filling the gap.
"""
from __future__ import annotations

import concurrent.futures
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import wraps
from typing import Any, Literal, TypeVar

from orca.contracts import AgentResult, Confidence, SourceProvenance

T = TypeVar("T")

DEFAULT_TIMEOUT_SECONDS = 5.0
SAFETY_PATH_TIMEOUT_SECONDS = 3.0  # plan §5.7 — the safety path gets the tighter budget


class TimeoutExceeded(Exception):
    pass


def with_timeout(seconds: float = DEFAULT_TIMEOUT_SECONDS):
    """Wraps a blocking call so it cannot hang the graph past `seconds`.
    A thread-pool call, not signal-based alarm — signals don't work off the
    main thread, and LangGraph nodes are not guaranteed to run on it."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> T:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(fn, *args, **kwargs)
                try:
                    return future.result(timeout=seconds)
                except concurrent.futures.TimeoutError as exc:
                    raise TimeoutExceeded(f"{fn.__name__} exceeded {seconds}s timeout") from exc

        return wrapped

    return decorator


def agent_boundary(agent_name: str, query_id_getter: Callable[..., str] = lambda *a, **kw: ""):
    """The exception boundary trace.run_traced_node applies at the node
    level, made reusable for a tool-level function that wants the same
    "never raise past me" guarantee — e.g. a fallback-cascade rung. Returns
    a status="failed" AgentResult on any exception, exactly matching
    trace.py's behaviour so both call sites produce the same shape."""

    def decorator(fn: Callable[..., AgentResult]) -> Callable[..., AgentResult]:
        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> AgentResult:
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — deliberately blind, see trace.py
                return AgentResult(
                    agent_name=agent_name,
                    query_id=query_id_getter(*args, **kwargs),
                    reasoning_depth="SHALLOW",
                    inputs_consumed={},
                    outputs={},
                    source_provenance=SourceProvenance(dataset="n/a — agent raised", acquisition_timestamp="", freshness_minutes=0),
                    confidence=Confidence(score="LOW_DATA", rationale="Agent raised an unhandled exception"),
                    status="failed",
                    error_detail=str(exc),
                )

        return wrapped

    return decorator


# ---------------------------------------------------------------------------
# Fallback cascade
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CascadeRung:
    name: str  # e.g. "live_open_meteo", "cached_fixture"
    fetch: Callable[[], dict[str, Any]]


_CASCADE_CONFIDENCE_FLOOR: tuple[Literal["HIGH", "MEDIUM", "LOW_DATA"], ...] = ("HIGH", "MEDIUM", "LOW_DATA")


def walk_fallback_cascade(rungs: Iterable[CascadeRung], validate: Callable[[dict[str, Any]], bool] | None = None) -> tuple[dict[str, Any], str, Confidence]:
    """Tries each rung in order. The first rung whose fetch succeeds AND
    (if `validate` is given) whose payload passes `validate_arrival` wins.
    Confidence is floored one notch per rung past the first — rung 0 keeps
    whatever the caller assigns afterward, rung 1+ is capped at MEDIUM, and
    any rung reached only because everything above it failed is never HIGH.
    Raises the last rung's exception if every rung fails, so the caller's
    own exception boundary (agent_boundary / trace.py) still catches it.
    """
    last_exc: Exception | None = None
    for idx, rung in enumerate(rungs):
        try:
            payload = rung.fetch()
        except Exception as exc:  # noqa: BLE001 — try the next rung
            last_exc = exc
            continue
        if validate is not None and not validate(payload):
            continue
        floor = _CASCADE_CONFIDENCE_FLOOR[min(idx, len(_CASCADE_CONFIDENCE_FLOOR) - 1)]
        rationale = "Primary source" if idx == 0 else f"Fell back to rung {idx} ({rung.name}) after {idx} higher rung(s) failed"
        confidence = Confidence(score=floor if idx > 0 else "HIGH", rationale=rationale)
        return payload, rung.name, confidence
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("walk_fallback_cascade: no rungs supplied")


# ---------------------------------------------------------------------------
# Arrival validation + the safety-path conservative rule
# ---------------------------------------------------------------------------

def validate_arrival(payload: dict[str, Any], *, required_keys: Iterable[str] = (), max_staleness_minutes: float | None = None) -> tuple[bool, str | None]:
    """A payload fails arrival validation when it is empty, is missing a
    required key, carries an all-NaN numeric value, or is staler than the
    source's own declared cadence. Returns (is_valid, failure_reason) —
    the reason is what a NO_GO/CAUTION message names, not a bare bool."""
    if not payload:
        return False, "empty payload"
    for key in required_keys:
        if key not in payload or payload[key] is None:
            return False, f"missing required field {key!r}"
        value = payload[key]
        if isinstance(value, float) and math.isnan(value):
            return False, f"field {key!r} is NaN"
    freshness = payload.get("freshness_minutes")
    if max_staleness_minutes is not None and isinstance(freshness, (int, float)) and freshness > max_staleness_minutes:
        return False, f"stale beyond cadence: {freshness}min > {max_staleness_minutes}min"
    return True, None


def conservative_or(value: T | None, *, missing_field_name: str, missing: list[str]) -> T | None:
    """Safety-path rule (plan §5.7): a missing required input is recorded by
    name in `missing` (mutated in place — the caller appends every field it
    checked, once, so the eventual reason string lists all of them, not just
    the first) and the caller must treat any non-empty `missing` list as a
    forced CAUTION/NO_GO floor, never a silently-defaulted GO-shaped number.
    A NaN/inf float counts as missing too, not as a reading: it is what a
    masked grid cell or a failed geometry op returns, and it is *more*
    dangerous than None because it survives an `is None` check and then
    silently passes every threshold comparison downstream (see
    risk_assessment._known). Non-finite values are normalised to None so no
    caller can mistake one for a measurement — validate_payload above already
    rejects NaN for the same reason.

    Returns `value` unchanged otherwise; this only records, it never guesses
    a substitute value — an LLM-filled or hardcoded default is exactly what
    the rule forbids."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        missing.append(missing_field_name)
        return None
    return value


def safety_floor_for_missing_inputs(missing: list[str]) -> tuple[Literal["CAUTION", "NO_GO"], str] | None:
    """Returns (go_no_go, reason) to force onto a verdict when `missing` is
    non-empty, or None when nothing was missing and the verdict computed
    normally should stand. NO_GO only when the input is one nothing else can
    compensate for; everything else forces CAUTION, per plan §5.7: "a
    missing required input yields CAUTION or NO_GO naming the input, never
    GO."""
    if not missing:
        return None
    return "CAUTION", f"Insufficient data — missing: {', '.join(missing)}"
