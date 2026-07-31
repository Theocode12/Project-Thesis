from unittest.mock import MagicMock

from shared.service_metrics import ServiceMetrics


def make_mock_collector(container_dict=None):
    collector = MagicMock()
    snapshot = collector.snapshot.return_value
    snapshot.to_dict.return_value = (
        container_dict or {"cpu_percent": 10.0}
    )
    return collector


class TestServiceMetricsKey:

    def test_sensor_generator_prefix(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        assert metrics.metrics_key == "sg_metrics"

    def test_other_service_prefixes(self):
        assert ServiceMetrics(
            "edge-detector",
            collector=make_mock_collector(),
        ).metrics_key == "ed_metrics"
        assert ServiceMetrics(
            "cloud-classifier",
            collector=make_mock_collector(),
        ).metrics_key == "cc_metrics"

    def test_unknown_service_falls_back_to_name(self):
        metrics = ServiceMetrics(
            "custom-service",
            collector=make_mock_collector(),
        )
        assert metrics.metrics_key == "custom_service_metrics"


class TestServiceMetricsProcessing:

    def test_end_processing_returns_none_when_not_started(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        assert metrics.end_processing() is None

    def test_end_processing_returns_milliseconds(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing()
        result = metrics.end_processing()
        assert result is not None
        assert result >= 0

    def test_snapshot_includes_processing_time(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing()

        snapshot = metrics.snapshot()

        assert snapshot["processing_time_ms"] is not None
        assert "processed_at" in snapshot
        assert snapshot["container"] == {"cpu_percent": 10.0}

    def test_received_at_included_when_provided(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing(
            received_at="2026-01-01T00:00:00+00:00"
        )

        snapshot = metrics.snapshot()

        assert (
            snapshot["received_at"]
            == "2026-01-01T00:00:00+00:00"
        )

    def test_received_at_cleared_after_snapshot(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing(
            received_at="2026-01-01T00:00:00+00:00"
        )
        metrics.snapshot()
        metrics.start_processing()

        snapshot = metrics.snapshot()

        assert "received_at" not in snapshot

    def test_extra_metrics_merged(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing()

        snapshot = metrics.snapshot(
            extra={"stream_interval": 0.1}
        )

        assert snapshot["stream_interval"] == 0.1


class TestServiceMetricsWrap:

    def test_wrap_builds_data_and_metrics(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing()

        result = metrics.wrap(
            data_key="sample",
            data={"XMEAS_1": 1.0},
        )

        assert result["sample"] == {"XMEAS_1": 1.0}
        assert "sg_metrics" in result
        assert result["sg_metrics"]["container"] == {
            "cpu_percent": 10.0
        }
