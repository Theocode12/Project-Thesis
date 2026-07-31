from unittest.mock import MagicMock, patch

import pytest

from edge_detector_service import EdgeDetectorService
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
        "processing_time_ms": 3.0,
    }
    return metrics


@pytest.fixture
def service(mock_detector, mock_mqtt_service, mock_metrics):
    return EdgeDetectorService(
        detector=mock_detector,
        mqtt_service=mock_mqtt_service,
        metrics=mock_metrics,
    )


class TestEdgeDetectorServiceStartStop:

    def test_start_connects_and_subscribes(self, service, mock_mqtt_service):
        service.start()

        mock_mqtt_service.connect.assert_called_once()
        mock_mqtt_service.subscribe.assert_called_once_with(
            MQTTOPIC.SENSOR_RAW, service.handle_sample
        )
        mock_mqtt_service.start.assert_called_once()
        assert service.running is True

    def test_stop_disconnects(self, service, mock_mqtt_service):
        service.start()
        service.stop()

        assert service.running is False
        mock_mqtt_service.stop.assert_called_once()


class TestEdgeDetectorServiceHandleSample:

    def test_extracts_payload_and_detects(self, service, mock_detector):
        payload = {
            "payload": {"sample": {"sensor": 1}}
        }
        service.handle_sample(payload)
        mock_detector.detect.assert_called_once_with({"sensor": 1})

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
            "timestamp": "2026-01-01T00:00:00+00:00",
            "payload": {
                "sample": {
                    "faultNumber": 1,
                    "simulationRun": 3,
                    "sample": 50,
                },
                "sg_metrics": {"dummy": True},
            },
        }
        service.handle_sample(payload)

        mock_metrics.start_processing.assert_called_once_with(
            received_at="2026-01-01T00:00:00+00:00"
        )
        mock_metrics.snapshot.assert_called_once()

        assert mock_mqtt_service.publish.call_count == 1
        call_args = mock_mqtt_service.publish.call_args[0]
        assert call_args[0] == MQTTOPIC.ANOMALY_DETECTED
        event = call_args[1]
        assert event["source"] == "edge-detector"
        assert event["payload"]["sample"]["sample"] == 50
        assert event["payload"]["sg_metrics"] == {"dummy": True}
        assert event["payload"]["ed_metrics"] == {
            "container": {"cpu_percent": 20.0},
            "processing_time_ms": 3.0,
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
