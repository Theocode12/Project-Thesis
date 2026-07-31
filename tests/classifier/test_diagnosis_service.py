import time
from unittest.mock import MagicMock

import pytest

from diagnosis_service import DiagnosisService
from shared.mqtt_topics import MQTTOPIC


@pytest.fixture
def mock_classifier():
    classifier = MagicMock()
    classifier.predict.return_value = {
        "fault_number": 7,
        "diagnosis": "fault_7",
        "model": "heuristic",
        "confidence": 0.8,
        "sample_count": 4,
        "prediction_counts": {7: 4},
    }
    classifier.model = "heuristic"
    return classifier


@pytest.fixture
def mock_mqtt_service():
    return MagicMock()


@pytest.fixture
def mock_metrics():
    metrics = MagicMock()
    metrics.snapshot.return_value = {"dummy": True}
    return metrics


@pytest.fixture
def service(mock_classifier, mock_mqtt_service, mock_metrics):
    return DiagnosisService(
        classifier=mock_classifier,
        mqtt_service=mock_mqtt_service,
        metrics=mock_metrics,
    )


def sample_payload(batch_id="batch_test123456"):
    return {
        "batch": [
            {"faultNumber": 7, "xmeas_1": 1.0},
            {"faultNumber": 7, "xmeas_1": 2.0},
        ],
        "meta": {
            "batch_id": batch_id,
            "window_start": "2026-01-01T00:00:00+00:00",
        },
    }


class TestDiagnosisServiceSubmit:

    def test_submit_returns_meta_batch_id(
        self, service, mock_mqtt_service
    ):
        batch_id = service.submit(sample_payload())

        assert batch_id == "batch_test123456"

    def test_submit_generates_batch_id_when_missing(
        self, service, mock_mqtt_service
    ):
        batch_id = service.submit(sample_payload(batch_id=None))

        assert batch_id.startswith("batch_")

    def test_submit_returns_immediately(
        self, service, mock_mqtt_service
    ):
        start = time.time()
        service.submit(sample_payload())
        elapsed = time.time() - start

        assert elapsed < 0.1
        mock_mqtt_service.publish.assert_not_called()


class TestDiagnosisServiceProcess:

    def test_publishes_prediction_result(
        self,
        service,
        mock_classifier,
        mock_mqtt_service,
        mock_metrics,
    ):
        service._process("batch_test123456", sample_payload())

        mock_classifier.predict.assert_called_once()
        mock_metrics.start_processing.assert_called_once()
        mock_metrics.snapshot.assert_called_once()

        topic, envelope = mock_mqtt_service.publish.call_args[0]
        assert topic == MQTTOPIC.CLASSIFICATION_RESULT
        assert envelope["source"] == "classifier"

        result = envelope["payload"]
        assert result["batch_id"] == "batch_test123456"
        assert result["diagnosis"] == "fault_7"
        assert result["fault_number"] == 7
        assert result["model"] == "heuristic"
        assert result["confidence"] == 0.8
        assert result["sample_count"] == 4
        assert result["prediction_counts"] == {7: 4}
        assert result["meta"]["batch_id"] == "batch_test123456"
        assert result["classifier_metrics"] == {"dummy": True}

    def test_publishes_unknown_on_classifier_error(
        self,
        service,
        mock_classifier,
        mock_mqtt_service,
    ):
        mock_classifier.predict.side_effect = Exception("crashed")

        service._process("batch_x", sample_payload())

        result = published_payload(mock_mqtt_service)
        assert result["diagnosis"] == "unknown"
        assert result["fault_number"] is None
        assert result["confidence"] == 0.0
        assert result["sample_count"] == 2
        assert result["prediction_counts"] == {}

    def test_empty_batch(
        self, mock_mqtt_service, mock_metrics
    ):
        from classifier import HeuristicClassifier

        service = DiagnosisService(
            classifier=HeuristicClassifier(),
            mqtt_service=mock_mqtt_service,
            metrics=mock_metrics,
        )
        payload = {"batch": [], "meta": {"batch_id": "batch_empty"}}

        service._process("batch_empty", payload)

        result = published_payload(mock_mqtt_service)
        assert result["diagnosis"] == "unknown"
        assert result["sample_count"] == 0


class TestDiagnosisServiceWorker:

    def test_worker_processes_enqueued_job(
        self,
        service,
        mock_mqtt_service,
    ):
        service.start()
        try:
            service.submit(sample_payload())
            _wait_for(
                lambda: mock_mqtt_service.publish.call_count > 0
            )

            result = published_payload(mock_mqtt_service)
            assert result["batch_id"] == "batch_test123456"
            assert result["diagnosis"] == "fault_7"
        finally:
            service.stop()

    def test_start_stop_idempotent(
        self,
        service,
        mock_mqtt_service,
    ):
        service.start()
        service.start()
        service.stop()
        service.stop()


def published_payload(mock_mqtt_service) -> dict:
    topic, envelope = mock_mqtt_service.publish.call_args[0]
    assert topic == MQTTOPIC.CLASSIFICATION_RESULT
    return envelope["payload"]


def _wait_for(condition, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for condition")
