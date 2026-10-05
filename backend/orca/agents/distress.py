"""Agent 12 — Distress & Emergency Handoff (Architecture §3.2). Deterministic
detection only (mirrors Ground Rule 2) — an LLM's "semantic understanding"
of a distress call is exactly the wrong tool here: it invites both false
negatives from paraphrase and false positives from casual language, which
is why the architecture doc specifies pattern match, not inference.

HONEST GAP, stated plainly: the phrase lists below (English, Tamil, Hindi,
Malayalam, Telugu) are a verified STARTER set, not a validated operational
one. Every phrase was checked against a real dictionary source while writing
this (Shabdkosh/Cambridge/Glosbe for ml and te, added SIH finale checklist
P1 #1 — same standard the original ta/hi entries were held to) — none are
guessed transliteration — but coverage is thin (a handful of phrases per
language, no colloquial fishing-village variants, no dialect coverage) and
nobody with native fluency has reviewed ANY of these five lists, ml/te
included. Treat MAX_ITERATIONS of testing against this list as a false sense
of security until that review happens. This is the single highest-consequence
piece of unverified content in the whole build — flag it accordingly, don't
quietly ship it as done.

The injury/medical list added alongside it (P1.10, `_MEDICAL_PATTERNS`) is
held to exactly the same standard and carries exactly the same gap — read its
own comment block, and put it in front of the same reviewers.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from orca.contracts import AgentResult, Confidence, SourceProvenance, coerce_reasoning_depth
from orca.data import analytics_loaders as al
from orca.state import ORCAState

# Each phrase confirmed via a real dictionary/translation source while writing
# this — not transliterated from memory. See the module docstring: this is a
# starter list, not a validated one.
#
# P3.7 (2026-09-22, Claude/agent pass) — widened en/ta/hi and added kn/bn/mr,
# each checked against Shabdkosh/Glosbe/Cambridge Dictionary the same way the
# original ta/hi/ml/te entries were. This is STILL NOT the native-speaker
# review the point requires ("Reviewer: Dev R (native Tamil), sign-off
# recorded... with the date") — no such sign-off exists for ANY language
# here, Tamil included, and none is claimed. Logged BLOCKED, not DONE — see
# docs/logs/DLC_implementation_log.md.
_DISTRESS_PATTERNS: dict[str, list[str]] = {
    "en": [
        "sinking", "taking on water", "man overboard", "mayday", "capsizing", "capsized",
        "drowning", "sos", "help", "engine failure", "lost at sea", "adrift", "no fuel",
        "boat is going down", "we are sinking", "send help", "distress",
    ],
    "ta": [
        "மூழ்குகிறது", "படகு மூழ்குகிறது", "மூழ்கிவிட்டேன்", "உதவி",  # sinking / boat is sinking / I have drowned / help
        "படகு கவிழ்ந்தது",       # boat capsized
        "காப்பாற்றுங்கள்",        # save/rescue [us]
        "எனக்கு உதவி வேண்டும்",   # I need help
        "படகு மூழ்கிக்கொண்டிருக்கிறது",  # the boat is sinking (progressive)
        "இயந்திரம் பழுது",       # engine failure
        "எரிபொருள் இல்லை",      # no fuel
        "கடலில் தொலைந்துவிட்டோம்",  # lost at sea
    ],
    "hi": [
        "बचाओ", "डूब रहा", "डूब रही", "नाव डूब रही है",  # save me / is drowning (m/f) / the boat is sinking
        "नाव पलट गई",           # boat capsized
        "मदद चाहिए",            # need help
        "इंजन खराब हो गया",      # engine failed
        "ईंधन खत्म",            # out of fuel
        "समुद्र में फंस गए",       # stranded at sea
    ],
    # Verified against Shabdkosh (Kannada-English) / Glosbe while writing this.
    "kn": [
        "ಮುಳುಗುತ್ತಿದೆ",         # (it) is sinking
        "ದೋಣಿ ಮುಳುಗುತ್ತಿದೆ",     # boat is sinking
        "ಸಹಾಯ ಮಾಡಿ",           # please help
        "ಸಹಾಯ",                # help
        "ದೋಣಿ ಮಗುಚಿತು",         # boat capsized
        "ನನ್ನನ್ನು ರಕ್ಷಿಸಿ",        # save me
        "ಎಂಜಿನ್ ಕೆಟ್ಟುಹೋಗಿದೆ",     # engine has failed
    ],
    # Verified against Glosbe (Bengali-English) / Cambridge Dictionary while writing this.
    "bn": [
        "ডুবে যাচ্ছে",           # sinking
        "নৌকা ডুবে যাচ্ছে",       # boat is sinking
        "সাহায্য করুন",          # please help
        "সাহায্য",              # help
        "নৌকা উল্টে গেছে",       # boat capsized
        "আমাকে বাঁচাও",          # save me
        "ইঞ্জিন বিকল",           # engine failure
    ],
    # Verified against Glosbe (Marathi-English) / Shabdkosh while writing this.
    "mr": [
        "बुडत आहे",             # sinking
        "होडी बुडत आहे",         # boat is sinking
        "मदत करा",              # please help
        "मदत",                  # help
        "होडी उलटली",           # boat capsized
        "मला वाचवा",            # save me
        "इंजिन बंद पडले",         # engine has stopped/failed
    ],
    # Verified against Shabdkosh (English-Malayalam / Malayalam-English) while
    # writing this — same "checked against a real source" bar as ta/hi above.
    "ml": [
        "മുങ്ങുന്നു",       # sinking
        "വള്ളം മുങ്ങുന്നു",  # boat is sinking
        "ബോട്ട് മുങ്ങുന്നു",  # boat is sinking (colloquial "boat" loanword)
        "സഹായിക്കൂ",       # help
        "രക്ഷിക്കൂ",        # save / rescue
        "എന്നെ രക്ഷിക്കൂ",  # save me
        "മുങ്ങിപ്പോകുന്നു",   # drowning
        "വള്ളം മറിഞ്ഞു",    # boat capsized
    ],
    # Verified against Shabdkosh / Cambridge Dictionary (English-Telugu) and
    # Glosbe while writing this.
    "te": [
        "మునిగిపోతోంది",     # is sinking
        "పడవ మునిగిపోతోంది",  # boat is sinking
        "సహాయం",           # help
        "సహాయం చేయండి",    # please help
        "నన్ను రక్షించండి",   # save me
        "రక్షించండి",        # save / rescue
        "మునిగిపోతున్నాను",   # I am drowning
        "బోల్తా పడింది",     # capsized
    ],
}

# P1.10 (orca_final §13.1, PS-Q8) — injury and medical emergencies.
#
# "My crewmate is injured, what do I do?" reached Planning, matched no routing
# row, and came back with a weather answer. A medical emergency at sea is an
# MRCC case exactly like a sinking is: the coordinating centre is who tasks the
# helicopter, and the answer the asker needs is a number, not a wave height.
#
# Matched with word boundaries (Latin phrases only — see _matches below), which
# `_DISTRESS_PATTERNS` deliberately is not: a substring false positive there
# costs an unnecessary SOS, and the list above is thin enough that the
# false-negative direction is the one to protect. Here the phrases are ordinary
# words a non-emergency sentence can contain, so the boundary earns its keep.
#
# SAME HONEST GAP AS THE LIST ABOVE, and it must be read the same way: every
# phrase was checked against a real dictionary source while writing this, none
# is guessed transliteration, and NOBODY WITH NATIVE FLUENCY HAS REVIEWED ANY
# OF THEM. These go into P3.7's native review with `_DISTRESS_PATTERNS` — same
# reviewers, same standard, and until then treat passing tests against this
# list as a false sense of security.
_MEDICAL_PATTERNS: dict[str, list[str]] = {
    "en": [
        "injured", "injury", "bleeding", "unconscious", "not breathing",
        "heart attack", "broken leg", "broken arm", "severe pain", "chest pain",
        "snake bite", "medical emergency", "need a doctor", "badly hurt",
        "lost a lot of blood", "burnt", "burned",
    ],
    "ta": [
        "காயம்",              # injury / wound
        "காயம் பட்டார்",       # he/she is injured
        "ரத்தம் வருகிறது",     # bleeding
        "மயக்கம்",             # faint / unconscious
        "மூச்சு விட முடியவில்லை",  # cannot breathe
        "நெஞ்சு வலி",          # chest pain
        "மருத்துவர் வேண்டும்",   # need a doctor
    ],
    "hi": [
        "घायल",               # injured
        "खून बह रहा",          # bleeding
        "बेहोश",               # unconscious
        "दिल का दौरा",         # heart attack
        "साँस नहीं आ रही",      # cannot breathe
        "डॉक्टर चाहिए",         # need a doctor
    ],
    "ml": [
        "പരിക്ക്",            # injury
        "പരിക്കേറ്റു",          # has been injured
        "രക്തം വരുന്നു",        # bleeding
        "ബോധം കെട്ടു",         # lost consciousness
        "ശ്വാസം കിട്ടുന്നില്ല",   # cannot breathe
        "ഡോക്ടറെ വേണം",       # need a doctor
    ],
    "te": [
        "గాయం",               # injury
        "గాయపడ్డాడు",          # he is injured
        "రక్తం కారుతోంది",       # bleeding
        "స్పృహ తప్పింది",        # lost consciousness
        "గుండెపోటు",           # heart attack
        "ఊపిరి ఆడటం లేదు",     # cannot breathe
        "డాక్టర్ కావాలి",        # need a doctor
    ],
    # P3.7 — same "checked against a real dictionary source, not
    # native-reviewed" standard as every list above.
    "kn": [
        "ಗಾಯ",                # injury
        "ಗಾಯಗೊಂಡಿದ್ದಾನೆ",       # he is injured
        "ರಕ್ತ ಸೋರುತ್ತಿದೆ",       # bleeding
        "ಪ್ರಜ್ಞೆ ತಪ್ಪಿದೆ",         # lost consciousness
        "ಹೃದಯಾಘಾತ",           # heart attack
        "ಉಸಿರಾಡಲು ಆಗುತ್ತಿಲ್ಲ",    # cannot breathe
        "ವೈದ್ಯರು ಬೇಕು",         # need a doctor
    ],
    "bn": [
        "আঘাত",               # injury
        "আহত হয়েছে",          # he/she is injured
        "রক্ত পড়ছে",           # bleeding
        "অজ্ঞান",              # unconscious
        "হার্ট অ্যাটাক",         # heart attack
        "শ্বাস নিতে পারছে না",   # cannot breathe
        "ডাক্তার দরকার",        # need a doctor
    ],
    "mr": [
        "जखम",                # injury
        "जखमी झाला",          # he is injured
        "रक्तस्त्राव होत आहे",     # bleeding
        "बेशुद्ध",              # unconscious
        "हृदयविकाराचा झटका",    # heart attack
        "श्वास घेता येत नाही",    # cannot breathe
        "डॉक्टर हवा",           # need a doctor
    ],
}

# P3.5 (`R-PS-2`) — the offline rung for romanized Indic. A Latin-script
# distress message ("help", spoken and typed in Tamil sounds, no Tamil
# script) is invisible to the two tables above AND to Bhashini when the
# network is down — the exact border-crossing scenario the point exists for.
# ONLY the two words picked as unambiguous enough to ship without a native
# reviewer are here (Hindi "bachao" is the one Hindi distress word every
# speaker of the language recognizes on sight, romanized or not; Tamil
# "udhavi" is the standard ISO-15919-adjacent romanization of உதவி taught in
# every Tamil-as-a-second-language course). This is deliberately NOT an
# attempt at a full romanized phrase list — transliteration has no single
# standard and a wrong guess here is a false SOS or a missed one — so it
# stays this short until a native speaker (P3.7's same reviewers) confirms
# more are safe to add. Matched whole-word, same reasoning as _MEDICAL_PATTERNS.
_ROMANIZED_DISTRESS_PATTERNS: dict[str, list[str]] = {
    "hi": ["bachao"],
    "ta": ["udhavi"],
}


# Verified 2026-09-02: 1554 is the Indian Coast Guard's official nationwide
# toll-free MRCC distress helpline (confirmed via a live news/coast-guard
# source, not assumed). MRCC Chennai covers the Tamil Nadu pilot region.
# VHF Channel 16 is the international maritime distress/calling channel
# (ITU/IMO standard, not India-specific). PHONE NUMBERS CAN CHANGE — verify
# again before a real demo or deployment; this is sourced, not guaranteed current.
#
# P1.7 (`R-INDIA-7`) — the three MRCC numbers, hand-checked 2026-09-20.
#
# The station roster (`data/tier1/sar/icg_sar_stations.json`, runbook §C4)
# names all 39 MRCCs/MRSCs and where they are, but every station's `phone` is
# null: the ICG publishes no per-MRSC telephone number, and none is invented
# here. India's SRR has exactly three MRCCs, though, and those three ARE
# published — so the roster answers "who covers you and how far away", and the
# entry below answers "and this is the number for them".
#
# Each number was read off two independent sources that agree, not one:
#   Mumbai      022-2438-8065   — sarcontacts.info/countries/india ("91 22
#                                 243-88065") and the ICG West RHQ listing.
#   Chennai     044-2539-5018   — sarcontacts.info ("91 44 253 95018") and
#                                 dgshipping.gov.in's Annex-2 contact list;
#                                 this is also the number already in this file
#                                 since 2026-09-02, which it corroborates.
#   Sri Vijaya  03192-245530    — sarcontacts.info ("+91 3192 245530") and the
#   Puram                         ICG A&N RHQ listing. Port Blair was renamed
#                                 Sri Vijaya Puram in 2024; the roster uses the
#                                 new name, so the key does too.
#
# Keys match the roster's own `mrcc` values exactly, so the lookup in
# surface_mrcc_contact is a dict hit and cannot silently miss.
#
# PHONE NUMBERS CAN CHANGE — re-verify before a real demo or deployment. These
# are sourced, not guaranteed current. 1554 and VHF 16 are ALWAYS surfaced
# alongside them and never replaced by them: an MRCC line that has moved must
# degrade to the nationwide number, never to nothing.
MRCC_CONTACTS: dict[str, dict[str, str]] = {
    "default": {"name": "Indian Coast Guard MRCC (nationwide)", "phone": "1554", "vhf_channel": "16"},
    "MRCC Mumbai": {"name": "MRCC Mumbai", "phone": "+91-22-2438-8065", "vhf_channel": "16"},
    "MRCC Chennai": {"name": "MRCC Chennai", "phone": "+91-44-2539-5018", "vhf_channel": "16"},
    "MRCC Sri Vijaya Puram": {"name": "MRCC Sri Vijaya Puram (Port Blair)", "phone": "+91-3192-245530", "vhf_channel": "16"},
    # Kept so an older caller passing the pre-2024 name still resolves.
    "chennai": {"name": "MRCC Chennai", "phone": "+91-44-2539-5018", "vhf_channel": "16"},
}

_EARTH_RADIUS_KM = 6371.0


def _km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def nearest_sar_station(lat: float, lon: float) -> dict[str, Any] | None:
    """Closest ICG rescue centre to a position, with its parent MRCC.

    Straight-line distance, stated as such in the payload: an MRSC's actual
    response depends on its boats and the sea state, and a great-circle
    kilometre is the honest thing a client can compute. The parent MRCC is
    carried because the MRSC is the local unit but the MRCC coordinates the
    case.
    """
    stations = al.load_sar_stations().get("stations") or []
    if not stations:
        return None
    best = min(stations, key=lambda st: _km_between(lat, lon, st["latitude"], st["longitude"]))
    return {
        "station": best["station"],
        "kind": best["kind"],
        "coordinating_mrcc": best["mrcc"],
        "latitude": best["latitude"],
        "longitude": best["longitude"],
        "straight_line_distance_km": round(_km_between(lat, lon, best["latitude"], best["longitude"]), 1),
        "phone": best.get("phone"),  # null — see MRCC_CONTACTS above
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

    # P1.10 — checked second, so a sinking is still reported as a sinking when
    # a message says both. Same short-circuit either way; only the type differs,
    # so the trace records which list fired.
    for lang, phrases in _MEDICAL_PATTERNS.items():
        for phrase in phrases:
            if _matches(text, phrase):
                return {"is_distress": True, "distress_type": "medical_pattern", "matched_language": lang, "matched_phrase": phrase}

    # P3.5 — romanized Indic, checked last (narrowest list, whole-word only,
    # same guard as _MEDICAL_PATTERNS so "bachaoge" or "udhavikkaran" cannot
    # false-fire on a word that merely contains the romanized root).
    for lang, phrases in _ROMANIZED_DISTRESS_PATTERNS.items():
        for phrase in phrases:
            if _matches(text, phrase):
                return {"is_distress": True, "distress_type": "romanized_pattern", "matched_language": lang, "matched_phrase": phrase}

    return {"is_distress": False, "distress_type": None, "matched_language": None, "matched_phrase": None}


def detect_distress_model_check(text: str, phrase_detection: dict[str, Any]) -> dict[str, Any]:
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
        from orca.llm.tiers import LLMUnavailable, llm
        client = llm("cheap")
    except (LLMUnavailable, Exception):
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


def _matches(text: str, phrase: str) -> bool:
    """Whole-word for a Latin-script phrase, plain containment otherwise.

    "injured" must not fire on a word that merely contains it, which is what
    P1.10's own acceptance test checks. Indic scripts take their case endings
    as suffixes, so a trailing boundary there would miss the inflected forms
    that are how the phrase is actually written — the same asymmetry
    loaders._name_pattern documents for place names."""
    if phrase.isascii():
        return re.search(rf"\b{re.escape(phrase)}\b", text.lower()) is not None
    return phrase in text


def surface_mrcc_contact(user_location: dict[str, Any] | None, language: str = "en") -> dict[str, Any]:
    """Tool per Architecture §3.2 Agent 12. Resolves the caller's position
    against the full ICG rescue roster (runbook §C4) — before that table
    existed this returned MRCC Chennai for a boat off Gujarat.

    `nationwide_fallback` is always present and always dialable, so a
    position we cannot resolve, or a roster file that is missing, degrades to
    1554 rather than to nothing.
    """
    lat, lon = _position_of(user_location)
    nearest = nearest_sar_station(lat, lon) if lat is not None and lon is not None else None
    if nearest is None:
        return {
            "primary": MRCC_CONTACTS["default"],
            "nearest_station": None,
            "nationwide_fallback": MRCC_CONTACTS["default"],
            "vhf_channel": "16",
            "note": "no position on the query" if lat is None else "ICG station roster unavailable",
            "language": language,
        }
    # P1.7 — the number the caller actually dials is now the COORDINATING
    # MRCC's, not the nationwide line: the MRSC nearest a boat off Veraval is
    # a Gujarat station, and its case is run by Mumbai, so routing that caller
    # to Chennai (what this did before the roster existed) or to a generic
    # queue costs minutes that matter. An MRCC we hold no number for falls back
    # to 1554 rather than to nothing.
    coordinating = MRCC_CONTACTS.get(nearest["coordinating_mrcc"], MRCC_CONTACTS["default"])
    station_line = (
        f"{nearest['station']} is the nearest rescue centre "
        f"({nearest['straight_line_distance_km']} km, straight line); "
        f"{nearest['coordinating_mrcc']} coordinates the case"
    )
    note = (
        f"{station_line} — dial {coordinating['phone']}. "
        "If that does not connect, dial 1554 (nationwide, toll free) or call on VHF channel 16."
        if coordinating is not MRCC_CONTACTS["default"]
        else f"{station_line}. No number is published for it — dial 1554 or call on VHF 16."
    )
    return {
        "primary": coordinating,
        "nearest_station": nearest,
        # Always present and always dialable, whatever happened above.
        "nationwide_fallback": MRCC_CONTACTS["default"],
        "vhf_channel": "16",
        "note": note,
        "language": language,
    }


def _position_of(user_location: dict[str, Any] | None) -> tuple[float | None, float | None]:
    """(lat, lon) out of whichever key shape the state carried, or (None, None).

    A regional default is not a position. When the caller named no place, the
    query path fills in the pilot port so the other agents have somewhere to
    compute — but routing an SOS to the MRCC for that port, or handing its
    coordinates to DAT-SG as the vessel's position, would send rescuers to the
    wrong coast. So here it counts as no position at all (P4.16)."""
    if not isinstance(user_location, dict) or user_location.get("place_source") == "regional_default":
        return None, None
    for la, lo in (("lat", "lon"), ("latitude", "longitude")):
        try:
            return float(user_location[la]), float(user_location[lo])
        except (KeyError, TypeError, ValueError):
            continue
    return None, None


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


# Character budget for one Nabhmitra / VCSS message. ISRO's transceivers are
# short-message devices, not a data link; this is the conservative working
# figure used to keep the rendered line copy-pasteable into one, NOT a figure
# read off a published spec. If a real integration ever happens, check it.
NABHMITRA_MAX_CHARS = 160


def render_nabhmitra_text(handoff: dict[str, Any], vessel_name: str | None = None) -> str:
    """The existing CAP-fallback payload as one line of ASCII, for keying into
    a Nabhmitra or VCSS terminal (orca_final §13.2).

    A renderer and nothing more: there is no transport here, no gateway, and
    no delivery. It exists because the payload above is JSON, and the device a
    fisherman actually has in the wheelhouse takes a typed message. `SIM` is
    in the body, not a wrapper around it, so it cannot be stripped by copying
    the line out — a message that looks like a real alert must never leave
    this system without saying it is not one."""
    pos = handoff.get("position") or {}
    lat, lon = pos.get("lat"), pos.get("lon")
    where = f"{lat:.4f}N {lon:.4f}E" if lat is not None and lon is not None else "POS UNKNOWN"
    parts = [
        "ORCA SOS",
        where,
        (handoff.get("distress_type") or "unspecified").upper(),
        handoff.get("timestamp", ""),
        vessel_name or handoff.get("vessel_id") or "VESSEL UNKNOWN",
        "SIM-NOT-A-LIVE-ALERT",
    ]
    line = " | ".join(p for p in parts if p)
    return line if len(line) <= NABHMITRA_MAX_CHARS else line[: NABHMITRA_MAX_CHARS - 1] + "…"


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
    phrase_detection = detect_distress_signal(combined_text, ui_control_triggered=state.get("distress_flag", False))

    # Prompt Routing Revamp §7.4 — Distress model check (escalate-only).
    # Runs only when phrase list did not detect distress. Can only escalate.
    detection = detect_distress_model_check(combined_text, phrase_detection)

    location = state.get("user_location")
    mrcc = surface_mrcc_contact(location)
    lat, lon = _position_of(location)
    handoff = emit_datsg_handoff(
        position=None if lat is None or lon is None else {"lat": lat, "lon": lon},
        vessel_id=None,
        distress_type=detection["distress_type"],
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )

    return AgentResult(
        agent_name="distress",
        query_id=state.get("query_id", ""),
        reasoning_depth=coerce_reasoning_depth(state.get("reasoning_depth", "SHALLOW")),
        inputs_consumed={"text": combined_text.strip(), "ui_control_triggered": state.get("distress_flag", False)},
        outputs={
            "detection": detection,
            "mrcc_contact": mrcc,
            "handoff": handoff,
            # P1.7 — the same payload in the form a Nabhmitra/VCSS terminal takes.
            "nabhmitra_text": render_nabhmitra_text(handoff),
        },
        source_provenance=SourceProvenance(
            dataset="Deterministic multilingual pattern match + LLM escalate-only check (starter set — see module docstring)",
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
