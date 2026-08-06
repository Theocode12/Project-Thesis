from unittest.mock import MagicMock

import pytest

from mqtt_client import DashboardClient
from sensor_store import SensorGeneratorController, SensorGeneratorStore
from shared.mqtt_topics import MQTTOPIC


def make_sample_envelope(fault=0, run=1):
    return {
        "source": "sensor-generator",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "sample": {
                "xmeas_1": 1.5,
                "xmv_1": 2.5,
                "_stream": {"fault": fault, "run": run},
            },
            "sg_metrics": {
                "container": {"cpu_percent": 12.5},
                "processing_time_ms": 0.4,
                "processed_at": "2026-01-01T00:00:00+00:00",
                "stream_interval": 0.1,
                "status_interval": 5.0,
            },
        },
    }


def make_status_envelope(running=True, fault=0, run=1, position=42):
    return {
        "source": "sensor-generator",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "payload": {
            "status": {
                "running": running,
                "fault": fault,
                "run": run,
                "position": position,
                "loaded": True,
            },
            "sg_metrics": {
                "container": {"cpu_percent": 12.5},
                "processing_time_ms": 0.4,
                "processed_at": "2026-01-01T00:00:00+00:00",
                "stream_interval": 0.1,
                "status_interval": 5.0,
            },
        },
    }


class TestSensorGeneratorStore:

    def test_handle_raw_stores_sample(self):
        store = SensorGeneratorStore()
        store.handle_raw(make_sample_envelope())

        samples = store.recent_samples()
        assert len(samples) == 1
        assert samples[0]["fault"] == 0
        assert samples[0]["run"] == 1
        assert samples[0]["values"]["xmeas_1"] == 1.5

    def test_handle_raw_stores_metrics(self):
        store = SensorGeneratorStore()
        store.handle_raw(make_sample_envelope())

        metrics = store.get_metrics()
        assert metrics["sg_metrics"]["container"]["cpu_percent"] == 12.5
        assert metrics["sg_metrics"]["stream_interval"] == 0.1

    def test_handle_raw_stores_processing_history(self):
        store = SensorGeneratorStore()
        store.handle_raw(make_sample_envelope())
        store.handle_raw(make_sample_envelope())

        history = store.recent_processing_times()
        assert len(history) == 2
        assert history[0]["processing_time_ms"] == 0.4

    def test_handle_status_stores_status(self):
        store = SensorGeneratorStore()
        store.handle_status(make_status_envelope())

        status = store.get_status()
        assert status["status"]["running"] is True
        assert status["status"]["fault"] == 0
        assert status["status"]["run"] == 1
        assert status["status"]["position"] == 42

    def test_handle_status_stores_metrics(self):
        store = SensorGeneratorStore()
        store.handle_status(make_status_envelope(running=False))

        metrics = store.get_metrics()
        assert metrics["sg_metrics"]["stream_interval"] == 0.1
        assert store.recent_processing_times()[0]["processing_time_ms"] == 0.4

    def test_channels_excludes_stream_metadata(self):
        store = SensorGeneratorStore()
        store.handle_raw(make_sample_envelope())

        assert store.channels() == ["xmeas_1", "xmv_1"]

    def test_empty_store(self):
        store = SensorGeneratorStore()
        assert store.channels() == []
        assert store.recent_samples() == []
        assert store.get_status() is None
        assert store.get_metrics() is None
        assert store.recent_actions() == []

    def test_message_count_increments(self):
        store = SensorGeneratorStore()
        store.handle_raw(make_sample_envelope())
        store.handle_raw(make_sample_envelope())
        store.handle_raw(make_sample_envelope())

        assert store.get_message_count() == 3

    def test_log_event_records_most_recent_first(self):
        store = SensorGeneratorStore()
        store.action_log.log("state", "Generator started")
        store.action_log.log("fault", "Fault changed to 5")

        actions = store.recent_actions()
        assert actions[0]["text"] == "Fault changed to 5"
        assert actions[1]["text"] == "Generator started"

    def test_handle_status_logs_running_transitions(self):
        store = SensorGeneratorStore()
        store.handle_status(make_status_envelope(running=True))

        texts = [e["text"] for e in store.recent_actions()]
        assert "Generator started" in texts

        store.handle_status(
            make_status_envelope(running=False, fault=0, position=50)
        )
        texts = [e["text"] for e in store.recent_actions()]
        assert texts[0] == "Generator paused"

    def test_handle_status_logs_fault_change(self):
        store = SensorGeneratorStore()
        store.handle_status(make_status_envelope(fault=0))
        store.handle_status(make_status_envelope(fault=7))

        texts = [e["text"] for e in store.recent_actions()]
        assert texts[0] == "Fault scenario changed to 7"

    def test_handle_raw_logs_first_stream_event(self):
        store = SensorGeneratorStore()
        store.handle_raw(make_sample_envelope())

        texts = [e["text"] for e in store.recent_actions()]
        assert "Raw sensor stream established" in texts


class TestDashboardClient:

    @pytest.fixture
    def client(self):
        mqtt_service = MagicMock()
        return DashboardClient(mqtt_service=mqtt_service), mqtt_service

    def test_start_connects_and_starts(self, client):
        dashboard, mqtt_service = client
        dashboard.start()

        mqtt_service.connect.assert_called_once()
        mqtt_service.start.assert_called_once()
        assert dashboard.connected is True

    def test_stop_disconnects(self, client):
        dashboard, mqtt_service = client
        dashboard.start()
        dashboard.stop()

        mqtt_service.stop.assert_called_once()
        assert dashboard.connected is False

    def test_start_on_failure_stays_disconnected(self, client):
        dashboard, mqtt_service = client
        mqtt_service.connect.side_effect = ConnectionError("no broker")
        dashboard.start()

        assert dashboard.connected is False

    def test_subscribe_registers_handler(self, client):
        dashboard, mqtt_service = client
        handler = lambda envelope: None  # noqa: E731
        dashboard.subscribe(MQTTOPIC.SENSOR_RAW, handler)

        assert mqtt_service.subscribe.call_count == 1
        registered_topic, registered_callback = mqtt_service.subscribe.call_args.args
        assert registered_topic == MQTTOPIC.SENSOR_RAW.value

        envelope = {"payload": {"sample": {"xmeas_1": 1.0}}}
        registered_callback(envelope)

        assert dashboard.last_topic == MQTTOPIC.SENSOR_RAW.value
        assert dashboard.last_message_at is not None

    def test_subscribe_invokes_handler(self, client):
        dashboard, mqtt_service = client
        received = []

        def handler(envelope):
            received.append(envelope)

        dashboard.subscribe(MQTTOPIC.SENSOR_RAW, handler)
        registered_callback = mqtt_service.subscribe.call_args.args[1]

        registered_callback({"payload": {"sample": {"xmeas_1": 1.0}}})

        assert len(received) == 1
        assert received[0]["payload"]["sample"]["xmeas_1"] == 1.0

    def test_inbound_message_marks_connected(self, client):
        dashboard, mqtt_service = client
        handler = lambda envelope: None  # noqa: E731
        dashboard.subscribe(MQTTOPIC.SENSOR_RAW, handler)
        registered_callback = mqtt_service.subscribe.call_args.args[1]

        dashboard.connected = True
        registered_callback({"payload": {}})

        assert dashboard.is_connected() is True

    def test_note_message_tracks_health(self, client):
        dashboard, _ = client
        assert dashboard.last_topic is None
        assert dashboard.is_connected() is False

        dashboard.connected = True
        dashboard.note_message(MQTTOPIC.SENSOR_RAW)

        assert dashboard.last_topic == MQTTOPIC.SENSOR_RAW.value
        assert dashboard.last_message_at is not None
        assert dashboard.is_connected() is True

    def test_send_command_builds_payload(self, client):
        dashboard, mqtt_service = client
        dashboard.send_command("sg_set_fault", fault=7)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "sg_set_fault", "fault": 7},
        )


class TestSensorGeneratorController:

    @pytest.fixture
    def controller(self):
        mqtt_service = MagicMock()
        client = DashboardClient(mqtt_service=mqtt_service)
        store = SensorGeneratorStore()
        return SensorGeneratorController(store, client), mqtt_service, store

    def test_send_start(self, controller):
        command, mqtt_service, _ = controller
        command.send_start()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "sg_start"},
        )

    def test_send_stop(self, controller):
        command, mqtt_service, _ = controller
        command.send_stop()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "sg_stop"},
        )

    def test_send_reset(self, controller):
        command, mqtt_service, _ = controller
        command.send_reset()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "sg_reset"},
        )

    def test_send_halt(self, controller):
        command, mqtt_service, _ = controller
        command.send_halt()

        assert mqtt_service.publish.call_count == 2
        assert mqtt_service.publish.call_args_list[0] == (
            (
                MQTTOPIC.SYSTEM_CONTROL,
                {"action": "sg_stop"},
            ),
            {},
        )
        assert mqtt_service.publish.call_args_list[1] == (
            (
                MQTTOPIC.SYSTEM_CONTROL,
                {"action": "sg_reset"},
            ),
            {},
        )

    def test_send_set_fault(self, controller):
        command, mqtt_service, _ = controller
        command.send_set_fault(3)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "sg_set_fault", "fault": 3},
        )

    def test_send_set_stream(self, controller):
        command, mqtt_service, _ = controller
        command.send_set_stream(fault=2, run=7)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "sg_set_stream", "fault": 2, "run": 7},
        )

    def test_send_set_stream_interval(self, controller):
        command, mqtt_service, _ = controller
        command.send_set_stream_interval(0.5)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "sg_set_stream_interval", "interval": 0.5},
        )

    def test_send_set_status_interval(self, controller):
        command, mqtt_service, _ = controller
        command.send_set_status_interval(10)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "sg_set_status_interval", "interval": 10},
        )

    def test_commands_log_actions(self, controller):
        command, _, store = controller
        command.send_start()
        command.send_set_fault(3)

        texts = [e["text"] for e in store.recent_actions()]
        assert texts[0] == "Fault scenario set to 3"
        assert "Start command sent" in texts
