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
from orca.engines import DETERMINISTIC

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
    except Exception as exc:
        logger.warning("query_cache: Redis unavailable (%s)", exc)
        return None
    return json.loads(cached) if cached is not None else None  # type: ignore[no-any-return]


def store(key: str, response: dict[str, Any]) -> None:
    # Chatbot plan C0.2 — an answer written without a model (every provider
    # down, "Deterministic — …") is an outage artefact. Cached, it would be
    # replayed for 30 minutes after the providers came back.
    if str(response.get("response_engine") or "").startswith(DETERMINISTIC):
        return
    try:
        client = redis_client()
        client.setex(key, TTL_SECONDS, json.dumps(response, default=str))
    except Exception as exc:
        logger.warning("query_cache: failed to store %s (%s)", key, exc)


# P6.11 (orca_final §4.6) — "when every weather source fails, return the
# last computed verdict for that place, with its age, forced to LOW-DATA,
# rather than a verdict built on nothing." A separate, long-lived key from
# `resolved_key`'s 30-minute near-duplicate cache above: that TTL is fixed to
# the tightest safety-relevant cadence (lightning, ~30 min) on purpose, so it
# is gone long before it would be useful as a last resort. 7 days is a
# judgement call, not a spec number: long enough that a multi-hour outage
# (the case this exists for) still has something to fall back to, short
# enough that "last known good" cannot silently mean "from last month."
LAST_KNOWN_TTL_SECONDS = 7 * 24 * 3600


def last_known_key(lat: float, lon: float, vessel_class: str | None) -> str:
    """Location-only key (no query text, no persona/depth) — unlike
    `resolved_key`, this is not about deduplicating one phrasing of one
    question; it is "the last real verdict ORCA computed anywhere near here,"
    which two different questions at the same spot should both be able to
    fall back to. Same 3-decimal (~111 m) rounding as `resolved_key`."""
    raw = json.dumps({"lat": round(lat, 3), "lon": round(lon, 3), "vessel_class": vessel_class or ""}, sort_keys=True)
    return f"orca:last_known_verdict:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def store_last_known_verdict(lat: float, lon: float, vessel_class: str | None, risk_assessment: dict[str, Any]) -> None:
    """Called after every query whose weather data was real (never after an
    outage response itself — that would let a degraded answer become the
    fallback for the next one). `computed_at` is stamped here, once, rather
    than derived from Redis TTL math at read time."""
    import datetime as _dt

    try:
        client = redis_client()
        payload = {"risk_assessment": risk_assessment, "computed_at": _dt.datetime.now(_dt.UTC).isoformat()}
        client.setex(last_known_key(lat, lon, vessel_class), LAST_KNOWN_TTL_SECONDS, json.dumps(payload, default=str))
    except Exception as exc:
        logger.warning("query_cache: failed to store last-known verdict (%s)", exc)


def get_last_known_verdict(lat: float, lon: float, vessel_class: str | None) -> dict[str, Any] | None:
    try:
        client = redis_client()
        cached = client.get(last_known_key(lat, lon, vessel_class))
    except Exception as exc:
        logger.warning("query_cache: last-known verdict lookup failed (%s)", exc)
        return None
    return json.loads(cached) if cached is not None else None  # type: ignore[no-any-return]
