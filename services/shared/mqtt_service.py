import json
from typing import Any, Callable

import paho.mqtt.client as mqtt

from mqtt_config import MQTTConfig
from services.shared.mqtt_topics import MQTTOPIC

class MQTTService:

    def __init__(
        self,
        config: MQTTConfig
    ) -> None:

        self.config: MQTTConfig = config
        self.callbacks: dict[str, Callable[[dict], Any]] = {}
        self.client: mqtt.Client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=config.client_id
        )

        self.client.on_connect = (
            self._on_connect
        )

        self.client.on_message = (
            self._on_message
        )

    def connect(self) -> None:

        self.client.connect(
            self.config.host,
            self.config.port,
            self.config.keepalive
        )

    def start(self) -> None:

        self.client.loop_start()

    def stop(self) -> None:

        self.client.loop_stop()

        self.client.disconnect()

    def publish(
        self,
        topic: MQTTOPIC,
        payload: dict
    ) -> None:

        self.client.publish(
            topic.value,
            json.dumps(payload)
        )

    def subscribe(
        self,
        topic: str,
        callback: Callable[[dict], Any]
    ) -> None:

        self.callbacks[topic] = callback

        self.client.subscribe(topic)

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: dict,
        reason_code: int,
        properties: Any
    ) -> None:

        print(
            f"MQTT connected: {reason_code}"
        )

        for topic in self.callbacks:

            client.subscribe(topic)

    def _on_message(
        self,
        client: mqtt.Client,
        userdata: Any,
        msg: mqtt.MQTTMessage
    ) -> None:

        topic = msg.topic

        if topic not in self.callbacks:
            return

        try:

            payload = json.loads(
                msg.payload.decode()
            )

        except Exception:

            payload = {
                "raw": msg.payload.decode()
            }

        callback = self.callbacks[
            topic
        ]

        callback(payload)
