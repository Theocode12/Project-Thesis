"""
diagnosis_service.py

Background job runner for the classifier service.

Diagnosis requests are enqueued by the HTTP layer and processed by a
single daemon worker thread. This keeps the HTTP request path fast
(return early) while inference and MQTT publishing happen off the
request path.
"""

import logging
import threading
from queue import Queue
from uuid import uuid4

from classifier import Classifier

from shared.mqtt_message_envelop import MQTTMessageEnvelope
from shared.mqtt_service import MQTTService
from shared.mqtt_topics import MQTTOPIC
from shared.service_metrics import ServiceMetrics

log = logging.getLogger(__name__)

_STOP_SENTINEL = object()


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
        self._queue: Queue = Queue()
        self._worker = threading.Thread(
            target=self._run,
            name="diagnosis-worker",
            daemon=True,
        )
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._worker.start()
        log.info("Diagnosis worker started")

    def stop(self) -> None:
        if not self._started:
            return
        self._queue.put(_STOP_SENTINEL)
        self._worker.join(timeout=5)
        self._started = False
        log.info("Diagnosis worker stopped")

    def submit(self, payload: dict) -> str:
        batch_id = self._extract_batch_id(payload)
        self._queue.put((batch_id, payload))
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
                batch_id, payload = job
                self._process(batch_id, payload)
            except Exception:
                log.exception("Diagnosis worker error")
            finally:
                self._queue.task_done()

    def _process(self, batch_id: str, payload: dict) -> None:
        batch = payload.get("batch") or []
        meta = payload.get("meta") or {}

        self.metrics.start_processing()

        try:
            prediction = self.classifier.predict(batch)
        except Exception:
            log.exception("Classification failed | batch_id=%s", batch_id)
            prediction = {
                "fault_number": None,
                "diagnosis": "unknown",
                "model": getattr(self.classifier, "model", "unknown"),
                "confidence": 0.0,
                "sample_count": len(batch),
                "prediction_counts": {},
                "error": "classification_failed",
            }

        result = {
            "batch_id": batch_id,
            "diagnosis": prediction.get("diagnosis", "unknown"),
            "fault_number": prediction.get("fault_number"),
            "model": prediction.get("model", "unknown"),
            "confidence": prediction.get("confidence", 0.0),
            "sample_count": prediction.get("sample_count", len(batch)),
            "prediction_counts": prediction.get("prediction_counts", {}),
            "meta": meta,
            "classifier_metrics": self.metrics.snapshot(),
        }

        self.mqtt_service.publish(
            MQTTOPIC.CLASSIFICATION_RESULT,
            MQTTMessageEnvelope.create(
                source="classifier",
                payload=result,
            ).to_dict(),
        )

    @staticmethod
    def _extract_batch_id(payload: dict) -> str:
        meta = payload.get("meta") or {}
        batch_id = meta.get("batch_id")
        if batch_id:
            return str(batch_id)
        return f"batch_{uuid4().hex[:12]}"
