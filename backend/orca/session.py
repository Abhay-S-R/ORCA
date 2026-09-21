"""orca/session.py — SIH finale checklist P0 #1: multi-turn conversational
memory (currently doesn't exist — `GET /query` took no `session_id`, and
`_persist_audit_trace_log` hardcoded `session_id=None`).

A session-scoped Redis TTL is the honest scope here: the PS asks for
"supporting contextual, multi-turn conversations that enable users to
refine queries and explore related scenarios," not durable cross-device
history. Reuses orca/cache.py's Redis client and graceful-degradation
pattern — same shape as query_cache.py — rather than a second mechanism.

The session id is one Ask *chat*, not one browser tab: the frontend mints a
new one on "New chat" (frontend/app/ask/useAskThread.ts), so context never
leaks from one chat into the next.

Every write also lands in a small in-process mirror, read whenever Redis
can't answer. Without it a Redis outage (or a dev machine with no Redis at
all) silently turned every follow-up back into turn one — no error, no
disclosure — which is exactly the failure docs/ORCA_DLC_Extension_Pack.md
R-AUTH-3 describes. For a cache that's a latency hit; for conversation
memory it is the whole feature.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from orca.cache import redis_client

logger = logging.getLogger(__name__)

TTL_SECONDS = 1800  # a fishing trip's planning window, not a durable log
MAX_TURNS = 5
# Enough of the previous answer for "why?" / "and that zone?" to resolve
# against what ORCA actually said, without five full answers bloating every
# narrative prompt.
ANSWER_CHARS = 500

# Carrying a place forward from a prior turn is only honest when that turn
# itself named a real place — never from a turn that fell back to the
# regional default, or "what about tomorrow instead?" would silently inherit
# a place nobody actually asked about. "session_carried" counts: it is a real
# place carried once already, and leaving it out meant the place was lost as
# soon as the turn that originally named it rolled out of the window.
_REAL_PLACE_SOURCES = {"explicit", "port_fixture", "tide_station", "gazetteer", "session_carried"}

# ponytail: per-process mirror — with several uvicorn workers and Redis down,
# a follow-up routed to a different worker starts fresh. Redis is the shared
# store; this only has to keep one worker's conversations alive without it.
_LOCAL_MAX_SESSIONS = 2000
_local: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_local_lock = threading.Lock()


def _key(session_id: str) -> str:
    return f"orca:session:{session_id}"


def _local_get(session_id: str) -> list[dict[str, Any]]:
    with _local_lock:
        entry = _local.get(session_id)
        if entry is None:
            return []
        if entry[0] < time.monotonic():
            del _local[session_id]
            return []
        return list(entry[1])


def _local_set(session_id: str, turns: list[dict[str, Any]]) -> None:
    now = time.monotonic()
    with _local_lock:
        if session_id not in _local and len(_local) >= _LOCAL_MAX_SESSIONS:
            for sid in [s for s, (expires, _) in _local.items() if expires < now]:
                del _local[sid]
            if len(_local) >= _LOCAL_MAX_SESSIONS:
                del _local[min(_local, key=lambda s: _local[s][0])]  # soonest to expire
        _local[session_id] = (now + TTL_SECONDS, turns)


def get_turns(session_id: str | None) -> list[dict[str, Any]]:
    if not session_id:
        return []
    try:
        client = redis_client()
        raw = client.get(_key(session_id))
    except Exception as exc:  # noqa: BLE001 — a cache outage falls back to the in-process mirror, never a failed request
        logger.warning("session: Redis unavailable (%s), using in-process memory", exc)
        return _local_get(session_id)
    # A miss in Redis can still be a hit here: turns written while Redis was
    # down live only in the mirror.
    return json.loads(raw) if raw is not None else _local_get(session_id)


def append_turn(session_id: str | None, turn: dict[str, Any]) -> None:
    replace_turns(session_id, get_turns(session_id) + [turn])


def replace_turns(session_id: str | None, turns: list[dict[str, Any]]) -> None:
    """Set the whole window at once — how a chat reopened from history gets
    its context back after the TTL let it lapse (/api/session/{id}/context)."""
    if not session_id:
        return
    turns = turns[-MAX_TURNS:]
    _local_set(session_id, turns)
    try:
        client = redis_client()
        client.setex(_key(session_id), TTL_SECONDS, json.dumps(turns, default=str))
    except Exception as exc:  # noqa: BLE001 — the mirror already holds it; Redis is best-effort
        logger.warning("session: failed to store turn for %s in Redis (%s)", session_id, exc)


# P2.14 (orca_final §16.2, `R-PS-3`) — "forget that, start fresh".
#
# A reset is NOT a marine question and must never reach the graph: routing it
# would answer a question about the sea that nobody asked, on inherited
# context the user just said to drop. So it is matched here, deterministically,
# and short-circuited in the route.
#
# Deterministic for the same reason `distress.py` and `planning.is_out_of_scope`
# are: a reset decided by a model is a reset that sometimes does not happen,
# and the failure mode — answering with context the user explicitly discarded —
# is one the user cannot see and cannot correct.
#
# **Same honest gap as P1.5's Tamil place names and P1.10's injury phrases: no
# native speaker has reviewed the four Indic lists below.** They go to P3.7's
# reviewers together. A green test here means the wiring works, not that the
# phrases are right.
#
# Matched on the WHOLE normalized message, not as a substring. "Forget the
# tide, what about the wind?" contains "forget" and is a marine question; only
# a message that is *nothing but* a reset is one. This is the opposite choice
# from `_DISTRESS_PATTERNS` (substring, deliberately over-eager), and for the
# opposite reason: a missed reset costs one repeated question, a wrongly-fired
# one silently discards a conversation.
_RESET_PHRASES: dict[str, tuple[str, ...]] = {
    "en": (
        "forget that", "forget that start fresh", "forget it", "start fresh", "start over",
        "start again", "new chat", "new conversation", "clear this", "clear the chat",
        "reset", "reset the chat", "never mind", "nevermind", "forget everything",
        "forget what i said", "let's start over", "lets start over", "start from scratch",
    ),
    "ta": (
        "அதை மறந்துவிடு", "மறந்துவிடு", "மீண்டும் ஆரம்பி", "புதிதாக ஆரம்பி",
        "புதிய உரையாடல்", "அழி", "விடு",
    ),
    "hi": (
        "भूल जाओ", "इसे भूल जाओ", "फिर से शुरू करो", "नई शुरुआत", "नई बातचीत",
        "रीसेट", "सब मिटा दो",
    ),
    "ml": ("അത് മറക്കൂ", "മറക്കൂ", "വീണ്ടും തുടങ്ങാം", "പുതിയ സംഭാഷണം", "റീസെറ്റ്"),
    "te": ("అది మర్చిపో", "మర్చిపో", "మళ్ళీ మొదలుపెట్టు", "కొత్త సంభాషణ", "రీసెట్"),
}

# Punctuation a reset phrase is commonly typed with. Stripped from the ends
# AND normalised internally, so "forget that!", "reset." and — the one that
# caught this in live verification — "forget that, start fresh" all match.
# The comma is the realistic way a person types the phrase this point is
# literally named after, and edge-stripping alone missed it: the message was
# routed as a marine question and answered with the context it asked to drop.
_RESET_STRIP = " \t\r\n.!?,;:\"'।॥-–—"
_RESET_PUNCT = str.maketrans({c: " " for c in ".!?,;:\"'।॥-–—"})


def _normalize_reset(text: str) -> str:
    """Lowercased, punctuation flattened to spaces, runs of whitespace
    collapsed. Applied to both sides of the comparison so the phrase lists
    stay readable as the sentences people actually type."""
    return " ".join(text.translate(_RESET_PUNCT).lower().split())

RESET_CONFIRMATION = (
    "Done — I've forgotten this conversation. Your next question starts fresh, "
    "so name the place and the time again if they matter."
)


def is_reset_request(text: str | None) -> bool:
    """True when this message is a request to forget the conversation and
    nothing else. Checked against every core language's list, because the
    reset has to work in the language the user is already speaking."""
    if not text:
        return False
    normalized = _normalize_reset(text)
    if not normalized:
        return False
    for phrases in _RESET_PHRASES.values():
        for phrase in phrases:
            if normalized == _normalize_reset(phrase):
                return True
    return False


def clear(session_id: str | None) -> None:
    """Drops the whole context window — the Redis key and the in-process
    mirror both, or the mirror would immediately re-seed a "cleared" session
    on the next read. Best-effort on Redis, same as every other write here:
    the mirror is already gone, and a Redis outage must not make a reset fail
    silently in the other direction."""
    if not session_id:
        return
    with _local_lock:
        _local.pop(session_id, None)
    try:
        redis_client().delete(_key(session_id))
    except Exception as exc:  # noqa: BLE001 — the mirror is already cleared
        logger.warning("session: failed to clear %s in Redis (%s)", session_id, exc)


def turn_from_final(query: str, final: dict[str, Any]) -> dict[str, Any]:
    """One remembered turn, built from the `final_response` payload main.py
    streams — the one shape every path (fresh run, query-cache hit, a
    coalesced follower) produces, so all three remember identically."""
    return {
        "query": query,
        # English, since that is what Planning and Agent 9's prompt read — a
        # Tamil follow-up is still resolved against the English history.
        "english_query": final.get("normalized_english_query") or query,
        "user_location": final.get("user_location"),
        "verdict": (final.get("risk_assessment") or {}).get("go_no_go"),
        "intent_rows": final.get("matched_intent_rows") or [],
        # P2.9 — so "what about the day after?" after "and in a trawler?" is
        # still about the trawler. Stored as the DB-enum value the request
        # resolved to, which is the same vocabulary /query takes as a parameter.
        "vessel_class": final.get("vessel_class"),
        "answer": (final.get("final_english_response") or "")[:ANSWER_CHARS],
    }


def last_vessel_class(turns: list[dict[str, Any]]) -> str | None:
    """The most recent turn that actually named a vessel. None when no turn
    in the window did — never a default, for the same reason `last_place`
    returns None rather than the regional default: an inherited value has to
    be traceable to a turn the user can be shown."""
    for turn in reversed(turns):
        vessel = turn.get("vessel_class")
        if vessel:
            return vessel
    return None


def last_place(turns: list[dict[str, Any]]) -> tuple[float, float, str | None] | None:
    """The most recent turn's resolved position, for a follow-up that names
    no place of its own ("what about tomorrow instead?"). None if there is
    no history, or every turn so far used the regional default."""
    for turn in reversed(turns):
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

    with mock.patch(f"{__name__}.redis_client", return_value=_FakeClient()):
        assert get_turns("s1") == []
        assert last_place(get_turns("s1")) is None

        append_turn("s1", {
            "query": "is it safe near Thoothukudi",
            "user_location": {"lat": 8.77, "lon": 78.23, "place_name": "Thoothukudi", "place_source": "gazetteer"},
            "verdict": "GO",
        })
        assert last_place(get_turns("s1")) == (8.77, 78.23, "Thoothukudi")

        append_turn("s1", {
            "query": "what about the regional default",
            "user_location": {"lat": 1.0, "lon": 2.0, "place_source": "regional_default"},
            "verdict": "GO",
        })
        # Regional-default turn must not overwrite the last real place.
        assert last_place(get_turns("s1")) == (8.77, 78.23, "Thoothukudi")

        for i in range(MAX_TURNS + 2):
            append_turn("s1", {"query": f"q{i}", "user_location": {}, "verdict": "GO"})
        assert len(get_turns("s1")) == MAX_TURNS

    with mock.patch(f"{__name__}.redis_client", side_effect=ConnectionError("down")):
        append_turn("offline", {"query": "q", "user_location": {}, "verdict": "GO"})
        assert len(get_turns("offline")) == 1, "Redis down must not erase the conversation"

    print("session self-check ok")
