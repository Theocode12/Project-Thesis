import logging
import os
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
        edge_mqtt_service: Optional[MQTTService] = None,
        cloud_mqtt_service: Optional[MQTTService] = None,
        event_recorder=None,
    ) -> None:
        self.mode = os.getenv("DEPLOYMENT_MODE", "").strip().lower()
        self.mqtt_service = mqtt_service
        self.edge_mqtt_service = edge_mqtt_service
        self.cloud_mqtt_service = cloud_mqtt_service
        self.event_recorder = event_recorder

        if mqtt_service is None and self.mode == "hybrid":
            self.edge_mqtt_service = edge_mqtt_service or MQTTService(
                MQTTConfig(
                    host=os.getenv("EDGE_MQTT_HOST", "edge-host"),
                    port=int(os.getenv("EDGE_MQTT_PORT", "1883")),
                    client_id="dashboard-edge",
                )
            )
            self.cloud_mqtt_service = cloud_mqtt_service or MQTTService(
                MQTTConfig(
                    host=os.getenv("CLOUD_MQTT_HOST", "cloud-host"),
                    port=int(os.getenv("CLOUD_MQTT_PORT", "1883")),
                    client_id="dashboard-cloud",
                )
            )
        elif mqtt_service is None:
            self.mqtt_service = MQTTService(
                mqtt_config or MQTTConfig(client_id="dashboard")
            )

        self.connected: bool = False
        self.edge_connected: bool = False
        self.cloud_connected: bool = False
        self.last_message_at: Optional[float] = None
        self.last_topic: Optional[str] = None

    def start(self) -> None:
        services = self._broker_services()
        failures = False

        for name, service in services.items():
            try:
                service.connect()
                service.start()
                setattr(self, f"{name}_connected", True)
                log.info("Dashboard %s MQTT client started", name)
            except Exception:
                failures = True
                setattr(self, f"{name}_connected", False)
                log.exception(
                    "Dashboard %s MQTT client failed to connect", name
                )

        self.connected = bool(services) and not failures

    def stop(self) -> None:
        for name, service in self._broker_services().items():
            if getattr(self, f"{name}_connected", False):
                service.stop()
                setattr(self, f"{name}_connected", False)
                log.info("Dashboard %s MQTT client stopped", name)
        self.connected = False

    def subscribe(self, topic: MQTTOPIC, handler: Callable[[dict], Any]) -> None:
        service = self._service_for_topic(topic)

        def wrapped(envelope: dict) -> None:
            self.note_message(topic)
            handler(envelope)

        service.subscribe(topic.value, wrapped)

    def publish(self, topic: MQTTOPIC, payload: dict) -> None:
        self._service_for_topic(topic).publish(topic, payload)

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
        if self.event_recorder is not None:
            self.event_recorder.record_command(
                action,
                params,
                self.broker_name_for_command(action),
            )
        self._service_for_command(action).publish(
            MQTTOPIC.SYSTEM_CONTROL,
            payload,
        )

    def broker_name_for_topic(self, topic: MQTTOPIC) -> str:
        services = self._broker_services()
        if len(services) == 1:
            return next(iter(services))
        if topic in {
            MQTTOPIC.SENSOR_RAW,
            MQTTOPIC.SENSOR_STATUS,
            MQTTOPIC.ANOMALY_DETECTED,
            MQTTOPIC.DETECTOR_STATUS,
            MQTTOPIC.ORCHESTRATOR_DECISION,
        }:
            return "edge"
        return "cloud"

    def broker_name_for_command(self, action: str) -> str:
        services = self._broker_services()
        if len(services) == 1:
            return next(iter(services))
        if action.startswith(("sg_", "det_", "orchestrator_")):
            return "edge"
        return "cloud"

    def _broker_services(self) -> dict[str, MQTTService]:
        if self.edge_mqtt_service is not None or self.cloud_mqtt_service is not None:
            services = {}
            if self.edge_mqtt_service is not None:
                services["edge"] = self.edge_mqtt_service
            if self.cloud_mqtt_service is not None:
                services["cloud"] = self.cloud_mqtt_service
            return services
        return {"mqtt": self.mqtt_service}

    def _service_for_topic(self, topic: MQTTOPIC) -> MQTTService:
        services = self._broker_services()
        if len(services) == 1:
            return next(iter(services.values()))

        edge_topics = {
            MQTTOPIC.SENSOR_RAW,
            MQTTOPIC.SENSOR_STATUS,
            MQTTOPIC.ANOMALY_DETECTED,
            MQTTOPIC.DETECTOR_STATUS,
            MQTTOPIC.ORCHESTRATOR_DECISION,
        }
        if topic in edge_topics:
            return services["edge"]
        return services["cloud"]

    def _service_for_command(self, action: str) -> MQTTService:
        services = self._broker_services()
        if len(services) == 1:
            return next(iter(services.values()))

        edge_prefixes = ("sg_", "det_", "orchestrator_")
        if action.startswith(edge_prefixes):
            return services["edge"]
        return services["cloud"]
