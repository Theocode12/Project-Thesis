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
def service(mock_replay_engine, mock_mqtt_service):
    return SensorGeneratorService(
        replay_engine=mock_replay_engine,
        mqtt_service=mock_mqtt_service,
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
