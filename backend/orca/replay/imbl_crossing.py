"""orca/replay/imbl_crossing.py — P6.7 (orca_final §7, PS-C8), Scenario 2:
the IMBL border-crossing demonstration. A scripted vessel *track* (a fixed
line of lat/lon positions, chosen by hand for a clean, all-open-water,
single-segment approach to the real Sri Lanka-India IMBL near Palk Bay) run
through the same `sentinel.geofence_check()` a live `geofence_approach`
watch polls and the same `risk_assessment.evaluate_marine_safety()` the
query path uses at every position — the band, verdict and reciprocal
heading below are computed from the real boundary geometry, never scripted
to read out a band name.
"""
from __future__ import annotations

from typing import Any

from orca.agents import risk_assessment, sentinel

# 9.30N, stepped west from open Palk Bay water (~13 nm from the line) across
# it (to ~1 nm on the far side) — every point here is real open water
# (verified against orca.agents.geospatial.depth_at_point when this track
# was picked) whose nearest boundary line is consistently "Sri Lanka -
# India", so the crossing reads as one continuous approach, not a jump
# between unrelated boundary segments.
_TRACK: tuple[tuple[float, float], ...] = (
    (9.30, 79.74), (9.30, 79.72), (9.30, 79.69), (9.30, 79.66),
    (9.30, 79.64), (9.30, 79.62), (9.30, 79.60), (9.30, 79.59),
    (9.30, 79.57), (9.30, 79.55), (9.30, 79.54), (9.30, 79.52),
)

# Fixed calm-weather inputs: this scenario demonstrates the geofence axis of
# evaluate_marine_safety in isolation, not a compound wave/wind/boundary
# scenario — CAUTION/NO_GO on this track comes only from imbl_distance_nm.
_WAVE_HEIGHT_M = 0.6
_WIND_SPEED_KMH = 12.0


def imbl_crossing_track(vessel_class: str = "small_fishing") -> dict[str, Any]:
    frames: list[dict[str, Any]] = []
    for lat, lon in _TRACK:
        snap = sentinel.geofence_check(lat, lon)
        verdict = risk_assessment.evaluate_marine_safety(
            wave_height_m=_WAVE_HEIGHT_M,
            wind_speed_kmh=_WIND_SPEED_KMH,
            lightning_active=False,
            cyclone_alert=None,
            imbl_distance_nm=snap.distance_nm,
            mpa_violation=False,
            vessel_class=vessel_class,  # type: ignore[arg-type]
        )
        reciprocal_heading = round((snap.bearing_deg + 180.0) % 360.0, 1) if snap.bearing_deg is not None else None
        frames.append({
            "lat": lat, "lon": lon,
            "distance_nm": snap.distance_nm, "band": snap.band,
            "line_name": snap.line_name, "between": snap.between,
            "bearing_deg": snap.bearing_deg,
            "reciprocal_heading_deg": reciprocal_heading,
            "go_no_go": verdict["go_no_go"], "status": verdict["status"], "reason": verdict["reason"],
        })
    return {"vessel_class": vessel_class, "frames": frames}


if __name__ == "__main__":
    result = imbl_crossing_track()
    bands = [f["band"] for f in result["frames"]]
    assert bands[0] == "CLEAR", bands
    assert "ADVISORY" in bands and "WATCH" in bands and "WARNING" in bands and "CRITICAL" in bands, bands
    assert result["frames"][-1]["go_no_go"] == "NO_GO"
    assert result["frames"][-1]["reciprocal_heading_deg"] is not None
    print(f"imbl_crossing self-check passed: {len(result['frames'])} frames, bands {bands}")
