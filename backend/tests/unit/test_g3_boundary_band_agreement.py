"""G3 verification: the geospatial boundary alert level agrees with the risk
assessment verdict bands.

Formerly, there were two conflicting band tables:
- Geospatial labeled: DANGER <= 1.0 NM, CAUTION <= 5.0 NM, else CLEAR
- Risk assessment verdict: NO_GO <= 1.0 NM, CAUTION <= 3.0 NM, else GO

At 4.0 NM (between 3.0 and 5.0 NM), geospatial reported CAUTION while the
safety verdict was GO. G3 synchronizes the CAUTION threshold at 3.0 NM so
the label and verdict always agree.
"""
from __future__ import annotations

import pytest

from orca.agents.geospatial import _alert_level, _PROXIMITY_BANDS
from orca.agents.risk_assessment import evaluate_marine_safety


def test_proximity_bands_threshold_is_3nm():
    """_PROXIMITY_BANDS CAUTION threshold is 3.0 NM, matching risk_assessment."""
    assert _PROXIMITY_BANDS == ((1.0, "DANGER"), (3.0, "CAUTION"))


@pytest.mark.parametrize(
    ("dist_nm", "expected_label", "expected_verdict"),
    [
        (0.5, "DANGER", "NO_GO"),
        (1.0, "DANGER", "NO_GO"),
        (1.5, "CAUTION", "CAUTION"),
        (2.0, "CAUTION", "CAUTION"),
        (3.0, "CAUTION", "CAUTION"),
        # The defect G3 boundary point: at 4.0 NM, old code had CAUTION vs GO
        (3.5, "CLEAR", "GO"),
        (4.0, "CLEAR", "GO"),
        (4.5, "CLEAR", "GO"),
        (6.0, "CLEAR", "GO"),
    ],
)
def test_label_and_verdict_agree_across_distances(
    dist_nm: float, expected_label: str, expected_verdict: str
):
    """At every distance, geospatial's alert level and risk_assessment's verdict
    must agree in semantic category."""
    label = _alert_level(dist_nm, inside=False)
    assert label == expected_label, f"Distance {dist_nm} NM gave label {label}, expected {expected_label}"

    safety = evaluate_marine_safety(
        wave_height_m=0.5,
        wind_speed_kmh=10.0,
        lightning_active=False,
        cyclone_alert=None,
        imbl_distance_nm=dist_nm,
        mpa_violation=False,
    )
    verdict = safety["go_no_go"]
    assert verdict == expected_verdict, f"Distance {dist_nm} NM gave verdict {verdict}, expected {expected_verdict}"


def test_inside_boundary_always_danger_and_no_go():
    """A point inside a restricted boundary is labeled INSIDE and yields NO_GO."""
    label = _alert_level(0.0, inside=True)
    assert label == "INSIDE"

    safety = evaluate_marine_safety(
        wave_height_m=0.5,
        wind_speed_kmh=10.0,
        lightning_active=False,
        cyclone_alert=None,
        imbl_distance_nm=0.0,
        mpa_violation=True,
    )
    assert safety["go_no_go"] == "NO_GO"
