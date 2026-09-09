"""orca/session.py — SIH finale checklist P0 #1: multi-turn conversational
memory (currently doesn't exist — `GET /query` took no `session_id`, and
`_persist_audit_trace_log` hardcoded `session_id=None`).

A session-scoped Redis TTL is the honest scope here: the PS asks for
"supporting contextual, multi-turn conversations that enable users to
refine queries and explore related scenarios," not durable cross-device
history. Reuses orca/cache.py's Redis client and graceful-degradation
pattern — same shape as query_cache.py — rather than a second mechanism.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from orca.cache import redis_client

logger = logging.getLogger(__name__)

TTL_SECONDS = 1800  # a fishing trip's planning window, not a durable log
MAX_TURNS = 5

# Carrying a place forward from a prior turn is only honest when that turn
# itself named a real place — never from a turn that fell back to the
# regional default, or "what about tomorrow instead?" would silently inherit
# a place nobody actually asked about.
_REAL_PLACE_SOURCES = {"explicit", "port_fixture", "tide_station", "pilot_gazetteer"}


def _key(session_id: str) -> str:
    return f"orca:session:{session_id}"


def get_turns(session_id: str | None) -> list[dict[str, Any]]:
    if not session_id:
        return []
    try:
        client = redis_client()
        raw = client.get(_key(session_id))
    except Exception as exc:  # noqa: BLE001 — a cache outage just means no memory this turn, never a failed request
        logger.warning("session: Redis unavailable (%s)", exc)
        return []
    return json.loads(raw) if raw is not None else []


def append_turn(session_id: str | None, turn: dict[str, Any]) -> None:
    if not session_id:
        return
    try:
        client = redis_client()
        turns = (get_turns(session_id) + [turn])[-MAX_TURNS:]
        client.setex(_key(session_id), TTL_SECONDS, json.dumps(turns, default=str))
    except Exception as exc:  # noqa: BLE001 — a write failure just means this turn isn't remembered
        logger.warning("session: failed to store turn for %s (%s)", session_id, exc)


def last_place(session_id: str | None) -> tuple[float, float, str | None] | None:
    """The most recent turn's resolved position, for a follow-up that names
    no place of its own ("what about tomorrow instead?"). None if there is
    no session, no history, or every turn so far used the regional default."""
    for turn in reversed(get_turns(session_id)):
        loc = turn.get("user_location") or {}
        if loc.get("place_source") in _REAL_PLACE_SOURCES and loc.get("lat") is not None:
            return loc["lat"], loc["lon"], loc.get("place_name")
    return None


if __name__ == "__main__":
    import unittest.mock as mock

    store: dict[str, str] = {}

    class _FakeClient:
        def get(self, key: str) -> str | None:
            return store.get(key)

        def setex(self, key: str, ttl: int, value: str) -> None:
            store[key] = value

    with mock.patch("orca.session.redis_client", return_value=_FakeClient()):
        assert get_turns("s1") == []
        assert last_place("s1") is None

        append_turn("s1", {
            "query": "is it safe near Thoothukudi",
            "user_location": {"lat": 8.77, "lon": 78.23, "place_name": "Thoothukudi", "place_source": "pilot_gazetteer"},
            "verdict": "GO",
        })
        assert last_place("s1") == (8.77, 78.23, "Thoothukudi")

        append_turn("s1", {
            "query": "what about the regional default",
            "user_location": {"lat": 1.0, "lon": 2.0, "place_source": "regional_default"},
            "verdict": "GO",
        })
        # Regional-default turn must not overwrite the last real place.
        assert last_place("s1") == (8.77, 78.23, "Thoothukudi")

        for i in range(MAX_TURNS + 2):
            append_turn("s1", {"query": f"q{i}", "user_location": {}, "verdict": "GO"})
        assert len(get_turns("s1")) == MAX_TURNS

    print("session self-check ok")
