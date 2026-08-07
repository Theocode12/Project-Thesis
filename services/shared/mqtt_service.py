import json
import logging
import time
from typing import Any, Callable

import paho.mqtt.client as mqtt

from .mqtt_config import MQTTConfig
from .mqtt_topics import MQTTOPIC

log = logging.getLogger(__name__)


class MQTTService:

    def __init__(self, config: MQTTConfig) -> None:
        self.config = config
        self.callbacks: dict[str, list[Callable[[dict], Any]]] = {}
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id,
        )

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def connect(self, retries: int = 5, delay: float = 1.0) -> None:
        last_exc = None

        for attempt in range(retries):
            try:
                self.client.connect(
                    self.config.host,
                    self.config.port,
                    self.config.keepalive,
                )

                log.info(
                    "Connected to MQTT broker at %s:%s",
                    self.config.host,
                    self.config.port,
                )
                return

            except Exception as exc:
                last_exc = exc
                log.warning(
                    "MQTT connect attempt %d/%d failed: %s",
                    attempt + 1,
                    retries,
                    exc,
                )
                if attempt < retries - 1:
                    time.sleep(delay * (2 ** attempt))

        raise ConnectionError(
            f"Failed to connect to MQTT broker at "
            f"{self.config.host}:{self.config.port} after {retries} attempts"
        ) from last_exc

    def start(self) -> None:
        self.client.loop_start()
        log.info("MQTT network loop started")

    def stop(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        log.info("MQTT network loop stopped and disconnected")

    def publish(self, topic: MQTTOPIC, payload: dict) -> None:
        result = self.client.publish(topic.value, json.dumps(payload))

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            log.error("Failed to publish to %s | reason=%s", topic.value, result.rc)

    def subscribe(self, topic: str, callback: Callable[[dict], Any]) -> None:
        self.callbacks.setdefault(topic, []).append(callback)
        self.client.subscribe(topic)
        log.info("Subscribed to %s", topic)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: dict,
        reason_code: int,
        properties: Any,
    ) -> None:
        log.info("MQTT connected | reason_code=%s", reason_code)

        for topic in self.callbacks:
            client.subscribe(topic)
            log.info("Resubscribed to %s", topic)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        msg: mqtt.MQTTMessage,
    ) -> None:
        topic = msg.topic

        if topic not in self.callbacks:
            log.debug("Ignoring message on unhandled topic: %s", topic)
            return

        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            payload = {"raw": msg.payload.decode()}
            log.warning("Failed to parse message payload from %s", topic)

        log.debug("Received message on %s | payload=%s", topic, payload)

        for callback in self.callbacks.get(topic, ()):
            callback(payload)
