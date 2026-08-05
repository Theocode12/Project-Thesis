import logging
import time
from collections import deque

from detector import Detector
from anomaly_event import AnomalyEvent

from shared.mqtt_topics import MQTTOPIC
from shared.mqtt_service import MQTTService
from shared.service_metrics import ServiceMetrics
from shared.mqtt_message_envelop import MQTTMessageEnvelope

log = logging.getLogger(__name__)

STATUS_INTERVAL_SECONDS = 2.0
RATE_WINDOW_SECONDS = 5.0
LATENCY_WINDOW_SECONDS = 30.0


class EdgeDetectorService:

    def __init__(
        self,
        detector: Detector,
        mqtt_service: MQTTService,
        metrics: ServiceMetrics = None
    ):
        self.detector = detector
        self.mqtt_service = mqtt_service
        self.metrics = (
            metrics or ServiceMetrics(
                service_name="edge-detector"
            )
        )
        self.running = False
        self.detection_enabled = True
        self.model_loaded = True
        self.samples_processed = 0
        self._sample_times: deque = deque()
        self._latencies: deque = deque()
        self._last_reconstruction_error = None
        self._last_status_at = 0.0
        self._action_map = {
            "ed_start": self._cmd_start,
            "ed_stop": self._cmd_stop,
            "ed_reset": self._cmd_reset,
        }

    def start(self):
        self.mqtt_service.connect()
        self.mqtt_service.subscribe(MQTTOPIC.SENSOR_RAW, self.handle_sample)
        self.mqtt_service.subscribe(
            MQTTOPIC.SYSTEM_CONTROL, self.handle_command
        )
        self.mqtt_service.start()

        self.running = True
        log.info("Edge detector started")

        self.publish_status()

    def stop(self):
        self.running = False
        self.mqtt_service.stop()
        log.info("Edge detector stopped")

    def handle_command(self, payload: dict):
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
        self.publish_status()

    def _cmd_start(self, payload: dict):
        self.detection_enabled = True
        log.info("Detection enabled")

    def _cmd_stop(self, payload: dict):
        self.detection_enabled = False
        log.info("Detection disabled")

    def _cmd_reset(self, payload: dict):
        self.samples_processed = 0
        self._sample_times.clear()
        self._latencies.clear()
        self._last_reconstruction_error = None
        log.info("Detector state reset")

    def handle_sample(self, payload: dict):
        try:
            if not self.detection_enabled:
                return

            inner = payload.get("payload") or {}
            sample = inner.get("sample")
            if sample is None:
                return

            self.metrics.start_processing(
                received_at=payload.get("timestamp")
            )

            started_at = time.perf_counter()
            result = self.detector.detect(sample)
            latency_ms = (time.perf_counter() - started_at) * 1000.0

            self._record_sample(latency_ms)
            self._last_reconstruction_error = result.get(
                "reconstruction_error"
            )

            if not result["anomaly"]:
                return

            event = AnomalyEvent.create(
                result=result,
                sample=sample,
                sg_metrics=inner.get("sg_metrics"),
                ed_metrics=self.metrics.snapshot(),
            )
            self.mqtt_service.publish(
                MQTTOPIC.ANOMALY_DETECTED,
                event.to_dict(),
            )

            log.info(
                "Anomaly detected | metric=%s value=%s reconstruction_error=%s",
                result.get("metric"),
                result.get("value"),
                result.get("reconstruction_error"),
            )

        except Exception:
            log.exception("Error processing sample")

    def _record_sample(self, latency_ms: float) -> None:
        now = time.time()
        self.samples_processed += 1
        self._sample_times.append(now)
        self._latencies.append((now, latency_ms))
        rate_cutoff = now - RATE_WINDOW_SECONDS
        while self._sample_times and self._sample_times[0] < rate_cutoff:
            self._sample_times.popleft()
        latency_cutoff = now - LATENCY_WINDOW_SECONDS
        while self._latencies and self._latencies[0][0] < latency_cutoff:
            self._latencies.popleft()

    def _inference_rate(self) -> float:
        if not self._sample_times:
            return 0.0
        window = min(RATE_WINDOW_SECONDS, time.time() - self._sample_times[0])
        if window <= 0:
            return 0.0
        return round(len(self._sample_times) / window, 2)

    def _avg_processing_time_ms(self) -> float | None:
        if not self._latencies:
            return None
        return round(
            sum(latency for _, latency in self._latencies)
            / len(self._latencies),
            3,
        )

    def publish_status(self) -> None:
        try:
            threshold = None
            try:
                threshold = float(getattr(self.detector, "threshold", None))
            except (TypeError, ValueError):
                threshold = None

            payload = self.metrics.wrap(
                data_key="status",
                data={
                    "running": self.running,
                    "detection_enabled": self.detection_enabled,
                    "model_loaded": self.model_loaded,
                    "threshold": threshold,
                    "samples_processed": self.samples_processed,
                    "inference_rate": self._inference_rate(),
                    "reconstruction_error": self._last_reconstruction_error,
                    "avg_processing_time_ms": (
                        self._avg_processing_time_ms()
                    ),
                },
            )

            message = MQTTMessageEnvelope.create(
                source="edge-detector",
                payload=payload,
            )
            self.mqtt_service.publish(
                MQTTOPIC.EDGE_STATUS,
                message.to_dict(),
            )
        except Exception:
            log.exception("Error publishing status")

    def run(self):
        while self.running:
            try:
                now = time.time()
                if (
                    now - self._last_status_at
                    >= STATUS_INTERVAL_SECONDS
                ):
                    self.publish_status()
                    self._last_status_at = now
                time.sleep(0.25)
            except Exception:
                log.exception("Error in run loop")
