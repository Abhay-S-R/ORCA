"""orca/query_cache.py — near-duplicate whole-response caching (Architecture
§9.1, phase4 plan §2.3). Scoped to resolved parameters rather than semantic
embedding similarity: covers the architecture's own headline case ("many
fishermen from the same home port ask near-identical queries") without a new
embedding-index dependency — see phase4 plan §2.3 for the gap this leaves
(a paraphrase from the same location is not caught). Reuses orca/cache.py's
Redis client and graceful-degradation pattern rather than a second mechanism.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from orca.cache import redis_client

logger = logging.getLogger(__name__)

# Architecture's own worked example of the tightest real safety-relevant
# cadence in the system (lightning nowcast, ~30 min) — used as a fixed
# ceiling rather than computed per-response from "which sources this
# response actually used" (a real refinement, deliberately not built this
# pass — see phase4 plan §2.3). A cached GO can therefore never outlive the
# data that justified it by more than the architecture's own worst case.
TTL_SECONDS = 1800


def resolved_key(
    query: str, lat: float, lon: float, vessel_class: str | None, persona: str | None, depth: str | None
) -> str:
    """The resolved-parameter cache/coalescing key. §9.1's own safety rule:
    "must include the resolved target_bbox + target_time_window, never just
    raw text similarity — two different villages asking 'is it safe' must
    never share a cache entry." Location rounded to 3 decimals (~111 m) —
    tight enough that two villages a few km apart never collide, loose
    enough that the same registered home port's repeat queries collapse."""
    raw = json.dumps(
        {
            "q": (query or "").strip().lower(),
            "lat": round(lat, 3),
            "lon": round(lon, 3),
            "vessel_class": vessel_class or "",
            "persona": persona or "",
            "depth": depth or "",
        },
        sort_keys=True,
    )
    return f"orca:query_cache:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def get(key: str) -> dict[str, Any] | None:
    try:
        client = redis_client()
        cached = client.get(key)
    except Exception as exc:  # noqa: BLE001 — a cache outage is a latency hit, never a failed request
        logger.warning("query_cache: Redis unavailable (%s)", exc)
        return None
    return json.loads(cached) if cached is not None else None  # type: ignore[no-any-return]


def store(key: str, response: dict[str, Any]) -> None:
    try:
        client = redis_client()
        client.setex(key, TTL_SECONDS, json.dumps(response, default=str))
    except Exception as exc:  # noqa: BLE001 — a write failure just means the next identical query misses too
        logger.warning("query_cache: failed to store %s (%s)", key, exc)
