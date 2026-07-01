import json
import logging

from autoencoder_detector import AutoEncoderDetector

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

FEATURE_COLUMNS_PATH = "models/feature_columns.json"

with open(
    FEATURE_COLUMNS_PATH,
    "r",
    encoding="utf-8"
) as fp:

    FEATURE_COLUMNS = json.load(fp)

detector = AutoEncoderDetector(
    model_path="models/autoencoder.pt",
    scaler_path="models/scaler.pkl",
    threshold_path="models/threshold.json",
    feature_columns=FEATURE_COLUMNS,
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