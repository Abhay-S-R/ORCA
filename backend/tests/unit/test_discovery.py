from orca.agents.discovery import SOURCE_REGISTRY, select_best_source


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
