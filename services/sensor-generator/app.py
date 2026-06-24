import logging

from catalog import Catalog
from data_loader import DataLoader
from replay_engine import ReplayEngine

from sensor_generator_service import (
SensorGeneratorService
)

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("app")
log.info("Starting sensor-generator service")

catalog = Catalog(
        "dataset/runtime/catalog.json"
    )

loader = DataLoader(
        "dataset/runtime"
    )

replay_engine = ReplayEngine(
        loader=loader,
        catalog=catalog
    )

replay_engine.set_fault(0)

mqtt_service = MQTTService(
        MQTTConfig(
            host="localhost",
            port=1883,
            client_id="sensor-generator"
        )
    )

service = SensorGeneratorService(
        replay_engine=replay_engine,
        mqtt_service=mqtt_service
    )

log.info("Sensor-generator service initialised")

try:
    service.start()
    service.run()
except KeyboardInterrupt:
    log.info("Shutdown requested")
    service.stop()
    log.info("Sensor-generator service stopped")

