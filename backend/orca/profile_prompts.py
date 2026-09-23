"""P3.4 (`R-UX-6`) — "ask at the moment it first matters," the conversational
half of the setup wizard. The mandatory screens (language, role — P3.3/P3.4)
cover what every account needs before its first answer; everything else the
DLC names (home port, vessel, crew, departure hour, range offshore,
phone/SMS consent, reading comfort, units) is asked only when a specific
question would actually use it, and never more than once.

The field rule from the plan is not optional: *name the answer that changes
if we know this*; if none, do not ask. Both prompts below name theirs —
`vessel_class` changes the safety thresholds `risk_assessment` applies
(`_VESSEL_DELTAS`); `home_port` changes the fallback position every
place-less query after this one resolves to (P3.1).

Deterministic and gated on the SAME routing rows Planning already computed
— reads `matched_intent_rows`, never re-classifies anything, so this cannot
become a second place intent is decided (Ground Rule 1). Runs after the
graph, not inside it: a DB outage here degrades to "no prompt this turn",
never to a missing or wrong answer.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

# Routing rows whose dispatched agents include risk_assessment — the vessel
# class actually changes the verdict for exactly these (planning.py's own
# ROUTING_TABLE agent lists), so this set is read from that fact, not
# guessed independently of it.
_VESSEL_SENSITIVE_INTENTS = frozenset({"SAFETY_CHECK", "CONDITIONS", "HAZARD_ALERTS", "REGULATORY", "ROUTE"})

_VESSEL_OPTIONS = [
    {"value": "catamaran", "label": "Catamaran"},
    {"value": "fibreglass", "label": "Fibreglass boat"},
    {"value": "mechanised", "label": "Mechanised boat"},
    {"value": "trawler", "label": "Trawler"},
    {"value": "cargo", "label": "Cargo vessel"},
]


def profile_prompt(
    *, user_id: uuid.UUID | None, matched_intent_rows: list[str], place_source: str | None,
) -> dict[str, Any] | None:
    """One prompt at most, or None. Vessel takes priority over home port —
    it is the safety-relevant one. Anonymous callers (no `user_id`) are
    never prompted: there is no account to write the answer to.

    `needs_home_port` fires when this query resolved to a REAL position —
    a named place or a live GPS fix — not the regional default. That is the
    opposite of the first version written here, which offered to save the
    *fallback* position as home port precisely when there was no real
    position to offer; caught before this ever answered a query, by reading
    what `place_source` values `orca/api/main.py` actually produces
    (P1.2/P3.1) rather than assuming "regional_default" meant "a place worth
    remembering"."""
    if user_id is None:
        return None

    needs_vessel = any(row in _VESSEL_SENSITIVE_INTENTS for row in matched_intent_rows)
    needs_home_port = place_source not in (None, "regional_default", "session_carried")
    if not (needs_vessel or needs_home_port):
        return None

    try:
        from orca.db.engine import get_sessionmaker
        from orca.db.models import User

        db = get_sessionmaker()()
        try:
            user = db.get(User, user_id)
            if user is None:
                return None
            if needs_vessel and user.active_vessel_id is None:
                return {
                    "field": "vessel_class",
                    "question": _localize(
                        "What boat are you taking? I'll use this for your safety limits from now on.", user.language,
                    ),
                    "input_type": "choice",
                    "options": [
                        {"value": o["value"], "label": _localize(o["label"], user.language)} for o in _VESSEL_OPTIONS
                    ],
                }
            if needs_home_port and user.home_port is None:
                return {
                    "field": "home_port",
                    "question": _localize(
                        "Save this as your home port, so I can answer at your position when you don't name one?",
                        user.language,
                    ),
                    "input_type": "confirm",
                }
        finally:
            db.close()
    except Exception:
        logging.getLogger("orca.profile_prompts").warning("profile prompt check failed", exc_info=True)
    return None


def _localize(text: str, language: str) -> str:
    """P3.3's "takes effect across UI chrome, answers, voice and alerts"
    applies to this prompt too — it's a question ORCA asks, same as an
    answer. Same fallback discipline as `main.py`'s language-change
    confirmation: a translation failure (unconfigured Bhashini, no
    IndicTrans2 backend, an unreachable rung) degrades to the English
    question rather than raising into a broken turn."""
    if language == "en":
        return text
    try:
        from orca.agents.language import _ALL_LANGUAGES, translate_from_english

        return translate_from_english(text, target=language) if language in _ALL_LANGUAGES else text  # type: ignore[arg-type]
    except Exception:
        return text
