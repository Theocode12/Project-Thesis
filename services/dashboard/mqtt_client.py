import logging
import threading
import time
from typing import Any, Optional

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService
from shared.mqtt_topics import MQTTOPIC

log = logging.getLogger(__name__)

SAMPLE_WINDOW_SECONDS = 60.0
RATE_WINDOW_SECONDS = 5.0
MAX_SAMPLES = 2000


class DashboardDataStore:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.status: Optional[dict] = None
        self.metrics: Optional[dict] = None
        self.samples: list[dict] = []
        self.processing_history: list[dict] = []
        self.last_message_at: Optional[float] = None
        self.last_topic: Optional[str] = None
        self.sample_rate: float = 0.0

    def handle_raw(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        sample = payload.get("sample")
        now = time.time()

        with self._lock:
            if sample is not None:
                self.samples.append({
                    "t": now,
                    "fault": sample.get("_stream", {}).get("fault"),
                    "run": sample.get("_stream", {}).get("run"),
                    "values": sample,
                })
                self._trim_samples()

            if "sg_metrics" in payload:
                self.metrics = {
                    "sg_metrics": payload.get("sg_metrics"),
                    "received_at": now,
                }
                processing_time = (
                    payload.get("sg_metrics") or {}
                ).get("processing_time_ms")
                if processing_time is not None:
                    self.processing_history.append({
                        "t": now,
                        "processing_time_ms": processing_time,
                    })
                    self._trim_processing_history()

            self.last_message_at = now
            self.last_topic = MQTTOPIC.SENSOR_RAW.value
            self._update_rate()

    def handle_status(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()

        with self._lock:
            self.status = {
                "status": payload.get("status"),
                "received_at": now,
            }
            self.last_message_at = now
            self.last_topic = MQTTOPIC.SENSOR_STATUS.value

    def channels(self) -> list[str]:
        with self._lock:
            if not self.samples:
                return []
            return [
                key
                for key in self.samples[-1]["values"].keys()
                if not key.startswith("_")
            ]

    def get_status(self) -> Optional[dict]:
        with self._lock:
            return self.status

    def get_metrics(self) -> Optional[dict]:
        with self._lock:
            return self.metrics

    def recent_samples(self) -> list[dict]:
        with self._lock:
            return list(self.samples)

    def recent_processing_times(self) -> list[dict]:
        with self._lock:
            return list(self.processing_history)

    def _trim_samples(self) -> None:
        cutoff = time.time() - SAMPLE_WINDOW_SECONDS
        while self.samples and self.samples[0]["t"] < cutoff:
            self.samples.pop(0)

        if len(self.samples) > MAX_SAMPLES:
            self.samples = self.samples[-MAX_SAMPLES:]

    def _trim_processing_history(self) -> None:
        cutoff = time.time() - SAMPLE_WINDOW_SECONDS
        while (
            self.processing_history
            and self.processing_history[0]["t"] < cutoff
        ):
            self.processing_history.pop(0)

    def _update_rate(self) -> None:
        now = time.time()
        cutoff = now - RATE_WINDOW_SECONDS
        count = sum(1 for sample in self.samples if sample["t"] >= cutoff)
        self.sample_rate = round(count / RATE_WINDOW_SECONDS, 2)


class DashboardClient:

    def __init__(
        self,
        store: Optional[DashboardDataStore] = None,
        mqtt_service: Optional[MQTTService] = None,
        mqtt_config: Optional[MQTTConfig] = None,
    ) -> None:
        self.store = store or DashboardDataStore()
        self.mqtt_service = mqtt_service or MQTTService(
            mqtt_config or MQTTConfig(client_id="dashboard")
        )
        self._connected = False

    def start(self) -> None:
        self.mqtt_service.subscribe(
            MQTTOPIC.SENSOR_RAW,
            self.store.handle_raw,
        )
        self.mqtt_service.subscribe(
            MQTTOPIC.SENSOR_STATUS,
            self.store.handle_status,
        )
        self.mqtt_service.connect()
        self.mqtt_service.start()
        self._connected = True
        log.info("Dashboard MQTT client started")

    def stop(self) -> None:
        if self._connected:
            self.mqtt_service.stop()
            self._connected = False
            log.info("Dashboard MQTT client stopped")

    def send_command(self, action: str, **params: Any) -> None:
        payload = {"action": action, **params}
        log.info("Sending command: %s", payload)
        self.mqtt_service.publish(
            MQTTOPIC.SYSTEM_CONTROL,
            payload,
        )

    def send_start(self) -> None:
        self.send_command("start")

    def send_stop(self) -> None:
        self.send_command("stop")

    def send_reset(self) -> None:
        self.send_command("reset")

    def send_set_fault(self, fault: int) -> None:
        self.send_command("set_fault", fault=fault)

    def send_set_stream(self, fault: int, run: int) -> None:
        self.send_command(
            "set_stream",
            fault=fault,
            run=run,
        )

    def send_set_stream_interval(self, interval: float) -> None:
        self.send_command(
            "set_stream_interval",
            interval=interval,
        )

    def send_set_status_interval(self, interval: float) -> None:
        self.send_command(
            "set_status_interval",
            interval=interval,
        )
