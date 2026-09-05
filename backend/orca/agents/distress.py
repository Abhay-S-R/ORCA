"""Agent 12 — Distress & Emergency Handoff (Architecture §3.2). Deterministic
detection only (mirrors Ground Rule 2) — an LLM's "semantic understanding"
of a distress call is exactly the wrong tool here: it invites both false
negatives from paraphrase and false positives from casual language, which
is why the architecture doc specifies pattern match, not inference.

HONEST GAP, stated plainly: the Tamil and Hindi phrase lists below are a
verified STARTER set, not a validated operational one. Every phrase was
checked against a real source while writing this (see the comment on each
list) — none are guessed transliteration — but coverage is thin (a handful
of phrases per language, no colloquial fishing-village variants, no dialect
coverage) and nobody with native fluency has reviewed it. Treat MAX_ITERATIONS
of testing against this list as a false sense of security until that review
happens. This is the single highest-consequence piece of unverified content
in the whole build — flag it accordingly, don't quietly ship it as done.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.state import ORCAState

# Each phrase confirmed via a real dictionary/translation source while writing
# this — not transliterated from memory. See the module docstring: this is a
# starter list, not a validated one.
_DISTRESS_PATTERNS: dict[str, list[str]] = {
    "en": ["sinking", "taking on water", "man overboard", "mayday", "capsizing", "capsized", "drowning", "sos", "help"],
    "ta": ["மூழ்குகிறது", "படகு மூழ்குகிறது", "மூழ்கிவிட்டேன்", "உதவி"],  # sinking / boat is sinking / I have drowned / help
    "hi": ["बचाओ", "डूब रहा", "डूब रही", "नाव डूब रही है"],  # save me / is drowning (m/f) / the boat is sinking
}

# Verified 2026-09-02: 1554 is the Indian Coast Guard's official nationwide
# toll-free MRCC distress helpline (confirmed via a live news/coast-guard
# source, not assumed). MRCC Chennai covers the Tamil Nadu pilot region.
# VHF Channel 16 is the international maritime distress/calling channel
# (ITU/IMO standard, not India-specific). PHONE NUMBERS CAN CHANGE — verify
# again before a real demo or deployment; this is sourced, not guaranteed current.
MRCC_CONTACTS: dict[str, dict[str, str]] = {
    "default": {"name": "Indian Coast Guard MRCC (nationwide)", "phone": "1554", "vhf_channel": "16"},
    "chennai": {"name": "MRCC Chennai", "phone": "+91-44-2539-5018", "vhf_channel": "16"},
}


def detect_distress_signal(text: str, ui_control_triggered: bool = False) -> dict[str, Any]:
    """Tool per Architecture §3.2 Agent 12. Any ONE trigger is sufficient
    (explicit SOS tap always wins immediately, no text needed)."""
    if ui_control_triggered:
        return {"is_distress": True, "distress_type": "sos_control", "matched_language": None, "matched_phrase": None}

    text_lower = text.lower()
    for lang, phrases in _DISTRESS_PATTERNS.items():
        for phrase in phrases:
            needle = phrase if lang != "en" else phrase.lower()
            if needle in (text if lang != "en" else text_lower):
                return {"is_distress": True, "distress_type": "text_pattern", "matched_language": lang, "matched_phrase": phrase}

    return {"is_distress": False, "distress_type": None, "matched_language": None, "matched_phrase": None}


def surface_mrcc_contact(user_location: dict[str, Any] | None, language: str = "en") -> dict[str, Any]:
    """Tool per Architecture §3.2 Agent 12. Region resolution is coarse
    (pilot region only has one MRCC in scope) — a real multi-region lookup
    is out of scope while the pilot is a single coastal strip. Always
    returns the nationwide 1554 number regardless, so a lookup miss is
    never a total miss."""
    contact = MRCC_CONTACTS.get("chennai", MRCC_CONTACTS["default"])
    return {
        "primary": contact,
        "nationwide_fallback": MRCC_CONTACTS["default"],
        "language": language,
    }


def emit_datsg_handoff(
    position: dict[str, float] | None, vessel_id: str | None, distress_type: str | None, timestamp: str
) -> dict[str, Any]:
    """Tool per Architecture §3.2 Agent 12. No direct DAT-SG/Sagarmitra API
    integration exists (out of scope for a hackathon build, per the
    architecture doc's own note) — this emits the CAP-compatible fallback
    format explicitly named as acceptable when direct integration isn't
    available."""
    return {
        "format": "CAP-fallback",
        "position": position,
        "vessel_id": vessel_id,
        "distress_type": distress_type,
        "timestamp": timestamp,
        "status": "SIMULATED",  # no real transponder/gateway exists — never claim delivered
    }


def run(state: ORCAState) -> AgentResult:
    """(ORCAState) -> AgentResult. Bypasses normal persona-rendering (Agent
    9's job) entirely — this agent's output is surfaced directly per
    Architecture §3.2 step 1, not synthesized."""
    # Check BOTH the original-language and English-normalized text, not
    # either/or — whichever pipeline stage this runs relative to Agent 1's
    # translation, a vernacular distress phrase must not go unmatched just
    # because only the translated field got populated (or vice versa).
    # Missing a real distress call is the one failure mode worse than a
    # redundant check.
    raw_text = state.get("raw_user_query", "") or ""
    normalized_text = state.get("normalized_english_query", "") or ""
    combined_text = f"{raw_text} {normalized_text}"
    detection = detect_distress_signal(combined_text, ui_control_triggered=state.get("distress_flag", False))

    location = state.get("user_location")
    mrcc = surface_mrcc_contact(location)
    handoff = emit_datsg_handoff(
        position=location,
        vessel_id=None,
        distress_type=detection["distress_type"],
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )

    return AgentResult(
        agent_name="distress",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"text": combined_text.strip(), "ui_control_triggered": state.get("distress_flag", False)},
        outputs={"detection": detection, "mrcc_contact": mrcc, "handoff": handoff},
        source_provenance=SourceProvenance(
            dataset="Deterministic multilingual pattern match (starter set — see module docstring)",
            acquisition_timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            freshness_minutes=0,
        ),
        # HIGH only for an explicit SOS tap — unambiguous regardless of
        # outcome. Everything routed through the text pattern list is MEDIUM
        # at best, in BOTH directions: a match could be a false positive from
        # casual phrasing the list doesn't distinguish, and — the more
        # dangerous direction — a non-match could be a false negative because
        # the list's coverage is thin. Never claim HIGH confidence in "not a
        # distress" off an unreviewed list; that overclaim is the whole risk.
        confidence=Confidence(
            score="HIGH" if detection["distress_type"] == "sos_control" else "MEDIUM",
            rationale="Explicit SOS control tap — unambiguous"
            if detection["distress_type"] == "sos_control"
            else "Deterministic pattern match against an unreviewed starter list (see module docstring) — "
            "true in both directions: a match may be a false positive, a non-match may be a false negative",
        ),
    )
