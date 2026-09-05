"""Request coalescing (Architecture §9.9, phase4 plan §2.2) — two concurrent
callers for the same key must share one producer invocation and see
identical items; a caller for a different key, or a caller after the first
key's producer finished, must get its own independent run.
"""
from __future__ import annotations

import asyncio

import pytest

from orca.query_coalescing import coalesce


async def _slow_producer(calls: list[int], value: str):
    calls.append(1)
    await asyncio.sleep(0.05)
    yield f"{value}-1"
    await asyncio.sleep(0.05)
    yield f"{value}-2"


@pytest.mark.anyio
async def test_two_concurrent_identical_requests_share_one_producer_run():
    calls: list[int] = []

    async def collect():
        return [item async for item in coalesce("k1", lambda: _slow_producer(calls, "a"))]

    results = await asyncio.gather(collect(), collect())

    assert len(calls) == 1  # the producer only actually ran once
    assert results[0] == ["a-1", "a-2"]
    assert results[1] == ["a-1", "a-2"]  # the follower saw the same items


@pytest.mark.anyio
async def test_different_keys_never_share_a_producer():
    calls: list[int] = []

    async def collect(key: str, value: str):
        return [item async for item in coalesce(key, lambda: _slow_producer(calls, value))]

    results = await asyncio.gather(collect("k1", "a"), collect("k2", "b"))

    assert len(calls) == 2
    assert results[0] == ["a-1", "a-2"]
    assert results[1] == ["b-1", "b-2"]


@pytest.mark.anyio
async def test_a_later_request_after_the_leader_finished_runs_its_own_producer():
    calls: list[int] = []

    first = [item async for item in coalesce("k1", lambda: _slow_producer(calls, "a"))]
    second = [item async for item in coalesce("k1", lambda: _slow_producer(calls, "a"))]

    assert len(calls) == 2  # no stale leader left behind to (incorrectly) coalesce onto
    assert first == second == ["a-1", "a-2"]
