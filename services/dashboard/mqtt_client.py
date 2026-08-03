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
MAX_EVENTS = 80


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
        self.message_count: int = 0
        self.events: list[dict] = []
        self.connected: bool = False
        self._last_running: Optional[bool] = None
        self._last_fault: Optional[int] = None
        self._last_stream_interval: Optional[float] = None

    def log_event(self, kind: str, text: str) -> None:
        with self._lock:
            self.events.insert(0, {
                "kind": kind,
                "text": text,
                "ts": time.time(),
            })
            if len(self.events) > MAX_EVENTS:
                self.events = self.events[:MAX_EVENTS]

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
                self.message_count += 1
                if self.message_count == 1:
                    self.events.insert(0, {
                        "kind": "stream",
                        "text": "Raw sensor stream established",
                        "ts": now,
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

                stream_interval = (
                    payload.get("sg_metrics") or {}
                ).get("stream_interval")
                if (
                    stream_interval is not None
                    and stream_interval != self._last_stream_interval
                ):
                    self._last_stream_interval = stream_interval
                    self.events.insert(0, {
                        "kind": "interval",
                        "text": (
                            f"Stream interval set to {stream_interval:g}s"
                        ),
                        "ts": now,
                    })
                    if len(self.events) > MAX_EVENTS:
                        self.events = self.events[:MAX_EVENTS]

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
            status = payload.get("status") or {}

            running = status.get("running")
            if running is not None and running != self._last_running:
                self._last_running = running
                self.events.insert(0, {
                    "kind": "state",
                    "text": (
                        "Generator started"
                        if running else "Generator paused"
                    ),
                    "ts": now,
                })
                if len(self.events) > MAX_EVENTS:
                    self.events = self.events[:MAX_EVENTS]

            fault = status.get("fault")
            if fault is not None and fault != self._last_fault:
                self._last_fault = fault
                self.events.insert(0, {
                    "kind": "fault",
                    "text": f"Fault scenario changed to {fault}",
                    "ts": now,
                })
                if len(self.events) > MAX_EVENTS:
                    self.events = self.events[:MAX_EVENTS]

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

    def recent_events(self) -> list[dict]:
        with self._lock:
            return list(self.events)

    def get_message_count(self) -> int:
        with self._lock:
            return self.message_count

    def is_connected(self) -> bool:
        with self._lock:
            return (
                self.connected
                and self.last_message_at is not None
                and time.time() - self.last_message_at < 15.0
            )

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
        try:
            self.mqtt_service.connect()
            self.mqtt_service.start()
            self._connected = True
            self.store.connected = True
            self.store.log_event("mqtt", "MQTT connected")
            log.info("Dashboard MQTT client started")
        except Exception:
            self._connected = False
            self.store.connected = False
            self.store.log_event("mqtt", "MQTT connection failed")
            log.exception("Dashboard MQTT client failed to connect")

    def stop(self) -> None:
        if self._connected:
            self.mqtt_service.stop()
            self._connected = False
            self.store.connected = False
            self.store.log_event("mqtt", "MQTT disconnected")
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
        self.store.log_event("state", "Start command sent")

    def send_stop(self) -> None:
        self.send_command("stop")
        self.store.log_event("state", "Pause command sent")

    def send_reset(self) -> None:
        self.send_command("reset")
        self.store.log_event("state", "Reset command sent")

    def send_halt(self) -> None:
        self.send_command("stop")
        self.send_command("reset")
        self.store.log_event("state", "Stop command sent (halted and rewound)")

    def send_set_fault(self, fault: int) -> None:
        self.send_command("set_fault", fault=fault)
        self.store.log_event("fault", f"Fault scenario set to {fault}")

    def send_set_stream(self, fault: int, run: int) -> None:
        self.send_command(
            "set_stream",
            fault=fault,
            run=run,
        )
        self.store.log_event(
            "fault",
            f"Stream switched to fault_{fault} run_{run}",
        )

    def send_set_stream_interval(self, interval: float) -> None:
        self.send_command(
            "set_stream_interval",
            interval=interval,
        )
        self.store.log_event("interval", f"Stream interval set to {interval:g}s")

    def send_set_status_interval(self, interval: float) -> None:
        self.send_command(
            "set_status_interval",
            interval=interval,
        )
