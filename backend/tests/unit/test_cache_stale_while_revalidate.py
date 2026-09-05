"""Stale-while-revalidate (Architecture §9.14, phase4 plan §2.4) — scoped to
non-safety-gating sources only. `orca_cache(..., stale_ok=True)` must return
the last cached value immediately once the ":fresh" marker has expired,
without blocking on a fetch; `stale_ok` unset (every safety-path source)
must behave exactly as before — a miss past TTL always blocks on a fetch.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from orca.cache import orca_cache


def test_stale_ok_serves_old_value_without_blocking_when_fresh_marker_expired():
    fake_redis = MagicMock()
    # ":fresh" marker gone (expired), value key still within the hard ceiling.
    fake_redis.get.side_effect = lambda key: None if key.endswith(":fresh") else b'{"sst_c": 27.5}'
    fetch = MagicMock(return_value={"sst_c": 99.0}, __name__="fetch")

    with patch("orca.cache.redis_client", return_value=fake_redis):
        wrapped = orca_cache("some_stale_source", stale_ok=True)(fetch)
        result = wrapped(8.8, 78.14)

    assert result == {"sst_c": 27.5}  # the stale value, not a fresh fetch
    time.sleep(0.05)  # background refresh thread gets a moment to run
    fetch.assert_called_once_with(8.8, 78.14)  # refresh happened, just not on this call's return path


def test_non_stale_ok_source_blocks_on_a_fresh_fetch_when_marker_expired():
    fake_redis = MagicMock()
    fake_redis.get.side_effect = lambda key: None if key.endswith(":fresh") else b'{"wave_height_m": 1.0}'
    fetch = MagicMock(return_value={"wave_height_m": 2.5}, __name__="fetch")

    with patch("orca.cache.redis_client", return_value=fake_redis):
        wrapped = orca_cache("open_meteo")(fetch)  # stale_ok defaults False — safety-path shape
        result = wrapped(8.8, 78.14)

    assert result == {"wave_height_m": 2.5}  # never the stale value
    fetch.assert_called_once_with(8.8, 78.14)


def test_stale_ok_still_returns_fresh_value_directly_when_marker_present():
    fake_redis = MagicMock()
    fake_redis.get.return_value = b'{"sst_c": 27.5}'  # both fresh marker and value present
    fetch = MagicMock(return_value={"sst_c": 99.0}, __name__="fetch")

    with patch("orca.cache.redis_client", return_value=fake_redis):
        wrapped = orca_cache("some_stale_source", stale_ok=True)(fetch)
        result = wrapped(8.8, 78.14)

    assert result == {"sst_c": 27.5}
    fetch.assert_not_called()
