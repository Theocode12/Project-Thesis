import logging

from detector import DummyDetector

from edge_detector_service import (
    EdgeDetectorService
)

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("app")

log.info(
    "Starting edge-detector service"
)

detector = DummyDetector(
    threshold=0.5
)

mqtt_service = MQTTService(
    MQTTConfig(
        client_id="edge-detector"
    )
)

service = EdgeDetectorService(
    detector=detector,
    mqtt_service=mqtt_service
)

log.info(
    "Edge-detector service initialised"
)

try:

    service.start()
    service.run()

except KeyboardInterrupt:

    log.info(
        "Shutdown requested"
    )

    service.stop()

    log.info(
        "Edge-detector service stopped"
    )