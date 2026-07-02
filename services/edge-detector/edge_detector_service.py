import logging

from detector import Detector
from anomaly_event import AnomalyEvent

from shared.mqtt_topics import MQTTOPIC
from shared.mqtt_service import MQTTService

log = logging.getLogger(__name__)


class EdgeDetectorService:

    def __init__(self, detector: Detector, mqtt_service: MQTTService):
        self.detector = detector
        self.mqtt_service = mqtt_service
        self.running = False

    def start(self):
        self.mqtt_service.connect()
        self.mqtt_service.subscribe(MQTTOPIC.SENSOR_RAW, self.handle_sample)
        self.mqtt_service.start()

        self.running = True
        log.info("Edge detector started")

    def stop(self):
        self.running = False
        self.mqtt_service.stop()
        log.info("Edge detector stopped")

    def handle_sample(self, payload: dict):
        try:
            sample = payload.get("payload")
            if sample is None:
                return

            result = self.detector.detect(sample)
            if not result["anomaly"]:
                return

            event = AnomalyEvent.create(result=result, sample=sample)
            self.mqtt_service.publish(MQTTOPIC.ANOMALY_DETECTED, event.to_dict())

            log.info(
                "Anomaly detected | metric=%s value=%s reconstruction_error=%s",
                result.get("metric"),
                result.get("value"),
                result.get("reconstruction_error"),
            )

        except Exception:
            log.exception("Error processing sample")

    def run(self):
        import time
        while self.running:
            time.sleep(1)