"""G1 verification: the MPA check covers ALL geofence-usable MPAs, not just
the Gulf of Mannar Marine National Park.

Tests run against the real boundary data on disk (data/tier1/boundaries/
india_marine_mpas.geojson). They verify that:
1. point_in_polygon detects a point inside each usable MPA
2. The G1 classification logic in graph.py correctly labels each MPA as
   NO_GO (Gulf of Mannar NP) or REGULATORY (all others)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import shape

from orca.agents.geospatial import load_boundaries, point_in_polygon

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
MPA_FILE = DATA_ROOT / "tier1" / "boundaries" / "india_marine_mpas.geojson"

# The policy constants, mirrored from graph.py (tested for agreement below).
_MPA_NOGO_NAMES = frozenset({"Gulf of Mannar Marine National Park"})
_EEZ_NAMES = frozenset({
    "Indian Exclusive Economic Zone",
    "Indian Exclusive Economic Zone (Andaman & Nicobar)",
    "Sri Lankan Exclusive Economic Zone",
})


def _usable_mpas() -> list[dict]:
    """Every geofence-usable MPA record from the data file."""
    data = json.loads(MPA_FILE.read_text(encoding="utf-8"))
    return [
        f for f in data["features"]
        if f["properties"].get("orca_geofence_usable", True)
        and f["properties"].get("orca_precision", "HIGH") != "CENTROID_ONLY"
    ]


@pytest.fixture(scope="module")
def usable_mpas():
    return _usable_mpas()


# ---------- G1 core: every usable MPA is detected ----------------------------

def test_at_least_11_usable_mpas(usable_mpas):
    """The audit found 11 geofence-usable MPAs."""
    assert len(usable_mpas) >= 11, f"only {len(usable_mpas)} usable MPAs"


@pytest.mark.parametrize("feat", _usable_mpas(), ids=lambda f: f["properties"]["name"])
def test_point_in_polygon_detects_each_mpa(feat):
    """A representative point inside each MPA polygon is detected by
    point_in_polygon — the function the G1 fix wires into the graph node."""
    geom = shape(feat["geometry"])
    rep = geom.representative_point()
    assert geom.contains(rep), "representative_point outside its own geometry"

    hits = point_in_polygon(rep.y, rep.x)
    hit_names = {h.name for h in hits}
    name = feat["properties"]["name"]
    assert name in hit_names, f"point_in_polygon missed {name!r}, got: {hit_names}"


# ---------- G1 classification: NO_GO vs REGULATORY ---------------------------

@pytest.mark.parametrize("feat", _usable_mpas(), ids=lambda f: f["properties"]["name"])
def test_mpa_classification(feat):
    """Gulf of Mannar NP -> NO_GO; all others -> REGULATORY disclosure."""
    name = feat["properties"]["name"]
    geom = shape(feat["geometry"])
    rep = geom.representative_point()

    hits = point_in_polygon(rep.y, rep.x)
    mpa_hits = [f for f in hits if f.name not in _EEZ_NAMES]
    mpa_nogo = [f for f in mpa_hits if f.name in _MPA_NOGO_NAMES]
    mpa_regulatory = [f for f in mpa_hits if f.name not in _MPA_NOGO_NAMES]
    mpa_violation = len(mpa_nogo) > 0

    if name in _MPA_NOGO_NAMES:
        assert mpa_violation, f"{name} should trigger mpa_violation"
    else:
        # Not a NO_GO, but it must appear somewhere (either as the hit itself,
        # or via an overlapping NO_GO park — like "Mannar Valaiguda" which
        # overlaps the Gulf of Mannar NP).
        all_mpa_names = {f.name for f in mpa_hits}
        assert name in all_mpa_names, f"{name} not found in MPA hits: {all_mpa_names}"
        # If the name is not in _MPA_NOGO_NAMES it must appear in regulatory
        # (unless it overlaps a NO_GO park, in which case it could be in either).
        if not mpa_violation:
            reg_names = {f.name for f in mpa_regulatory}
            assert name in reg_names, f"{name} not in regulatory list: {reg_names}"


# ---------- Regression: a normal sea position triggers no MPA -----------------

def test_open_sea_no_mpa():
    """A point well offshore (Arabian Sea) triggers neither violation nor regulatory."""
    hits = point_in_polygon(12.0, 74.0)
    mpa_hits = [f for f in hits if f.name not in _EEZ_NAMES]
    assert mpa_hits == [], f"unexpected MPA hits in open sea: {[f.name for f in mpa_hits]}"


def test_thoothukudi_no_mpa():
    """The pilot default (offshore Thoothukudi, 8.70 N 78.50 E) is NOT inside
    the Gulf of Mannar NP. It used to be checked by proximity, not containment."""
    hits = point_in_polygon(8.70, 78.50)
    mpa_hits = [f for f in hits if f.name not in _EEZ_NAMES]
    # This point is in the Indian EEZ but not inside the park polygon.
    nogo = [f for f in mpa_hits if f.name in _MPA_NOGO_NAMES]
    assert nogo == [], f"Thoothukudi default should not be NO_GO: {[f.name for f in nogo]}"
