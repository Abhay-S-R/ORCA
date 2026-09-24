"""CAP 1.2 generation + the four-channel broadcast preview (plan §4 D2 Day
20). Pure — no DB. The aggregation privacy assertion lives in
test_notifications.py where a Session is available."""
from xml.etree import ElementTree as ET

from orca.ops.cap import CAP_NS, build_cap_xml, build_multilingual_cap_xml, four_channel_preview


def test_cap_xml_is_well_formed_and_has_required_cap_1_2_elements():
    xml = build_cap_xml(
        headline="High waves off Thoothukudi",
        description="Forecast significant wave height 3.2 m for the next 12 hours.",
        severity="danger",
        circle=(8.8, 78.14, 25.0),
    )
    root = ET.fromstring(xml)
    assert root.tag == f"{{{CAP_NS}}}alert"
    tags = {child.tag.split('}')[-1] for child in root}
    assert {"identifier", "sender", "sent", "status", "msgType", "scope", "info"} <= tags
    info = root.find(f"{{{CAP_NS}}}info")
    info_tags = {c.tag.split('}')[-1] for c in info}
    assert {"category", "event", "urgency", "severity", "certainty", "headline", "area"} <= info_tags
    assert info.find(f"{{{CAP_NS}}}severity").text == "Extreme"  # danger -> Extreme
    area = info.find(f"{{{CAP_NS}}}area")
    assert area.find(f"{{{CAP_NS}}}circle").text == "8.8,78.14 25.0"


def test_cap_severity_mapping():
    for sev, cap_sev in [("info", "Minor"), ("advisory", "Moderate"), ("warning", "Severe"), ("danger", "Extreme")]:
        xml = build_cap_xml(headline="h", description="d", severity=sev)
        root = ET.fromstring(xml)
        assert root.find(f"{{{CAP_NS}}}info/{{{CAP_NS}}}severity").text == cap_sev


def test_multilingual_cap_xml_carries_one_info_block_per_language():
    # P6.10 — CAP 1.2's documented multilingual pattern: one <alert>, several
    # <info> blocks, one per language, sharing a single identifier.
    xml = build_multilingual_cap_xml(
        severity="warning",
        translations={
            "en-IN": ("High waves", "3.2m forecast", "Return to harbour"),
            "ta-IN": ("அலைகள் அதிகம்", "3.2 மீ முன்னறிவிப்பு", "துறைமுகத்திற்கு திரும்பவும்"),
        },
    )
    root = ET.fromstring(xml)
    infos = root.findall(f"{{{CAP_NS}}}info")
    assert len(infos) == 2
    langs = {i.find(f"{{{CAP_NS}}}language").text for i in infos}
    assert langs == {"en-IN", "ta-IN"}
    ta_info = next(i for i in infos if i.find(f"{{{CAP_NS}}}language").text == "ta-IN")
    assert ta_info.find(f"{{{CAP_NS}}}headline").text == "அலைகள் அதிகம்"
    # a single identifier for the whole multilingual alert, not one per language
    assert len(root.findall(f"{{{CAP_NS}}}identifier")) == 1


def test_four_channel_preview_sms_is_gsm7_and_within_160():
    channels = four_channel_preview(verdict="NO-GO", hazard="High waves", location="Thoothukudi")
    # P6.10 — whatsapp/missed_call/vhf/harbour_board added alongside the
    # original four; the function name is kept (it is the one place the
    # frontend and this test reference), but it now previews nine channels.
    assert set(channels) == {"web", "sms", "ivr", "ussd", "whatsapp", "missed_call", "vhf", "harbour_board"}
    assert channels["sms"]["chars"] <= 160
    assert channels["sms"]["gsm7_ok"] is True
    assert channels["ussd"]["chars"] <= 182
    assert channels["harbour_board"]["chars"] <= 120
    assert "Securite" in channels["vhf"]["body"]
    # every channel is a pure render of the same inputs — none is empty
    assert all(channels[c]["body"] for c in channels)
