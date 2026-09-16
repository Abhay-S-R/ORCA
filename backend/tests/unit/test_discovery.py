from orca.agents.discovery import (
    FALLBACK_CASCADES,
    SOURCE_REGISTRY,
    select_best_source,
    select_source_with_fallback,
)


def test_picks_freshest_tier1_source() -> None:
    picked = select_best_source("wave_height")
    assert picked is not None
    assert picked.source.id == "open_meteo_marine"
    assert "Tier 1" in picked.reason


def test_reason_string_is_human_readable() -> None:
    picked = select_best_source("bathymetry")
    assert picked is not None
    assert picked.reason  # non-empty
    assert picked.source.dataset in picked.reason


def test_unknown_data_type_returns_none() -> None:
    assert select_best_source("nonexistent_type") is None


def test_registry_has_no_duplicate_ids() -> None:
    ids = [s.id for s in SOURCE_REGISTRY]
    assert len(ids) == len(set(ids))


def test_full_catalog_covers_all_four_tiers() -> None:
    tiers = {s.authority_tier for s in SOURCE_REGISTRY}
    assert tiers == {"TIER1", "TIER2", "TIER3"}
    assert len(SOURCE_REGISTRY) >= 20  # full master-list catalog, not the Phase-1 seed


def test_fallback_cascade_ids_all_resolve() -> None:
    ids = {s.id for s in SOURCE_REGISTRY}
    for primary, chain in FALLBACK_CASCADES.items():
        assert primary in ids
        for fid in chain:
            assert fid in ids, f"{primary} cascades to unknown source {fid}"


def test_source_decision_narrates_a_comparison() -> None:
    d = select_source_with_fallback("chlorophyll")
    assert d is not None
    assert d.chosen.dataset in d.narrative
    assert d.narrative.endswith(".")


def test_source_decision_falls_down_the_declared_cascade_when_primary_down() -> None:
    d = select_source_with_fallback("chlorophyll", down=("mosdac_open_chl",))
    assert d is not None
    assert d.chosen.id == "nasa_ocean_color"  # the declared §12.1 fallback
    assert "fallback" in d.narrative.lower()


def test_source_decision_none_when_nothing_covers_type() -> None:
    assert select_source_with_fallback("teleportation") is None


# --- local_catalog: an index is not the data -----------------------------

def test_local_catalog_marks_index_only_sources_as_not_held():
    from orca.agents.discovery import local_catalog

    granules = local_catalog("nasa_ocean_color")
    assert granules and all(g["held_locally"] is False for g in granules)
    assert all(g["granule"] for g in granules)

    # The INCOIS grids ARE on disk — same call, opposite flag, plus the
    # licence line that is recorded nowhere else.
    ww3 = local_catalog("incois_osf_ww3")
    assert ww3 and ww3[0]["held_locally"] is True
    assert "CC-BY" in ww3[0]["license"]

    # A source with no local index returns [], not a guess.
    assert local_catalog("soi_tide_tables") == []
    assert local_catalog("no_such_source") == []
