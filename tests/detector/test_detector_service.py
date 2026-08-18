from unittest.mock import MagicMock, patch

import time

import pytest

from detector_service import DetectorService
from shared.mqtt_topics import MQTTOPIC


@pytest.fixture
def mock_detector():
    detector = MagicMock()
    detector.detect.return_value = {
        "anomaly": False,
        "reconstruction_error": 0.001,
        "reason": None,
        "metric": "reconstruction_error",
        "value": 0.001,
    }
    return detector


@pytest.fixture
def mock_mqtt_service():
    return MagicMock()


@pytest.fixture
def mock_metrics():
    metrics = MagicMock()
    metrics.snapshot.return_value = {
        "container": {"cpu_percent": 20.0},
        "processing_started_at": 1000.0,
        "processing_ended_at": 1000.003,
        "inference_started_at": 1000.0,
        "inference_ended_at": 1000.003,
    }
    metrics.mark.side_effect = lambda *args, **kwargs: time.time()
    return metrics


@pytest.fixture
def service(mock_detector, mock_mqtt_service, mock_metrics):
    return DetectorService(
        detector=mock_detector,
        mqtt_service=mock_mqtt_service,
        metrics=mock_metrics,
    )


class TestDetectorServiceStartStop:

    def test_start_connects_and_subscribes(self, service, mock_mqtt_service):
        service.start()

        mock_mqtt_service.connect.assert_called_once()
        mock_mqtt_service.subscribe.assert_any_call(
            MQTTOPIC.SENSOR_RAW, service.handle_sample
        )
        mock_mqtt_service.subscribe.assert_any_call(
            MQTTOPIC.SYSTEM_CONTROL, service.handle_command
        )
        mock_mqtt_service.start.assert_called_once()
        assert service.running is True

    def test_stop_disconnects(self, service, mock_mqtt_service):
        service.start()
        service.stop()

        assert service.running is False
        mock_mqtt_service.stop.assert_called_once()


class TestDetectorServiceHandleCommand:

    def test_action_map_has_all_actions(self, service):
        assert set(service._action_map.keys()) == {
            "det_start", "det_stop", "det_reset"
        }

    def test_none_payload_does_nothing(self, service):
        service.handle_command(None)

        assert service.detection_enabled is True

    def test_unknown_action_does_nothing(self, service):
        service.handle_command({"action": "unknown"})

        assert service.detection_enabled is True

    def test_plain_start_action_is_ignored(self, service):
        service.handle_command({"action": "start"})

        assert service.detection_enabled is True

    def test_det_start_enables_detection(self, service):
        service.detection_enabled = False
        service.handle_command({"action": "det_start"})

        assert service.detection_enabled is True

    def test_det_stop_disables_detection(self, service):
        service.handle_command({"action": "det_stop"})

        assert service.detection_enabled is False

    def test_det_reset_clears_state(self, service, mock_mqtt_service):
        service.samples_processed = 10
        service._sample_times.append(time.time())
        service._latencies.append((time.time() - 0.002, time.time()))
        service._last_reconstruction_error = 0.9

        service.handle_command({"action": "det_reset"})

        assert service.samples_processed == 0
        assert len(service._sample_times) == 0
        assert len(service._latencies) == 0
        assert service._last_reconstruction_error is None

    def test_commands_publish_status(self, service, mock_mqtt_service):
        service.handle_command({"action": "det_start"})

        published = [
            call.args[0]
            for call in mock_mqtt_service.publish.call_args_list
        ]
        assert MQTTOPIC.DETECTOR_STATUS in published


class TestDetectorServiceHandleSample:

    def test_extracts_payload_and_detects(self, service, mock_detector):
        payload = {
            "payload": {"sample": {"sensor": 1}}
        }
        service.handle_sample(payload)
        mock_detector.detect.assert_called_once_with({"sensor": 1})

    def test_skips_sample_when_detection_disabled(
        self, service, mock_detector
    ):
        service.detection_enabled = False
        service.handle_sample({"payload": {"sample": {"sensor": 1}}})

        mock_detector.detect.assert_not_called()

    def test_skips_no_payload(self, service, mock_detector):
        service.handle_sample({})
        mock_detector.detect.assert_not_called()

    def test_skips_none_payload(self, service, mock_detector):
        service.handle_sample({"payload": None})
        mock_detector.detect.assert_not_called()

    def test_publishes_anomaly_when_detected(
        self, service, mock_detector, mock_mqtt_service, mock_metrics
    ):
        mock_detector.detect.return_value = {
            "anomaly": True,
            "reconstruction_error": 0.05,
            "reason": "reconstruction_error",
            "metric": "reconstruction_error",
            "value": 0.05,
        }

        payload = {
            "timestamp": 1000.0,
            "payload": {
                "sample": {
                    "faultNumber": 1,
                    "simulationRun": 3,
                    "sample": 50,
                },
                "sg_metrics": {"dummy": True},
            },
        }
        mock_metrics.snapshot.side_effect = (
            lambda extra=None: {
                **mock_metrics.snapshot.return_value,
                **(extra or {}),
            }
        )
        with patch("detector_service.time.time", return_value=2000.0):
            service.handle_sample(payload)

        mock_metrics.start_processing.assert_called_once_with(
            received_at=2000.0
        )
        mock_metrics.snapshot.assert_called_once_with(
            extra={"sensor_published_at": 1000.0}
        )

        assert mock_mqtt_service.publish.call_count == 1
        call_args = mock_mqtt_service.publish.call_args[0]
        assert call_args[0] == MQTTOPIC.ANOMALY_DETECTED
        event = call_args[1]
        assert event["source"] == "detector"
        assert event["payload"]["sample"]["sample"] == 50
        assert event["payload"]["sg_metrics"] == {"dummy": True}
        assert event["payload"]["det_metrics"] == {
            "container": {"cpu_percent": 20.0},
            "processing_started_at": 1000.0,
            "processing_ended_at": 1000.003,
            "inference_started_at": 1000.0,
            "inference_ended_at": 1000.003,
            "sensor_published_at": 1000.0,
        }

    def test_does_not_publish_when_no_anomaly(
        self, service, mock_mqtt_service, mock_metrics
    ):
        payload = {
            "payload": {"sample": {"sensor": 1}}
        }
        service.handle_sample(payload)
        mock_mqtt_service.publish.assert_not_called()
        mock_metrics.snapshot.assert_not_called()

    def test_handles_detector_exception(
        self, service, mock_detector, mock_mqtt_service
    ):
        mock_detector.detect.side_effect = Exception("detector crashed")

        payload = {
            "payload": {"sample": {"sensor": 1}}
        }
        service.handle_sample(payload)

        mock_mqtt_service.publish.assert_not_called()

    def test_records_processing_stats_per_sample(
        self, service, mock_detector
    ):
        service.handle_sample({"payload": {"sample": {"sensor": 1}}})
        service.handle_sample({"payload": {"sample": {"sensor": 2}}})

        assert service.samples_processed == 2
        assert service._last_reconstruction_error == 0.001
        assert len(service._latencies) == 2

    def test_does_not_count_samples_when_disabled(
        self, service, mock_detector
    ):
        service.detection_enabled = False
        service.handle_sample({"payload": {"sample": {"sensor": 1}}})

        assert service.samples_processed == 0


class TestDetectorServiceStatus:

    @pytest.fixture
    def service(self, mock_detector, mock_mqtt_service, mock_metrics):
        mock_metrics.wrap.side_effect = (
            lambda data_key, data, extra=None: {
                data_key: data,
                "det_metrics": mock_metrics.snapshot(),
            }
        )
        return DetectorService(
            detector=mock_detector,
            mqtt_service=mock_mqtt_service,
            metrics=mock_metrics,
        )

    def test_publish_status_publishes_telemetry(
        self, service, mock_mqtt_service
    ):
        service.running = True
        service.samples_processed = 5
        now = time.time()
        service._latencies.append((now - 0.002, now))

        service.publish_status()

        mock_mqtt_service.publish.assert_called_once()
        topic, message = mock_mqtt_service.publish.call_args[0]
        assert topic == MQTTOPIC.DETECTOR_STATUS
        assert message["source"] == "detector"

        status = message["payload"]["status"]
        assert status["running"] is True
        assert status["detection_enabled"] is True
        assert status["model_loaded"] is True
        assert status["samples_processed"] == 5
        assert status["avg_processing_time_ms"] == 2.0
        assert "threshold" in status
        assert "inference_rate" in status
        assert "reconstruction_error" in status
