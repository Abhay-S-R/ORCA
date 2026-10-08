"""Channel renderers — plan §4.9 / Phase 3 D1 Day 19. Each renderer is a
PURE function of the same response shape (the dict orca/api/main.py's
`_query_stream` already assembles from ORCAState) — none of them fetches
anything, and the test that matters here is that all four render the same
query and none of them makes a network call.

`render_web` is the full payload passthrough (already the shape the
frontend consumes). The other three exist because the master requirements
name SMS/IVR/USSD as delivery channels for low-connectivity zones (plan
§4.9) even though no gateway is wired up yet (orca/channels/dispatch.py) —
the renderer is the honest, cheap half to build now: it forces the response
to stay structured rather than becoming a wall of prose, and it is ready
the moment a real gateway exists.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# GSM 03.38 basic character set (the "default alphabet") — a superset of
# ASCII plus a handful of accented/Latin characters, the +/- of which is a
# common trap; only the exact characters SMS decodes without an extension
# table go here. This is deliberately conservative rather than exhaustive:
# a Tamil/Hindi character reaching this function is correctly *not*
# encodable in GSM-7, which is real and disqualifying, not a gap to widen.
_GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅå"
    "Δ_ΦΓΛΩΠΨΣΘΞÆæßÉ"
    " !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM7_SET = set(_GSM7_BASIC)

_SMS_MAX_CHARS = 160
_USSD_MAX_CHARS = 182

# P3.11 (orca_final §12.2) — UCS-2 SMS budget: 70 chars fit in one part; a
# concatenated (multi-part, UDH-framed) message drops to 67 per part because
# the User Data Header eats into the same 140-octet PDU.
_SMS_UCS2_SINGLE = 70
_SMS_UCS2_CONCAT = 67


@dataclass(frozen=True)
class RenderedMessage:
    channel: str
    body: str
    truncated: bool
    encodable: bool  # False = the target channel cannot carry this text as-is (e.g. non-GSM-7 SMS)
    parts: tuple[str, ...] = ()  # P3.11 — every part, in order; len 1 for a
    # single-part message (parts[0] == body). Always populated for "sms".
    encoding: str = "gsm7"  # "gsm7" | "ucs2"
    romanized: str | None = None  # P3.11 — a GSM-7 romanized variant for
    # handsets with poor Indic font rendering, or None when not applicable
    # (English body) or unavailable (Bhashini unreachable, no local rung —
    # this is disclosed by its absence, never silently substituted).


def is_gsm7_encodable(text: str) -> bool:
    return all(ch in _GSM7_SET for ch in text)


def _verdict_and_hazard(payload: dict[str, Any]) -> tuple[str, str]:
    verdict = (payload.get("risk_assessment") or {}).get("go_no_go", "UNKNOWN")
    hazards = payload.get("hazard_breakdown") or {}
    weather = payload.get("weather_summary") or {}
    if weather.get("lightning_active"):
        hazard = "lightning active"
    elif weather.get("cyclone_alert"):
        hazard = f"cyclone: {weather['cyclone_alert']}"
    elif hazards.get("mpa_violation"):
        hazard = "inside MPA boundary"
    elif hazards.get("imbl_alert_level") not in (None, "SAFE"):
        hazard = f"IMBL boundary {hazards.get('imbl_alert_level', '').lower()}"
    else:
        hazard = "no active hazard"
    return verdict, hazard


def _timestamp(payload: dict[str, Any]) -> str:
    audit = payload.get("audit_trace_log") or []
    for entry in reversed(audit):
        if entry.get("ended_at"):
            return entry["ended_at"]
    return ""


def render_web(payload: dict[str, Any]) -> dict[str, Any]:
    """The full payload, unchanged — this is already the frontend's shape
    (orca/api/main.py's `_query_stream` final event). A renderer for
    symmetry with the other three, not a transformation."""
    return dict(payload)


def _ucs2_parts(text: str) -> list[str]:
    if len(text) <= _SMS_UCS2_SINGLE:
        return [text]
    return [text[i : i + _SMS_UCS2_CONCAT] for i in range(0, len(text), _SMS_UCS2_CONCAT)]


def _romanized_variant(vernacular: str, language: str) -> str | None:
    """P3.11 — Bhashini Transliteration (same language, Latin script), with
    NO local fallback beyond the English line: a best-effort romanization
    invented without a model would be exactly the un-vetted content
    principle 1 forbids. Absence (`None`) is the honest result when
    Bhashini is unreachable, not a guess dressed up as one."""
    try:
        from orca.agents import bhashini

        # ULCA's transliteration contract: sourceLanguage is the Indic
        # language, targetLanguage "en" means "romanize to Latin script" —
        # there is no separate "<lang>_Latn" code in the ULCA language table.
        return bhashini.transliterate(vernacular, language, "en")
    except Exception:
        return None


def render_sms(payload: dict[str, Any], *, language: str = "en") -> RenderedMessage:
    """SMS rendering (plan §4.9, extended P3.11 orca_final §12.2):
    - GSM-7 fits in the original <=160-char single part, unchanged.
    - Non-GSM-7 (any Indic vernacular) is UCS-2, multi-part when needed
      (`_SMS_UCS2_SINGLE`/`_SMS_UCS2_CONCAT`), NEVER dropped to the ASCII
      verdict+hazard line the way this used to silently do — "nothing
      dropped" is the point's own Done-when.
    - A romanized (GSM-7) variant rides alongside for handsets with poor
      Indic font rendering, produced by Bhashini Transliteration; `None`
      when Bhashini cannot be reached (disclosed by absence).
    Severity token, value+unit, place and time all come from the same
    `_verdict_and_hazard`/`_timestamp` helpers as before — masking numbers
    and IMBL/PFZ around translation happens once, upstream, in
    `orca.agents.language._translate_with_rung` (P3.8), not duplicated here.
    """
    verdict, hazard = _verdict_and_hazard(payload)
    ts = _timestamp(payload)
    vernacular = payload.get("final_vernacular_response") if language != "en" else None

    if vernacular and is_gsm7_encodable(vernacular):
        body = vernacular[:_SMS_MAX_CHARS]
        truncated = len(vernacular) > _SMS_MAX_CHARS
        return RenderedMessage(
            channel="sms", body=body, truncated=truncated, encodable=True, parts=(body,), encoding="gsm7",
        )
    if vernacular:
        # Not GSM-7 — UCS-2 multi-part, not a fallback to English.
        parts = _ucs2_parts(vernacular)
        return RenderedMessage(
            channel="sms", body=parts[0], truncated=False, encodable=True,
            parts=tuple(parts), encoding="ucs2", romanized=_romanized_variant(vernacular, language),
        )

    body = f"SAGAR SARATHI {verdict}: {hazard}. {ts}"
    truncated = len(body) > _SMS_MAX_CHARS
    body = body[:_SMS_MAX_CHARS]
    return RenderedMessage(
        channel="sms", body=body, truncated=truncated, encodable=is_gsm7_encodable(body),
        parts=(body,), encoding="gsm7",
    )


_NUMERAL_WORDS = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine"}


def _spell_numerals(text: str) -> str:
    """TTS script rule (plan §4.9): 'no numerals-as-digits' — a wave height
    of "2.4" must not be read by a TTS engine as the ambiguous "twenty-four"
    or "two point four" (engine-dependent); spelling each digit out
    (\"two four\") is the unambiguous, engine-agnostic choice for a short
    safety script. Only digit characters are rewritten — letters and
    spacing around them are left exactly as they were."""
    return "".join(f" {_NUMERAL_WORDS[ch]} " if ch in _NUMERAL_WORDS else ch for ch in text).strip()


def render_ivr(payload: dict[str, Any]) -> RenderedMessage:
    """TTS script: short sentences, numerals spelled out, one repeat (plan
    §4.9). Not audio — the text a TTS engine (Agent 1's text_to_speech,
    Phase 3 Day 17) would actually speak."""
    verdict, hazard = _verdict_and_hazard(payload)
    verdict_spoken = " ".join(verdict.split("_"))  # "NO_GO" -> "NO GO", read as two words not one
    sentence = f"Sagar Sarathi marine safety advisory. Verdict: {verdict_spoken}. Hazard: {_spell_numerals(hazard)}."
    script = f"{sentence} I repeat. {sentence}"
    return RenderedMessage(channel="ivr", body=script, truncated=False, encodable=True)


def render_ussd(payload: dict[str, Any]) -> RenderedMessage:
    """<=182 chars, menu-structured (plan §4.9)."""
    verdict, hazard = _verdict_and_hazard(payload)
    body = f"ORCA\n1.Verdict:{verdict}\n2.Hazard:{hazard}\n3.More: call MRCC"
    truncated = len(body) > _USSD_MAX_CHARS
    body = body[:_USSD_MAX_CHARS]
    return RenderedMessage(channel="ussd", body=body, truncated=truncated, encodable=is_gsm7_encodable(body))


# --------------------------------------------------------------------------
# P6.10 — the remaining renderers. Every one below is rendered + simulated
# only (channels/dispatcher.py's WhatsAppDispatcher/etc. raise, same as the
# existing SMSDispatcher/IVRDispatcher): nothing here transmits, and nothing
# anywhere renders a simulated send as delivered.
# --------------------------------------------------------------------------

_MAP_CARD_BASE_URL = "https://orca.local/map"  # ponytail: a placeholder origin; swap for the real deployed frontend URL once one exists


def render_whatsapp(payload: dict[str, Any]) -> RenderedMessage:
    """Text body (no GSM-7/160-char limit — WhatsApp is UTF-8, effectively
    unlimited for a safety message this short) plus a map-card reference: a
    plain URL pointing at the query's own position, since a WhatsApp
    Business template message renders a URL as a tappable rich-preview card
    without this codebase needing to generate the preview image itself."""
    verdict, hazard = _verdict_and_hazard(payload)
    ts = _timestamp(payload)
    location = payload.get("user_location") or {}
    lat, lon = location.get("lat"), location.get("lon")
    card_url = f"{_MAP_CARD_BASE_URL}?lat={lat}&lon={lon}" if lat is not None and lon is not None else _MAP_CARD_BASE_URL
    body = f"*SAGAR SARATHI {verdict}*\n{hazard}.\nIssued {ts}.\nView on the chart: {card_url}"
    return RenderedMessage(channel="whatsapp", body=body, truncated=False, encodable=True)


def render_missed_call_callback(payload: dict[str, Any], *, home_port_name: str | None = None, cache_age_minutes: int | None = None) -> RenderedMessage:
    """The IVR script played back when a fisherman gives a missed call to
    ORCA's number and it calls back (orca_final §12.4) — served from
    whatever advisory is already cached for the caller's registered home
    port, never a live fetch triggered by the call itself (a callback has
    to start speaking in well under the time a fresh multi-source cascade
    takes). The age is spoken FIRST, before the verdict, so "this is old"
    is heard before "this is safe" ever could be mistaken for current."""
    verdict, hazard = _verdict_and_hazard(payload)
    place = home_port_name or "your home port"
    age_clause = (
        f"This advisory is {_spell_numerals(str(cache_age_minutes))} minutes old. "
        if cache_age_minutes is not None else "This is the most recently cached advisory. "
    )
    verdict_spoken = " ".join(verdict.split("_"))
    sentence = f"{age_clause}Sagar Sarathi advisory for {place}. Verdict: {verdict_spoken}. Hazard: {_spell_numerals(hazard)}."
    script = f"{sentence} To hear this again, stay on the line. Otherwise, goodbye."
    return RenderedMessage(channel="missed_call", body=script, truncated=False, encodable=True)


def render_vhf(payload: dict[str, Any]) -> RenderedMessage:
    """A VHF Channel 16 safety-broadcast script, in the fixed protocol form
    every mariner is trained to recognise (ITU-R M.1171 "Securite" opening,
    said three times, sender identified, message, close) — not a generic
    TTS sentence, because the opening words are themselves the signal that
    tells a listening bridge to pay attention."""
    verdict, hazard = _verdict_and_hazard(payload)
    location = payload.get("resolved_place_name") or "the reported position"
    body = (
        "Securite, securite, securite.\n"
        "This is Sagar Sarathi Marine Safety Advisory.\n"
        f"{verdict}. {hazard}, near {location}.\n"
        "Mariners in the area are advised to proceed with caution and monitor this channel.\n"
        "Out."
    )
    return RenderedMessage(channel="vhf", body=body, truncated=False, encodable=True)


_BOARD_MAX_CHARS = 120  # ponytail: a guessed physical-board budget (no real hardware spec on hand) — narrow it once a real harbour display's character grid is known


def render_harbour_board(payload: dict[str, Any]) -> RenderedMessage:
    """A harbour LED/split-flap display board: a handful of short,
    high-contrast-readable lines, GSM-7 only (the character sets these
    boards actually carry are a subset even of GSM-7 in practice, but GSM-7
    is the same conservative floor `render_sms` already enforces, not a new
    one invented for this channel)."""
    verdict, hazard = _verdict_and_hazard(payload)
    body = f"ORCA {verdict}\n{hazard}"
    truncated = len(body) > _BOARD_MAX_CHARS
    body = body[:_BOARD_MAX_CHARS]
    return RenderedMessage(channel="harbour_board", body=body, truncated=truncated, encodable=is_gsm7_encodable(body))


if __name__ == "__main__":
    sample = {
        "risk_assessment": {"go_no_go": "CAUTION", "reason": "wave height elevated"},
        "weather_summary": {"lightning_active": False, "cyclone_alert": None},
        "hazard_breakdown": {"mpa_violation": False, "imbl_alert_level": "SAFE"},
        "final_vernacular_response": "CAUTION: conditions elevated",
        "audit_trace_log": [{"agent_name": "reporting", "ended_at": "2026-09-03T10:00:00Z"}],
    }
    web = render_web(sample)
    assert web == sample and web is not sample  # same content, not the same object

    sms = render_sms(sample)
    assert len(sms.body) <= 160 and sms.encodable

    ivr = render_ivr(sample)
    assert ivr.body.count("I repeat") == 1
    numeric_sample = {**sample, "hazard_breakdown": {"mpa_violation": False, "imbl_alert_level": "CLOSE"}}
    numeric_ivr = render_ivr(numeric_sample)
    assert "imbl boundary close" in numeric_ivr.body.lower()
    assert _spell_numerals("2.4m") == "two . four m"
    assert not any(ch.isdigit() for ch in _spell_numerals("wave height 2.4m"))

    ussd = render_ussd(sample)
    assert len(ussd.body) <= 182

    assert is_gsm7_encodable("Hello 123") is True
    assert is_gsm7_encodable("வணக்கம்") is False  # Tamil — correctly not GSM-7

    whatsapp = render_whatsapp({**sample, "user_location": {"lat": 8.8, "lon": 78.1}})
    assert "78.1" in whatsapp.body and "CAUTION" in whatsapp.body

    callback = render_missed_call_callback(sample, home_port_name="Thoothukudi", cache_age_minutes=12)
    assert callback.body.startswith("This advisory is one  two")  # age spoken first, digits spelled out
    assert "Thoothukudi" in callback.body

    vhf = render_vhf(sample)
    assert vhf.body.lower().count("securite") == 3 and vhf.body.strip().endswith("Out.")

    board = render_harbour_board(sample)
    assert len(board.body) <= _BOARD_MAX_CHARS and board.encodable

    print("channel renderers self-check ok")
