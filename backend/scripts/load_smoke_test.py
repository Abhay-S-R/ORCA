"""Load smoke test — the priority lane (Architecture §9.10, phase4 plan §8).

Fires a burst of concurrent SAFETY_CHECK-shaped requests alongside a burst of
standard-lane requests against a locally running instance, and reports
p50/p95/p99 latency per lane plus error counts. This is a smoke test, not a
benchmark: run it once against a real running server to confirm the priority
lane holds up under a burst; it is not wired into CI and not meant to be
re-run repeatedly chasing a number (phase4 plan §8's own instruction).

Usage:
    uvicorn orca.api.main:app --port 8000   # in one terminal
    python scripts/load_smoke_test.py --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx

PRIORITY_QUERY = {"q": "is it safe to go to sea tomorrow morning", "lat": 8.8, "lon": 78.14}
STANDARD_QUERY = {"q": "nearest fishing zone", "lat": 8.8, "lon": 78.14, "depth": "DEEP"}


async def _one_request(client: httpx.AsyncClient, base_url: str, params: dict) -> tuple[float, bool]:
    start = time.perf_counter()
    ok = True
    try:
        async with client.stream("GET", f"{base_url}/query", params=params, timeout=30.0) as resp:
            async for _ in resp.aiter_lines():
                pass
            ok = resp.status_code == 200
    except Exception:  # noqa: BLE001 — a smoke test counts failures, it doesn't crash on one
        ok = False
    return time.perf_counter() - start, ok


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return float("nan")
    idx = min(len(sorted_values) - 1, int(len(sorted_values) * pct))
    return sorted_values[idx]


def _report(label: str, latencies: list[float], errors: int) -> None:
    latencies = sorted(latencies)
    print(f"\n{label} — {len(latencies)} requests, {errors} errors")
    if latencies:
        print(f"  p50={_percentile(latencies, 0.50):.2f}s  p95={_percentile(latencies, 0.95):.2f}s  p99={_percentile(latencies, 0.99):.2f}s")


async def _burst(base_url: str, params: dict, count: int) -> tuple[list[float], int]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_one_request(client, base_url, params) for _ in range(count)])
    latencies = [t for t, ok in results if ok]
    errors = sum(1 for _t, ok in results if not ok)
    return latencies, errors


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--priority-count", type=int, default=20)
    parser.add_argument("--standard-count", type=int, default=10)
    args = parser.parse_args()

    priority_task = _burst(args.base_url, PRIORITY_QUERY, args.priority_count)
    standard_task = _burst(args.base_url, STANDARD_QUERY, args.standard_count)
    (priority_lat, priority_err), (standard_lat, standard_err) = await asyncio.gather(priority_task, standard_task)

    _report("Priority lane (SAFETY_CHECK, SHALLOW)", priority_lat, priority_err)
    _report("Standard lane (everything else)", standard_lat, standard_err)


if __name__ == "__main__":
    asyncio.run(main())
