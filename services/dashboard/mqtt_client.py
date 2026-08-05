import logging
import threading
import time
from typing import Any, Callable, Optional

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService
from shared.mqtt_topics import MQTTOPIC

log = logging.getLogger(__name__)

MAX_EVENTS = 80


class ActionLog:
    """Thread-safe, per-view action/event log (ring buffer).

    Each service view owns its own ActionLog so command and state
    history stays scoped to the page that produced it.
    """

    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self._lock = threading.Lock()
        self._max_events = max_events
        self._events: list[dict] = []

    def log(self, kind: str, text: str) -> None:
        with self._lock:
            self._events.insert(0, {
                "kind": kind,
                "text": text,
                "ts": time.time(),
            })
            if len(self._events) > self._max_events:
                self._events = self._events[:self._max_events]

    def recent(self) -> list[dict]:
        with self._lock:
            return list(self._events)


class DashboardClient:
    """Generic MQTT transport facade for the dashboard.

    Owns the broker connection and exposes subscribe/publish primitives
    plus broker health tracking. View-specific state and commands live
    in per-view stores / controllers.
    """

    def __init__(
        self,
        mqtt_service: Optional[MQTTService] = None,
        mqtt_config: Optional[MQTTConfig] = None,
    ) -> None:
        self.mqtt_service = mqtt_service or MQTTService(
            mqtt_config or MQTTConfig(client_id="dashboard")
        )
        self.connected: bool = False
        self.last_message_at: Optional[float] = None
        self.last_topic: Optional[str] = None

    def start(self) -> None:
        try:
            self.mqtt_service.connect()
            self.mqtt_service.start()
            self.connected = True
            log.info("Dashboard MQTT client started")
        except Exception:
            self.connected = False
            log.exception("Dashboard MQTT client failed to connect")

    def stop(self) -> None:
        if self.connected:
            self.mqtt_service.stop()
            self.connected = False
            log.info("Dashboard MQTT client stopped")

    def subscribe(self, topic: MQTTOPIC, handler: Callable[[dict], Any]) -> None:
        def wrapped(envelope: dict) -> None:
            self.note_message(topic)
            handler(envelope)

        self.mqtt_service.subscribe(topic.value, wrapped)

    def publish(self, topic: MQTTOPIC, payload: dict) -> None:
        self.mqtt_service.publish(topic, payload)

    def note_message(self, topic: MQTTOPIC) -> None:
        self.last_message_at = time.time()
        self.last_topic = topic.value

    def is_connected(self) -> bool:
        return (
            self.connected
            and self.last_message_at is not None
            and time.time() - self.last_message_at < 15.0
        )

    def send_command(self, action: str, **params: Any) -> None:
        payload = {"action": action, **params}
        log.info("Sending command: %s", payload)
        self.publish(MQTTOPIC.SYSTEM_CONTROL, payload)
