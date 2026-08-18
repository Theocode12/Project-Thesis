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
            "detector",
            collector=make_mock_collector(),
        ).metrics_key == "det_metrics"
        assert ServiceMetrics(
            "classifier",
            collector=make_mock_collector(),
        ).metrics_key == "cl_metrics"
        assert ServiceMetrics(
            "classifier",
            collector=make_mock_collector(),
        ).metrics_key == "cl_metrics"

    def test_unknown_service_falls_back_to_name(self):
        metrics = ServiceMetrics(
            "custom-service",
            collector=make_mock_collector(),
        )
        assert metrics.metrics_key == "custom_service_metrics"


class TestServiceMetricsProcessing:

    def test_snapshot_includes_processing_timestamps(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing()

        snapshot = metrics.snapshot()

        assert snapshot["processing_started_at"] is not None
        assert snapshot["processing_ended_at"] is not None
        assert (
            snapshot["processing_ended_at"]
            >= snapshot["processing_started_at"]
        )
        assert "processing_time_ms" not in snapshot
        assert "processed_at" not in snapshot
        assert snapshot["container"] == {"cpu_percent": 10.0}

    def test_mark_records_named_timestamp(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing()

        value = metrics.mark("inference_started_at")

        snapshot = metrics.snapshot()
        assert snapshot["inference_started_at"] == value
        assert snapshot["inference_started_at"] is not None

    def test_mark_returns_timestamp_value(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing()

        started = metrics.mark("inference_started_at")
        ended = metrics.mark("inference_ended_at")

        assert ended >= started

    def test_received_at_included_when_provided(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing(received_at=1000.0)

        snapshot = metrics.snapshot()

        assert snapshot["received_at"] == 1000.0

    def test_received_at_cleared_after_snapshot(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing(received_at=1000.0)
        metrics.snapshot()
        metrics.start_processing()

        snapshot = metrics.snapshot()

        assert "received_at" not in snapshot

    def test_mark_reset_after_snapshot(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )
        metrics.start_processing()
        metrics.mark("inference_started_at")
        metrics.snapshot()

        metrics.start_processing()
        snapshot = metrics.snapshot()

        assert "inference_started_at" not in snapshot

    def test_snapshot_without_processing_start_has_no_end_timestamp(self):
        metrics = ServiceMetrics(
            "sensor-generator",
            collector=make_mock_collector(),
        )

        snapshot = metrics.snapshot()

        assert "processing_started_at" not in snapshot
        assert "processing_ended_at" not in snapshot

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
