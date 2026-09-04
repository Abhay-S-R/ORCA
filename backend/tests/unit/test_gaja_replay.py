"""Cyclone Gaja historical replay (parent plan §1.3, phase4 plan §3). Runs
against the real procured files on disk (IBTrACS best-track + ERA5
wind/wave), same rationale as the geospatial tests that use the real
boundary files rather than mocking them — a schema mismatch in either
dataset is exactly what a mock would hide. Skips cleanly if the data isn't
present on this machine.
"""
from __future__ import annotations

import pytest

from orca.replay import gaja

pytestmark = pytest.mark.skipif(
    not (gaja.TRACK_FILE.exists() and gaja.ERA5_FILE.exists()),
    reason="Cyclone Gaja replay data not present on this machine (data/cyclone_gaja/)",
)


def test_track_has_the_documented_point_count_and_provenance():
    payload = gaja.replay_payload()
    assert len(payload["track"]) == 76
    assert all(p["provenance_class"] == gaja.PROVENANCE_CLASS for p in payload["track"])
    assert payload["storm"]["name"] == "GAJA"


def test_hazard_cascade_flags_a_real_no_go_around_the_landfall_window():
    cascade = gaja.hazard_cascade()
    assert len(cascade) > 0
    no_go = [c for c in cascade if c["go_no_go"] == "NO_GO"]
    # Landfall was 15-16 Nov 2018 (Vedaranyam) — a regression here means
    # Agent 7's own thresholds changed in a way that stops flagging a real,
    # historically-verified cyclone as dangerous.
    assert no_go, "expected at least one NO_GO timestep around the Gaja landfall window"
    assert any(c["timestamp"].startswith("2018-11-15") or c["timestamp"].startswith("2018-11-16") for c in no_go)


def test_every_cascade_frame_carries_historical_provenance_never_live_or_simulated():
    cascade = gaja.hazard_cascade()
    assert all(c["provenance_class"] == gaja.PROVENANCE_CLASS for c in cascade)
    assert all("LIVE" not in c["provenance_class"] and "SIMULATED" not in c["provenance_class"] for c in cascade)


def test_wind_frames_match_the_flowfieldcanvas_point_shape():
    frames = gaja.wind_vector_frames()
    assert len(frames) > 0
    point = frames[0]["points"][0]
    assert {"lat", "lon", "speed_ms", "direction_deg"} <= point.keys()
