from unittest.mock import patch

from shared.container_metrics import (
    ContainerMetricsCollector,
    ContainerMetricsSnapshot,
)


class TestContainerMetricsSnapshot:

    def test_snapshot_returns_dataclass(self):
        collector = ContainerMetricsCollector()
        snapshot = collector.snapshot()
        assert isinstance(snapshot, ContainerMetricsSnapshot)

    def test_snapshot_to_dict_has_all_fields(self):
        collector = ContainerMetricsCollector()
        snapshot = collector.snapshot().to_dict()

        assert set(snapshot.keys()) == {
            "cgroup_version",
            "cpu_percent",
            "cpu_time_seconds",
            "cpu_cores",
            "memory_used_bytes",
            "memory_limit_bytes",
            "memory_percent",
            "uptime_seconds",
            "process_count",
        }

    def test_cpu_percent_computed_from_delta(self):
        collector = ContainerMetricsCollector()
        collector._prev_cpu_usage_usec = 1_000_000
        collector._prev_wall = 100.0

        with patch.object(
            collector,
            "_read_cpu_usage_usec",
            return_value=3_000_000,
        ):
            with patch(
                "shared.container_metrics.time.monotonic",
                side_effect=[101.0, 101.0],
            ):
                with patch.object(
                    collector,
                    "_read_cpu_quota_cores",
                    return_value=1.0,
                ):
                    snapshot = collector.snapshot()

        assert snapshot.cpu_percent == 200.0

    def test_cpu_time_seconds_from_usage(self):
        collector = ContainerMetricsCollector()

        with patch.object(
            collector,
            "_read_cpu_usage_usec",
            return_value=5_000_000,
        ):
            snapshot = collector.snapshot()

        assert snapshot.cpu_time_seconds == 5.0

    def test_stale_window_resets_baseline(self):
        collector = ContainerMetricsCollector()
        collector._prev_cpu_usage_usec = 0
        collector._prev_wall = 0.0

        with patch.object(
            collector,
            "_read_cpu_usage_usec",
            return_value=1_000_000,
        ):
            with patch(
                "shared.container_metrics.time.monotonic",
                side_effect=[30.0, 30.0],
            ):
                snapshot = collector.snapshot()

        assert snapshot.cpu_percent == 0.0
        assert collector._prev_wall == 30.0

    def test_memory_percent_when_limit_known(self):
        collector = ContainerMetricsCollector()

        with patch.object(
            collector,
            "_read_memory_used_bytes",
            return_value=500,
        ):
            with patch.object(
                collector,
                "_read_memory_limit_bytes",
                return_value=1000,
            ):
                snapshot = collector.snapshot()

        assert snapshot.memory_used_bytes == 500
        assert snapshot.memory_limit_bytes == 1000
        assert snapshot.memory_percent == 50.0

    def test_memory_percent_none_when_no_limit(self):
        collector = ContainerMetricsCollector()

        with patch.object(
            collector,
            "_read_memory_used_bytes",
            return_value=500,
        ):
            with patch.object(
                collector,
                "_read_memory_limit_bytes",
                return_value=None,
            ):
                snapshot = collector.snapshot()

        assert snapshot.memory_percent is None

    def test_uptime_falls_back_to_monotonic(self):
        collector = ContainerMetricsCollector()

        with patch.object(
            collector,
            "_read_container_uptime",
            return_value=None,
        ):
            snapshot = collector.snapshot()

        assert snapshot.uptime_seconds >= 0
