from unittest.mock import MagicMock

import pytest

from detection_store import (
    DetectionController,
    DetectionStore,
    MAX_DETECTIONS,
)
from mqtt_client import DashboardClient
from shared.mqtt_topics import MQTTOPIC


def make_anomaly_envelope(
    metric="reconstruction_error",
    value=1.5,
    fault=3,
    run=4,
):
    return {
        "source": "detector",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "anomaly": True,
            "reason": "threshold exceeded",
            "metric": metric,
            "value": value,
            "fault": fault,
            "simulationRun": run,
            "sample": {"xmeas_1": 1.5},
            "sg_metrics": {},
        "det_metrics": {"container": {"cpu_percent": 5.0}},
        },
    }


def make_status_envelope(
    detection_enabled=True,
    model_loaded=True,
    threshold=0.05,
    samples_processed=10,
    inference_rate=9.5,
    reconstruction_error=0.02,
    avg_processing_time_ms=3.0,
    cpu_percent=12.5,
    memory_used_bytes=41_000_000,
):
    return {
        "source": "detector",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "status": {
                "running": True,
                "detection_enabled": detection_enabled,
                "model_loaded": model_loaded,
                "threshold": threshold,
                "samples_processed": samples_processed,
                "inference_rate": inference_rate,
                "reconstruction_error": reconstruction_error,
                "avg_processing_time_ms": avg_processing_time_ms,
            },
        "det_metrics": {
                "container": {
                    "cpu_percent": cpu_percent,
                    "memory_used_bytes": memory_used_bytes,
                },
            },
        },
    }


def make_decision_envelope(decision="normal", anomaly_ratio=0.02):
    return {
        "source": "orchestrator",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "decision": decision,
            "anomaly_ratio": anomaly_ratio,
            "anomaly_rate": 0.5,
            "confidence": anomaly_ratio,
            "anomaly_count": 2,
            "window_seconds": 10.0,
        },
    }


class TestDetectionStore:

    def test_handle_anomaly_stores_detection(self):
        store = DetectionStore()
        store.handle_anomaly(make_anomaly_envelope())

        detections = store.recent_detections()
        assert len(detections) == 1
        assert detections[0]["metric"] == "reconstruction_error"
        assert detections[0]["value"] == 1.5
        assert detections[0]["fault"] == 3
        assert detections[0]["run"] == 4
        assert detections[0]["anomaly"] is True

    def test_latest_detection_tracks_last(self):
        store = DetectionStore()
        store.handle_anomaly(make_anomaly_envelope(value=1.0))
        store.handle_anomaly(make_anomaly_envelope(value=2.0))

        assert store.latest_detection()["value"] == 2.0

    def test_recent_detections_ordered_oldest_first(self):
        store = DetectionStore()
        store.handle_anomaly(make_anomaly_envelope(value=1.0))
        store.handle_anomaly(make_anomaly_envelope(value=2.0))

        values = [d["value"] for d in store.recent_detections()]
        assert values == [1.0, 2.0]

    def test_detections_trim_to_max(self):
        store = DetectionStore()
        for _ in range(MAX_DETECTIONS + 10):
            store.handle_anomaly(make_anomaly_envelope())

        assert len(store.recent_detections()) == MAX_DETECTIONS

    def test_handle_anomaly_logs_action(self):
        store = DetectionStore()
        store.handle_anomaly(make_anomaly_envelope(metric="z_score", value=2.5))

        actions = store.recent_actions()
        assert actions[0]["kind"] == "detect"
        assert "z_score" in actions[0]["text"]
        assert actions[1]["kind"] == "stream"
        assert "published" in actions[1]["text"]

    def test_empty_store(self):
        store = DetectionStore()
        assert store.recent_detections() == []
        assert store.latest_detection() is None
        assert store.recent_actions() == []


class TestDetectionStoreStatus:

    def test_handle_detector_status_stores_telemetry(self):
        store = DetectionStore()
        store.handle_detector_status(make_status_envelope())

        assert store.detection_enabled is True
        assert store.model_loaded is True
        assert store.threshold == 0.05
        assert store.samples_processed == 10
        assert store.inference_rate == 9.5
        assert store.avg_processing_time_ms == 3.0

    def test_handle_detector_status_records_score_history(self):
        store = DetectionStore()
        store.handle_detector_status(
            make_status_envelope(reconstruction_error=0.02)
        )
        store.handle_detector_status(
            make_status_envelope(reconstruction_error=0.09)
        )

        scores = store.recent_scores()
        assert len(scores) == 2
        assert [s["value"] for s in scores] == [0.02, 0.09]
        assert scores[0]["anomaly"] is False
        assert scores[1]["anomaly"] is True

    def test_handle_detector_status_records_runtime_series(self):
        store = DetectionStore()
        store.handle_detector_status(
            make_status_envelope(cpu_percent=10.0, memory_used_bytes=20_000_000)
        )
        store.handle_detector_status(
            make_status_envelope(cpu_percent=15.0, memory_used_bytes=25_000_000)
        )

        runtime = store.recent_runtime()
        assert [p["value"] for p in runtime["cpu"]] == [10.0, 15.0]
        assert [p["value"] for p in runtime["memory"]] == [20_000_000, 25_000_000]
        assert [p["value"] for p in runtime["latency"]] == [3.0, 3.0]

    def test_status_transitions_log_lifecycle_events(self):
        store = DetectionStore()
        store.handle_detector_status(
            make_status_envelope(detection_enabled=False)
        )
        store.handle_detector_status(
            make_status_envelope(detection_enabled=True)
        )

        texts = [e["text"] for e in store.recent_actions()]
        assert "Detector stopped" in texts
        assert "Detector started" in texts

    def test_threshold_change_logs_event(self):
        store = DetectionStore()
        store.handle_detector_status(make_status_envelope(threshold=0.05))
        store.handle_detector_status(make_status_envelope(threshold=0.08))

        texts = [e["text"] for e in store.recent_actions()]
        assert any("Threshold updated to 0.08" in t for t in texts)

    def test_model_reload_logs_event(self):
        store = DetectionStore()
        store.handle_detector_status(make_status_envelope(model_loaded=False))
        store.handle_detector_status(make_status_envelope(model_loaded=True))

        texts = [e["text"] for e in store.recent_actions()]
        assert "Model reloaded" in texts

    def test_score_history_trims(self):
        store = DetectionStore()
        from detection_store import MAX_SCORE_POINTS

        for _ in range(MAX_SCORE_POINTS + 10):
            store.handle_detector_status(make_status_envelope())

        assert len(store.recent_scores()) == MAX_SCORE_POINTS


class TestDetectionStoreDecision:

    def test_handle_decision_maps_risk(self):
        store = DetectionStore()
        for decision, expected in (
            ("normal", "LOW"),
            ("uncertain", "MEDIUM"),
            ("anomaly", "HIGH"),
        ):
            store.handle_decision(make_decision_envelope(decision=decision))
            assert store.risk == expected

    def test_handle_decision_stores_ratio(self):
        store = DetectionStore()
        store.handle_decision(make_decision_envelope(anomaly_ratio=0.25))

        assert store.anomaly_rate_percent() == 25.0
        assert store.latest_decision["decision"] == "normal"

    def test_anomaly_rate_none_without_decision(self):
        store = DetectionStore()
        assert store.anomaly_rate_percent() is None

    def test_risk_change_logs_event(self):
        store = DetectionStore()
        store.handle_decision(make_decision_envelope(decision="normal"))
        store.handle_decision(make_decision_envelope(decision="anomaly"))

        texts = [e["text"] for e in store.recent_actions()]
        assert "Risk level HIGH" in texts


class TestDetectionController:

    @pytest.fixture
    def controller(self):
        mqtt_service = MagicMock()
        client = DashboardClient(mqtt_service=mqtt_service)
        store = DetectionStore()
        return DetectionController(store, client), mqtt_service, store

    def test_send_start(self, controller):
        command, mqtt_service, _ = controller
        command.send_start()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "det_start"},
        )

    def test_send_stop(self, controller):
        command, mqtt_service, _ = controller
        command.send_stop()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "det_stop"},
        )

    def test_send_reset(self, controller):
        command, mqtt_service, _ = controller
        command.send_reset()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "det_reset"},
        )

    def test_commands_log_actions(self, controller):
        command, _, store = controller
        command.send_start()
        command.send_stop()

        texts = [e["text"] for e in store.recent_actions()]
        assert texts[0] == "Detection stop sent"
        assert "Detection start sent" in texts
