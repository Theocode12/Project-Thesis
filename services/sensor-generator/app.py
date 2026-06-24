from catalog import Catalog
from data_loader import DataLoader
from replay_engine import ReplayEngine

from sensor_generator_service import (
SensorGeneratorService
)

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService

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

service.start()

try:

    while True:
        pass


except KeyboardInterrupt:

    service.stop()
