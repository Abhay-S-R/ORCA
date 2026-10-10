"""Agent 13 — Understand (Prompt Routing Revamp §6).

One cheap-tier LLM call that READS every prompt, replacing the word-list gates.
Returns a fixed structure: kind, intents, places, when, is_followup.

Word lists stay as the offline fallback when every model is unreachable.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.llm.tiers import LLMUnavailable, llm
from orca.state import ORCAState

# PC2.1 (`R-AGENT-2`, `PS-ARCH`) — the set of specialist agent names Understand
# may suggest. Hallucinated names are silently dropped in _parse_understand_output.
# These are the graph node names from graph.py (the only names the graph knows).
_KNOWN_SPECIALISTS = frozenset({
    "marine_data_discovery",
    "weather_intelligence",
    "ocean_analytics",
    "geospatial",
    "risk_assessment",
    "visualization",
    "reporting",
})


@dataclass(frozen=True)
class UnderstoodPrompt:
    kind: Literal[
        "sea_question",
        "greeting_or_small_talk",
        "clock_or_position",
        "what_can_orca_do",
        "reset_or_language_switch",
        "chat_followup",
        "inland_place",
        "distress",
        "off_topic",
    ]
    intents: list[str]  # subset of ROUTING_TABLE row names
    places: list[dict[str, Any]]  # each: {"raw": str, "normalized": str | None}
    when: dict[str, Any] | None  # {"start": iso, "end": iso} or None
    is_followup: bool
    agents: list[str]  # PC2.1: subset of _KNOWN_SPECIALISTS; recorded, not yet acted on
    # PC5.2: the message rendered in plain English, for display only. It is never read for routing,
    # place lookup or validation, so a wrong reading cannot move a verdict; the "I understood: ..."
    # line (PC5.5) is what shows it to the user.
    english_reading: str | None = None
    # PC5.8: the language the user EXPLICITLY asked the answer to be in ("answer in Kannada",
    # "ಕನ್ನಡದಲ್ಲಿ ಹೇಳಿ"), as one of the ten supported codes, or None. Never inferred from the
    # language the message is written in (that is the script's job): None means "no request".
    reply_language: str | None = None
    # CONTEXT-2: True only when the message asks for NOTHING but the earlier answer in another language ("answer the
    # same in Kannada", "now in English please"). The model reads it; planning checks it against the real history.
    language_only: bool = False


_ROUTING_ROW_NAMES = (
    "SAFETY_CHECK", "PFZ_NEAREST", "CONDITIONS", "HAZARD_ALERTS", "ZONES_TO_AVOID",
    "ROUTE", "DIAGNOSTIC", "REGULATORY", "META", "EXPORT", "SUBSCRIPTION",
    "ADMINISTRATIVE", "WORTHWHILENESS", "TIMING", "COUNTERFACTUAL", "COMPARISON",
    "ENDURANCE", "FUEL_ECONOMICS", "HISTORICAL",
)

_KIND_VALUES = (
    "sea_question", "greeting_or_small_talk", "clock_or_position",
    "what_can_orca_do", "reset_or_language_switch", "chat_followup", "inland_place", "distress", "off_topic",
)

# Every kind that is answered without running the sea agents. The one list the
# graph and planning both read, so adding a kind cannot be forgotten in one of
# them (a kind missing from a copy of this list would be run as a sea question).
NON_SEA_KINDS = frozenset(_KIND_VALUES) - {"sea_question"}


def _build_understand_prompt(
    message: str,
    session_history: list[dict] | None,
    user_location: dict[str, Any] | None,
    current_time_iso: str,
) -> str:
    history_block = ""
    if session_history:
        from orca.session import MAX_TURNS, RECENT_TURNS

        turns = []
        first_recent = max(0, len(session_history) - RECENT_TURNS)
        for i, t in enumerate(session_history, 1):
            q = t.get("english_query") or t.get("query")
            if q:
                about = (t.get("user_location") or {}).get("place_name")
                turns.append(f'{i}. User: "{q}"' + (f" [answered for: {about}]" if about else ""))
                # What ORCA replied is what a short follow-up refers to: "more
                # detail" after a capability answer is not "more detail" after a PFZ. Older turns
                # keep their question only (FIX-CONTEXT-1), so the whole chat is still in view.
                if t.get("answer") and i > first_recent:
                    turns.append(f'   Sagar Sarathi replied: "{str(t["answer"])[:240]}"')
        if turns:
            gone = (
                f"\n(Only the last {MAX_TURNS} turns of this chat are kept; anything earlier is not available.)"
                if len(session_history) >= MAX_TURNS else ""
            )
            history_block = "\nRECENT TURNS (oldest first; the last few include Sagar Sarathi's reply):\n" + "\n".join(turns) + gone

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

    return f"""You are Sagar Sarathi's prompt understanding layer. Read the user's message in context and classify it.

USER MESSAGE: "{message}"
{history_block}
{location_block}
CURRENT TIME: {current_time_iso}
DATA EXTENT: India's maritime waters (5.0°N to 25.0°N, 66.0°E to 96.0°E — Arabian Sea, Lakshadweep, Bay of Bengal, Andaman & Nicobar).
FORECAST HORIZON: Up to 7 days ahead.

CAPABILITY CATALOGUE:
- Sea Safety & Go/No-Go: Real-time risk assessment, boat safety thresholds, advisory warnings.
- Sea Conditions: Wave height, swell, wind speed & direction, current, sea surface temperature.
- Tides: High/low tide timings, tidal heights, ebb/flood directions.
- Potential Fishing Zones (PFZ): INCOIS PFZ coordinates, bearing, distance, persistence; state-assigned fishing limits and home port zones.
- Maritime Boundaries: International Maritime Boundary Line (IMBL), state fishing limits (0–12 NM under MFRA), EEZ borders, restricted zones.
- Severe Weather: Cyclone tracking, storm surge, squall alerts, lightning hazards.
- Trip Optimization: Best departure timing, endurance/range limits, fuel economics.

ROUTING CATEGORIES (intents): {row_names}
KIND VALUES: {kind_values}

OUTPUT FORMAT — JSON only, no markdown wrapping, no extra text:
{{
  "kind": "<one of the KIND_VALUES>",
  "intents": ["<zero or more routing category names>"],
  "places": [{{"raw": "<text as typed>", "normalized": "<gazetteer coastal place name or null>"}}],
  "when": {{"start": "<ISO datetime>", "end": "<ISO datetime>"}} or null,
  "is_followup": true/false,
  "agents": ["<zero or more specialist names>"],
  "english_reading": "<the message in plain English, or the message itself if it is already English>",
  "reply_language": "<ta|hi|te|ml|kn|bn|mr|gu|or|en, only if the user explicitly asked for the answer in a language, else null>",
  "language_only": true/false
}}

KNOWN SPECIALISTS (agents field): marine_data_discovery, weather_intelligence, ocean_analytics, geospatial, risk_assessment, visualization, reporting
Pick the specialists this query most likely needs. Use an empty list for non-sea queries. Do NOT invent names outside the known list.

RULES:
1. kind = "distress" ONLY when the message clearly signals an active emergency at sea (sinking, capsized, boat taking on water, man overboard, mayday, medical emergency at sea, engine failure adrift, no fuel adrift). A question about what to do in a hypothetical or general case ("what should I do if my engine fails at sea", "how do I use a flare", "what is the MRCC number") is NOT an emergency: use "sea_question" (or "what_can_orca_do" when it is about ORCA). The person must be describing something that is happening to them now. If unsure, use "sea_question".
2. kind = "clock_or_position" for "what time is it", "where am I", "current location/time", "what is my position" — questions about ORCA's own context, not the sea.
3. kind = "greeting_or_small_talk" for "hi", "hello", "namaste", "vanakkam", "thanks", "who are you", "good morning" — conversational openers.
4. kind = "what_can_orca_do" for capability and identity questions, in any language ("what do you do", "help me", "how can you assist", "features", "who are you", "what is your name", "what are you"). A question about the assistant itself is never a sea question.
5. kind = "reset_or_language_switch" ONLY for a request to wipe or restart the conversation ("reset", "clear conversation", "start over", "forget that") or to change the app's own display language with no answer being asked for ("change language", "change the app language"). A request to have an ANSWER in a language ("switch to Tamil", "talk in Hindi", "answer the same in Kannada", "in Hindi please", "say that in Tamil") is NOT a reset: it is rule 18.
6. kind = "off_topic" for clearly non-marine content (recipes, sports, stocks, movies, coding, general trivia). A message that only makes sense as a reply to RECENT TURNS is never off_topic just because it has no marine words in it; see rule 14.
7. kind = "sea_question" for questions about conditions, safety, fishing, weather, or navigation at sea off India.
8. MIXED LANGUAGE & TRANSLITERATION: The message may be in Romanized Indian languages (Hinglish, Tanglish, Manglish, etc., e.g., "machli kahan milegi", "nale kadal povan pattuva", "pondi la nalaiku safe ah"). Classify according to its marine meaning.
9. TYPOS & INFORMAL PHRASING: Tolerate typos and abbreviations (e.g. "whr is pfz", "is it sf to go", "wav hight", "tide tmrw").
10. PLACES & STATE SHORTFORMS: Extract all place mentions. Recognize Indian coastal state shortforms and common names:
    - TN / Tamil Nadu (Chennai, Tuticorin, Rameswaram, Cuddalore, Nagapattinam, Kanyakumari)
    - KL / Kerala (Kochi, Cochin, Vizhinjam, Beypore, Calicut, Kollam, Munambam)
    - AP / Andhra Pradesh (Vizag, Visakhapatnam, Kakinada, Machilipatnam, Krishnapatnam)
    - MH / Maharashtra (Mumbai, Bombay, Ratnagiri, Malvan, Alibaug)
    - KA / KTK / Karnataka (Mangalore, Mangaluru, Karwar, Malpe)
    - GA / Goa (Panaji, Mormugao)
    - WB / West Bengal (Digha, Haldia, Diamond Harbour)
    - OD / Odisha (Paradip, Puri, Gopalpur, Dhamra)
    - Pondy / PY / Puducherry / Pondicherry
    - Gujarat (Veraval, Porbandar, Okha, Kandla, Mangrol)
    - Island territories (Port Blair, Havelock, Lakshadweep, Kavaratti, Agatti, Minicoy)
    In `normalized`, provide the standard English gazetteer name if recognizable, else null.
11. WHEN: Parse explicit and relative times into ISO strings:
    - "today", "now", "current" -> start: today 00:00, end: today 23:59 (or null if "now").
    - "tomorrow", "tmrw" -> start: tomorrow 00:00, end: tomorrow 23:59.
    - "day after tomorrow", "in 2 days" -> corresponding ISO dates.
    - Out of range (> 7 days ahead or past dates) should still be parsed with their ISO dates so validation can catch them.
12. FOLLOW-UPS: is_followup = true if the query is a continuation of the previous turn (e.g. "and tomorrow?", "what about in a fiber boat?", "how about wind?", "also check tides").
13. NEVER invent numbers, distances, or mock data. Only classify and extract.
13a. A MESSAGE THAT REFERS TO A PLACE WITHOUT NAMING IT ("the same place", "there", "that port", "same as before", "the first one", "and for that place in Hindi"): work out which place the user means from RECENT TURNS (each turn shows the place it was answered for), and put THAT place in `places`: `raw` is the user's own words ("the same place"), `normalized` is the place's name as it appears in RECENT TURNS. The most recent place is the usual meaning; use an earlier one only when the message points at it ("the first place", "the one before"). Never invent a place that is not in RECENT TURNS; when no turn shows a place, leave `places` empty.
14. MESSAGES THAT REFER TO THE CONVERSATION. Read RECENT TURNS, including what Sagar Sarathi replied, then decide in this order:
    a. The message asks for ANY sea reading: new, repeated, more detailed, or for another time, place, boat or measure ("what about tomorrow evening?", "and in a trawler?", "how about wind?", "why is that?", "more detail", "explain that", "is that zone far?"), and Sagar Sarathi's last reply was a sea answer -> kind = "sea_question", is_followup = true, and leave places empty so the earlier place carries over.
    b. Only when it wants NO sea reading, because it talks about Sagar Sarathi or Sagar Sarathi's last reply: asks to elaborate on a capability answer or on a refusal, challenges or questions a limit ("so you can't give me a land forecast?", "why can't you?"), or reacts ("ok", "that's not what I asked") -> kind = "chat_followup".
    c. When Sagar Sarathi's last reply was a sea answer, a short follow-up is (a). When it was a capability answer, a refusal or chat, a follow-up that wants more is (b).
    d. A message that depends on the conversation is never "off_topic", and never a sea_question about a place the user did not name.
15. INLAND PLACES. kind = "inland_place" when the user asks for weather, conditions or a forecast at a place that is clearly inland, far from the sea (Bengaluru, Delhi, Hyderabad, Pune, Jaipur, Lucknow). Put the place in `places` as typed. It is NOT off_topic (the user is asking about weather) and NOT a sea_question (Sagar Sarathi has no sea data for it). A coastal city or port is always a sea_question: Mumbai, Chennai, Kochi, Visakhapatnam, Kolkata, Mangalore, Goa. If unsure whether a place is on the coast, use sea_question.
16. ENGLISH READING. `english_reading` is one short sentence: what the user wrote, in plain English, WITHOUT any instruction about the reply language ("answer in Kannada: pfzs near Mangalore" reads "PFZs near Mangalore"). Translate or transliterate Indian-language and romanized text ("kal subah rameswaram ke paas samudra mein jaana safe hai kya" becomes "Is it safe to go to sea near Rameswaram tomorrow morning?"). If the message is already English, copy it with its typos fixed. Keep place names. Do not answer the question, do not add facts, and do not guess a place the user did not write. It is shown to the user so they can see how they were understood.
17. REPLY LANGUAGE. `reply_language` is set ONLY when the user explicitly asks for the answer in a language: "answer in Kannada", "reply in Tamil", "Hindi mein batao", "ಕನ್ನಡದಲ್ಲಿ ಹೇಳಿ", also when the language is misspelt ("kannda", "tamizh"). Give its code: ta Tamil, hi Hindi, te Telugu, ml Malayalam, kn Kannada, bn Bengali, mr Marathi, gu Gujarati, or Odia, en English. In every other case it is null, including when the message itself is written in an Indian language or in romanized Hindi, Tamil or Kannada: the language a message is written in is NOT a request for a reply in it. The request words are an instruction about the reply, not part of the sea question: still read the places, time and intent from the rest of the message.
18. ASKING FOR THE EARLIER ANSWER IN ANOTHER LANGUAGE. When RECENT TURNS show a sea answer and the message only asks for it in a language ("answer the same in Kannada", "okay fine, now in Hindi", "in Tamil please", "say that again in Telugu", "can you give me that in Gujarati?", in any language or spelling) -> kind = "sea_question", is_followup = true, places and intents empty (the earlier question carries over), reply_language = that language's code, english_reading = the earlier question in plain English. It is never "reset_or_language_switch" and never "off_topic". Also set `"language_only": true` for it: the message asks for NOTHING but that earlier answer in another language. `language_only` is false whenever the message also asks anything else ("in Hindi, and what about tomorrow?", "in Tamil and the wind?", "now in English: SST and chlorophyll of the same place", a different measure, a new place, a new time) and whenever it is not a request for a language. When there is no earlier sea answer, and the message names no sea question, kind = "chat_followup" and reply_language is still set.
"""


_ENGLISH_READING_MAX = 240

# The languages a reply can be translated into (language._ALL_LANGUAGES; a test keeps the two equal).
# Kept as a literal here so this module does not import the translation stack.
_REPLY_LANGUAGES = ("ta", "hi", "te", "ml", "kn", "bn", "mr", "gu", "or", "en")


def _clean_reply_language(value: Any) -> str | None:
    """A supported language code, or None. The model proposes, code validates: anything that is
    not exactly one of the ten codes (a language name, a code we cannot translate to, a non-string)
    is "no request", so a garbled value can never send the reply to an unsupported language."""
    if not isinstance(value, str):
        return None
    code = value.strip().lower()
    return code if code in _REPLY_LANGUAGES else None


def _clean_english_reading(value: Any) -> str | None:
    """The model's English rendering of the message, or None. A non-string, an empty string and an
    over-long one are all "no reading": it is a display line, so anything odd is dropped, never
    repaired or trusted for anything else."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text if text and len(text) <= _ENGLISH_READING_MAX else None


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
    if when is not None and (not isinstance(when, dict) or "start" not in when or "end" not in when):
        when = None

    is_followup = bool(data.get("is_followup", False))

    # PC2.1 — validate against known specialist names; hallucinated names are dropped.
    agents = [a for a in data.get("agents", []) if a in _KNOWN_SPECIALISTS]

    return UnderstoodPrompt(
        kind=kind,  # type: ignore[arg-type]
        intents=intents,
        places=places,
        when=when,
        is_followup=is_followup,
        agents=agents,
        english_reading=_clean_english_reading(data.get("english_reading")),
        reply_language=_clean_reply_language(data.get("reply_language")),
        language_only=data.get("language_only") is True,
    )


# The offline reading of "answer in <language>": names and the common misspellings (the model, not this list, is the
# normal reader; this is only what is left when no model can be reached).
_LANGUAGE_NAMES = {
    "ta": ("tamil", "tamizh", "thamizh"),
    "hi": ("hindi",),
    "te": ("telugu",),
    "ml": ("malayalam",),
    "kn": ("kannada", "kannda", "kanada"),
    "bn": ("bengali", "bangla"),
    "mr": ("marathi",),
    "gu": ("gujarati",),
    "or": ("odia", "oriya"),
    "en": ("english",),
}
_LANGUAGE_NAME_RE = re.compile(
    r"\b(?:in|into|to)\s+(" + "|".join(n for names in _LANGUAGE_NAMES.values() for n in names) + r")\b"
    r"|^(?:please\s+)?(" + "|".join(n for names in _LANGUAGE_NAMES.values() for n in names) + r")(?:\s+please)?\W*$"
)


def requested_reply_language(message: str) -> str | None:
    """A language code when the message asks for the answer in a language ("in kannada", "answer the same in Hindi").
    Offline reading only: `understand` has the model do this; the code just validates what it proposes."""
    m = _LANGUAGE_NAME_RE.search((message or "").lower())
    if not m:
        return None
    word = m.group(1) or m.group(2)
    return next((code for code, names in _LANGUAGE_NAMES.items() if word in names), None)


def _fallback_understand(message: str, session_history: list[dict] | None) -> UnderstoodPrompt:
    """Offline fallback using the existing word lists (planning.py)."""
    from orca.agents.planning import (
        _INJECTION_PATTERNS,
        _NON_MARINE_TASKS,
        carry_intent,
        classify_intent_deterministic,
        is_continuation,
        is_out_of_scope,
        is_self_context_question,
    )
    from orca.data.loaders import resolve_all_places_from_text

    lowered = message.lower().strip()

    # Distress check (phrase list only — conservative)
    from orca.agents.distress import detect_distress_signal
    det = detect_distress_signal(message)
    if det["is_distress"]:
        return UnderstoodPrompt(
            kind="distress", intents=[], places=[], when=None, is_followup=False, agents=[],
        )

    # Injection / non-marine tasks
    if any(p in lowered for p in _INJECTION_PATTERNS):
        return UnderstoodPrompt(kind="off_topic", intents=[], places=[], when=None, is_followup=False, agents=[])
    if any(p in lowered for p in _NON_MARINE_TASKS):
        return UnderstoodPrompt(kind="off_topic", intents=[], places=[], when=None, is_followup=False, agents=[])

    # Self-context (clock/position)
    if is_self_context_question(lowered):
        return UnderstoodPrompt(kind="clock_or_position", intents=[], places=[], when=None, is_followup=False, agents=[])

    # Greeting / small talk / capability
    greetings = {"hi", "hello", "hey", "thanks", "thank you", "who are you", "what are you", "what can you do", "help"}
    if any(g in lowered.split() for g in greetings) and len(lowered.split()) <= 5:
        return UnderstoodPrompt(kind="greeting_or_small_talk", intents=[], places=[], when=None, is_followup=False, agents=[])

    # "answer the same in Kannada": the earlier sea answer again, in that language (never a reset)
    asked_language = requested_reply_language(lowered)
    if asked_language and carry_intent(session_history) and len(lowered.split()) <= 10:
        return UnderstoodPrompt(
            kind="sea_question", intents=[], places=[], when=None, is_followup=True, agents=[], reply_language=asked_language,
            language_only=True,
        )

    # Reset / language switch
    if not asked_language and any(w in lowered for w in ("reset", "change language", "switch language", "language")):
        return UnderstoodPrompt(kind="reset_or_language_switch", intents=[], places=[], when=None, is_followup=False, agents=[])

    # Out of scope (no marine vocab, no known place, not self-context). Not for a continuation of
    # an earlier sea turn: "and tomorrow?" has no marine words of its own and inherits them. This is
    # the rule planning applied before the planning/understand merge; without it a follow-up was
    # refused whenever no model was reachable.
    continues_a_sea_turn = bool(carry_intent(session_history)) and is_continuation(lowered)
    if is_out_of_scope(lowered) and not continues_a_sea_turn:
        return UnderstoodPrompt(kind="off_topic", intents=[], places=[], when=None, is_followup=False, agents=[])

    # Sea question — use deterministic classifier for intents
    intents = [name for name, _ in classify_intent_deterministic(lowered)]
    places_raw = resolve_all_places_from_text(message)
    places = [{"raw": p.name, "normalized": p.name} for p in places_raw]

    # Follow-up detection
    followup = is_continuation(lowered) and bool(session_history)

    # PC2.1 — offline fallback derives agents from the same planning table LLM would use.
    from orca.agents.planning import generate_execution_plan
    fallback_agents = [a for a in generate_execution_plan(intents, "SHALLOW") if a in _KNOWN_SPECIALISTS]

    return UnderstoodPrompt(
        kind="sea_question", intents=intents, places=places, when=None, is_followup=followup,
        agents=fallback_agents,
    )


def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Runs once per query, before planning."""
    message = state.get("raw_user_query", "") or ""
    session_history = state.get("session_history")
    user_location = state.get("user_location")
    current_time_iso = datetime.now(UTC).astimezone().isoformat()

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
            "agents": understood.agents,  # PC2.1
        },
        source_provenance=SourceProvenance(
            dataset="LLM prompt understanding (cheap tier) or deterministic fallback",
            acquisition_timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
    state: ORCAState = {  # type: ignore[typeddict-item]  # a partial state is enough for this check
        "query_id": "test-1",
        "raw_user_query": "hi",
        "session_history": [],
        "user_location": None,
    }
    result = run(state)
    assert result.outputs["kind"] == "greeting_or_small_talk"
    print("understand self-check ok")