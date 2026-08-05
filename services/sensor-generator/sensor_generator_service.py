import logging
import time
from os import getenv

from replay_engine import ReplayEngine

from shared.mqtt_topics import MQTTOPIC
from shared.mqtt_service import MQTTService
from shared.mqtt_message_envelop import MQTTMessageEnvelope
from shared.service_metrics import ServiceMetrics

log = logging.getLogger(__name__)


class SensorGeneratorService:

    def __init__(
        self,
        replay_engine: ReplayEngine,
        mqtt_service: MQTTService,
        metrics: ServiceMetrics = None
    ):

        self.replay_engine = replay_engine
        self.mqtt_service = mqtt_service
        self.metrics = (
            metrics or ServiceMetrics(
                service_name="sensor-generator"
            )
        )
        self.running = False
        self.STREAM_INTERVAL_SECONDS = float(
            getenv("STREAM_INTERVAL", "0.1")
        )
        self.STATUS_INTERVAL_SECONDS = float(
            getenv("STATUS_INTERVAL", "5")
        )
        self._action_map = {
            "start": self._cmd_start,
            "stop": self._cmd_stop,
            "reset": self._cmd_reset,
            "set_fault": self._cmd_set_fault,
            "set_stream": self._cmd_set_stream,
            "set_stream_interval": self._cmd_set_stream_interval,
            "set_status_interval": self._cmd_set_status_interval,
        }

    def start(self):

        self.mqtt_service.subscribe(
            MQTTOPIC.SYSTEM_CONTROL,
            self.handle_command
        )

        self.mqtt_service.connect()
        self.mqtt_service.start()
        self.running = True
        self.replay_engine.start()

        log.info(
            "Started | stream_interval=%ss, status_interval=%ss",
            self.STREAM_INTERVAL_SECONDS,
            self.STATUS_INTERVAL_SECONDS,
        )

    def stop(self):

        self.running = False
        self.replay_engine.stop()
        self.mqtt_service.stop()

        log.info("Stopped")

    def handle_command(
        self,
        payload: dict
    ):

        if not payload:
            log.warning("Received empty payload")
            return

        action = payload.get("action")
        handler = self._action_map.get(action)

        if handler is None:
            log.warning("Unknown action: %s", action)
            return

        log.info("Handling command: %s", action)
        handler(payload)

        try:
            self.publish_status()
        except Exception:
            log.exception(
                "Failed to publish status after command: %s",
                action,
            )

    def _cmd_start(
        self,
        payload: dict
    ):
        self.replay_engine.start()

    def _cmd_stop(
        self,
        payload: dict
    ):
        self.replay_engine.stop()

    def _cmd_reset(
        self,
        payload: dict
    ):
        self.replay_engine.reset()

    def _cmd_set_fault(
        self,
        payload: dict
    ):
        fault = payload["fault"]
        self.replay_engine.set_fault(fault)
        log.info("Fault set to %s", fault)

    def _cmd_set_stream(
        self,
        payload: dict
    ):
        fault = payload["fault"]
        run = payload["run"]
        self.replay_engine.set_stream(
            fault=fault,
            run=run
        )
        log.info("Stream set to fault=%s, run=%s", fault, run)

    def _cmd_set_stream_interval(
        self,
        payload: dict
    ):
        interval = float(payload["interval"])
        self.STREAM_INTERVAL_SECONDS = interval
        log.info("Stream interval set to %ss", interval)

    def _cmd_set_status_interval(
        self,
        payload: dict
    ):
        interval = float(payload["interval"])
        self.STATUS_INTERVAL_SECONDS = interval
        log.info("Status interval set to %ss", interval)

    def _interval_metrics(self) -> dict:
        return {
            "stream_interval": self.STREAM_INTERVAL_SECONDS,
            "status_interval": self.STATUS_INTERVAL_SECONDS,
        }

    def publish_sample(self) -> dict | None:

        self.metrics.start_processing()

        sample = self.replay_engine.next_sample()

        if sample is None:
            return None

        message_payload = self.metrics.wrap(
            data_key="sample",
            data=sample,
            extra=self._interval_metrics()
        )

        message = MQTTMessageEnvelope.create(
            source="sensor-generator",
            payload=message_payload
        )
        self.mqtt_service.publish(
            MQTTOPIC.SENSOR_RAW,
            message.to_dict()
        )

        log.debug(
            "Published sample | fault=%s, run=%s",
            sample.get("_stream", {}).get("fault"),
            sample.get("_stream", {}).get("run"),
        )

        return message_payload

    def publish_status(self) -> dict | None:

        self.metrics.start_processing()

        status = self.replay_engine.get_status()

        message_payload = self.metrics.wrap(
            data_key="status",
            data=status,
            extra=self._interval_metrics()
        )

        message = MQTTMessageEnvelope.create(
            source="sensor-generator",
            payload=message_payload
        )
        self.mqtt_service.publish(
            MQTTOPIC.SENSOR_STATUS,
            message.to_dict()
        )

        log.info(
            "Published status | running=%s, fault=%s, run=%s, position=%s, loaded=%s",
            status.get("running"),
            status.get("fault"),
            status.get("run"),
            status.get("position"),
            status.get("loaded"),
        )

        return message_payload

    def run(self):

        log.info(
            "Entering run loop | stream_interval=%ss, status_interval=%ss",
            self.STREAM_INTERVAL_SECONDS,
            self.STATUS_INTERVAL_SECONDS,
        )

        next_sample = time.time()
        next_status = time.time()

        while self.running:

            try:

                now = time.time()

                if now >= next_sample:
                    self.publish_sample()
                    next_sample += self.STREAM_INTERVAL_SECONDS

                if now >= next_status:
                    self.publish_status()
                    next_status += self.STATUS_INTERVAL_SECONDS

                time.sleep(0.05)

            except Exception:
                log.exception(
                    "Error in run loop"
                )
