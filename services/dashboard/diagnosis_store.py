"""Diagnosis Service view data store.

Holds classifier telemetry (topic ``classifier/status``), diagnosis results
(topic ``classification/result``) and incoming diagnosis requests (topic
``classification/request``), together with the page's own action log. The
controller translates view actions into MQTT commands (``cl_start`` /
``cl_stop`` / ``cl_reset``) decoupled from the transport details.

The heartbeat is the primary source of health/throughput data; results
provide the authoritative latest diagnosis. Reset statistics clears the
runtime counters on the service plus the dashboard-local history only.
"""

import threading
import time
from typing import Optional

from mqtt_client import ActionLog, DashboardClient

MAX_RESULTS = 100
MAX_RUNTIME_POINTS = 60
QUEUE_WARN_DEPTH = 10


class DiagnosisStore:

    def __init__(self, action_log: Optional[ActionLog] = None) -> None:
        self._lock = threading.Lock()
        self.action_log = action_log or ActionLog()

        # classifier health / throughput (heartbeat)
        self.status: Optional[dict] = None
        self.running: Optional[bool] = None
        self.model_loaded: Optional[bool] = None
        self.model: Optional[str] = None
        self.classes_available: Optional[int] = None
        self.queue_depth: int = 0
        self.classifications_processed: int = 0
        self.batch_count: int = 0
        self.classification_rate: float = 0.0
        self.avg_processing_time_ms: Optional[float] = None

        # latest diagnosis (heartbeat fallback + result source)
        self.last_fault_number: Optional[int] = None
        self.last_diagnosis: Optional[str] = None
        self.last_confidence: Optional[float] = None
        self.latest: Optional[dict] = None
        self.results: list[dict] = []

        # runtime sparkline history
        self.cpu_history: list[dict] = []
        self.mem_history: list[dict] = []
        self.latency_history: list[dict] = []

        self._last_running: Optional[bool] = None
        self._last_model_loaded: Optional[bool] = None

    # ------------------------------------------------------------------ #
    # ingest
    # ------------------------------------------------------------------ #

    def handle_status(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        status = payload.get("status") or {}
        cl_metrics = payload.get("cl_metrics") or {}
        container = cl_metrics.get("container") or {}
        now = time.time()

        with self._lock:
            self.status = {"status": status, "received_at": now}

            running = status.get("running")
            if running is not None and running != self._last_running:
                self._last_running = running
                self.action_log.log(
                    "state",
                    "Service started" if running else "Service stopped",
                )

            model_loaded = status.get("model_loaded")
            if model_loaded is True and self._last_model_loaded is False:
                self.action_log.log("state", "Model loaded")
            if model_loaded is not None:
                self._last_model_loaded = model_loaded

            self.running = running
            self.model_loaded = model_loaded
            if status.get("model") is not None:
                self.model = status["model"]
            if status.get("classes_available") is not None:
                self.classes_available = status["classes_available"]
            if status.get("queue_depth") is not None:
                self.queue_depth = status["queue_depth"]
            if status.get("classifications_processed") is not None:
                self.classifications_processed = status[
                    "classifications_processed"
                ]
            if status.get("batch_count") is not None:
                self.batch_count = status["batch_count"]
            if status.get("classification_rate") is not None:
                self.classification_rate = status["classification_rate"]
            if status.get("last_fault_number") is not None:
                self.last_fault_number = status["last_fault_number"]
            if status.get("last_diagnosis") is not None:
                self.last_diagnosis = status["last_diagnosis"]
            if status.get("last_confidence") is not None:
                self.last_confidence = status["last_confidence"]

            avg_ms = status.get("avg_processing_time_ms")
            if avg_ms is not None:
                self.avg_processing_time_ms = avg_ms
                self.latency_history.append({"t": now, "value": avg_ms})
                self._trim_history(self.latency_history, MAX_RUNTIME_POINTS)

            cpu = container.get("cpu_percent")
            if cpu is not None:
                self.cpu_history.append({"t": now, "value": cpu})
                self._trim_history(self.cpu_history, MAX_RUNTIME_POINTS)

            mem = container.get("memory_used_bytes")
            if mem is not None:
                self.mem_history.append({"t": now, "value": mem})
                self._trim_history(self.mem_history, MAX_RUNTIME_POINTS)

    def handle_result(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()

        with self._lock:
            result = {
                "t": now,
                "batch_id": payload.get("batch_id"),
                "fault_number": payload.get("fault_number"),
                "diagnosis": payload.get("diagnosis"),
                "confidence": payload.get("confidence"),
                "model": payload.get("model"),
                "sample_count": payload.get("sample_count"),
            }
            self.results.append(result)
            if len(self.results) > MAX_RESULTS:
                self.results = self.results[-MAX_RESULTS:]
            self.latest = result

            diagnosis = payload.get("diagnosis") or "unknown"
            self.action_log.log("mqtt", "MQTT result published")
            self.action_log.log("fault", f"Classification completed | {diagnosis}")

    def handle_request(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        meta = payload.get("meta") or {}
        batch_id = meta.get("batch_id")

        with self._lock:
            detail = f" | {batch_id}" if batch_id else ""
            self.action_log.log(
                "mqtt", f"Diagnosis request received{detail}"
            )

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    def latest_diagnosis(self) -> Optional[dict]:
        """Most recent diagnosis, preferring the result topic.

        Falls back to the ``last_*`` fields carried by the heartbeat so the
        centrepiece card still works when only ``classifier/status`` is
        being consumed.
        """
        with self._lock:
            if self.latest is not None:
                return self.latest
            if self.last_diagnosis is None and self.last_fault_number is None:
                return None
            return {
                "t": (self.status or {}).get("received_at"),
                "batch_id": None,
                "fault_number": self.last_fault_number,
                "diagnosis": self.last_diagnosis,
                "confidence": self.last_confidence,
                "model": self.model,
                "sample_count": None,
            }

    def recent_results(self) -> list[dict]:
        with self._lock:
            return list(self.results)

    def recent_runtime(self) -> dict:
        with self._lock:
            return {
                "cpu": list(self.cpu_history),
                "memory": list(self.mem_history),
                "latency": list(self.latency_history),
            }

    def queue_backed_up(self) -> bool:
        with self._lock:
            return self.queue_depth >= QUEUE_WARN_DEPTH

    def recent_actions(self) -> list[dict]:
        return self.action_log.recent()

    def reset(self) -> None:
        """Clear runtime counters and dashboard statistics only.

        The event log is intentionally kept so operators can still see the
        reset action in the timeline.
        """
        with self._lock:
            self.classifications_processed = 0
            self.batch_count = 0
            self.classification_rate = 0.0
            self.avg_processing_time_ms = None
            self.queue_depth = 0
            self.results = []
            self.latest = None
            self.last_fault_number = None
            self.last_diagnosis = None
            self.last_confidence = None
            self.cpu_history = []
            self.mem_history = []
            self.latency_history = []

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _trim_history(history: list, max_len: int) -> None:
        if len(history) > max_len:
            del history[: len(history) - max_len]


class DiagnosisController:
    """Translates Diagnosis UI actions into MQTT commands."""

    def __init__(
        self,
        store: DiagnosisStore,
        client: DashboardClient,
    ) -> None:
        self.store = store
        self.client = client

    def send_start(self) -> None:
        self.client.send_command("cl_start")
        self.store.action_log.log("state", "Classifier start sent")

    def send_stop(self) -> None:
        self.client.send_command("cl_stop")
        self.store.action_log.log("state", "Classifier stop sent")

    def send_reset(self) -> None:
        self.client.send_command("cl_reset")
        self.store.reset()
        self.store.action_log.log("state", "Reset statistics sent")
