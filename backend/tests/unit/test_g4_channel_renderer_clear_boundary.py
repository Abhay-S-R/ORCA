"""G4 verification: channel renderers must not report 'IMBL boundary clear' as an active hazard.

Defect G4 in docs/ORCA_Agent_Trace_and_Audit.md:
The channel renderer tests `imbl_alert_level not in (None, 'SAFE')`, but geospatial
emits 'CLEAR'. Every GO summary with a clear boundary named 'IMBL boundary clear'
as the hazard instead of 'no active hazard'.
"""

import pytest
import httpx
from orca.channels.renderers import (
    _verdict_and_hazard,
    render_sms,
    render_ivr,
    render_whatsapp,
    render_ussd,
    render_vhf,
    render_harbour_board,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*a, **kw):
        raise AssertionError("renderer must be pure without network calls")
    monkeypatch.setattr(httpx, "get", blocked)
    monkeypatch.setattr(httpx, "post", blocked)


_BASE_PAYLOAD = {
    "risk_assessment": {"go_no_go": "GO", "reason": "all clear"},
    "weather_summary": {"lightning_active": False, "cyclone_alert": None},
    "hazard_breakdown": {"mpa_violation": False, "imbl_alert_level": "CLEAR"},
    "final_english_response": "GO: clear to sail.",
    "final_vernacular_response": "GO: clear to sail.",
    "audit_trace_log": [{"agent_name": "reporting", "ended_at": "2026-09-03T10:00:00Z"}],
    "user_location": {"lat": 8.8, "lon": 78.1},
}


def test_verdict_and_hazard_clear_boundary():
    verdict, hazard = _verdict_and_hazard(_BASE_PAYLOAD)
    assert verdict == "GO"
    assert hazard == "no active hazard"


@pytest.mark.parametrize("safe_level", ["SAFE", "CLEAR", "clear", "safe", None, ""])
def test_verdict_and_hazard_all_safe_variations(safe_level):
    payload = {
        **_BASE_PAYLOAD,
        "hazard_breakdown": {"mpa_violation": False, "imbl_alert_level": safe_level},
    }
    verdict, hazard = _verdict_and_hazard(payload)
    assert verdict == "GO"
    assert hazard == "no active hazard"


@pytest.mark.parametrize("hazard_level,expected_hazard", [
    ("CAUTION", "IMBL boundary caution"),
    ("DANGER", "IMBL boundary danger"),
    ("INSIDE", "IMBL boundary inside"),
    ("CLOSE", "IMBL boundary close"),
])
def test_verdict_and_hazard_active_boundary_hazards(hazard_level, expected_hazard):
    payload = {
        **_BASE_PAYLOAD,
        "hazard_breakdown": {"mpa_violation": False, "imbl_alert_level": hazard_level},
    }
    _, hazard = _verdict_and_hazard(payload)
    assert hazard == expected_hazard


def test_sms_renderer_does_not_say_boundary_clear():
    sms = render_sms(_BASE_PAYLOAD)
    assert "no active hazard" in sms.body
    assert "IMBL boundary clear" not in sms.body


def test_ivr_renderer_does_not_say_boundary_clear():
    ivr = render_ivr(_BASE_PAYLOAD)
    assert "no active hazard" in ivr.body.lower()
    assert "imbl boundary clear" not in ivr.body.lower()


def test_whatsapp_renderer_does_not_say_boundary_clear():
    whatsapp = render_whatsapp(_BASE_PAYLOAD)
    assert "no active hazard" in whatsapp.body
    assert "IMBL boundary clear" not in whatsapp.body


def test_ussd_renderer_does_not_say_boundary_clear():
    ussd = render_ussd(_BASE_PAYLOAD)
    assert "2.Hazard:no active hazard" in ussd.body
    assert "IMBL boundary clear" not in ussd.body


def test_vhf_renderer_does_not_say_boundary_clear():
    vhf = render_vhf(_BASE_PAYLOAD)
    assert "no active hazard" in vhf.body
    assert "IMBL boundary clear" not in vhf.body


def test_harbour_board_renderer_does_not_say_boundary_clear():
    board = render_harbour_board(_BASE_PAYLOAD)
    assert "no active hazard" in board.body
    assert "IMBL boundary clear" not in board.body
