"""Agent 13 — Understand (Prompt Routing Revamp §6).

One cheap-tier LLM call that READS every prompt, replacing the word-list gates.
Returns a fixed structure: kind, intents, places, when, is_followup.

Word lists stay as the offline fallback when every model is unreachable.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.llm.tiers import LLMUnavailable, llm
from orca.state import ORCAState


@dataclass(frozen=True)
class UnderstoodPrompt:
    kind: Literal[
        "sea_question",
        "greeting_or_small_talk",
        "clock_or_position",
        "what_can_orca_do",
        "reset_or_language_switch",
        "distress",
        "off_topic",
    ]
    intents: list[str]  # subset of ROUTING_TABLE row names
    places: list[dict[str, Any]]  # each: {"raw": str, "normalized": str | None}
    when: dict[str, Any] | None  # {"start": iso, "end": iso} or None
    is_followup: bool


_ROUTING_ROW_NAMES = (
    "SAFETY_CHECK", "PFZ_NEAREST", "CONDITIONS", "HAZARD_ALERTS", "ZONES_TO_AVOID",
    "ROUTE", "DIAGNOSTIC", "REGULATORY", "META", "EXPORT", "SUBSCRIPTION",
    "ADMINISTRATIVE", "WORTHWHILENESS", "TIMING", "COUNTERFACTUAL", "COMPARISON",
    "ENDURANCE", "FUEL_ECONOMICS", "HISTORICAL",
)

_KIND_VALUES = (
    "sea_question", "greeting_or_small_talk", "clock_or_position",
    "what_can_orca_do", "reset_or_language_switch", "distress", "off_topic",
)


def _build_understand_prompt(
    message: str,
    session_history: list[dict] | None,
    user_location: dict[str, Any] | None,
    current_time_iso: str,
) -> str:
    history_block = ""
    if session_history:
        turns = []
        for i, t in enumerate(session_history[-5:], 1):
            q = t.get("english_query") or t.get("query")
            if q:
                turns.append(f'{i}. "{q}"')
        if turns:
            history_block = f"\nRECENT TURNS (oldest first, max 5):\n" + "\n".join(turns)

    location_block = ""
    if user_location:
        lat, lon = user_location.get("lat"), user_location.get("lon")
        name = user_location.get("place_name")
        src = user_location.get("place_source")
        if lat is not None and lon is not None:
            location_block = f"\nCALLER'S POSITION: {lat:.4f}, {lon:.4f}"
            if name:
                location_block += f" ({name}, source: {src})"

    row_names = ", ".join(_ROUTING_ROW_NAMES)
    kind_values = ", ".join(_KIND_VALUES)

    return f"""You are ORCA's prompt understanding layer. Read the user's message in context and classify it.

USER MESSAGE: "{message}"
{history_block}
{location_block}
CURRENT TIME (IST): {current_time_iso}

ROUTING CATEGORIES (intents): {row_names}
KIND VALUES: {kind_values}

OUTPUT FORMAT — JSON only, no extra text:
{{
  "kind": "<one of the KIND_VALUES>",
  "intents": ["<zero or more routing category names>"],
  "places": [{{"raw": "<text as typed>", "normalized": "<gazetteer name or null>"}}],
  "when": {{"start": "<ISO datetime>", "end": "<ISO datetime>"}} or null,
  "is_followup": true/false
}}

RULES:
1. kind = "distress" ONLY when the message clearly signals an emergency at sea (sinking, capsized, man overboard, mayday, medical emergency at sea, engine failure adrift, no fuel adrift). If unsure, use "sea_question" — the deterministic distress_check node runs separately and can escalate.
2. kind = "clock_or_position" for "what time is it", "where am I", "current location/time" — questions about ORCA's own context, not the sea.
3. kind = "greeting_or_small_talk" for "hi", "hello", "thanks", "who are you", "what can you do" — conversational openers.
4. kind = "what_can_orca_do" for capability questions ("what do you do", "help me with").
5. kind = "reset_or_language_switch" for "reset", "change language", "switch to Tamil".
6. kind = "off_topic" for clearly non-marine content (recipes, sports, stocks, jokes).
7. kind = "sea_question" for everything else about conditions at sea off India.
8. intents: pick zero or more from the routing categories. A "wave height at Kochi" -> ["CONDITIONS"]. "safe to go tomorrow near Kochi" -> ["SAFETY_CHECK", "TIMING"]. "nearest fishing zone" -> ["PFZ_NEAREST"].
9. places: extract every place mention as typed. normalized = gazetteer name if you recognize it (e.g. "ktaka" -> "Karnataka", "pondy" -> "Puducherry"), else null.
10. when: if the message implies a time range (today, tomorrow, day after, next Friday, in 3 days), return ISO start/end in IST. "now" -> null. If ambiguous, return null.
11. is_followup: true if this continues the previous turn (short, starts with "and", "what about", "how about", "also", "then", "or", "but", "in a", "on a", "with a").
12. NEVER invent numbers, distances, or sea conditions. Only classify.
"""


def _parse_understand_output(raw: str) -> UnderstoodPrompt | None:
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        return None

    kind = data.get("kind")
    if kind not in _KIND_VALUES:
        return None

    intents = [i for i in data.get("intents", []) if i in _ROUTING_ROW_NAMES]
    places = []
    for p in data.get("places", []):
        if isinstance(p, dict) and "raw" in p:
            places.append({"raw": p["raw"], "normalized": p.get("normalized")})

    when = data.get("when")
    if when is not None:
        if not isinstance(when, dict) or "start" not in when or "end" not in when:
            when = None

    is_followup = bool(data.get("is_followup", False))

    return UnderstoodPrompt(
        kind=kind,  # type: ignore[arg-type]
        intents=intents,
        places=places,
        when=when,
        is_followup=is_followup,
    )


def _fallback_understand(message: str, session_history: list[dict] | None) -> UnderstoodPrompt:
    """Offline fallback using the existing word lists (planning.py)."""
    from orca.agents.planning import (
        is_out_of_scope,
        is_self_context_question,
        is_continuation,
        _MARINE_VOCAB,
        _NON_MARINE_TASKS,
        _INJECTION_PATTERNS,
        _SELF_CONTEXT_PHRASES,
        _CONTINUATION_OPENERS,
        classify_intent_deterministic,
    )
    from orca.data.loaders import resolve_all_places_from_text

    lowered = message.lower().strip()

    # Distress check (phrase list only — conservative)
    from orca.agents.distress import detect_distress_signal
    det = detect_distress_signal(message)
    if det["is_distress"]:
        return UnderstoodPrompt(
            kind="distress", intents=[], places=[], when=None, is_followup=False
        )

    # Injection / non-marine tasks
    if any(p in lowered for p in _INJECTION_PATTERNS):
        return UnderstoodPrompt(kind="off_topic", intents=[], places=[], when=None, is_followup=False)
    if any(p in lowered for p in _NON_MARINE_TASKS):
        return UnderstoodPrompt(kind="off_topic", intents=[], places=[], when=None, is_followup=False)

    # Self-context (clock/position)
    if is_self_context_question(lowered):
        return UnderstoodPrompt(kind="clock_or_position", intents=[], places=[], when=None, is_followup=False)

    # Greeting / small talk / capability
    greetings = {"hi", "hello", "hey", "thanks", "thank you", "who are you", "what are you", "what can you do", "help"}
    if any(g in lowered.split() for g in greetings) and len(lowered.split()) <= 5:
        return UnderstoodPrompt(kind="greeting_or_small_talk", intents=[], places=[], when=None, is_followup=False)

    # Reset / language switch
    if any(w in lowered for w in ("reset", "change language", "switch language", "language")):
        return UnderstoodPrompt(kind="reset_or_language_switch", intents=[], places=[], when=None, is_followup=False)

    # Out of scope (no marine vocab, no known place, not self-context)
    if is_out_of_scope(lowered):
        return UnderstoodPrompt(kind="off_topic", intents=[], places=[], when=None, is_followup=False)

    # Sea question — use deterministic classifier for intents
    intents = [name for name, _ in classify_intent_deterministic(lowered)]
    places_raw = resolve_all_places_from_text(message)
    places = [{"raw": p.name, "normalized": p.name} for p in places_raw]

    # Follow-up detection
    followup = is_continuation(lowered) and bool(session_history)

    return UnderstoodPrompt(
        kind="sea_question", intents=intents, places=places, when=None, is_followup=followup
    )


def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Runs once per query, before planning."""
    message = state.get("raw_user_query", "") or ""
    session_history = state.get("session_history")
    user_location = state.get("user_location")
    current_time_iso = datetime.now(timezone.utc).astimezone().isoformat()

    try:
        client = llm("cheap")
        prompt = _build_understand_prompt(message, session_history, user_location, current_time_iso)
        raw = client.complete([{"role": "user", "content": prompt}]).strip()
        understood = _parse_understand_output(raw)
        if understood is None:
            raise ValueError("invalid understand output")
        engine = getattr(client, "engine", "unknown")
    except (LLMUnavailable, Exception):
        understood = _fallback_understand(message, session_history)
        engine = "deterministic (fallback)"

    return AgentResult(
        agent_name="understand",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth("SHALLOW"),
        inputs_consumed={
            "message": message,
            "history_turns": len(session_history or []),
            "has_location": bool(user_location),
        },
        outputs={
            "kind": understood.kind,
            "intents": understood.intents,
            "places": understood.places,
            "when": understood.when,
            "is_followup": understood.is_followup,
        },
        source_provenance=SourceProvenance(
            dataset="LLM prompt understanding (cheap tier) or deterministic fallback",
            acquisition_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,
        ),
        confidence=Confidence(
            score="HIGH" if engine != "deterministic (fallback)" else "MEDIUM",
            rationale="LLM understanding" if engine != "deterministic (fallback)" else "Deterministic word-list fallback",
        ),
        engine=engine,
    )


if __name__ == "__main__":
    # Self-check: no network
    os.environ["ORCA_LLM_ENABLED"] = "0"
    from orca.state import ORCAState
    state: ORCAState = {
        "query_id": "test-1",
        "raw_user_query": "hi",
        "session_history": [],
        "user_location": None,
    }
    result = run(state)
    assert result.outputs["kind"] == "greeting_or_small_talk"
    print("understand self-check ok")