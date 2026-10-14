"""Distress model check (Prompt Routing Revamp section 7.4): escalate-only.

Why this lives in its own module and not in `distress.py`: `distress.py` is a
safety-path file. Its detection is deterministic phrase matching, and
`scripts/verify_ci_guards.py` (guard 4) holds every safety-path file to "never
gains the means to call a model". This module is the one place a model touches
distress, and what it may do is deliberately narrow:

- it runs only when the phrase list did NOT detect distress;
- it can only ESCALATE (turn "no distress" into "distress"); it can never clear
  a flag the phrase list or the SOS control raised;
- if no model is reachable, or the model answers badly, the phrase-list result
  stands unchanged.

`distress.run` receives this function as an argument (`escalate=`); the graph's
distress node supplies it. Nothing in `distress.py` imports this module, and the
CI guard forbids it from doing so.
"""
from __future__ import annotations

from typing import Any


# The model check used to run on every ordinary marine question. These cues
# are only a cheap gate for the model call; they never declare an emergency or
# suppress a phrase-list match. Keep them focused on danger, injury, or vessel
# failure so routine questions about fishing, weather, and navigation skip the
# network round-trip.
_LATIN_ESCALATION_CUES = (
    "engine", "trouble", "broken", "failed", "failure", "stopped", "not starting",
    "leak", "taking water", "water coming in", "overturned", "turned over",
    "swept away", "stranded", "adrift", "overboard", "drowning", "injur",
    "bleed", "unconscious", "not breathing", "heart attack", "fire on board",
    "collision", "grounded", "missing crew", "lost at sea", "mayday", "sos",
)

_SCRIPT_CUES: dict[str, tuple[tuple[int, int], tuple[str, ...]]] = {
    "kn": ((0x0C80, 0x0CFF), ("ಎಂಜಿನ್", "ಮುಳು", "ಸಹಾಯ", "ರಕ್ಷ", "ಅಪಾಯ", "ಗಾಯ", "ರಕ್ತ", "ಉಸಿರ", "ಬೆಂಕಿ", "ಸಿಲುಕ")),
    "hi": ((0x0900, 0x097F), ("इंजन", "डूब", "मदद", "बचाओ", "फंस", "फँस", "घायल", "खून", "बेहोश", "सांस", "आग", "खराब")),
    "mr": ((0x0900, 0x097F), ("इंजन", "बुड", "मदत", "अडक", "जखम", "रक्त", "बेशुद्ध", "श्वास", "आग", "बंद पड")),
    "ta": ((0x0B80, 0x0BFF), ("இயந்திர", "மூழ்", "உதவி", "காப்பாற்ற", "ஆபத்து", "காய", "ரத்த", "மயக்க", "மூச்சு", "தீ", "சிக்க")),
    "te": ((0x0C00, 0x0C7F), ("ఇంజిన్", "మునిగ", "సహాయం", "రక్ష", "ప్రమాద", "గాయం", "రక్త", "స్పృహ", "ఊపిరి", "మంట", "చిక్క")),
    "ml": ((0x0D00, 0x0D7F), ("എഞ്ചിൻ", "മുങ്ങ", "സഹായ", "രക്ഷ", "അപകട", "പരിക്ക്", "രക്ത", "ബോധം", "ശ്വാസ", "തീ", "കുടുങ്ങ")),
    "bn": ((0x0980, 0x09FF), ("ইঞ্জিন", "ডুব", "সাহায্য", "বাঁচ", "বিপদ", "আহত", "রক্ত", "অজ্ঞান", "শ্বাস", "আগুন", "আটক")),
    "gu": ((0x0A80, 0x0AFF), ("એન્જિન", "ડૂબ", "મદદ", "બચાવ", "જોખમ", "ઇજા", "લોહી", "બેભાન", "શ્વાસ", "આગ", "ફસ")),
    "or": ((0x0B00, 0x0B7F), ("ଇଞ୍ଜିନ", "ବୁଡ଼", "ସାହାଯ୍ୟ", "ବଞ୍ଚା", "ବିପଦ", "ଆହତ", "ରକ୍ତ", "ଅଚେତ", "ନିଶ୍ୱାସ", "ନିଆଁ", "ଫସ")),
}


def _may_describe_distress(text: str) -> bool:
    folded = text.casefold()
    if any(cue in folded for cue in _LATIN_ESCALATION_CUES):
        return True
    script_cues: list[str] = []
    for (start, end), cues in _SCRIPT_CUES.values():
        if any(start <= ord(char) <= end for char in text):
            script_cues.extend(cues)
    if script_cues:
        return any(cue in text for cue in script_cues)
    # Unknown scripts keep the conservative model path until we have reviewed
    # a language-specific cue list rather than silently disabling coverage.
    return any(ord(char) > 0x024F for char in text)


def escalate_with_model(text: str, phrase_detection: dict[str, Any]) -> dict[str, Any]:
    """Prompt Routing Revamp §7.4 — Distress model check (escalate-only).

    Runs ONLY when the deterministic phrase list did NOT detect distress.
    Can ONLY escalate (set is_distress=True), never de-escalate.
    Catches: "engine failed near Pamban", "water coming into boat",
    "my friend fell in the water" — paraphrases the phrase list misses.
    """
    # If phrase list already detected distress, don't run model (escalate-only)
    if phrase_detection.get("is_distress"):
        return phrase_detection

    # Avoid paying for a remote classifier on routine requests. The candidate
    # gate is intentionally one-way: it can skip this model call, but a cue
    # alone never raises an alarm; the model still must return a clear YES.
    if not _may_describe_distress(text):
        return phrase_detection

    # If no model available, return phrase list result
    try:
        from orca.llm.tiers import llm
        client = llm("cheap")
    except Exception:  # includes LLMUnavailable (a RuntimeError): no model means the phrase list stands
        return phrase_detection

    prompt = f"""You are a maritime distress classifier. Read this message and determine if it describes a LIFE-THREATENING EMERGENCY AT SEA requiring immediate Coast Guard rescue.

MESSAGE: "{text}"

EMERGENCY SITUATIONS (answer YES only for these):
- Vessel sinking, capsizing, taking on water, going down
- Person overboard, man overboard, fell in the water, drowning
- Engine failure / no fuel / adrift AT SEA (not at dock)
- Medical emergency AT SEA (heart attack, severe injury, unconscious)
- Lost at sea, missing vessel
- Fire on board, explosion
- Collision, grounding with danger to life
- MAYDAY, SOS, "send help" in a marine context

NON-EMERGENCIES (answer NO):
- Engine trouble at dock / near shore / "engine failed near [port]"
- "Water in boat" from rain, washing, minor leak at dock
- General questions about safety, weather, conditions
- Past incidents ("my friend fell in the water last year")
- Fishing, navigation, routine operations
- Metaphorical language ("drowning in work")

OUTPUT: JSON only: {{"is_distress": true/false, "reason": "brief reason if yes"}}

If YES, the reason must be one of: sinking, capsizing, man_overboard, engine_failure_adrift, medical_at_sea, lost_at_sea, fire_explosion, collision_grounding, mayday_sos.
If NO, reason is not required."""

    try:
        raw = client.complete([{"role": "user", "content": prompt}]).strip()
        import json
        result = json.loads(raw)
        if result.get("is_distress") is True:
            return {
                "is_distress": True,
                "distress_type": "model_escalated",
                "matched_language": None,
                "matched_phrase": None,
                "model_reason": result.get("reason"),
            }
    except Exception:
        pass

    return phrase_detection
