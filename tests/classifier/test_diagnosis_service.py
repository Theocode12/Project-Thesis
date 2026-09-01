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
    metrics.metrics_key = "cl_metrics"
    metrics.mark.side_effect = [1000.001, 1000.003]
    metrics.snapshot.return_value = {
        "dummy": True,
        "received_at": 1000.0,
        "processing_started_at": 1000.001,
        "inference_started_at": 1000.001,
        "inference_ended_at": 1000.003,
        "processing_ended_at": 1000.004,
    }
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
            "sg_metrics": {"stream_interval": 0.1},
            "det_metrics": {"inference_ended_at": 1000.003},
            "event_audit": [{
                "sg_metrics": {"stream_interval": 0.1},
                "det_metrics": {"inference_ended_at": 1000.003},
            }],
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
        assert result["meta"]["det_metrics"] == {
            "inference_ended_at": 1000.003
        }
        assert len(result["meta"]["event_audit"]) == 1
        assert result["cl_metrics"]["dummy"] is True
        assert result["cl_metrics"]["received_at"] == 1000.0
        assert result["cl_metrics"]["inference_started_at"] == 1000.001
        assert result["cl_metrics"]["inference_ended_at"] == 1000.003
        assert result["accuracy"] is None
        assert result["correct_count"] is None
        assert result["ground_truth_available"] is None

        extra = mock_metrics.snapshot.call_args.kwargs["extra"]
        assert extra["batch_id"] == "batch_test123456"
        assert extra["batch_size"] == 2
        assert "inference_ms" not in extra
        assert "queue_wait_ms" not in extra
        assert extra["accuracy"] is None

    def test_publishes_accuracy_from_predictor(
        self,
        service,
        mock_classifier,
        mock_mqtt_service,
        mock_metrics,
    ):
        mock_classifier.predict.return_value = {
            "fault_number": 7,
            "diagnosis": "fault_7",
            "model": "heuristic",
            "confidence": 0.8,
            "sample_count": 4,
            "prediction_counts": {7: 4},
            "accuracy": 0.75,
            "correct_count": 3,
            "ground_truth_available": 4,
        }

        service._process("batch_x", sample_payload())

        result = published_payload(mock_mqtt_service)
        assert result["accuracy"] == 0.75
        assert result["correct_count"] == 3
        assert result["ground_truth_available"] == 4

        extra = mock_metrics.snapshot.call_args.kwargs["extra"]
        assert extra["accuracy"] == 0.75
        assert extra["correct_count"] == 3
        assert extra["ground_truth_available"] == 4

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

    def test_empty_batch(self, mock_mqtt_service, mock_metrics):
        classifier = MagicMock()
        classifier.predict.return_value = {
            "fault_number": None,
            "diagnosis": "unknown",
            "confidence": 0.0,
            "sample_count": 0,
            "prediction_counts": {},
            "accuracy": None,
        }
        service = DiagnosisService(
            classifier=classifier,
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
                lambda: _classification_published(mock_mqtt_service)
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


class TestDiagnosisServiceStatus:

    def test_publishes_status_heartbeat(
        self,
        service,
        mock_mqtt_service,
    ):
        service.start()
        try:
            _wait_for(
                lambda: _status_published(mock_mqtt_service),
                timeout=5.0,
            )

            topic, envelope = _last_status_call(mock_mqtt_service)
            assert topic == MQTTOPIC.CLASSIFIER_STATUS
            assert envelope["source"] == "classifier"

            payload = envelope["payload"]
            assert payload["cl_metrics"]["container"] is not None
            status = payload["status"]
            assert status["running"] is True
            assert status["model"] == "heuristic"
            assert status["model_loaded"] is True
            assert status["batch_count"] == 0
            assert status["classifications_processed"] == 0
            assert status["queue_depth"] == 0
        finally:
            service.stop()

    def test_status_reflects_processed_batches(
        self,
        service,
        mock_mqtt_service,
    ):
        service.start()
        try:
            service.submit(sample_payload())
            _wait_for(
                lambda: _classification_published(mock_mqtt_service),
                timeout=5.0,
            )
            _wait_for(
                lambda: _status_batch_count(mock_mqtt_service) >= 1,
                timeout=5.0,
            )

            payload = _last_status_payload(mock_mqtt_service)
            assert payload["status"]["batch_count"] == 1
            assert payload["status"]["classifications_processed"] == 2
        finally:
            service.stop()


class TestDiagnosisServiceCommands:

    def test_cl_start_starts_worker(self, service):
        service._cmd_start({})
        try:
            assert service._started is True
        finally:
            service.stop()

    def test_cl_stop_stops_worker(self, service):
        service.start()
        service._cmd_stop({})

        assert service._started is False

    def test_cl_reset_clears_counters(
        self, service, mock_mqtt_service
    ):
        service._process("batch_x", sample_payload())
        assert service.batch_count == 1
        assert service.classifications_processed == 2

        service._cmd_reset({})

        assert service.batch_count == 0
        assert service.classifications_processed == 0
        assert service._last_prediction["fault_number"] is None
        assert service._last_prediction["diagnosis"] is None

    def test_handle_command_publishes_status(
        self, service, mock_mqtt_service
    ):
        service.handle_command({"action": "cl_start"})
        try:
            topic, envelope = _last_status_call(mock_mqtt_service)
            assert topic == MQTTOPIC.CLASSIFIER_STATUS
            assert envelope["payload"]["status"]["running"] is True
        finally:
            service.stop()

    def test_handle_command_unknown_action_ignored(self, service):
        service.handle_command({"action": "nope"})

        assert service._started is False

    def test_handle_command_requires_payload(self, service):
        service.handle_command(None)
        service.handle_command({})

        assert service._started is False


def published_payload(mock_mqtt_service) -> dict:
    for call in mock_mqtt_service.publish.call_args_list:
        if call.args[0] == MQTTOPIC.CLASSIFICATION_RESULT:
            return call.args[1]["payload"]
    raise AssertionError("No classification result published")


def _classification_published(mock_mqtt_service) -> bool:
    return any(
        call.args[0] == MQTTOPIC.CLASSIFICATION_RESULT
        for call in mock_mqtt_service.publish.call_args_list
    )


def _status_published(mock_mqtt_service) -> bool:
    return any(
        call.args[0] == MQTTOPIC.CLASSIFIER_STATUS
        for call in mock_mqtt_service.publish.call_args_list
    )


def _last_status_call(mock_mqtt_service):
    for call in mock_mqtt_service.publish.call_args_list:
        if call.args[0] == MQTTOPIC.CLASSIFIER_STATUS:
            last = call
    if "last" not in locals():
        raise AssertionError("No classifier status published")
    return last.args[0], last.args[1]


def _last_status_payload(mock_mqtt_service) -> dict:
    topic, envelope = _last_status_call(mock_mqtt_service)
    return envelope["payload"]


def _status_batch_count(mock_mqtt_service) -> int:
    try:
        payload = _last_status_payload(mock_mqtt_service)
    except AssertionError:
        return 0
    return payload["status"]["batch_count"]


def _wait_for(condition, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for condition")
