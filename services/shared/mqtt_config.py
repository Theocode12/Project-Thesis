from dataclasses import dataclass
from os import getenv


@dataclass(slots=True)
class MQTTConfig:

    host: str = getenv(
        "MQTT_HOST",
        "localhost"
    )
    port: int = int(
        getenv(
            "MQTT_PORT",
            "1883"
        )
    )
    keepalive: int = 60
    client_id: str = "service"
