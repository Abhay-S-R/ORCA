import httpx
import pytest

from orca.channels.renderers import (
    is_gsm7_encodable,
    render_ivr,
    render_sms,
    render_ussd,
    render_web,
)

_SAMPLE = {
    "risk_assessment": {"go_no_go": "CAUTION", "reason": "wave height elevated"},
    "weather_summary": {"lightning_active": False, "cyclone_alert": None},
    "hazard_breakdown": {"mpa_violation": False, "imbl_alert_level": "SAFE"},
    "final_english_response": "CAUTION: wave height elevated near your position.",
    "final_vernacular_response": "CAUTION: wave height elevated near your position.",
    "audit_trace_log": [{"agent_name": "reporting", "ended_at": "2026-09-03T10:00:00Z"}],
}

_NO_GO_LIGHTNING = {
    **_SAMPLE,
    "risk_assessment": {"go_no_go": "NO_GO", "reason": "lightning within 8km"},
    "weather_summary": {"lightning_active": True, "cyclone_alert": None},
}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **kw):
        raise AssertionError("a channel renderer made a network call — it must be a pure function")
    monkeypatch.setattr(httpx, "get", blocked)
    monkeypatch.setattr(httpx, "post", blocked)


def test_all_four_renderers_run_on_the_same_payload_with_no_fetch():
    web = render_web(_SAMPLE)
    sms = render_sms(_SAMPLE)
    ivr = render_ivr(_SAMPLE)
    ussd = render_ussd(_SAMPLE)
    assert web["risk_assessment"]["go_no_go"] == "CAUTION"
    assert "CAUTION" in sms.body
    assert "CAUTION" in ivr.body
    assert "CAUTION" in ussd.body


def test_render_web_is_a_passthrough_copy_not_a_transform():
    web = render_web(_SAMPLE)
    assert web == _SAMPLE
    assert web is not _SAMPLE


def test_sms_stays_within_gsm7_160_char_budget():
    sms = render_sms(_SAMPLE)
    assert len(sms.body) <= 160
    assert sms.encodable is True
    assert is_gsm7_encodable(sms.body)


def test_ussd_stays_within_182_char_budget_and_is_menu_structured():
    ussd = render_ussd(_SAMPLE)
    assert len(ussd.body) <= 182
    assert "1." in ussd.body and "2." in ussd.body


def test_ivr_script_repeats_exactly_once_and_spells_out_verdict_words():
    ivr = render_ivr(_NO_GO_LIGHTNING)
    assert ivr.body.count("I repeat") == 1
    assert "NO GO" in ivr.body  # underscore split into two spoken words, not "NO_GO"


def test_non_gsm7_vernacular_text_falls_back_to_the_encodable_composed_line():
    # Tamil/Hindi script is never GSM-7 (verified directly by
    # is_gsm7_encodable below) — render_sms must not ship mojibake for it,
    # so it falls back to the ASCII verdict+hazard+timestamp line rather
    # than truncating a non-encodable string and calling it done.
    tamil_text = "எச்சரிக்கை: அலை உயரம் அதிகம்"
    assert is_gsm7_encodable(tamil_text) is False
    tamil_payload = {**_SAMPLE, "final_vernacular_response": tamil_text}
    sms = render_sms(tamil_payload, language="ta")
    assert sms.encodable is True
    assert tamil_text not in sms.body


def test_english_vernacular_is_gsm7_encodable():
    sms = render_sms(_SAMPLE, language="en")
    assert sms.encodable is True


def test_lightning_hazard_takes_priority_in_the_hazard_summary():
    sms = render_sms(_NO_GO_LIGHTNING)
    assert "lightning" in sms.body.lower()
