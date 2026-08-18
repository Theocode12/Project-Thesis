import json
import logging

from autoencoder_detector import AutoEncoderDetector
from detector_service import DetectorService

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("app")


def main() -> None:
    log.info("Starting detector service")

    with open("models/feature_columns.json", "r", encoding="utf-8") as fp:
        feature_columns = json.load(fp)

    detector = AutoEncoderDetector(
        model_path="models/autoencoder.pt",
        scaler_path="models/scaler.pkl",
        threshold_path="models/threshold.json",
        feature_columns=feature_columns,
    )

    mqtt_service = MQTTService(MQTTConfig(client_id="detector"))

    service = DetectorService(detector=detector, mqtt_service=mqtt_service)

    log.info("Detector service initialised")

    try:
        service.start()
        service.run()
    except KeyboardInterrupt:
        log.info("Shutdown requested")
        service.stop()
        log.info("Detector service stopped")


if __name__ == "__main__":
    main()
