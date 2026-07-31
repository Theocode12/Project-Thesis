from unittest.mock import MagicMock, call, patch

import pytest

from data_management_service import DataManagementService
from shared.mqtt_topics import MQTTOPIC


@pytest.fixture
def mock_batch_manager():
    return MagicMock()


@pytest.fixture
def mock_cloud_storage():
    return MagicMock()


@pytest.fixture
def mock_local_storage():
    return MagicMock()


@pytest.fixture
def mock_cache_manager():
    return MagicMock()


@pytest.fixture
def mock_mqtt_service():
    return MagicMock()


@pytest.fixture
def service(
    mock_batch_manager,
    mock_cloud_storage,
    mock_local_storage,
    mock_cache_manager,
    mock_mqtt_service,
):
    return DataManagementService(
        batch_manager=mock_batch_manager,
        cloud_storage=mock_cloud_storage,
        local_storage=mock_local_storage,
        cache_manager=mock_cache_manager,
        mqtt_service=mock_mqtt_service,
    )


class TestDataManagementServiceStartStop:

    def test_start_connects_and_subscribes(
        self, service, mock_mqtt_service
    ):
        service.start()

        mock_mqtt_service.connect.assert_called_once()
        assert mock_mqtt_service.subscribe.call_args_list == [
            call(MQTTOPIC.SENSOR_RAW, service.handle_sample),
            call(MQTTOPIC.SYSTEM_CONTROL, service.handle_command),
        ]
        mock_mqtt_service.start.assert_called_once()
        assert service.running is True

    def test_stop_disconnects(
        self, service, mock_mqtt_service
    ):
        service.start()
        service.stop()

        assert service.running is False
        mock_mqtt_service.stop.assert_called_once()


class TestDataManagementServiceInit:
    def test_action_map_has_all_actions(self, service):
        assert set(service._action_map.keys()) == {"start", "stop"}

    def test_storage_enabled_by_default(self, service):
        assert service.storage_enabled is True


class TestDataManagementServiceHandleCommand:
    def test_none_payload_does_nothing(self, service):
        service.handle_command(None)

        assert service.storage_enabled is True

    def test_unknown_action_does_nothing(self, service):
        service.handle_command({"action": "unknown"})

        assert service.storage_enabled is True

    def test_start_action_enables_storage(self, service):
        service.storage_enabled = False
        service.handle_command({"action": "start"})

        assert service.storage_enabled is True

    def test_stop_action_disables_storage(self, service):
        service.handle_command({"action": "stop"})

        assert service.storage_enabled is False


class TestDataManagementServiceHandleSample:

    def test_handle_sample_adds_to_batch(
        self, service, mock_batch_manager
    ):
        payload = {
            "payload": {"sample": {"sensor": 1}}
        }
        service.handle_sample(payload)
        mock_batch_manager.add_sample.assert_called_once_with(
            {"sensor": 1}
        )

    def test_handle_sample_drops_when_storage_disabled(
        self, service, mock_batch_manager
    ):
        service.storage_enabled = False
        service.handle_sample(
            {"payload": {"sample": {"sensor": 1}}}
        )

        mock_batch_manager.add_sample.assert_not_called()

    def test_handle_sample_skips_no_payload(
        self, service, mock_batch_manager
    ):
        service.handle_sample({})
        mock_batch_manager.add_sample.assert_not_called()

    def test_handle_sample_skips_no_sample(
        self, service, mock_batch_manager
    ):
        service.handle_sample(
            {"payload": {"sg_metrics": {}}}
        )
        mock_batch_manager.add_sample.assert_not_called()

    def test_handle_sample_skips_none_payload(
        self, service, mock_batch_manager
    ):
        service.handle_sample({"payload": None})
        mock_batch_manager.add_sample.assert_not_called()


class TestDataManagementServiceDispatch:

    def test_dispatch_to_cloud_when_available(
        self, service, mock_batch_manager, mock_cloud_storage
    ):
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = True
        mock_batch_manager.get_rate.return_value = 2.0
        mock_batch_manager.current_interval = 5.0

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "abcdef123456"
            service._dispatch_batch([{"a": 1}])

        mock_cloud_storage.store.assert_called_once()
        batch_id = mock_cloud_storage.store.call_args[0][0]
        assert batch_id.startswith("batch_")
        mock_local_storage = service.local_storage
        mock_local_storage.save.assert_not_called()

    def test_fallback_to_local_when_cloud_unavailable(
        self, service, mock_cloud_storage, mock_local_storage
    ):
        mock_cloud_storage.is_available.return_value = False

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "fedcba654321"
            service._dispatch_batch([{"a": 1}])

        mock_cloud_storage.store.assert_not_called()
        mock_local_storage.save.assert_called_once()

    def test_fallback_to_local_when_cloud_store_fails(
        self, service, mock_cloud_storage, mock_local_storage
    ):
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = False

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "112233445566"
            service._dispatch_batch([{"a": 1}])

        mock_local_storage.save.assert_called_once()

    def test_dispatch_logs_rate_and_interval(
        self, service, mock_batch_manager, mock_cloud_storage
    ):
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = True
        mock_batch_manager.get_rate.return_value = 1.5
        mock_batch_manager.current_interval = 6.0

        service._dispatch_batch([{"a": 1}, {"b": 2}])
        mock_cloud_storage.store.assert_called_once()
        stored_data = mock_cloud_storage.store.call_args[0][1]
        assert stored_data == [{"a": 1}, {"b": 2}]


class TestDataManagementServiceRun:

    def test_run_dispatches_and_ticks(
        self, service, mock_batch_manager, mock_cloud_storage, mock_cache_manager
    ):
        mock_batch_manager.should_flush.side_effect = [
            True, True, True,
        ]
        mock_batch_manager.flush.side_effect = [
            [{"a": 1}], [{"b": 2}], [],
        ]
        mock_cloud_storage.is_available.return_value = True
        mock_cloud_storage.store.return_value = True
        mock_batch_manager.get_rate.return_value = 1.0
        mock_batch_manager.current_interval = 5.0

        def stop_after_two(*args):
            stop_after_two.calls = getattr(stop_after_two, "calls", 0) + 1
            if stop_after_two.calls >= 2:
                service.running = False

        mock_cache_manager.tick.side_effect = stop_after_two

        service.running = True
        with patch("time.sleep"):
            service.run()

        assert mock_cloud_storage.store.call_count >= 1
        assert mock_cache_manager.tick.call_count >= 2

    def test_run_skips_flush_when_storage_disabled(
        self, service, mock_batch_manager, mock_cache_manager
    ):
        def stop_on_first_tick(*args):
            service.running = False

        mock_cache_manager.tick.side_effect = stop_on_first_tick

        service.running = True
        service.storage_enabled = False
        with patch("time.sleep"):
            service.run()

        mock_batch_manager.should_flush.assert_not_called()
        mock_batch_manager.flush.assert_not_called()

    def test_run_handles_exception_continues(
        self, service, mock_batch_manager, mock_cache_manager
    ):
        mock_batch_manager.should_flush.side_effect = [
            Exception("boom"), False,
        ]

        def stop_on_first_tick(*args):
            service.running = False

        mock_cache_manager.tick.side_effect = stop_on_first_tick

        service.running = True
        with patch("time.sleep"):
            service.run()

        assert not service.running
        mock_batch_manager.flush.assert_not_called()
