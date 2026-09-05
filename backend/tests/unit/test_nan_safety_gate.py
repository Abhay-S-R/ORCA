"""A non-finite input must never be able to produce a GO verdict.

Every comparison against NaN is False, so an unguarded threshold chain falls
straight through to its GO fall-through. That is not a synthetic edge case:
ERA5 masks significant wave height as NaN at Thoothukudi's own grid point
(orca/replay/gaja.py), and a failed geometry op yields NaN for the IMBL
distance — the single highest-consequence number in the product.
"""
from __future__ import annotations

import math

from orca.agents.risk_assessment import evaluate_marine_safety
from orca.resilience import conservative_or, safety_floor_for_missing_inputs

NAN = float("nan")
CALM = {"wave_height_m": 1.0, "wind_speed_kmh": 10.0, "lightning_active": False,
        "cyclone_alert": None, "imbl_distance_nm": 50.0, "mpa_violation": False}


def _verdict(**overrides):
    return evaluate_marine_safety(**{**CALM, **overrides})


def test_all_finite_calm_inputs_still_produce_go():
    """The guard must not break the happy path it is wrapped around."""
    assert _verdict()["go_no_go"] == "GO"


def test_nan_or_none_never_produces_go():
    for field in ("wave_height_m", "wind_speed_kmh", "imbl_distance_nm"):
        for bad in (NAN, math.inf, -math.inf, None):
            v = _verdict(**{field: bad})
            assert v["go_no_go"] != "GO", f"{field}={bad!r} produced {v}"
            assert field in v["reason"], f"{field}={bad!r} did not name the input: {v}"


def test_known_hazards_still_fire_when_another_input_is_unreadable():
    """An unreadable input degrades to CAUTION, but it must not mask a hazard
    that a *readable* input already proves — CAUTION would be an upgrade."""
    assert _verdict(imbl_distance_nm=NAN, wave_height_m=9.0)["go_no_go"] == "NO_GO"
    assert _verdict(wave_height_m=NAN, lightning_active=True)["go_no_go"] == "NO_GO"
    assert _verdict(wave_height_m=NAN, mpa_violation=True)["go_no_go"] == "NO_GO"
    assert _verdict(wind_speed_kmh=NAN, cyclone_alert="Red")["go_no_go"] == "NO_GO"


def test_conservative_or_records_non_finite_as_missing():
    """NaN is more dangerous than None: it survives an `is None` check. It has
    to be recorded as missing AND normalised away so no caller sees it."""
    for bad in (NAN, math.inf, -math.inf, None):
        missing: list[str] = []
        assert conservative_or(bad, missing_field_name="imbl_distance_nm", missing=missing) is None
        assert missing == ["imbl_distance_nm"]
        assert safety_floor_for_missing_inputs(missing)[0] == "CAUTION"

    missing = []
    assert conservative_or(4.2, missing_field_name="wave_height_m", missing=missing) == 4.2
    assert missing == []
    assert safety_floor_for_missing_inputs(missing) is None
