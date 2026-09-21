"""P2.4 (`R-PS-5`, `R-AGENT-3`) — cross-source reconciliation, where it meets
the safety verdict.

`orca/reconcile.py` has its own `__main__` self-check for the arithmetic. This
file covers the part that matters more: what reconciliation does to
`risk_assessment.run`, which is the one module in the codebase where a bug is a
life-safety issue. Every assertion here is about direction — reconciliation may
only ever move a verdict *toward* caution, and may only ever move confidence
*down*.
"""
from __future__ import annotations

from orca import reconcile
from orca.agents import risk_assessment
from orca.contracts import Confidence


def _weather(**overrides):
    base = {
        "hourly": [{"time": "2026-09-20T06:00:00Z", "wave_height": 1.1, "wind_speed_10m": 4.0}],
        "dataset": "Open-Meteo Marine",
        "acquisition_timestamp": "2026-09-20T06:00:00Z",
        "freshness_minutes": 10,
        "lightning_active": False,
        "cyclone_alert": None,
        "confidence": Confidence(score="HIGH", rationale="live"),
    }
    base.update(overrides)
    return base


def _ocean(wave_m: float | None, wind_ms: float | None = 4.0, when: str = "2026-09-20T06:00:00Z"):
    if wave_m is None:
        return {}
    return {
        "osf_point_forecast": {
            "available": True,
            "wave": {
                "forecast_time": when,
                "significant_wave_height_m": wave_m,
                "wind_speed_ms": wind_ms,
            },
        }
    }


def _geo(imbl_nm: float = 12.0):
    return {
        "imbl_distance_nm": imbl_nm,
        "mpa_violation": False,
        "confidence": Confidence(score="MEDIUM", rationale="IMBL proxy boundary, not treaty line"),
    }


def _run(weather, ocean, geo=None):
    return risk_assessment.run({  # type: ignore[arg-type]
        "query_id": "t-recon",
        "reasoning_depth": "SHALLOW",
        "weather_data": weather,
        "ocean_data": ocean,
        "geospatial_data": geo if geo is not None else _geo(),
        "vessel_class": None,
    })


def test_a_divergence_makes_the_verdict_use_the_conservative_reading() -> None:
    """Open-Meteo says 1.1 m (GO); INCOIS OSF says 2.4 m, which is inside the
    CAUTION band for a small boat. The verdict must be computed from 2.4."""
    result = _run(_weather(), _ocean(2.4))
    assert result.outputs["go_no_go"] == "CAUTION", result.outputs
    rows = result.outputs["reconciliation"]
    wave = next(r for r in rows if r["variable"] == "wave_height_m")
    assert wave["status"] == "diverged"
    assert wave["used_value"] == 2.4


def test_agreeing_sources_leave_the_verdict_exactly_where_it_was() -> None:
    agree = _run(_weather(), _ocean(1.2))
    alone = _run(_weather(), {})
    assert agree.outputs["go_no_go"] == alone.outputs["go_no_go"] == "GO"
    wave = next(r for r in agree.outputs["reconciliation"] if r["variable"] == "wave_height_m")
    assert wave["status"] == "agree"
    assert wave["confidence_penalty"] is False


def test_readings_far_apart_in_time_are_not_treated_as_a_disagreement() -> None:
    """Two statements about different days are not a disagreement. This is the
    live case: the OSF point series on disk is a days-old extraction, and
    reporting it as a conflict would put a false sentence on every answer."""
    result = _run(_weather(), _ocean(2.4, when="2026-09-16T21:00:00Z"))
    wave = next(r for r in result.outputs["reconciliation"] if r["variable"] == "wave_height_m")
    assert wave["status"] == "not_comparable"
    assert wave["used_value"] == 1.1, "the primary stands when the pair cannot be compared"
    assert wave["confidence_penalty"] is False
    assert result.outputs["go_no_go"] == "GO"


def test_a_divergence_costs_exactly_one_confidence_tier_and_never_raises_one() -> None:
    clean = _run(_weather(), _ocean(1.2), _geo())
    diverged = _run(_weather(), _ocean(2.4), _geo())
    order = ("HIGH", "MEDIUM", "LOW_DATA")
    assert order.index(diverged.confidence.score) > order.index(clean.confidence.score)
    assert order.index(diverged.confidence.score) - order.index(clean.confidence.score) == 1


def test_a_missing_input_still_outranks_a_divergence_penalty() -> None:
    """LOW_DATA from a missing reading is already the floor; a divergence must
    not lift it, and the rationale must keep naming the missing input."""
    result = _run(_weather(hourly=[{"time": "2026-09-20T06:00:00Z", "wind_speed_10m": 4.0}]), _ocean(2.4))
    assert result.confidence.score == "LOW_DATA"
    assert "Missing required input" in result.confidence.rationale


def test_an_absent_second_source_reconciles_nothing_and_claims_nothing() -> None:
    result = _run(_weather(), {})
    assert result.outputs["reconciliation"] == []
    assert reconcile.penalty([]) is False


def test_either_lightning_source_saying_active_forces_the_no_go() -> None:
    """The one reconciliation that can change a verdict on its own. IMD's
    district nowcast sat in the same dict as the CAPE proxy, disagreeing, and
    nothing read it — the verdict came from the proxy alone."""
    weather = _weather(
        lightning_active=False,
        lightning_source_agreement="disagree",
        imd_nowcast={"lightning_flagged": True},
        imd_nowcast_dataset="IMD Damini",
    )
    result = _run(weather, {})
    assert result.outputs["go_no_go"] == "NO_GO"
    assert result.outputs["status"] == "DANGER"
    row = next(r for r in result.outputs["reconciliation"] if r["variable"] == "lightning_active")
    assert row["used_value"] is True and row["confidence_penalty"] is True


def test_an_expired_imd_snapshot_is_not_a_second_opinion() -> None:
    weather = _weather(lightning_source_agreement="single_source", imd_nowcast={"lightning_flagged": False})
    result = _run(weather, {})
    assert all(r["variable"] != "lightning_active" for r in result.outputs["reconciliation"])
    assert result.outputs["go_no_go"] == "GO"


def test_only_disagreements_become_sentences_on_the_card() -> None:
    result = _run(_weather(), _ocean(1.2))
    assert reconcile.statements(result.outputs["reconciliation"]) == []
    diverged = _run(_weather(), _ocean(2.4))
    said = reconcile.statements(diverged.outputs["reconciliation"])
    assert len(said) == 1
    assert "Using the higher. Confidence reduced." in said[0]


def test_reconciliation_never_reaches_the_verdict_through_an_llm() -> None:
    """Ground Rule 2 / `scripts/verify_ci_guards.py` guard 4. Asserted here as
    well as in CI because this is the change that first gave risk_assessment a
    reason to read ocean_data at all."""
    import ast

    # Parsed imports, not a substring scan: this module's own docstring
    # explains that it imports nothing from orca.llm, and a text search finds
    # that sentence and fails on it.
    with open(reconcile.__file__, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("orca.llm") for name in imported), imported


def test_a_second_source_too_old_to_compare_is_not_a_disclosure() -> None:
    """Found by looking at the running UI: the OSF point series on disk is days
    old, so `not_comparable` fired on every query and put two "75 h apart"
    banners above every answer. Nothing about the answer is degraded by a
    second opinion being unusable — it belongs in the panel, not above it."""
    result = _run(_weather(), _ocean(2.4, when="2026-09-16T21:00:00Z"))
    rows = result.outputs["reconciliation"]
    assert any(r["status"] == "not_comparable" for r in rows), "still recorded"
    assert reconcile.statements(rows) == [], "but never announced above the answer"
