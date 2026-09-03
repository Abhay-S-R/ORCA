"""Agent 11 — Sentinel crossing detection (plan §4 D2 Day 16). Pure logic
only here (no DB, no graph); the DB/dispatch wiring is covered by
test_notifications.py where a live Postgres is present.

The functional requirement under test: an unchanged condition is a NO-OP —
"no notification spam is a functional requirement" — verified by a second
identical poll producing fired=False.
"""
from orca.agents import sentinel
from orca.agents.sentinel import WatchSnapshot, detect_crossing, evaluate


def _snap(**kw) -> WatchSnapshot:
    base = {
        "go_no_go": "GO", "reason": "calm", "wave_height_m": 0.8, "wind_speed_ms": 3.0,
        "lightning_active": False, "cyclone_alert": None, "active_hazard_types": [], "confidence": "HIGH",
    }
    base.update(kw)
    return WatchSnapshot(**base)


def test_first_calm_poll_is_silent():
    c = detect_crossing("weather", {}, _snap(), last_payload=None)
    assert c.fired is False


def test_go_to_caution_fires():
    c = detect_crossing("weather", {}, _snap(go_no_go="CAUTION", reason="rough"), last_payload={"go_no_go": "GO"})
    assert c.fired is True
    assert c.severity == "warning"


def test_caution_to_no_go_fires_danger():
    c = detect_crossing("weather", {}, _snap(go_no_go="NO_GO"), last_payload={"go_no_go": "CAUTION"})
    assert c.fired is True
    assert c.severity == "danger"


def test_unchanged_verdict_is_a_noop():
    prev = _snap(go_no_go="CAUTION").as_payload()
    c = detect_crossing("weather", {}, _snap(go_no_go="CAUTION"), last_payload=prev)
    assert c.fired is False


def test_second_identical_poll_produces_no_notification():
    """Exit-criterion shape: poll twice with the same conditions, second
    poll fires nothing."""
    snap = _snap(go_no_go="CAUTION")
    first = detect_crossing("weather", {}, snap, last_payload={"go_no_go": "GO"})
    assert first.fired is True
    second = detect_crossing("weather", {}, snap, last_payload=snap.as_payload())
    assert second.fired is False


def test_new_active_hazard_fires_even_if_verdict_unchanged():
    prev = _snap(go_no_go="NO_GO", active_hazard_types=[]).as_payload()
    c = detect_crossing(
        "lightning", {}, _snap(go_no_go="NO_GO", lightning_active=True, active_hazard_types=["lightning"]),
        last_payload=prev,
    )
    assert c.fired is True
    assert "lightning" in c.title


def test_explicit_wave_threshold_crossing_fires_once():
    thresholds = {"wave_height_m": 2.5}
    # below -> no fire
    assert not detect_crossing("wave_height", thresholds, _snap(wave_height_m=2.0), None).fired
    # crosses up -> fire
    crossed = detect_crossing(
        "wave_height", thresholds, _snap(wave_height_m=2.7),
        last_payload=_snap(wave_height_m=2.0).as_payload(),
    )
    assert crossed.fired is True
    # stays above -> no second fire
    again = detect_crossing(
        "wave_height", thresholds, _snap(wave_height_m=2.8),
        last_payload=_snap(wave_height_m=2.7).as_payload(),
    )
    assert again.fired is False


def test_evaluate_uses_injected_check_and_produces_a_query_id_and_sms_payload():
    decision = evaluate(
        watch_id="w1",
        watch_type="wave_height",
        location={"lat": 8.8, "lon": 78.1},
        location_name="your watch point",
        thresholds={"wave_height_m": 2.5},
        last_payload=None,
        check=lambda lat, lon, vessel_class=None: _snap(go_no_go="CAUTION", wave_height_m=3.0, reason="rough seas"),
    )
    assert decision.fired is True
    assert decision.query_id  # correlation id minted per evaluation
    assert decision.alert_payload["sagar_vani_sms"]
    assert len(decision.alert_payload["sagar_vani_sms"]) <= 160


def test_evaluate_silent_when_no_crossing():
    decision = evaluate(
        watch_id="w1", watch_type="weather", location={"lat": 8.8, "lon": 78.1},
        location_name="your watch point", thresholds={}, last_payload=None,
        check=lambda lat, lon, vessel_class=None: _snap(),
    )
    assert decision.fired is False
    assert decision.alert_payload == {}


def test_cyclone_alert_severity_helper():
    assert sentinel.risk_assessment_cyclone_alert([]) is None
    assert sentinel.risk_assessment_cyclone_alert([{"severity": "Red"}]) == "Red"
    assert sentinel.risk_assessment_cyclone_alert([{"severity": "Orange"}, {"severity": "Yellow"}]) == "Orange"
