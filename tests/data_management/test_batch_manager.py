from unittest.mock import MagicMock, patch

import pytest

from batch_manager import BatchManager


class TestBatchManagerInit:

    def test_default_values(self):
        bm = BatchManager()
        assert bm.target_batch_count == 10
        assert bm.min_interval == 2.0
        assert bm.max_interval == 30.0
        assert bm.buffer_size == 0
        assert bm.current_interval == 30.0

    def test_custom_values(self):
        bm = BatchManager(
            target_batch_count=5, min_interval=1.0, max_interval=15.0
        )
        assert bm.target_batch_count == 5
        assert bm.min_interval == 1.0
        assert bm.max_interval == 15.0

    def test_buffer_empty_on_init(self):
        bm = BatchManager()
        assert bm.should_flush() is False
        assert bm.flush() == []

    def test_get_rate_zero_on_init(self):
        bm = BatchManager()
        assert bm.get_rate() == 0.0


class TestBatchManagerAddSample:

    def test_add_sample_increases_buffer(self):
        bm = BatchManager()
        bm.add_sample({"a": 1})
        assert bm.buffer_size == 1

    def test_add_multiple_samples(self):
        bm = BatchManager()
        for i in range(5):
            bm.add_sample({"i": i})
        assert bm.buffer_size == 5

    def test_add_sample_records_timestamp(self):
        bm = BatchManager()
        with patch("time.time", return_value=1000.0):
            bm.add_sample({"a": 1})
        assert bm._timestamps == [1000.0]

    def test_add_sample_prunes_old_timestamps(self):
        bm = BatchManager()
        with patch("time.time") as mock_time:
            mock_time.return_value = 0.0
            bm.add_sample({"a": 1})
            mock_time.return_value = 10.0
            bm.add_sample({"b": 2})
            mock_time.return_value = 100.0
            bm.add_sample({"c": 3})
        assert bm._timestamps == [100.0]


class TestBatchManagerInterval:

    def test_single_sample_uses_max_interval(self):
        bm = BatchManager()
        with patch("time.time", return_value=1000.0):
            bm.add_sample({"a": 1})
        assert bm.current_interval == bm.max_interval

    def test_two_samples_same_time_uses_max_interval(self):
        bm = BatchManager()
        with patch("time.time", return_value=1000.0):
            bm.add_sample({"a": 1})
            bm.add_sample({"b": 2})
        assert bm.current_interval == bm.max_interval

    def test_rate_calculates_correct_interval(self):
        bm = BatchManager(target_batch_count=10)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            bm.add_sample({"a": 1})
            mock_time.return_value = 1004.0
            bm.add_sample({"b": 2})
        assert bm.current_interval == 20.0

    def test_interval_clamps_to_min(self):
        bm = BatchManager(target_batch_count=10, min_interval=2.0)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            bm.add_sample({"a": 1})
            mock_time.return_value = 1000.1
            bm.add_sample({"b": 2})
        assert bm.current_interval == 2.0

    def test_interval_clamps_to_max(self):
        bm = BatchManager(target_batch_count=10, max_interval=30.0)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            bm.add_sample({"a": 1})
            mock_time.return_value = 1100.0
            bm.add_sample({"b": 2})
        interval = 10 / (2 / 100)
        assert interval > 30.0
        assert bm.current_interval == 30.0

    def test_ten_samples_interval_updates(self):
        bm = BatchManager(target_batch_count=10)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            for i in range(10):
                bm.add_sample({"i": i})
                mock_time.return_value += 0.5
            assert bm.current_interval == 4.5


class TestBatchManagerGetRate:

    def test_zero_samples(self):
        bm = BatchManager()
        assert bm.get_rate() == 0.0

    def test_one_sample(self):
        bm = BatchManager()
        with patch("time.time", return_value=1000.0):
            bm.add_sample({"a": 1})
        assert bm.get_rate() == 0.0

    def test_two_samples(self):
        bm = BatchManager()
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            bm.add_sample({"a": 1})
            mock_time.return_value = 1002.0
            bm.add_sample({"b": 2})
        assert bm.get_rate() == 1.0

    def test_multiple_samples(self):
        bm = BatchManager()
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            for i in range(5):
                bm.add_sample({"i": i})
                mock_time.return_value += 1.0
        assert bm.get_rate() == 1.25


class TestBatchManagerShouldFlush:

    def test_false_when_buffer_empty(self):
        bm = BatchManager()
        with patch("time.time", return_value=1000.0):
            assert bm.should_flush() is False

    def test_false_before_interval(self):
        bm = BatchManager(target_batch_count=10)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            bm._last_flush = 1000.0
            bm._current_interval = 5.0
            bm.add_sample({"a": 1})
            mock_time.return_value = 1002.0
            assert bm.should_flush() is False

    def test_true_after_interval(self):
        bm = BatchManager(target_batch_count=10)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            bm._last_flush = 1000.0
            bm._current_interval = 5.0
            for i in range(10):
                bm.add_sample({"i": i})
                mock_time.return_value += 0.5
            mock_time.return_value = 1005.0
            assert bm.should_flush() is True

    def test_false_right_at_flush_boundary(self):
        bm = BatchManager(target_batch_count=10)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            bm._last_flush = 1000.0
            bm._current_interval = 5.0
            bm.add_sample({"a": 1})
            mock_time.return_value = 1004.999
            assert bm.should_flush() is False


class TestBatchManagerFlush:

    def test_flush_returns_buffered_samples(self):
        bm = BatchManager()
        bm.add_sample({"a": 1})
        bm.add_sample({"b": 2})
        batch = bm.flush()
        assert batch == [{"a": 1}, {"b": 2}]

    def test_flush_clears_buffer(self):
        bm = BatchManager()
        bm.add_sample({"a": 1})
        bm.flush()
        assert bm.buffer_size == 0

    def test_flush_resets_last_flush(self):
        bm = BatchManager()
        bm.add_sample({"a": 1})
        with patch("time.time", return_value=2000.0):
            bm.flush()
        assert bm._last_flush == 2000.0

    def test_flush_empty_buffer_returns_empty(self):
        bm = BatchManager()
        assert bm.flush() == []

    def test_flush_and_rebuffer(self):
        bm = BatchManager()
        bm.add_sample({"a": 1})
        bm.flush()
        bm.add_sample({"b": 2})
        assert bm.buffer_size == 1
        assert bm.flush() == [{"b": 2}]

    def test_should_flush_false_after_flush(self):
        bm = BatchManager(target_batch_count=10)
        with patch("time.time") as mock_time:
            mock_time.return_value = 1000.0
            bm._last_flush = 1000.0
            bm._current_interval = 5.0
            bm.add_sample({"a": 1})
            bm.flush()
            mock_time.return_value = 1002.0
            assert bm.should_flush() is False


class TestBatchManagerThreadSafety:

    def test_concurrent_add_and_flush(self):
        import threading

        bm = BatchManager()
        errors = []

        def adder():
            try:
                for _ in range(100):
                    bm.add_sample({"i": _})
            except Exception as e:
                errors.append(e)

        def flusher():
            try:
                for _ in range(20):
                    bm.flush()
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=adder),
            threading.Thread(target=flusher),
            threading.Thread(target=adder),
            threading.Thread(target=flusher),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent access: {errors}"
