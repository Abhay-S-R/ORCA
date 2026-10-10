"""Pure-logic tests for orca/sentinel_runtime.py's P5.17/P5.22 additions
(adaptive cadence, quiet hours, per-severity escalation) — no DB needed,
same discipline tests/unit/test_sentinel.py holds crossing detection to.
DB-touching behaviour (holding/flushing a real Notification row) is covered
by tests/unit/test_notifications.py against the live Postgres.
"""
from __future__ import annotations

from datetime import UTC, datetime

from orca.agents.sentinel import WatchDecision
from orca.sentinel_runtime import _is_near_threshold, effective_channels, quiet_hours_window


def _decision(**snapshot_payload) -> WatchDecision:
    return WatchDecision(
        watch_id="w1", query_id="q1", fired=True, severity="warning", title="t", body="b",
        alert_payload={}, snapshot_payload=snapshot_payload,
    )


# --- quiet_hours_window -----------------------------------------------------

def test_no_quiet_hours_set_is_never_in_window():
    assert quiet_hours_window(None) == (False, None)
    assert quiet_hours_window({}) == (False, None)


def test_same_day_window():
    now = datetime(2026, 9, 23, 14, 0, tzinfo=UTC)  # 14:00 UTC
    qh = {"start": "13:00", "end": "15:00", "tz": "UTC"}
    in_window, ends = quiet_hours_window(qh, now=now)
    assert in_window is True
    assert ends == datetime(2026, 9, 23, 15, 0, tzinfo=UTC)

    outside = quiet_hours_window(qh, now=datetime(2026, 9, 23, 16, 0, tzinfo=UTC))
    assert outside == (False, None)


def test_midnight_wrapping_window():
    qh = {"start": "22:00", "end": "06:00", "tz": "UTC"}
    # 23:30 — inside, after start, before midnight.
    in_window, ends = quiet_hours_window(qh, now=datetime(2026, 9, 23, 23, 30, tzinfo=UTC))
    assert in_window is True
    assert ends == datetime(2026, 9, 24, 6, 0, tzinfo=UTC)

    # 02:00 — inside, after midnight, before end.
    in_window2, ends2 = quiet_hours_window(qh, now=datetime(2026, 9, 24, 2, 0, tzinfo=UTC))
    assert in_window2 is True
    assert ends2 == datetime(2026, 9, 24, 6, 0, tzinfo=UTC)

    # noon — outside.
    assert quiet_hours_window(qh, now=datetime(2026, 9, 23, 12, 0, tzinfo=UTC)) == (False, None)


def test_malformed_quiet_hours_never_raises():
    assert quiet_hours_window({"start": "not-a-time", "end": "06:00", "tz": "UTC"}) == (False, None)
    assert quiet_hours_window({"start": "22:00", "end": "06:00", "tz": "Nowhere/Fake"}) == (False, None)


def test_timezone_is_honoured_not_just_parsed():
    # 21:00 UTC == 02:30 IST the next day (UTC+5:30) — inside a 22:00-06:00
    # IST window only when the conversion actually happens.
    qh = {"start": "22:00", "end": "06:00", "tz": "Asia/Kolkata"}
    in_window, _ = quiet_hours_window(qh, now=datetime(2026, 9, 23, 21, 0, tzinfo=UTC))
    assert in_window is True


# --- effective_channels ------------------------------------------------------

def test_effective_channels_falls_back_to_watch_channels_when_unconfigured():
    assert effective_channels(["in_app"], {}, "danger") == ["in_app"]
    assert effective_channels(["in_app"], None, "danger") == ["in_app"]


def test_effective_channels_uses_the_per_severity_override():
    escalation = {"danger": ["in_app", "sms"], "warning": ["in_app"]}
    assert effective_channels(["in_app"], escalation, "danger") == ["in_app", "sms"]
    assert effective_channels(["in_app", "sms"], escalation, "warning") == ["in_app"]
    # info has no entry -> falls back to the watch's own channels.
    assert effective_channels(["in_app"], escalation, "info") == ["in_app"]


# --- _is_near_threshold ------------------------------------------------------

def test_near_threshold_wave_height():
    assert _is_near_threshold("wave_height", {"wave_height_m": 2.5}, _decision(wave_height_m=2.1)) is True
    assert _is_near_threshold("wave_height", {"wave_height_m": 2.5}, _decision(wave_height_m=1.0)) is False
    assert _is_near_threshold("wave_height", {}, _decision(wave_height_m=2.4)) is False


def test_near_threshold_geofence_band():
    assert _is_near_threshold("geofence_approach", {}, _decision(band="WATCH")) is True
    assert _is_near_threshold("geofence_approach", {}, _decision(band="ADVISORY")) is False
    assert _is_near_threshold("geofence_approach", {}, _decision(band="CLEAR")) is False


def test_near_threshold_verdict_watches():
    assert _is_near_threshold("weather", {}, _decision(go_no_go="CAUTION")) is True
    assert _is_near_threshold("lightning", {}, _decision(go_no_go="GO")) is False


def test_pfz_shift_never_reports_near_threshold():
    assert _is_near_threshold("pfz_shift", {}, _decision(has_advisory=True)) is False


def test_near_threshold_all_watches():
    assert _is_near_threshold("all", {"wave_height_m": 2.5}, _decision(wave_height_m=2.1, go_no_go="GO")) is True
    assert _is_near_threshold("all", {}, _decision(wave_height_m=1.0, go_no_go="CAUTION")) is True
    assert _is_near_threshold("all", {}, _decision(wave_height_m=1.0, go_no_go="GO", geofence={"band": "WATCH"})) is True
    assert _is_near_threshold("all", {"wave_height_m": 2.5}, _decision(wave_height_m=1.0, go_no_go="GO", geofence={"band": "CLEAR"})) is False
