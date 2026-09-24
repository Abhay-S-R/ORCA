"""CAP 1.2 (Common Alerting Protocol, OASIS) XML generation from an ORCA
alert, plus the four-channel broadcast preview.

stdlib xml.etree only — a CAP message is ~15 elements; a templating library
or a CAP SDK would be rung-1 over-engineering. The element order and the
required children follow the OASIS CAP 1.2 spec (alert > info > area).

The four-channel preview reuses D1's channel renderers when they exist
(orca.agents.reporting.render_web / render_sms / render_ivr / render_ussd);
until then it falls back to the minimal renderers below so /ops is testable
and demoable now. Swap point marked TODO(D1).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

CAP_NS = "urn:oasis:names:tc:emergency:cap:1.2"

_SEVERITY_TO_CAP = {
    "info": ("Minor", "Advisory"),
    "advisory": ("Moderate", "Advisory"),
    "warning": ("Severe", "Warning"),
    "danger": ("Extreme", "Warning"),
}


def _iso(dt: datetime) -> str:
    # CAP wants an offset, not a 'Z'.
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "+00:00")


def _add_info_block(
    alert: ET.Element,
    *,
    language: str,
    event: str,
    severity: str,
    headline: str,
    description: str,
    instruction: str,
    area_desc: str,
    polygon: list[tuple[float, float]] | None,
    circle: tuple[float, float, float] | None,
) -> None:
    cap_severity, _ = _SEVERITY_TO_CAP.get(severity, ("Severe", "Warning"))
    info = ET.SubElement(alert, "info")
    ET.SubElement(info, "language").text = language
    ET.SubElement(info, "category").text = "Met"
    ET.SubElement(info, "event").text = event
    ET.SubElement(info, "urgency").text = "Expected"
    ET.SubElement(info, "severity").text = cap_severity
    ET.SubElement(info, "certainty").text = "Likely"
    ET.SubElement(info, "headline").text = headline
    ET.SubElement(info, "description").text = description
    ET.SubElement(info, "instruction").text = instruction

    area = ET.SubElement(info, "area")
    ET.SubElement(area, "areaDesc").text = area_desc
    if polygon:
        # CAP polygon: space-separated "lat,lon" pairs, first == last.
        pts = list(polygon)
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        ET.SubElement(area, "polygon").text = " ".join(f"{lat},{lon}" for lat, lon in pts)
    if circle:
        lat, lon, radius_km = circle
        ET.SubElement(area, "circle").text = f"{lat},{lon} {radius_km}"


def build_cap_xml(
    *,
    identifier: str | None = None,
    sender: str = "orca@incois.gov.in",
    sent: datetime | None = None,
    status: str = "Actual",
    msg_type: str = "Alert",
    scope: str = "Public",
    headline: str,
    description: str,
    instruction: str = "Return to the nearest safe harbour. Monitor VHF channel 16.",
    event: str = "Marine Weather Hazard",
    severity: str = "warning",
    area_desc: str = "Thoothukudi coastal sector",
    polygon: list[tuple[float, float]] | None = None,
    circle: tuple[float, float, float] | None = None,  # (lat, lon, radius_km)
    language: str = "en-IN",
) -> str:
    """Return a valid CAP 1.2 XML document as a string. `simulated=True` is
    not a parameter — nothing here transmits; whether it was sent is the
    caller's story (the notification status), not the payload's."""
    sent = sent or datetime.now(timezone.utc)

    alert = ET.Element("alert", {"xmlns": CAP_NS})
    ET.SubElement(alert, "identifier").text = identifier or f"ORCA-{uuid.uuid4()}"
    ET.SubElement(alert, "sender").text = sender
    ET.SubElement(alert, "sent").text = _iso(sent)
    ET.SubElement(alert, "status").text = status
    ET.SubElement(alert, "msgType").text = msg_type
    ET.SubElement(alert, "scope").text = scope

    _add_info_block(
        alert, language=language, event=event, severity=severity, headline=headline,
        description=description, instruction=instruction, area_desc=area_desc,
        polygon=polygon, circle=circle,
    )

    ET.indent(alert, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(alert, encoding="unicode")


# P6.10 — CAP 1.2 allows one <alert> to carry several <info> blocks, one per
# language, which is the OASIS-documented way to broadcast the same warning
# multilingually in a single document rather than issuing N separate alerts
# with N separate identifiers. `translations` is `{lang_code: (headline,
# description, instruction)}`, already-translated text (never produced here —
# translation is orca/agents/language.py's job, called by the route below);
# this function only assembles the XML.
def build_multilingual_cap_xml(
    *,
    identifier: str | None = None,
    sender: str = "orca@incois.gov.in",
    sent: datetime | None = None,
    status: str = "Actual",
    msg_type: str = "Alert",
    scope: str = "Public",
    event: str = "Marine Weather Hazard",
    severity: str = "warning",
    area_desc: str = "Thoothukudi coastal sector",
    polygon: list[tuple[float, float]] | None = None,
    circle: tuple[float, float, float] | None = None,
    translations: dict[str, tuple[str, str, str]],  # lang -> (headline, description, instruction)
) -> str:
    sent = sent or datetime.now(timezone.utc)
    ident = identifier or f"ORCA-{uuid.uuid4()}"

    alert = ET.Element("alert", {"xmlns": CAP_NS})
    ET.SubElement(alert, "identifier").text = ident
    ET.SubElement(alert, "sender").text = sender
    ET.SubElement(alert, "sent").text = _iso(sent)
    ET.SubElement(alert, "status").text = status
    ET.SubElement(alert, "msgType").text = msg_type
    ET.SubElement(alert, "scope").text = scope

    for lang, (headline, description, instruction) in translations.items():
        _add_info_block(
            alert, language=lang, event=event, severity=severity, headline=headline,
            description=description, instruction=instruction, area_desc=area_desc,
            polygon=polygon, circle=circle,
        )

    ET.indent(alert, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(alert, encoding="unicode")


# --------------------------------------------------------------------------
# Four-channel broadcast preview
# --------------------------------------------------------------------------

def _fallback_web(verdict: str, hazard: str, location: str, ts: str) -> str:
    return f"{verdict}: {hazard} near {location}. Issued {ts}. Follow local authority guidance."


def _fallback_sms(verdict: str, hazard: str, location: str, ts: str) -> str:
    # GSM-7 friendly, <=160 chars.
    return f"[ORCA {verdict}] {hazard} near {location}. Seek safety. {ts}"[:160]


def _fallback_ivr(verdict: str, hazard: str, location: str, ts: str) -> str:
    return (
        f"This is a coast guard advisory. {verdict}. "
        f"{hazard} has been reported near {location}. "
        "Return to harbour and stay off the water. This message will repeat once."
    )


def _fallback_ussd(verdict: str, hazard: str, location: str, ts: str) -> str:
    return f"ORCA ALERT\n{verdict}\n{hazard}\n{location}\n{ts}\n1. Safe harbours\n2. Repeat"[:182]


# P6.10 — the five channels added alongside the original four. Same
# (verdict, hazard, location, ts) -> str shape as every _fallback_* above,
# for the composer's free-text fields — the real per-channel renderers in
# orca/channels/renderers.py take a full query-response payload and derive
# hazard from structured flags, a shape the composer's three plain text
# inputs don't carry, so this preview stays consistent with the pattern
# web/sms/ivr/ussd already use here rather than force-fitting the other one.
def _fallback_whatsapp(verdict: str, hazard: str, location: str, ts: str) -> str:
    return f"*ORCA {verdict}*\n{hazard} near {location}.\nIssued {ts}.\nView on the chart: {_MAP_CARD_BASE_URL}?place={location}"


def _fallback_missed_call(verdict: str, hazard: str, location: str, ts: str) -> str:
    return (
        f"This is the most recently cached advisory. ORCA advisory for {location}. "
        f"Verdict: {' '.join(verdict.split('_'))}. Hazard: {hazard}. "
        "To hear this again, stay on the line. Otherwise, goodbye."
    )


def _fallback_vhf(verdict: str, hazard: str, location: str, ts: str) -> str:
    return (
        "Securite, securite, securite.\n"
        "This is ORCA Marine Safety Advisory.\n"
        f"{verdict}. {hazard}, near {location}.\n"
        "Mariners in the area are advised to proceed with caution and monitor this channel.\n"
        "Out."
    )


def _fallback_harbour_board(verdict: str, hazard: str, location: str, ts: str) -> str:
    return f"ORCA {verdict}\n{hazard}"[:120]


_MAP_CARD_BASE_URL = "https://orca.local/map"  # ponytail: placeholder origin, same one orca/channels/renderers.py names — swap both together once a real deployed frontend URL exists


def four_channel_preview(*, verdict: str, hazard: str, location: str, issued_at: str | None = None) -> dict[str, dict[str, Any]]:
    """web / sms / ivr / ussd renderings of one alert, side by side. Each is
    a pure function of the same inputs — no channel fetches anything (the
    property D1's renderer tests also assert)."""
    ts = issued_at or datetime.now(timezone.utc).isoformat(timespec="minutes").replace("+00:00", "Z")

    try:  # TODO(D1): use the real channel renderers once orca.agents.reporting exports them
        from orca.agents import reporting as _r

        web = getattr(_r, "render_web", None)
        if web is not None:  # pragma: no cover - lands when D1 ships renderers
            state = {"final_english_response": _fallback_web(verdict, hazard, location, ts)}
            return {
                "web": {"body": _r.render_web(state), "chars": None},  # type: ignore[attr-defined]
                "sms": {"body": _r.render_sms(state), "chars": len(_r.render_sms(state))},  # type: ignore[attr-defined]
                "ivr": {"body": _r.render_ivr(state), "chars": None},  # type: ignore[attr-defined]
                "ussd": {"body": _r.render_ussd(state), "chars": len(_r.render_ussd(state))},  # type: ignore[attr-defined]
            }
    except Exception:
        logger.debug("D1 channel renderers unavailable; using fallback preview", exc_info=True)

    sms = _fallback_sms(verdict, hazard, location, ts)
    ussd = _fallback_ussd(verdict, hazard, location, ts)
    board = _fallback_harbour_board(verdict, hazard, location, ts)
    return {
        "web": {"body": _fallback_web(verdict, hazard, location, ts), "chars": None},
        "sms": {"body": sms, "chars": len(sms), "gsm7_ok": all(ord(c) < 128 for c in sms)},
        "ivr": {"body": _fallback_ivr(verdict, hazard, location, ts), "chars": None},
        "ussd": {"body": ussd, "chars": len(ussd)},
        # P6.10
        "whatsapp": {"body": _fallback_whatsapp(verdict, hazard, location, ts), "chars": None},
        "missed_call": {"body": _fallback_missed_call(verdict, hazard, location, ts), "chars": None},
        "vhf": {"body": _fallback_vhf(verdict, hazard, location, ts), "chars": None},
        "harbour_board": {"body": board, "chars": len(board)},
    }
