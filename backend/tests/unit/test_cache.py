from unittest.mock import MagicMock, patch

import pytest

from orca.cache import DEFAULT_TTL_SECONDS, TTL_SECONDS, cache_stats, orca_cache


@pytest.fixture(autouse=True)
def _reset_stats():
    cache_stats()  # no-op touch; stats persist across tests intentionally like the real module
    yield


def test_ttl_table_matches_source_cadence():
    assert TTL_SECONDS["open_meteo"] == 3600
    assert TTL_SECONDS["pfz_advisory"] == 172800
    assert TTL_SECONDS["ww3_forecast"] == 21600
    assert TTL_SECONDS["boundary_geojson"] == 604800


def test_unknown_source_uses_default_ttl():
    assert "some_new_source" not in TTL_SECONDS
    # exercised indirectly via orca_cache below; the constant itself is public
    assert DEFAULT_TTL_SECONDS == 1800


def test_cache_miss_calls_real_fetch_and_stores_with_correct_ttl():
    fake_redis = MagicMock()
    fake_redis.get.return_value = None
    fetch = MagicMock(return_value={"wave_height_m": 1.2}, __name__="fetch")

    with patch("orca.cache._redis_client", return_value=fake_redis):
        wrapped = orca_cache("open_meteo")(fetch)
        result = wrapped(8.8, 78.14)

    assert result == {"wave_height_m": 1.2}
    fetch.assert_called_once_with(8.8, 78.14)
    args, _kwargs = fake_redis.setex.call_args
    assert args[1] == 3600  # open_meteo's cadence-aware TTL


def test_cache_hit_returns_stored_value_without_calling_real_fetch():
    fake_redis = MagicMock()
    fake_redis.get.return_value = b'{"wave_height_m": 1.2}'
    fetch = MagicMock(return_value={"wave_height_m": 999}, __name__="fetch")

    with patch("orca.cache._redis_client", return_value=fake_redis):
        wrapped = orca_cache("open_meteo")(fetch)
        result = wrapped(8.8, 78.14)

    assert result == {"wave_height_m": 1.2}
    fetch.assert_not_called()


def test_unreachable_redis_falls_through_to_real_fetch_silently():
    fetch = MagicMock(return_value={"wave_height_m": 1.2}, __name__="fetch")

    with patch("orca.cache._redis_client", side_effect=ConnectionError("no redis")):
        wrapped = orca_cache("open_meteo")(fetch)
        result = wrapped(8.8, 78.14)

    assert result == {"wave_height_m": 1.2}
    fetch.assert_called_once()


def test_default_ttl_used_for_unlisted_source():
    fake_redis = MagicMock()
    fake_redis.get.return_value = None
    fetch = MagicMock(return_value={"x": 1}, __name__="fetch")

    with patch("orca.cache._redis_client", return_value=fake_redis):
        wrapped = orca_cache("some_new_source")(fetch)
        wrapped()

    args, _kwargs = fake_redis.setex.call_args
    assert args[1] == DEFAULT_TTL_SECONDS


def test_cache_stats_counts_hits_and_misses():
    fake_redis = MagicMock()
    fetch = MagicMock(return_value={"x": 1}, __name__="fetch")

    with patch("orca.cache._redis_client", return_value=fake_redis):
        wrapped = orca_cache("open_meteo")(fetch)

        fake_redis.get.return_value = None
        before = cache_stats()
        wrapped()
        after_miss = cache_stats()
        assert after_miss["misses"] == before["misses"] + 1

        fake_redis.get.return_value = b'{"x": 1}'
        wrapped()
        after_hit = cache_stats()
        assert after_hit["hits"] == after_miss["hits"] + 1
