"""
diagnosis_service.py

Background job runner for the classifier service.

Diagnosis requests are enqueued by the HTTP layer and processed by a
single daemon worker thread. This keeps the HTTP request path fast
(return early) while inference and MQTT publishing happen off the
request path.

The service also owns a periodic status heartbeat (mirroring the
edge-detector) so consumers can observe classifier health, throughput
and backlog without waiting for a classification to occur. Both the
per-classification metrics and the heartbeat are published under the
service's metric key (``cl_metrics``).
"""

import logging
import threading
import time
from collections import deque
from queue import Queue
from uuid import uuid4

from classifier import Classifier

from shared.mqtt_message_envelop import MQTTMessageEnvelope
from shared.mqtt_service import MQTTService
from shared.mqtt_topics import MQTTOPIC
from shared.service_metrics import ServiceMetrics

log = logging.getLogger(__name__)

_STOP_SENTINEL = object()

STATUS_INTERVAL_SECONDS = 2.0
RATE_WINDOW_SECONDS = 5.0
LATENCY_WINDOW_SECONDS = 30.0


class DiagnosisService:

    def __init__(
        self,
        classifier: Classifier,
        mqtt_service: MQTTService,
        metrics: ServiceMetrics = None,
    ):
        self.classifier = classifier
        self.mqtt_service = mqtt_service
        self.metrics = (
            metrics or ServiceMetrics(
                service_name="classifier"
            )
        )
        # Status heartbeats use their own metrics instance so the periodic
        # publisher never races the worker on processing-timing state.
        self._status_metrics = ServiceMetrics(
            service_name="classifier"
        )

        self._queue: Queue = Queue()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._status_thread: threading.Thread | None = None
        self._started = False

        self._lock = threading.Lock()
        self.batch_count = 0
        self.classifications_processed = 0
        self._completion_times: deque = deque()
        self._latencies: deque = deque()
        self._last_prediction = {
            "fault_number": None,
            "diagnosis": None,
            "confidence": None,
        }
        self._action_map = {
            "cl_start": self._cmd_start,
            "cl_stop": self._cmd_stop,
            "cl_reset": self._cmd_reset,
        }

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop_event.clear()

        self.mqtt_service.subscribe(
            MQTTOPIC.SYSTEM_CONTROL, self.handle_command
        )

        self._worker = threading.Thread(
            target=self._run,
            name="diagnosis-worker",
            daemon=True,
        )
        self._worker.start()

        self._status_thread = threading.Thread(
            target=self._status_loop,
            name="classifier-status",
            daemon=True,
        )
        self._status_thread.start()

        log.info("Diagnosis worker started")

    def stop(self) -> None:
        if not self._started:
            return
        self._stop_event.set()
        self._queue.put(_STOP_SENTINEL)

        if self._worker is not None and self._worker.is_alive():
            self._worker.join(timeout=5)
        if (
            self._status_thread is not None
            and self._status_thread.is_alive()
        ):
            self._status_thread.join(timeout=5)

        self._started = False
        log.info("Diagnosis worker stopped")

    # ------------------------------------------------------------------
    # MQTT command handling (system/control)
    # ------------------------------------------------------------------

    def handle_command(self, payload: dict) -> None:
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

    def _cmd_start(self, payload: dict) -> None:
        self.start()
        log.info("Classifier started via command")

    def _cmd_stop(self, payload: dict) -> None:
        self.stop()
        log.info("Classifier stopped via command")

    def _cmd_reset(self, payload: dict) -> None:
        with self._lock:
            self.batch_count = 0
            self.classifications_processed = 0
            self._completion_times.clear()
            self._latencies.clear()
            self._last_prediction = {
                "fault_number": None,
                "diagnosis": None,
                "confidence": None,
            }
        log.info("Classifier statistics reset")

    def submit(self, payload: dict) -> str:
        batch_id = self._extract_batch_id(payload)
        self._queue.put(
            (batch_id, payload, time.time())
        )
        log.info(
            "Enqueued diagnosis job | batch_id=%s",
            batch_id,
        )
        return batch_id

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is _STOP_SENTINEL:
                    break
                batch_id, payload, submitted_at = job
                self._process(batch_id, payload, submitted_at)
            except Exception:
                log.exception("Diagnosis worker error")
            finally:
                self._queue.task_done()

    def _process(
        self,
        batch_id: str,
        payload: dict,
        submitted_at: float = None,
    ) -> None:
        batch = payload.get("batch") or []
        meta = payload.get("meta") or {}

        self.metrics.start_processing(received_at=submitted_at)

        queue_depth = self._queue.qsize()

        inference_started_at = self.metrics.mark(
            "inference_started_at"
        )
        try:
            prediction = self.classifier.predict(batch)
        except Exception:
            log.exception(
                "Classification failed | batch_id=%s",
                batch_id,
            )
            prediction = {
                "fault_number": None,
                "diagnosis": "unknown",
                "model": getattr(
                    self.classifier, "model", "unknown"
                ),
                "confidence": 0.0,
                "sample_count": len(batch),
                "prediction_counts": {},
                "accuracy": None,
                "error": "classification_failed",
            }
        finally:
            inference_ended_at = self.metrics.mark(
                "inference_ended_at"
            )

        extra = {
            "batch_id": batch_id,
            "batch_size": len(batch),
            "queue_depth": queue_depth,
            "model": prediction.get("model"),
            "classes_available": self._classes_available(),
            "accuracy": prediction.get("accuracy"),
            "correct_count": prediction.get("correct_count"),
            "ground_truth_available": prediction.get(
                "ground_truth_available"
            ),
        }

        metrics_snapshot = self.metrics.snapshot(extra=extra)

        self._record_batch(
            len(batch),
            inference_started_at,
            inference_ended_at,
        )
        self._last_prediction = {
            "fault_number": prediction.get("fault_number"),
            "diagnosis": prediction.get("diagnosis"),
            "confidence": prediction.get("confidence"),
        }

        result = {
            "batch_id": batch_id,
            "diagnosis": prediction.get("diagnosis", "unknown"),
            "fault_number": prediction.get("fault_number"),
            "model": prediction.get("model", "unknown"),
            "confidence": prediction.get("confidence", 0.0),
            "sample_count": prediction.get(
                "sample_count", len(batch)
            ),
            "prediction_counts": prediction.get(
                "prediction_counts", {}
            ),
            "accuracy": prediction.get("accuracy"),
            "correct_count": prediction.get("correct_count"),
            "ground_truth_available": prediction.get(
                "ground_truth_available"
            ),
            "meta": meta,
            self.metrics.metrics_key: metrics_snapshot,
        }

        self.mqtt_service.publish(
            MQTTOPIC.CLASSIFICATION_RESULT,
            MQTTMessageEnvelope.create(
                source="classifier",
                payload=result,
            ).to_dict(),
        )

    # ------------------------------------------------------------------
    # Status heartbeat
    # ------------------------------------------------------------------

    def _status_loop(self) -> None:
        while not self._stop_event.wait(STATUS_INTERVAL_SECONDS):
            self.publish_status()

    def publish_status(self) -> None:
        try:
            with self._lock:
                last = dict(self._last_prediction)
                batch_count = self.batch_count
                classified = self.classifications_processed

            status = {
                "running": self._started,
                "model_loaded": self._model_loaded(),
                "model": getattr(self.classifier, "model", None),
                "classes_available": self._classes_available(),
                "classifications_processed": classified,
                "batch_count": batch_count,
                "classification_rate": self._classification_rate(),
                "avg_processing_time_ms": (
                    self._avg_processing_time_ms()
                ),
                "queue_depth": self._queue.qsize(),
                "last_fault_number": last.get("fault_number"),
                "last_diagnosis": last.get("diagnosis"),
                "last_confidence": last.get("confidence"),
            }

            payload = self._status_metrics.wrap(
                data_key="status",
                data=status,
            )

            message = MQTTMessageEnvelope.create(
                source="classifier",
                payload=payload,
            )
            self.mqtt_service.publish(
                MQTTOPIC.CLASSIFIER_STATUS,
                message.to_dict(),
            )
        except Exception:
            log.exception("Error publishing classifier status")

    def _model_loaded(self) -> bool:
        return getattr(self.classifier, "model", None) is not None

    def _classes_available(self):
        try:
            encoder = getattr(
                self.classifier, "label_encoder", None
            )
            if encoder is None:
                return None
            return len(encoder.classes_)
        except Exception:
            return None

    def _record_batch(
        self,
        batch_size: int,
        started_at: float,
        ended_at: float,
    ) -> None:
        now = time.time()
        processing_time_ms = (ended_at - started_at) * 1000.0
        if batch_size:
            processing_time_ms /= batch_size
        with self._lock:
            self.batch_count += 1
            self.classifications_processed += batch_size

            self._completion_times.append(now)
            rate_cutoff = now - RATE_WINDOW_SECONDS
            while (
                self._completion_times
                and self._completion_times[0] < rate_cutoff
            ):
                self._completion_times.popleft()

            if processing_time_ms is not None:
                self._latencies.append(
                    (now, processing_time_ms)
                )
                latency_cutoff = now - LATENCY_WINDOW_SECONDS
                while (
                    self._latencies
                    and self._latencies[0][0] < latency_cutoff
                ):
                    self._latencies.popleft()

    def _classification_rate(self) -> float:
        now = time.time()
        with self._lock:
            times = [
                ts
                for ts in self._completion_times
                if ts >= now - RATE_WINDOW_SECONDS
            ]
            if not times:
                return 0.0
            window = min(
                RATE_WINDOW_SECONDS, now - times[0]
            )
            if window <= 0:
                return 0.0
            return round(len(times) / window, 2)

    def _avg_processing_time_ms(self) -> float | None:
        with self._lock:
            if not self._latencies:
                return None
            return round(
                sum(ms for _, ms in self._latencies)
                / len(self._latencies),
                3,
            )

    @staticmethod
    def _extract_batch_id(payload: dict) -> str:
        meta = payload.get("meta") or {}
        batch_id = meta.get("batch_id")
        if batch_id:
            return str(batch_id)
        return f"batch_{uuid4().hex[:12]}"
