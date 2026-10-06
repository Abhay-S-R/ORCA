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
