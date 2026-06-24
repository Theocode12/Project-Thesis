import threading
import time

from replay_engine import ReplayEngine

from shared.mqtt_topics import MQTTOPIC
from shared.mqtt_service import MQTTService

class SensorGeneratorService:

    STREAM_INTERVAL_SECONDS = 0.1

    STATUS_INTERVAL_SECONDS = 5

    def __init__(
        self,
        replay_engine: ReplayEngine,
        mqtt_service: MQTTService
    ):

        self.replay_engine = replay_engine
        self.mqtt_service = mqtt_service

        self.running = False

        self.stream_thread = None
        self.status_thread = None

    def start(self):

        self.mqtt_service.subscribe(
            MQTTOPIC.SYSTEM_CONTROL,
            self.handle_command
        )

        self.mqtt_service.connect()
        self.mqtt_service.start()

        self.running = True

        self.replay_engine.start()

        self.stream_thread = threading.Thread(
            target=self._stream_loop,
            daemon=True
        )

        self.status_thread = threading.Thread(
            target=self._status_loop,
            daemon=True
        )

        self.stream_thread.start()
        self.status_thread.start()

    def stop(self):

        self.running = False

        self.replay_engine.stop()

        self.mqtt_service.stop()

    def handle_command(
        self,
        payload: dict
    ):

        action = payload.get("action")

        if action == "start":

            self.replay_engine.start()

        elif action == "stop":

            self.replay_engine.stop()

        elif action == "reset":

            self.replay_engine.reset()

        elif action == "set_fault":

            fault = payload["fault"]

            self.replay_engine.set_fault(
                fault
            )

        elif action == "set_stream":

            fault = payload["fault"]

            run = payload["run"]

            self.replay_engine.set_stream(
                fault=fault,
                run=run
            )

    def _stream_loop(self):

        while self.running:

            sample = (
                self.replay_engine
                .next_sample()
            )

            if sample is not None:

                self.mqtt_service.publish(
                    MQTTOPIC.SENSOR_RAW,
                    sample
                )

            time.sleep(
                self.STREAM_INTERVAL_SECONDS
            )

    def _status_loop(self):

        while self.running:

            self.mqtt_service.publish(
                MQTTOPIC.SENSOR_STATUS,
                self.replay_engine.get_status()
            )

            time.sleep(
                self.STATUS_INTERVAL_SECONDS
            )

    # Alternative to Threads
    def run(self):

        next_sample = time.time()

        next_status = time.time()

        while self.running:

            now = time.time()

            if now >= next_sample:

                self.publish_sample()

                next_sample += 0.1

            if now >= next_status:

                self.publish_status()

                next_status += 5

            time.sleep(0.01)
