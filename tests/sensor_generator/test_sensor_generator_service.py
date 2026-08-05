from unittest.mock import MagicMock, patch

import pytest

from sensor_generator_service import (
    SensorGeneratorService,
)
from shared.mqtt_topics import MQTTOPIC


@pytest.fixture
def mock_replay_engine():
    return MagicMock()


@pytest.fixture
def mock_mqtt_service():
    return MagicMock()


@pytest.fixture
def mock_metrics():
    metrics = MagicMock()
    metrics.wrap.side_effect = (
        lambda data_key, data, extra=None: {
            data_key: data,
            "sg_metrics": {"dummy": True},
        }
    )
    return metrics


@pytest.fixture
def service(mock_replay_engine, mock_mqtt_service, mock_metrics):
    return SensorGeneratorService(
        replay_engine=mock_replay_engine,
        mqtt_service=mock_mqtt_service,
        metrics=mock_metrics,
    )


class TestSensorGeneratorServiceInit:
    def test_default_intervals(self, service):
        assert service.STREAM_INTERVAL_SECONDS == 0.1
        assert service.STATUS_INTERVAL_SECONDS == 5

    def test_action_map_has_all_actions(self, service):
        expected = {
            "start",
            "stop",
            "reset",
            "set_fault",
            "set_stream",
            "set_stream_interval",
            "set_status_interval",
        }
        assert set(service._action_map.keys()) == expected

    def test_env_intervals(self):
        with patch.dict(
            "os.environ",
            {
                "STREAM_INTERVAL": "0.05",
                "STATUS_INTERVAL": "10",
            },
        ):
            s = SensorGeneratorService(
                replay_engine=MagicMock(),
                mqtt_service=MagicMock(),
                metrics=MagicMock(),
            )
            assert s.STREAM_INTERVAL_SECONDS == 0.05
            assert s.STATUS_INTERVAL_SECONDS == 10.0


class TestSensorGeneratorServiceStartStop:
    def test_start_subscribes_and_connects(
        self, service, mock_mqtt_service, mock_replay_engine
    ):
        service.start()

        mock_mqtt_service.subscribe.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            service.handle_command,
        )
        mock_mqtt_service.connect.assert_called_once()
        mock_mqtt_service.start.assert_called_once()
        assert service.running is True
        mock_replay_engine.start.assert_called_once()

    def test_stop(self, service, mock_replay_engine, mock_mqtt_service):
        service.start()
        service.stop()

        assert service.running is False
        mock_replay_engine.stop.assert_called_once()
        mock_mqtt_service.stop.assert_called_once()


class TestSensorGeneratorServiceHandleCommand:
    def test_none_payload_does_nothing(
        self, service, mock_replay_engine
    ):
        service.handle_command(None)

        mock_replay_engine.start.assert_not_called()
        mock_replay_engine.stop.assert_not_called()
        mock_replay_engine.reset.assert_not_called()

    def test_unknown_action_does_nothing(
        self, service, mock_replay_engine
    ):
        service.handle_command({"action": "unknown"})

        mock_replay_engine.start.assert_not_called()
        mock_replay_engine.stop.assert_not_called()
        mock_replay_engine.reset.assert_not_called()

    def test_start_action(self, service, mock_replay_engine):
        service.handle_command({"action": "start"})

        mock_replay_engine.start.assert_called_once()

    def test_stop_action(self, service, mock_replay_engine):
        service.handle_command({"action": "stop"})

        mock_replay_engine.stop.assert_called_once()

    def test_reset_action(self, service, mock_replay_engine):
        service.handle_command({"action": "reset"})

        mock_replay_engine.reset.assert_called_once()

    def test_set_fault_action(self, service, mock_replay_engine):
        service.handle_command(
            {"action": "set_fault", "fault": 3}
        )

        mock_replay_engine.set_fault.assert_called_once_with(
            3
        )

    def test_set_stream_action(self, service, mock_replay_engine):
        service.handle_command(
            {"action": "set_stream", "fault": 2, "run": 7}
        )

        mock_replay_engine.set_stream.assert_called_once_with(
            fault=2, run=7
        )

    def test_set_stream_interval_action(self, service):
        service.handle_command(
            {
                "action": "set_stream_interval",
                "interval": "0.5",
            }
        )

        assert service.STREAM_INTERVAL_SECONDS == 0.5

    def test_set_status_interval_action(self, service):
        service.handle_command(
            {
                "action": "set_status_interval",
                "interval": "10",
            }
        )

        assert service.STATUS_INTERVAL_SECONDS == 10.0

    def test_command_publishes_status_immediately(
        self, service, mock_mqtt_service
    ):
        service.handle_command({"action": "start"})

        mock_mqtt_service.publish.assert_called_once()
        topic, _ = mock_mqtt_service.publish.call_args[0]
        assert topic == MQTTOPIC.SENSOR_STATUS


class TestSensorGeneratorServicePublish:

    def test_publish_sample_wraps_sample_with_metrics(
        self,
        service,
        mock_replay_engine,
        mock_mqtt_service,
        mock_metrics,
    ):
        sample = {"XMEAS_1": 1.0, "_stream": {"fault": 0, "run": 1}}
        mock_replay_engine.next_sample.return_value = sample

        result = service.publish_sample()

        assert result == {
            "sample": sample,
            "sg_metrics": {"dummy": True},
        }
        mock_metrics.start_processing.assert_called_once()
        mock_metrics.wrap.assert_called_once_with(
            data_key="sample",
            data=sample,
            extra={
                "stream_interval": 0.1,
                "status_interval": 5.0,
            },
        )
        mock_mqtt_service.publish.assert_called_once()

    def test_publish_sample_includes_updated_intervals(
        self, service, mock_replay_engine, mock_metrics
    ):
        service.handle_command(
            {
                "action": "set_stream_interval",
                "interval": "0.5",
            }
        )
        service.handle_command(
            {
                "action": "set_status_interval",
                "interval": "10",
            }
        )
        mock_replay_engine.next_sample.return_value = {"X": 1.0}

        service.publish_sample()

        assert mock_metrics.wrap.call_args[1]["extra"] == {
            "stream_interval": 0.5,
            "status_interval": 10.0,
        }

    def test_publish_sample_publishes_envelope(
        self, service, mock_replay_engine, mock_mqtt_service
    ):
        mock_replay_engine.next_sample.return_value = {
            "XMEAS_1": 2.0
        }

        service.publish_sample()

        call_args = mock_mqtt_service.publish.call_args[0]
        assert call_args[0] == MQTTOPIC.SENSOR_RAW
        envelope = call_args[1]
        assert envelope["source"] == "sensor-generator"
        assert "sample" in envelope["payload"]
        assert "sg_metrics" in envelope["payload"]

    def test_publish_sample_returns_none_when_no_sample(
        self, service, mock_replay_engine, mock_mqtt_service
    ):
        mock_replay_engine.next_sample.return_value = None

        result = service.publish_sample()

        assert result is None
        mock_mqtt_service.publish.assert_not_called()

    def test_publish_status_wraps_status_with_metrics(
        self,
        service,
        mock_replay_engine,
        mock_mqtt_service,
        mock_metrics,
    ):
        status = {
            "running": True,
            "fault": 0,
            "run": 1,
            "position": 5,
            "loaded": True,
        }
        mock_replay_engine.get_status.return_value = status

        result = service.publish_status()

        assert result == {
            "status": status,
            "sg_metrics": {"dummy": True},
        }
        call_args = mock_mqtt_service.publish.call_args[0]
        assert call_args[0] == MQTTOPIC.SENSOR_STATUS
        envelope = call_args[1]
        assert envelope["payload"]["status"] == status
        assert mock_metrics.wrap.call_args[1]["extra"] == {
            "stream_interval": 0.1,
            "status_interval": 5.0,
        }
