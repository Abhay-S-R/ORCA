"""orca/query_coalescing.py — request coalescing (Architecture §9.9, phase4
plan §2.2). Deduplicates CONCURRENT identical in-flight requests into one
producer, fanning results out to every waiter. In-process only — this only
needs to survive one concurrent burst on one worker, not a distributed lock,
so no new infrastructure is added. Orthogonal to orca/query_cache.py, which
handles SEQUENTIAL repeats across time instead of concurrent ones.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

_inflight: dict[str, "_Broadcast"] = {}


class _Broadcast:
    def __init__(self) -> None:
        self.buffer: list[Any] = []
        self.done = False
        self.event = asyncio.Event()


async def coalesce(key: str, produce: Callable[[], AsyncIterator[Any]]) -> AsyncIterator[Any]:
    """The first caller for `key` runs `produce()` for real (the leader);
    every concurrent caller for the same key (a follower) replays the
    leader's buffered items and then waits for new ones, never invoking
    `produce` itself. Once the leader finishes, `key` is free again — the
    next call becomes a new leader, which is exactly right for coalescing a
    hazard-window burst rather than caching across time (orca/query_cache.py
    already owns that)."""
    existing = _inflight.get(key)
    if existing is not None:
        idx = 0
        while True:
            while idx < len(existing.buffer):
                yield existing.buffer[idx]
                idx += 1
            if existing.done:
                return
            existing.event.clear()
            await existing.event.wait()
        return

    broadcast = _Broadcast()
    _inflight[key] = broadcast
    try:
        async for item in produce():
            broadcast.buffer.append(item)
            broadcast.event.set()
            yield item
    finally:
        broadcast.done = True
        broadcast.event.set()
        if _inflight.get(key) is broadcast:
            del _inflight[key]
