import logging
import time
from uuid import uuid4

from batch_manager import BatchManager
from cache_manager import CacheManager
from cloud_storage import CloudStorage
from local_storage import LocalStorage

from shared.mqtt_topics import MQTTOPIC
from shared.mqtt_service import MQTTService

log = logging.getLogger(__name__)


class DataManagementService:

    def __init__(
        self,
        batch_manager: BatchManager,
        cloud_storage: CloudStorage,
        local_storage: LocalStorage,
        cache_manager: CacheManager,
        mqtt_service: MQTTService,
    ):
        self.batch_manager = batch_manager
        self.cloud_storage = cloud_storage
        self.local_storage = local_storage
        self.cache_manager = cache_manager
        self.mqtt_service = mqtt_service
        self.running = False
        self.storage_enabled = True
        self._action_map = {
            "start": self._cmd_start,
            "stop": self._cmd_stop,
        }

    def start(self) -> None:
        self.mqtt_service.connect()
        self.mqtt_service.subscribe(
            MQTTOPIC.SENSOR_RAW, self.handle_sample
        )
        self.mqtt_service.subscribe(
            MQTTOPIC.SYSTEM_CONTROL, self.handle_command
        )
        self.mqtt_service.start()
        self.running = True
        log.info("Data management service started")

    def stop(self) -> None:
        self.running = False
        self.mqtt_service.stop()
        log.info("Data management service stopped")

    def handle_command(self, payload: dict) -> None:
        if not payload:
            log.warning("Received empty payload")
            return

        action = payload.get("action")
        handler = self._action_map.get(action)

        if handler is None:
            log.warning("Unknown action: %s", action)
            return

        log.info("Handling command: %s", action)
        handler(payload)

    def _cmd_start(self, payload: dict) -> None:
        self.storage_enabled = True
        log.info("Storage enabled")

    def _cmd_stop(self, payload: dict) -> None:
        self.storage_enabled = False
        log.info("Storage disabled")

    def handle_sample(self, payload: dict) -> None:
        try:
            if not self.storage_enabled:
                return
            inner = payload.get("payload") or {}
            sample = inner.get("sample")
            if sample is None:
                return
            self.batch_manager.add_sample(sample)
        except Exception:
            log.exception("Error processing sample")

    def run(self) -> None:
        log.info(
            "Entering run loop | target_batch_count=%d, min_interval=%.1fs, max_interval=%.1fs",
            self.batch_manager.target_batch_count,
            self.batch_manager.min_interval,
            self.batch_manager.max_interval,
        )

        while self.running:
            try:
                if self.storage_enabled and self.batch_manager.should_flush():
                    batch = self.batch_manager.flush()
                    if batch:
                        self._dispatch_batch(batch)

                self.cache_manager.tick()
                time.sleep(0.1)

            except Exception:
                log.exception("Error in run loop")

    def _dispatch_batch(self, batch: list[dict]) -> None:
        batch_id = f"batch_{uuid4().hex[:12]}"
        rate = self.batch_manager.get_rate()
        interval = self.batch_manager.current_interval

        log.info(
            "Dispatching batch %s | samples=%d, rate=%.2f/s, interval=%.1fs",
            batch_id,
            len(batch),
            rate,
            interval,
        )

        if self.cloud_storage.is_available():
            if self.cloud_storage.store(batch_id, batch):
                log.info("Batch %s successfully stored in cloud", batch_id)
                return
            log.warning(
                "Cloud store failed for batch %s, falling back to local cache",
                batch_id,
            )
        else:
            log.info(
                "Cloud unavailable, storing batch %s in local cache",
                batch_id,
            )

        self.local_storage.save(batch_id, batch)
