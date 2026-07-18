from unittest.mock import MagicMock, patch

import pytest

from cache_manager import CacheManager


@pytest.fixture
def mock_local_storage():
    return MagicMock()


@pytest.fixture
def mock_cloud_storage():
    return MagicMock()


@pytest.fixture
def cache_manager(mock_local_storage, mock_cloud_storage):
    return CacheManager(
        local_storage=mock_local_storage,
        cloud_storage=mock_cloud_storage,
        retry_interval=10.0,
        cleanup_interval=20.0,
        cleanup_max_age=3600,
    )


class TestCacheManagerRetry:

    def test_tick_no_pending_does_nothing(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {}
        with patch("time.time", return_value=100.0):
            cache_manager.tick()
        mock_cloud_storage.is_available.assert_not_called()

    def test_tick_retries_pending_when_cloud_available(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {
            "b1": {"count": 2},
        }
        mock_local_storage.read.return_value = [{"a": 1}, {"b": 2}]
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = True

        with patch("time.time", return_value=100.0):
            cache_manager.tick()

        mock_cloud_storage.store.assert_called_once_with(
            "b1", [{"a": 1}, {"b": 2}]
        )
        mock_local_storage.mark_synced.assert_called_once_with("b1")

    def test_tick_skips_when_cloud_unavailable(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {
            "b1": {"count": 1},
        }
        mock_cloud_storage.is_available.return_value = False

        with patch("time.time", return_value=100.0):
            cache_manager.tick()

        mock_cloud_storage.store.assert_not_called()
        mock_local_storage.mark_synced.assert_not_called()

    def test_tick_handles_store_failure(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {
            "b1": {"count": 1},
        }
        mock_local_storage.read.return_value = [{"a": 1}]
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = False

        with patch("time.time", return_value=100.0):
            cache_manager.tick()

        mock_local_storage.mark_synced.assert_not_called()

    def test_tick_handles_read_failure(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {
            "b1": {"count": 1},
        }
        mock_local_storage.read.return_value = None
        mock_cloud_storage.is_available.return_value = True

        with patch("time.time", return_value=100.0):
            cache_manager.tick()

        mock_cloud_storage.store.assert_not_called()

    def test_tick_multiple_pending_batches(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {
            "b1": {"count": 1},
            "b2": {"count": 2},
        }
        mock_local_storage.read.side_effect = [
            [{"a": 1}],
            [{"b": 1}, {"b": 2}],
        ]
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = True

        with patch("time.time", return_value=100.0):
            cache_manager.tick()

        assert mock_cloud_storage.store.call_count == 2
        assert mock_local_storage.mark_synced.call_count == 2


class TestCacheManagerCleanup:

    def test_tick_cleans_up_synced(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {}
        mock_local_storage.cleanup_synced.return_value = 2

        with patch("time.time", return_value=100.0):
            cache_manager._last_retry = 100.0
            cache_manager._last_cleanup = 0.0
            cache_manager.tick()

        mock_local_storage.cleanup_synced.assert_called_once_with(3600)

    def test_cleanup_logs_removed_count(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {}
        mock_local_storage.cleanup_synced.return_value = 3

        with patch("time.time", return_value=100.0):
            cache_manager._last_retry = 100.0
            cache_manager._last_cleanup = 0.0
            cache_manager.tick()

        mock_local_storage.cleanup_synced.assert_called_once_with(3600)


class TestCacheManagerIntervals:

    def test_respects_retry_interval(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {
            "b1": {"count": 1},
        }
        mock_local_storage.read.return_value = [{"a": 1}]
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = True

        with patch("time.time", return_value=100.0):
            cache_manager._last_retry = 95.0
            cache_manager.tick()

        mock_cloud_storage.store.assert_not_called()

    def test_retries_at_interval(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {
            "b1": {"count": 1},
        }
        mock_local_storage.read.return_value = [{"a": 1}]
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = True

        with patch("time.time", return_value=105.0):
            cache_manager._last_retry = 95.0
            cache_manager.tick()

        mock_cloud_storage.store.assert_called_once()

    def test_respects_cleanup_interval(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {}

        with patch("time.time", return_value=100.0):
            cache_manager._last_retry = 100.0
            cache_manager._last_cleanup = 90.0
            cache_manager.tick()

        mock_local_storage.cleanup_synced.assert_not_called()

    def test_cleans_at_interval(
        self, cache_manager, mock_local_storage, mock_cloud_storage
    ):
        mock_local_storage.get_pending_batches.return_value = {}
        mock_local_storage.cleanup_synced.return_value = 0

        with patch("time.time", return_value=100.0):
            cache_manager._last_retry = 100.0
            cache_manager._last_cleanup = 80.0
            cache_manager.tick()

        mock_local_storage.cleanup_synced.assert_called_once()
