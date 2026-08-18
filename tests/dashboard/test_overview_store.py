from datetime import UTC, datetime

import pytest

from detection_store import DetectionStore
from diagnosis_store import DiagnosisStore
from overview_store import (
    LATENCY_RETENTION_SECONDS,
    OverviewStore,
    MAX_LATENCY_POINTS,
)


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).isoformat()


def make_anomaly_envelope(sensor_ts: float, completed_ts: float):
    return {
        "source": "detector",
        "timestamp": iso(completed_ts),
        "payload": {
            "anomaly": True,
            "reason": "threshold exceeded",
            "metric": "reconstruction_error",
            "value": 1.5,
        "det_metrics": {"received_at": iso(sensor_ts)},
        },
    }


def make_anomaly_with_inference_timestamp(
    sensor_ts: float,
    inference_completed_ts: float,
    envelope_ts: float,
):
    envelope = make_anomaly_envelope(sensor_ts, envelope_ts)
    envelope["payload"]["det_metrics"]["inference_ended_at"] = (
        iso(inference_completed_ts)
    )
    return envelope


def make_anomaly_with_all_timestamps(
    sensor_published_ts: float,
    received_ts: float,
    inference_completed_ts: float,
    envelope_ts: float,
):
    envelope = make_anomaly_envelope(received_ts, envelope_ts)
    envelope["payload"]["det_metrics"].update({
        "sensor_published_at": iso(sensor_published_ts),
        "received_at": iso(received_ts),
        "inference_ended_at": iso(inference_completed_ts),
    })
    return envelope


def make_decision_envelope(
    decision_ts: float,
    decision: str = "anomaly",
    reported: bool = True,
    batch=None,
    batch_id: str = "batch_test123456",
    reporting_started_ts: float | None = None,
    cloud_payload_bytes: int = 1234,
):
    return {
        "source": "orchestrator",
        "timestamp": iso(decision_ts),
        "payload": {
            "batch_id": batch_id,
            "decision": decision,
            "reported": reported,
            "anomaly_ratio": 0.7,
            "anomaly_count": 70,
            "window_seconds": 10.0,
            "cloud_payload_bytes": cloud_payload_bytes,
            "or_metrics": {
                "reporting_started_at": iso(
                    reporting_started_ts
                    if reporting_started_ts is not None
                    else decision_ts
                )
            },
            "batch": batch if batch is not None else [
                {"xmeas_1": 1.5, "xmv_1": 2.5},
                {"xmeas_1": 1.6, "xmv_1": 2.6},
            ],
        },
    }


def make_result_envelope(
    result_ts: float,
    diagnosis: str = "fault_4",
    batch_id: str = "batch_test123456",
    meta=None,
):
    return {
        "source": "classifier",
        "timestamp": iso(result_ts),
        "payload": {
            "batch_id": batch_id,
            "diagnosis": diagnosis,
            "fault_number": 4,
            "confidence": 0.95,
            "sample_count": 6,
            "meta": meta or {},
        },
    }


class TestDetectionLatency:

    def test_latency_computed_from_timestamps(self):
        store = OverviewStore()
        store.handle_anomaly(make_anomaly_envelope(sensor_ts=100.0, completed_ts=100.012))

        points = store.recent_latencies()["detection"]
        assert len(points) == 1
        assert points[0]["ms"] == pytest.approx(12.0)

    def test_skips_without_sensor_timestamp(self):
        envelope = make_anomaly_envelope(100.0, 100.012)
        envelope["payload"]["det_metrics"] = {}
        store = OverviewStore()
        store.handle_anomaly(envelope)

        assert store.recent_latencies()["detection"] == []

    def test_skips_negative_latency(self):
        store = OverviewStore()
        store.handle_anomaly(make_anomaly_envelope(sensor_ts=200.0, completed_ts=100.0))

        assert store.recent_latencies()["detection"] == []

    def test_uses_inference_completion_timestamp(self):
        store = OverviewStore()
        store.handle_anomaly(
            make_anomaly_with_inference_timestamp(
                sensor_ts=100.0,
                inference_completed_ts=100.008,
                envelope_ts=100.012,
            )
        )

        points = store.recent_latencies()["detection"]
        assert points[0]["ms"] == pytest.approx(8.0)

    def test_detection_latency_uses_sensor_publication_timestamp(self):
        store = OverviewStore()
        store.handle_anomaly(
            make_anomaly_with_all_timestamps(
                sensor_published_ts=100.0,
                received_ts=100.005,
                inference_completed_ts=100.012,
                envelope_ts=100.013,
            )
        )

        points = store.recent_latencies()["detection"]
        assert points[0]["ms"] == pytest.approx(12.0)

    def test_stream_trims_to_cap(self):
        store = OverviewStore()
        for i in range(MAX_LATENCY_POINTS + 20):
            store.handle_anomaly(
                make_anomaly_envelope(sensor_ts=float(i), completed_ts=float(i) + 0.01)
            )

        points = store.recent_latencies()["detection"]
        assert len(points) == MAX_LATENCY_POINTS

    def test_latency_retention_is_time_based(self, monkeypatch):
        now = 10_000.0
        store = OverviewStore()
        history = [
            {"t": now - LATENCY_RETENTION_SECONDS - 1.0, "ms": 1.0},
            {"t": now - 1.0, "ms": 2.0},
        ]
        monkeypatch.setattr("overview_store.time.time", lambda: now)

        store._trim_latency(history)

        assert history == [{"t": now - 1.0, "ms": 2.0}]


class TestDiagnosisAndE2ELatency:

    def test_diagnosis_latency_uses_reporting_start(self):
        store = OverviewStore()
        store.handle_anomaly(make_anomaly_envelope(100.0, 100.012))
        store.handle_decision(
            make_decision_envelope(
                decision_ts=200.0,
                reporting_started_ts=199.900,
            )
        )
        store.handle_result(make_result_envelope(result_ts=200.035))

        lat = store.recent_latencies()
        assert lat["diagnosis"][0]["ms"] == pytest.approx(135.0)
        assert lat["e2e"][0]["ms"] == pytest.approx(100035.0)

    def test_result_without_pending_request_ignored(self):
        store = OverviewStore()
        store.handle_result(make_result_envelope(result_ts=200.0))

        assert store.recent_latencies()["diagnosis"] == []
        assert store.recent_latencies()["e2e"] == []

    def test_result_metadata_handles_result_before_decision(self):
        store = OverviewStore()
        store.handle_result(
            make_result_envelope(
                result_ts=200.035,
                meta={
                    "orchestrator_timestamps": {
                        "reporting_started_at": iso(199.900),
                    },
                    "event_audit": [{
                        "det_metrics": {
                            "sensor_published_at": iso(100.0),
                        },
                    }],
                },
            )
        )

        lat = store.recent_latencies()
        assert lat["diagnosis"][0]["ms"] == pytest.approx(135.0)
        assert lat["e2e"][0]["ms"] == pytest.approx(100035.0)

    def test_multiple_escalations_correlate_by_batch_id(self):
        store = OverviewStore()
        store.handle_anomaly(make_anomaly_envelope(100.0, 100.012))
        store.handle_decision(
            make_decision_envelope(
                decision_ts=200.0,
                batch_id="batch_a",
                reporting_started_ts=199.900,
            )
        )
        store.handle_decision(
            make_decision_envelope(
                decision_ts=210.0,
                batch_id="batch_b",
                reporting_started_ts=209.900,
            )
        )
        store.handle_result(
            make_result_envelope(result_ts=210.010, batch_id="batch_b")
        )
        store.handle_result(
            make_result_envelope(result_ts=200.020, batch_id="batch_a")
        )

        lat = store.recent_latencies()
        assert lat["diagnosis"][0]["ms"] == pytest.approx(110.0)
        assert lat["diagnosis"][1]["ms"] == pytest.approx(120.0)


class TestCloudCommunication:

    def test_bytes_accumulate_for_reported_escalations(self):
        store = OverviewStore()
        store.handle_decision(make_decision_envelope(decision_ts=200.0))
        store.handle_decision(make_decision_envelope(decision_ts=210.0))

        assert store.data_sent_to_cloud() > 0
        assert store.cloud_escalations() == 2

    def test_unreported_decisions_not_counted(self):
        store = OverviewStore()
        store.handle_decision(
            make_decision_envelope(decision_ts=200.0, reported=False)
        )

        assert store.cloud_escalations() == 0
        assert store.data_sent_to_cloud() == 0

    def test_empty_batch_counts_zero_bytes(self):
        store = OverviewStore()
        store.handle_decision(
            make_decision_envelope(
                decision_ts=200.0,
                batch=[],
                cloud_payload_bytes=0,
            )
        )

        assert store.data_sent_to_cloud() == 0
        assert store.cloud_escalations() == 1


class TestRiskState:

    def test_risk_updates_from_decision(self):
        store = OverviewStore()
        store.handle_decision(
            make_decision_envelope(decision_ts=200.0, decision="anomaly")
        )

        assert store.current_risk() == "HIGH"

    def test_risk_transition_logs_event(self):
        store = OverviewStore()
        store.handle_decision(
            make_decision_envelope(decision_ts=200.0, decision="normal")
        )
        store.handle_decision(
            make_decision_envelope(decision_ts=210.0, decision="anomaly")
        )

        texts = [e["text"] for e in store.recent_actions()]
        assert "Risk level HIGH" in texts
        assert "Risk level LOW" in texts


class TestSystemHealth:

    def test_critical_when_broker_down(self):
        store = OverviewStore()
        store.connected = False
        assert store.system_health()[0] == "CRITICAL"

    def test_warning_while_awaiting_telemetry(self):
        store = OverviewStore()
        store.connected = True
        assert store.system_health()[0] == "WARNING"

    def test_healthy_with_low_risk_and_telemetry(self):
        store = OverviewStore()
        store.connected = True
        store.handle_decision(
            make_decision_envelope(decision_ts=200.0, decision="normal")
        )
        label, tone = store.system_health()
        assert label == "HEALTHY"
        assert tone == "run"

    def test_warning_on_medium_risk(self):
        store = OverviewStore()
        store.connected = True
        store.handle_decision(
            make_decision_envelope(decision_ts=200.0, decision="uncertain")
        )
        assert store.system_health()[0] == "WARNING"

    def test_warning_when_queue_backed_up(self):
        store = OverviewStore()
        store.connected = True
        store.handle_decision(
            make_decision_envelope(decision_ts=200.0, decision="normal")
        )
        diagnosis = DiagnosisStore()
        diagnosis.queue_depth = 12
        store = OverviewStore(diagnosis_store=diagnosis)
        store.connected = True
        store.handle_decision(
            make_decision_envelope(decision_ts=200.0, decision="normal")
        )
        assert store.system_health()[0] == "WARNING"

    def test_warning_when_service_stopped(self):
        detection = DetectionStore()
        detection.detection_enabled = False
        store = OverviewStore(detection_store=detection)
        store.connected = True
        store.handle_decision(
            make_decision_envelope(decision_ts=200.0, decision="normal")
        )
        assert store.system_health()[0] == "WARNING"


class TestDeploymentMode:

    def test_unknown_when_unset(self, monkeypatch):
        monkeypatch.delenv("DEPLOYMENT_MODE", raising=False)
        assert OverviewStore().deployment_mode() == "UNKNOWN"

    def test_reads_env_normalised(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "hybrid")
        assert OverviewStore().deployment_mode() == "HYBRID"

    def test_invalid_env_falls_back_to_unknown(self, monkeypatch):
        monkeypatch.setenv("DEPLOYMENT_MODE", "edge-aws")
        assert OverviewStore().deployment_mode() == "UNKNOWN"


class TestRuntimeSummary:

    def test_reads_diagnosis_store_counters(self):
        diagnosis = DiagnosisStore()
        diagnosis.batch_count = 12
        diagnosis.queue_depth = 3
        store = OverviewStore(diagnosis_store=diagnosis)

        assert store.diagnosis_requests() == 12
        assert store.queue_depth() == 3

    def test_measurement_window_always_available(self):
        store = OverviewStore()
        assert store.measurement_window().endswith("s")
        assert store.uptime_str()
