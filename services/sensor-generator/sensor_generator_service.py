import time
from os import getenv

from replay_engine import ReplayEngine

from shared.mqtt_topics import MQTTOPIC
from shared.mqtt_service import MQTTService
from shared.mqtt_message_envelop import MQTTMessageEnvelope

class SensorGeneratorService:

    def __init__(
        self,
        replay_engine: ReplayEngine,
        mqtt_service: MQTTService
    ):

        self.replay_engine = replay_engine
        self.mqtt_service = mqtt_service
        self.running = False
        self.STREAM_INTERVAL_SECONDS = float(
            getenv("STREAM_INTERVAL", "0.1")
        )
        self.STATUS_INTERVAL_SECONDS = float(
            getenv("STATUS_INTERVAL", "5")
        )
        # self.stream_thread = None
        # self.status_thread = None
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

    def stop(self):

        self.running = False
        self.replay_engine.stop()
        self.mqtt_service.stop()

    def handle_command(
        self,
        payload: dict | None
    ):

        if payload is None:
            return
        handler = self._action_map.get(
            payload.get("action")
        )
        if handler is not None:
            handler(payload)

    def _cmd_start(
        self,
        payload: None
    ):
        self.replay_engine.start()

    def _cmd_stop(
        self,
        payload: None
    ):
        self.replay_engine.stop()

    def _cmd_reset(
        self,
        payload: None
    ):
        self.replay_engine.reset()

    def _cmd_set_fault(
        self,
        payload: dict
    ):
        self.replay_engine.set_fault(
            payload["fault"]
        )

    def _cmd_set_stream(
        self,
        payload: dict
    ):
        self.replay_engine.set_stream(
            fault=payload["fault"],
            run=payload["run"]
        )

    def _cmd_set_stream_interval(
        self,
        payload: dict
    ):
        self.STREAM_INTERVAL_SECONDS = float(
            payload["interval"]
        )

    def _cmd_set_status_interval(
        self,
        payload: dict
    ):
        self.STATUS_INTERVAL_SECONDS = float(
            payload["interval"]
        )

    def publish_sample(self):
        
        sample = self.replay_engine.next_sample()

        if sample is not None:
            message = MQTTMessageEnvelope.create(
                source="sensor-generator",
                payload=sample
            )
            self.mqtt_service.publish(
                MQTTOPIC.SENSOR_RAW,
                message.to_dict()
            )

    def publish_status(self):

        status = self.replay_engine.get_status()
        message = MQTTMessageEnvelope.create(
            source="sensor-generator",
            payload=status
        )
        self.mqtt_service.publish(
            MQTTOPIC.SENSOR_STATUS,
            message.to_dict()
        )

    # Alternative to Threads
    def run(self):

        next_sample = time.time()

        next_status = time.time()

        while self.running:

            now = time.time()

            if now >= next_sample:

                self.publish_sample()
                next_sample += self.STREAM_INTERVAL_SECONDS

            if now >= next_status:

                self.publish_status()
                next_status += self.STATUS_INTERVAL_SECONDS

            time.sleep(0.01)
