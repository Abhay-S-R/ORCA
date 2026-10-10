"""G2 verification: the fishing-ban 12 NM carve-out uses the distance to the
Indian coastline/baseline, not the nearest EEZ edge.

Near the Sri Lanka border (Palk Strait / Gulf of Mannar), the nearest EEZ edge is
the international maritime boundary line (IMBL), which can be 1-5 NM away while
the Indian coast is 20-35+ NM away. Formerly, this caused offshore vessels in the
EEZ to be falsely treated as inside the 12 NM territorial-waters carve-out,
suppressing the uniform annual fishing ban disclosure.
"""
from __future__ import annotations

from datetime import date
import pytest

from orca.agents.geospatial import distance_to_shore_nm, fishing_ban_status


def test_distance_to_shore_near_imbl_measures_to_indian_coast_not_border():
    """At 8.60 N, 79.10 E (Gulf of Mannar near IMBL):
    - Distance to treaty line / EEZ edge was ~3.1 NM
    - Distance to Indian shore is ~34 NM (well beyond 12 NM)
    """
    shore_nm = distance_to_shore_nm(8.60, 79.10)
    assert shore_nm is not None
    assert shore_nm > 30.0, f"shore distance was {shore_nm} NM; should be > 30 NM, not ~3.1 NM to IMBL"
    assert shore_nm < 45.0


def test_distance_to_shore_inshore_points():
    """Inshore points along the coast should measure < 12 NM."""
    # ~2 NM off Veraval (West coast)
    veraval_shore = distance_to_shore_nm(20.90, 70.30)
    assert veraval_shore is not None
    assert veraval_shore < 5.0

    # ~4 NM off Chennai (East coast)
    chennai_shore = distance_to_shore_nm(13.08, 80.38)
    assert chennai_shore is not None
    assert chennai_shore < 6.0


def test_distance_to_shore_on_land():
    """Points on land should return 0.0 NM."""
    # Chennai city center
    chennai_land = distance_to_shore_nm(13.08, 80.27)
    assert chennai_land == 0.0


def test_fishing_ban_applies_near_imbl_during_east_coast_ban():
    """During the east coast ban (15 Apr - 14 Jun), a vessel at 8.60 N, 79.10 E
    is in the EEZ beyond 12 NM of shore. The central ban MUST apply here.
    Under the old defect G2, applies_here was False because edge was 3.1 NM.
    """
    ban = fishing_ban_status(8.60, 79.10, when=date(2026, 5, 1))
    if not ban.get("available"):
        pytest.skip("Fishing ban rules not on disk")

    assert ban["in_ban_period"] is True
    assert ban["coast"] == "east"
    # G2 core assertion: applies_here is now True because distance from Indian shore > 12 NM
    assert ban["applies_here"] is True, "central ban must apply in EEZ beyond 12 NM of Indian shore"
    assert "uniform ban is in force in the EEZ beyond 12 NM" in ban["note"]
    assert ban["distance_from_shore_nm"] > 12.0


def test_fishing_ban_exempts_inshore_waters():
    """Inside territorial waters (< 12 NM from shore), the central ban defers to state notification."""
    # Veraval inshore on 1 July (during west coast ban 1 Jun - 31 Jul)
    ban = fishing_ban_status(20.90, 70.30, when=date(2026, 7, 1))
    if not ban.get("available"):
        pytest.skip("Fishing ban rules not on disk")

    assert ban["in_ban_period"] is True
    assert ban["coast"] == "west"
    assert ban["applies_here"] is False, "inshore waters (< 12 NM) must be carved out to state MFRA"
    assert "state" in ban["note"].lower()
    assert ban["distance_from_shore_nm"] < 12.0


def test_fishing_ban_status_backward_compatibility_keys():
    """fishing_ban_status returns both distance_from_shore_nm and distance_to_nearest_eez_edge_nm."""
    ban = fishing_ban_status(8.60, 79.10, when=date(2026, 5, 1))
    if not ban.get("available"):
        pytest.skip("Fishing ban rules not on disk")

    assert "distance_from_shore_nm" in ban
    assert "distance_to_nearest_eez_edge_nm" in ban
    assert ban["distance_from_shore_nm"] == ban["distance_to_nearest_eez_edge_nm"]
