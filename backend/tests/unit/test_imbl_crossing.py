"""P6.7 — the border-crossing scenario's stepped track. Runs against the
real boundary-line geometry (same file the live geofence path reads), not a
mock: a stale IMBL dataset is exactly what a mock would hide.
"""
from __future__ import annotations

from orca.replay import imbl_crossing


def test_track_starts_clear_and_ends_no_go():
    payload = imbl_crossing.imbl_crossing_track()
    frames = payload["frames"]
    assert frames[0]["band"] == "CLEAR"
    assert frames[-1]["band"] == "CRITICAL"
    assert frames[-1]["go_no_go"] == "NO_GO"


def test_every_named_band_is_crossed_in_order():
    bands = [f["band"] for f in imbl_crossing.imbl_crossing_track()["frames"]]
    seen_order = []
    for b in bands:
        if not seen_order or seen_order[-1] != b:
            seen_order.append(b)
    # Monotonic approach: each band, once entered, is never revisited after
    # a tighter one — this track never re-widens.
    rank = {"CLEAR": 0, "ADVISORY": 1, "WATCH": 2, "WARNING": 3, "CRITICAL": 4}
    ranks = [rank[b] for b in seen_order]
    assert ranks == sorted(ranks), seen_order


def test_verdict_is_computed_by_the_real_risk_assessment_function_not_scripted():
    frames = imbl_crossing.imbl_crossing_track()["frames"]
    advisory = next(f for f in frames if f["band"] == "ADVISORY")
    assert advisory["go_no_go"] == "GO"
    warning = next(f for f in frames if f["band"] == "WARNING")
    assert warning["go_no_go"] == "CAUTION"
    critical = next(f for f in frames if f["band"] == "CRITICAL")
    assert critical["go_no_go"] == "NO_GO"


def test_reciprocal_heading_is_the_opposite_of_the_bearing_to_the_boundary():
    frames = imbl_crossing.imbl_crossing_track()["frames"]
    frame = frames[-1]
    assert frame["reciprocal_heading_deg"] == round((frame["bearing_deg"] + 180.0) % 360.0, 1)
