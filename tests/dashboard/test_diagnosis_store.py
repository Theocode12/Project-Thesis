from unittest.mock import MagicMock

import pytest

from diagnosis_store import (
    DiagnosisController,
    DiagnosisStore,
    MAX_RESULTS,
)
from mqtt_client import DashboardClient
from shared.mqtt_topics import MQTTOPIC


def make_status_envelope(
    running=True,
    model_loaded=True,
    model="Neural Network",
    classes_available=21,
    classifications_processed=120,
    batch_count=30,
    classification_rate=9.5,
    avg_processing_time_ms=3.0,
    queue_depth=2,
    last_fault_number=4,
    last_diagnosis="fault_4",
    last_confidence=1.0,
    cpu_percent=12.5,
    memory_used_bytes=41_000_000,
):
    return {
        "source": "classifier",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "status": {
                "running": running,
                "model_loaded": model_loaded,
                "model": model,
                "classes_available": classes_available,
                "classifications_processed": classifications_processed,
                "batch_count": batch_count,
                "classification_rate": classification_rate,
                "avg_processing_time_ms": avg_processing_time_ms,
                "queue_depth": queue_depth,
                "last_fault_number": last_fault_number,
                "last_diagnosis": last_diagnosis,
                "last_confidence": last_confidence,
            },
            "cl_metrics": {
                "container": {
                    "cpu_percent": cpu_percent,
                    "memory_used_bytes": memory_used_bytes,
                },
            },
        },
    }


def make_result_envelope(
    batch_id="batch_test123456",
    diagnosis="fault_4",
    fault_number=4,
    confidence=0.95,
    model="Neural Network",
    sample_count=6,
):
    return {
        "source": "classifier",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "batch_id": batch_id,
            "diagnosis": diagnosis,
            "fault_number": fault_number,
            "model": model,
            "confidence": confidence,
            "sample_count": sample_count,
            "prediction_counts": {4: 6},
            "meta": {
                "ed_metrics": {"inference_ended_at": 1000.003},
                "event_audit": [],
            },
            "cl_metrics": {
                "received_at": 1000.0,
                "inference_started_at": 1000.001,
                "inference_ended_at": 1000.004,
            },
        },
    }


def make_request_envelope(batch_id="batch_test123456"):
    return {
        "source": "orchestrator",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "batch": [{"faultNumber": 4, "xmeas_1": 1.0}],
            "meta": {"batch_id": batch_id},
        },
    }


class TestDiagnosisStoreStatus:

    def test_handle_status_stores_telemetry(self):
        store = DiagnosisStore()
        store.handle_status(make_status_envelope())

        assert store.running is True
        assert store.model_loaded is True
        assert store.model == "Neural Network"
        assert store.classes_available == 21
        assert store.queue_depth == 2
        assert store.classifications_processed == 120
        assert store.batch_count == 30
        assert store.classification_rate == 9.5
        assert store.avg_processing_time_ms == 3.0
        assert store.last_fault_number == 4
        assert store.last_diagnosis == "fault_4"
        assert store.last_confidence == 1.0

    def test_handle_status_records_runtime_series(self):
        store = DiagnosisStore()
        store.handle_status(
            make_status_envelope(
                cpu_percent=10.0, memory_used_bytes=20_000_000, avg_processing_time_ms=2.0
            )
        )
        store.handle_status(
            make_status_envelope(
                cpu_percent=15.0, memory_used_bytes=25_000_000, avg_processing_time_ms=4.0
            )
        )

        runtime = store.recent_runtime()
        assert [p["value"] for p in runtime["cpu"]] == [10.0, 15.0]
        assert [p["value"] for p in runtime["memory"]] == [20_000_000, 25_000_000]
        assert [p["value"] for p in runtime["latency"]] == [2.0, 4.0]

    def test_status_transitions_log_lifecycle_events(self):
        store = DiagnosisStore()
        store.handle_status(make_status_envelope(running=False))
        store.handle_status(make_status_envelope(running=True))

        texts = [e["text"] for e in store.recent_actions()]
        assert "Service stopped" in texts
        assert "Service started" in texts

    def test_model_load_logs_event(self):
        store = DiagnosisStore()
        store.handle_status(make_status_envelope(model_loaded=False))
        store.handle_status(make_status_envelope(model_loaded=True))

        texts = [e["text"] for e in store.recent_actions()]
        assert "Model loaded" in texts

    def test_runtime_series_trims(self):
        store = DiagnosisStore()
        from diagnosis_store import MAX_RUNTIME_POINTS

        for _ in range(MAX_RUNTIME_POINTS + 10):
            store.handle_status(make_status_envelope())

        runtime = store.recent_runtime()
        assert len(runtime["cpu"]) == MAX_RUNTIME_POINTS
        assert len(runtime["latency"]) == MAX_RUNTIME_POINTS


class TestDiagnosisStoreResult:

    def test_handle_result_preserves_audit_metadata(self):
        store = DiagnosisStore()
        store.handle_result(make_result_envelope())

        result = store.latest_diagnosis()
        assert result["meta"]["ed_metrics"]["inference_ended_at"] == 1000.003
        assert result["cl_metrics"]["received_at"] == 1000.0

    def test_handle_result_stores_latest(self):
        store = DiagnosisStore()
        store.handle_result(make_result_envelope())

        latest = store.latest_diagnosis()
        assert latest["batch_id"] == "batch_test123456"
        assert latest["diagnosis"] == "fault_4"
        assert latest["fault_number"] == 4
        assert latest["confidence"] == 0.95
        assert latest["model"] == "Neural Network"

    def test_handle_result_logs_events(self):
        store = DiagnosisStore()
        store.handle_result(make_result_envelope(diagnosis="fault_7"))

        texts = [e["text"] for e in store.recent_actions()]
        assert texts[0] == "Classification completed | fault_7"
        assert "MQTT result published" in texts

    def test_results_trim_to_max(self):
        store = DiagnosisStore()
        for i in range(MAX_RESULTS + 10):
            store.handle_result(
                make_result_envelope(batch_id=f"batch_{i}")
            )

        assert len(store.recent_results()) == MAX_RESULTS
        assert store.latest["batch_id"] == f"batch_{MAX_RESULTS + 9}"


class TestDiagnosisStoreRequest:

    def test_handle_request_logs_event(self):
        store = DiagnosisStore()
        store.handle_request(make_request_envelope(batch_id="batch_test123456"))

        texts = [e["text"] for e in store.recent_actions()]
        assert "Diagnosis request received | batch_test123456" in texts

    def test_handle_request_logs_without_batch_id(self):
        store = DiagnosisStore()
        store.handle_request(make_request_envelope(batch_id=None))

        texts = [e["text"] for e in store.recent_actions()]
        assert "Diagnosis request received" in texts


class TestDiagnosisStoreLatest:

    def test_latest_none_without_data(self):
        store = DiagnosisStore()
        assert store.latest_diagnosis() is None

    def test_latest_prefers_result_over_heartbeat(self):
        store = DiagnosisStore()
        store.handle_status(make_status_envelope())
        store.handle_result(
            make_result_envelope(diagnosis="fault_7", fault_number=7)
        )

        latest = store.latest_diagnosis()
        assert latest["fault_number"] == 7
        assert latest["diagnosis"] == "fault_7"

    def test_latest_falls_back_to_heartbeat(self):
        store = DiagnosisStore()
        store.handle_status(make_status_envelope())

        latest = store.latest_diagnosis()
        assert latest["fault_number"] == 4
        assert latest["diagnosis"] == "fault_4"
        assert latest["confidence"] == 1.0


class TestDiagnosisStoreReset:

    def test_reset_clears_statistics_and_history(self):
        store = DiagnosisStore()
        store.handle_status(make_status_envelope())
        store.handle_result(make_result_envelope())

        store.reset()

        assert store.classifications_processed == 0
        assert store.batch_count == 0
        assert store.classification_rate == 0.0
        assert store.avg_processing_time_ms is None
        assert store.queue_depth == 0
        assert store.latest is None
        assert store.recent_results() == []
        assert store.recent_runtime()["cpu"] == []
        assert store.recent_runtime()["latency"] == []
        assert store.latest_diagnosis() is None

    def test_reset_keeps_action_log(self):
        store = DiagnosisStore()
        store.handle_status(make_status_envelope())

        store.reset()

        assert len(store.recent_actions()) > 0


class TestDiagnosisController:

    @pytest.fixture
    def controller(self):
        mqtt_service = MagicMock()
        client = DashboardClient(mqtt_service=mqtt_service)
        store = DiagnosisStore()
        return DiagnosisController(store, client), mqtt_service, store

    def test_send_start(self, controller):
        command, mqtt_service, _ = controller
        command.send_start()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "cl_start"},
        )

    def test_send_stop(self, controller):
        command, mqtt_service, _ = controller
        command.send_stop()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "cl_stop"},
        )

    def test_send_reset(self, controller):
        command, mqtt_service, _ = controller
        command.send_reset()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "cl_reset"},
        )

    def test_send_reset_clears_store(self, controller):
        command, _, store = controller
        store.handle_status(make_status_envelope())

        command.send_reset()

        assert store.classifications_processed == 0

    def test_commands_log_actions(self, controller):
        command, _, store = controller
        command.send_start()
        command.send_stop()

        texts = [e["text"] for e in store.recent_actions()]
        assert texts[0] == "Classifier stop sent"
        assert "Classifier start sent" in texts
