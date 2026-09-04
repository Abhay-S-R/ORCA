"""Near-duplicate response cache (Architecture §9.1, phase4 plan §2.3) —
identical resolved params hit; a different location, even nearby, never
shares an entry; a Redis outage degrades to a cache miss rather than failing
the request.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from orca.query_cache import TTL_SECONDS, get, resolved_key, store


def test_identical_resolved_params_produce_the_same_key():
    k1 = resolved_key("Is it safe to go to sea?", 8.8012, 78.1401, "small_fishing", "fisherman", "SHALLOW")
    k2 = resolved_key("is it safe to go to sea?  ", 8.8012, 78.1401, "small_fishing", "fisherman", "SHALLOW")
    assert k1 == k2  # case/whitespace-insensitive, same location


def test_a_few_km_away_never_shares_a_key():
    # Thoothukudi vs. a point ~15 km south — same query text, different port.
    k1 = resolved_key("is it safe", 8.80, 78.14, None, None, None)
    k2 = resolved_key("is it safe", 8.66, 78.14, None, None, None)
    assert k1 != k2


def test_store_then_get_round_trips_through_the_fake_redis():
    fake_redis = MagicMock()
    store_ = {}
    fake_redis.setex.side_effect = lambda key, ttl, value: store_.__setitem__(key, (ttl, value))
    fake_redis.get.side_effect = lambda key: store_.get(key, (None, None))[1]

    key = resolved_key("is it safe", 8.8, 78.14, None, "fisherman", "SHALLOW")
    with patch("orca.query_cache.redis_client", return_value=fake_redis):
        assert get(key) is None
        store(key, {"final_english_response": "GO"})
        assert get(key) == {"final_english_response": "GO"}
        ttl_used = fake_redis.setex.call_args[0][1]
        assert ttl_used == TTL_SECONDS == 1800  # the architecture's own safety ceiling


def test_redis_outage_degrades_to_a_miss_not_an_error():
    with patch("orca.query_cache.redis_client", side_effect=ConnectionError("no redis")):
        assert get("orca:query_cache:whatever") is None  # no exception raised
