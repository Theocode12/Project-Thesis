from unittest.mock import MagicMock

import pytest

from mqtt_client import DashboardClient, DashboardDataStore
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


class TestDashboardDataStore:

    def test_handle_raw_stores_sample(self):
        store = DashboardDataStore()
        store.handle_raw(make_sample_envelope())

        samples = store.recent_samples()
        assert len(samples) == 1
        assert samples[0]["fault"] == 0
        assert samples[0]["run"] == 1
        assert samples[0]["values"]["xmeas_1"] == 1.5

    def test_handle_raw_stores_metrics(self):
        store = DashboardDataStore()
        store.handle_raw(make_sample_envelope())

        metrics = store.get_metrics()
        assert metrics["sg_metrics"]["container"]["cpu_percent"] == 12.5
        assert metrics["sg_metrics"]["stream_interval"] == 0.1

    def test_handle_raw_stores_processing_history(self):
        store = DashboardDataStore()
        store.handle_raw(make_sample_envelope())
        store.handle_raw(make_sample_envelope())

        history = store.recent_processing_times()
        assert len(history) == 2
        assert history[0]["processing_time_ms"] == 0.4

    def test_handle_status_stores_status(self):
        store = DashboardDataStore()
        store.handle_status(make_status_envelope())

        status = store.get_status()
        assert status["status"]["running"] is True
        assert status["status"]["fault"] == 0
        assert status["status"]["run"] == 1
        assert status["status"]["position"] == 42

    def test_channels_excludes_stream_metadata(self):
        store = DashboardDataStore()
        store.handle_raw(make_sample_envelope())

        assert store.channels() == ["xmeas_1", "xmv_1"]

    def test_last_topic_tracks_source(self):
        store = DashboardDataStore()
        store.handle_raw(make_sample_envelope())
        assert store.last_topic == MQTTOPIC.SENSOR_RAW.value

        store.handle_status(make_status_envelope())
        assert store.last_topic == MQTTOPIC.SENSOR_STATUS.value

    def test_empty_store(self):
        store = DashboardDataStore()
        assert store.channels() == []
        assert store.recent_samples() == []
        assert store.get_status() is None
        assert store.get_metrics() is None


class TestDashboardClient:

    @pytest.fixture
    def client(self):
        mqtt_service = MagicMock()
        store = DashboardDataStore()
        return DashboardClient(
            store=store,
            mqtt_service=mqtt_service,
        ), mqtt_service

    def test_send_command_builds_payload(self, client):
        dashboard, mqtt_service = client
        dashboard.send_command("set_fault", fault=7)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "set_fault", "fault": 7},
        )

    def test_send_start(self, client):
        dashboard, mqtt_service = client
        dashboard.send_start()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "start"},
        )

    def test_send_stop(self, client):
        dashboard, mqtt_service = client
        dashboard.send_stop()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "stop"},
        )

    def test_send_reset(self, client):
        dashboard, mqtt_service = client
        dashboard.send_reset()

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "reset"},
        )

    def test_send_set_fault(self, client):
        dashboard, mqtt_service = client
        dashboard.send_set_fault(3)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "set_fault", "fault": 3},
        )

    def test_send_set_stream(self, client):
        dashboard, mqtt_service = client
        dashboard.send_set_stream(fault=2, run=7)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "set_stream", "fault": 2, "run": 7},
        )

    def test_send_set_stream_interval(self, client):
        dashboard, mqtt_service = client
        dashboard.send_set_stream_interval(0.5)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "set_stream_interval", "interval": 0.5},
        )

    def test_send_set_status_interval(self, client):
        dashboard, mqtt_service = client
        dashboard.send_set_status_interval(10)

        mqtt_service.publish.assert_called_once_with(
            MQTTOPIC.SYSTEM_CONTROL,
            {"action": "set_status_interval", "interval": 10},
        )

    def test_start_subscribes_and_connects(self, client):
        dashboard, mqtt_service = client
        dashboard.start()

        mqtt_service.subscribe.assert_any_call(
            MQTTOPIC.SENSOR_RAW,
            dashboard.store.handle_raw,
        )
        mqtt_service.subscribe.assert_any_call(
            MQTTOPIC.SENSOR_STATUS,
            dashboard.store.handle_status,
        )
        mqtt_service.connect.assert_called_once()
        mqtt_service.start.assert_called_once()

    def test_stop_disconnects(self, client):
        dashboard, mqtt_service = client
        dashboard.start()
        dashboard.stop()

        mqtt_service.stop.assert_called_once()
        assert dashboard._connected is False
