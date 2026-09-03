"""orca/cache.py — Redis caching with source-cadence-aware TTLs (plan §5 D1
Day 13, §9.1/§9.11). One decorator, `orca_cache`, wraps any agent tool fetch
function; the TTL is chosen from the source's own declared refresh cadence,
never a single global number — a PFZ advisory (~3x/week) must not expire on
the same clock as an hourly Open-Meteo pull.

Graceful degradation: a Redis outage falls through to the real fetch, silent
to the caller (logged, never raised) — caching is a latency optimization,
not a dependency the safety path can be blocked on.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from dotenv import load_dotenv

for _p in [Path(__file__).resolve().parents[2] / ".env", Path(__file__).resolve().parents[1] / ".env"]:
    if _p.exists():
        load_dotenv(_p)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Cadence-aware TTLs (plan §9.1/§9.11) — keyed by source name, not agent name,
# since one agent can call multiple sources with different real-world cadences.
TTL_SECONDS: dict[str, int] = {
    "open_meteo": 3600,  # hourly
    "pfz_advisory": 172800,  # ~2 days, INCOIS PFZ published 3x/week
    "ww3_forecast": 21600,  # 6h per model cycle
    "boundary_geojson": 604800,  # weekly — static reference data
}
DEFAULT_TTL_SECONDS = 1800  # 30 min, for any source not in the table above

_stats = {"hits": 0, "misses": 0}


def cache_stats() -> dict[str, int]:
    """Observability utility (plan §5 D1 Day 13) — hit/miss counts since
    process start. Not persisted; a restart resets it, which is fine for a
    latency metric nobody audits after the fact."""
    return dict(_stats)


def _redis_client() -> Any:
    import redis  # already-installed dependency (backend/requirements.txt)

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)


def _cache_key(source_name: str, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    # Args/kwargs are hashed, not embedded raw, so a lat/lon pair with many
    # decimal places doesn't blow the key past Redis's practical key-length
    # comfort zone; the hash still changes whenever the real inputs do.
    raw = json.dumps({"args": args, "kwargs": kwargs}, default=str, sort_keys=True)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"orca:cache:{source_name}:{fn.__name__}:{digest}"


def orca_cache(source_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: `@orca_cache("open_meteo")` on an agent tool fetch. Cache
    hit returns the stored JSON-decoded value; a miss calls the real `fn`,
    stores its result (must be JSON-serializable) with the cadence's TTL,
    and returns it. Any Redis error (down, timeout, unreachable) degrades
    silently to calling `fn` directly — never a cache failure blocking the
    pipeline."""
    ttl = TTL_SECONDS.get(source_name, DEFAULT_TTL_SECONDS)

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> T:
            key = _cache_key(source_name, fn, args, kwargs)
            try:
                client = _redis_client()
                cached = client.get(key)
            except Exception as exc:  # noqa: BLE001 — Redis outage falls through to the real fetch
                logger.warning("orca_cache: Redis unavailable (%s), calling %s directly", exc, fn.__name__)
                return fn(*args, **kwargs)

            if cached is not None:
                _stats["hits"] += 1
                return json.loads(cached)  # type: ignore[no-any-return]

            _stats["misses"] += 1
            result = fn(*args, **kwargs)
            try:
                client.setex(key, ttl, json.dumps(result, default=str))
            except Exception as exc:  # noqa: BLE001 — a write failure still returns the real result
                logger.warning("orca_cache: failed to store %s in Redis (%s)", key, exc)
            return result

        return wrapped

    return decorator
