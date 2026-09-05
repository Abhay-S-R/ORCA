"""CAP 1.2 generation + the four-channel broadcast preview (plan §4 D2 Day
20). Pure — no DB. The aggregation privacy assertion lives in
test_notifications.py where a Session is available."""
from xml.etree import ElementTree as ET

from orca.ops.cap import CAP_NS, build_cap_xml, four_channel_preview


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


def test_four_channel_preview_sms_is_gsm7_and_within_160():
    channels = four_channel_preview(verdict="NO-GO", hazard="High waves", location="Thoothukudi")
    assert set(channels) == {"web", "sms", "ivr", "ussd"}
    assert channels["sms"]["chars"] <= 160
    assert channels["sms"]["gsm7_ok"] is True
    assert channels["ussd"]["chars"] <= 182
    # every channel is a pure render of the same inputs — none is empty
    assert all(channels[c]["body"] for c in channels)
