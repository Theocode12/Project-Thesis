from unittest.mock import MagicMock, call, patch

import pytest

from orchestrator_service import OrchestratorService
from shared.mqtt_topics import MQTTOPIC


@pytest.fixture
def mock_decision_engine():
    engine = MagicMock()
    engine.window_seconds = 10.0
    return engine


@pytest.fixture
def mock_reporter():
    reporter = MagicMock()
    reporter.last_request_payload_bytes = 0
    return reporter


@pytest.fixture
def mock_mqtt_service():
    return MagicMock()


@pytest.fixture
def mock_metrics():
    return MagicMock()


@pytest.fixture
def service(
    mock_decision_engine,
    mock_reporter,
    mock_mqtt_service,
    mock_metrics,
):
    return OrchestratorService(
        decision_engine=mock_decision_engine,
        reporter=mock_reporter,
        mqtt_service=mock_mqtt_service,
        metrics=mock_metrics,
    )


def make_decision(
    decision="anomaly",
    ratio=0.9,
    count=9,
    batch=None,
):
    return {
        "batch_id": "batch_test123456",
        "decision": decision,
        "confidence": ratio,
        "window_start": "2026-01-01T00:00:00+00:00",
        "window_end": "2026-01-01T00:00:10+00:00",
        "window_seconds": 10.0,
        "anomaly_count": count,
        "total_samples": 10.0,
        "sensor_rate": 1.0,
        "anomaly_rate": 0.9,
        "anomaly_ratio": ratio,
        "batch": batch or [{"X": 1.0}],
        "batch_size": 1,
        "sg_metrics": {"stream_interval": 0.1},
        "det_metrics": {"inference_ended_at": 1000.003},
        "event_audit": [],
        "reported": False,
    }


class TestOrchestratorServiceInit:
    def test_action_map_has_all_actions(self, service):
        assert set(service._action_map.keys()) == {
            "start", "stop", "reset",
        }

    def test_evaluation_enabled_by_default(self, service):
        assert service.evaluation_enabled is True


class TestOrchestratorServiceStartStop:
    def test_start_subscribes_and_connects(
        self, service, mock_mqtt_service
    ):
        service.start()

        mock_mqtt_service.connect.assert_called_once()
        assert mock_mqtt_service.subscribe.call_args_list == [
            call(MQTTOPIC.ANOMALY_DETECTED, service.handle_anomaly),
            call(MQTTOPIC.SYSTEM_CONTROL, service.handle_command),
        ]
        mock_mqtt_service.start.assert_called_once()
        assert service.running is True

    def test_stop(self, service, mock_mqtt_service):
        service.start()
        service.stop()

        assert service.running is False
        mock_mqtt_service.stop.assert_called_once()


class TestOrchestratorServiceHandleCommand:
    def test_none_payload_does_nothing(self, service):
        service.handle_command(None)

        assert service.evaluation_enabled is True

    def test_unknown_action_does_nothing(self, service):
        service.handle_command({"action": "unknown"})

        assert service.evaluation_enabled is True

    def test_start_action_enables_evaluation(self, service):
        service.evaluation_enabled = False
        service.handle_command({"action": "start"})

        assert service.evaluation_enabled is True

    def test_stop_action_disables_evaluation(self, service):
        service.handle_command({"action": "stop"})

        assert service.evaluation_enabled is False

    def test_reset_action_clears_engine(
        self, service, mock_decision_engine
    ):
        service.handle_command({"action": "reset"})

        mock_decision_engine.reset.assert_called_once()


class TestOrchestratorServiceHandleAnomaly:
    def test_handle_anomaly_adds_to_engine(
        self, service, mock_decision_engine
    ):
        inner = {"sample": {"X": 1.0}, "fault": 7}
        service.handle_anomaly({"payload": inner})

        mock_decision_engine.add_anomaly.assert_called_once()
        actual = mock_decision_engine.add_anomaly.call_args.args[0]
        assert actual["sample"] == inner["sample"]
        assert actual["fault"] == inner["fault"]
        assert actual["edge_published_at"] is None
        assert isinstance(actual["orchestrator_received_at"], float)

    def test_handle_anomaly_drops_when_disabled(
        self, service, mock_decision_engine
    ):
        service.evaluation_enabled = False
        service.handle_anomaly({"payload": {"sample": {"X": 1.0}}})

        mock_decision_engine.add_anomaly.assert_not_called()

    def test_full_envelope_flow_at_one_hz_flags_anomaly(
        self,
        mock_reporter,
        mock_mqtt_service,
        mock_metrics,
    ):
        from decision_engine import DecisionEngine

        engine = DecisionEngine(
            window_seconds=10.0,
            high_ratio=0.5,
            low_ratio=0.1,
            fallback_stream_interval=0.1,
        )
        service = OrchestratorService(
            decision_engine=engine,
            reporter=mock_reporter,
            mqtt_service=mock_mqtt_service,
            metrics=mock_metrics,
        )

        envelope = {
            "source": "detector",
            "timestamp": "2026-08-06T13:43:24+00:00",
            "payload": {
                "anomaly": True,
                "reason": "threshold",
                "metric": "reconstruction_error",
                "value": 0.06,
                "fault": 4,
                "simulationRun": 476,
                "sample": {"faultNumber": 4},
                "sg_metrics": {"stream_interval": 1.0},
            "det_metrics": {},
            },
        }
        for _ in range(10):
            service.handle_anomaly(envelope)

        decision = engine.evaluate()
        assert decision["decision"] == "anomaly"
        assert decision["sensor_rate"] == 1.0
        assert decision["total_samples"] == 10.0
        assert decision["anomaly_ratio"] == 1.0
        assert decision["batch_size"] == 10


class TestOrchestratorServiceEvaluate:
    def test_publishes_decision(
        self, service, mock_decision_engine, mock_mqtt_service, mock_metrics
    ):
        mock_decision_engine.evaluate.return_value = make_decision()
        mock_metrics.snapshot.return_value = {"dummy": True}

        service._evaluate()

        published = mock_mqtt_service.publish.call_args[0]
        assert published[0] == MQTTOPIC.ORCHESTRATOR_DECISION
        envelope = published[1]
        assert envelope["source"] == "orchestrator"
        assert envelope["payload"]["batch_id"] == "batch_test123456"
        assert envelope["payload"]["decision"] == "anomaly"
        assert envelope["payload"]["batch_size"] == 1
        assert "batch" not in envelope["payload"]
        assert envelope["payload"]["or_metrics"] == {"dummy": True}
        assert envelope["payload"]["det_metrics"] == {
            "inference_ended_at": 1000.003
        }
        assert envelope["payload"]["cloud_payload_bytes"] == 0

    def test_reports_batch_when_anomaly(
        self, service, mock_decision_engine, mock_reporter
    ):
        batch = [{"X": 1.0}]
        mock_decision_engine.evaluate.return_value = make_decision(
            decision="anomaly", batch=batch
        )
        mock_reporter.report.return_value = True
        mock_reporter.last_request_payload_bytes = 1234

        service._evaluate()

        mock_reporter.report.assert_called_once()
        reported_batch = mock_reporter.report.call_args[0][0]
        assert reported_batch == batch
        meta = mock_reporter.report.call_args[1]["meta"]
        assert meta["batch_id"] == "batch_test123456"
        assert "det_metrics" in meta
        assert "event_audit" in meta
        assert "orchestrator_timestamps" in meta
        payload = service.mqtt_service.publish.call_args[0][1]["payload"]
        assert payload["cloud_payload_bytes"] == 1234

    def test_no_report_when_normal(
        self, service, mock_decision_engine, mock_reporter
    ):
        mock_decision_engine.evaluate.return_value = make_decision(
            decision="normal"
        )

        service._evaluate()

        mock_reporter.report.assert_not_called()

    def test_no_report_when_uncertain(
        self, service, mock_decision_engine, mock_reporter
    ):
        mock_decision_engine.evaluate.return_value = make_decision(
            decision="uncertain"
        )

        service._evaluate()

        mock_reporter.report.assert_not_called()

    def test_reported_flag_reflects_post(
        self, service, mock_decision_engine, mock_reporter, mock_mqtt_service
    ):
        mock_decision_engine.evaluate.return_value = make_decision()
        mock_reporter.report.return_value = True

        service._evaluate()

        payload = mock_mqtt_service.publish.call_args[0][1]["payload"]
        assert payload["reported"] is True


class TestOrchestratorServiceRun:
    def test_run_evaluates_on_window_interval(
        self, service, mock_decision_engine, mock_mqtt_service
    ):
        decision = make_decision()

        def evaluate_once():
            service.running = False
            return decision

        mock_decision_engine.evaluate.side_effect = evaluate_once
        service._last_eval = 0.0
        service.running = True

        with patch("time.sleep"):
            service.run()

        assert mock_decision_engine.evaluate.call_count == 1
        assert mock_mqtt_service.publish.call_count == 1

    def test_run_skips_evaluation_when_disabled(
        self, service, mock_decision_engine
    ):
        service.evaluation_enabled = False
        service.running = True

        def stop(*args):
            service.running = False

        with patch("time.sleep", side_effect=stop):
            service.run()

        mock_decision_engine.evaluate.assert_not_called()
