"""Edge Detection view data store.

Holds detector telemetry (topic ``edge/status``), orchestrator risk
decisions (topic ``orchestrator/decision``) and anomalies (topic
``anomaly/detected``), together with the page's own action log. The
controller translates view actions into MQTT commands (``ed_start`` /
``ed_stop`` / ``ed_reset``) decoupled from the transport details.
"""

import threading
import time
from typing import Optional

from mqtt_client import ActionLog, DashboardClient

MAX_DETECTIONS = 500
MAX_SCORE_POINTS = 300
MAX_RUNTIME_POINTS = 60
DEFAULT_THRESHOLD = None

RISK_MAP = {
    "normal": "LOW",
    "uncertain": "MEDIUM",
    "anomaly": "HIGH",
}


class DetectionStore:

    def __init__(self, action_log: Optional[ActionLog] = None) -> None:
        self._lock = threading.Lock()
        self.action_log = action_log or ActionLog()

        self.detections: list[dict] = []
        self.latest: Optional[dict] = None

        # detector telemetry details
        self.status: Optional[dict] = None
        self.detection_enabled: Optional[bool] = None
        self.model_loaded: Optional[bool] = None
        self.threshold: Optional[float] = None
        self.samples_processed: int = 0
        self.inference_rate: float = 0.0
        self.avg_processing_time_ms: Optional[float] = None

        # orchestrator risk
        self.risk: Optional[str] = None
        self.latest_decision: Optional[dict] = None

        # time-series for the reconstruction chart and the runtime
        # sparklines
        self.score_history: list[dict] = []
        self.cpu_history: list[dict] = []
        self.mem_history: list[dict] = []
        self.latency_history: list[dict] = []

        self._last_detection_enabled: Optional[bool] = None
        self._last_model_loaded: Optional[bool] = None
        self._last_threshold: Optional[float] = None
        self._last_risk: Optional[str] = None

    # ------------------------------------------------------------------ #
    # ingest
    # ------------------------------------------------------------------ #

    def handle_anomaly(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()

        with self._lock:
            detection = {
                "anomaly": payload.get("anomaly"),
                "reason": payload.get("reason"),
                "metric": payload.get("metric"),
                "value": payload.get("value"),
                "fault": payload.get("fault"),
                "run": payload.get("simulationRun"),
                "ed_metrics": payload.get("ed_metrics") or {},
                "t": now,
            }
            self.detections.append(detection)
            self.latest = detection
            if len(self.detections) > MAX_DETECTIONS:
                self.detections = self.detections[-MAX_DETECTIONS:]

            metric = detection.get("metric")
            value = detection.get("value")
            detail = f" | {metric} = {value}" if metric else ""
            self.action_log.log(
                "stream",
                "Anomaly published to orchestrator",
            )
            self.action_log.log(
                "detect",
                f"Anomaly detected{detail}",
            )

    def handle_edge_status(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        status = payload.get("status") or {}
        ed_metrics = payload.get("ed_metrics") or {}
        container = ed_metrics.get("container") or {}
        now = time.time()

        with self._lock:
            self.status = {"status": status, "received_at": now}

            detection_enabled = status.get("detection_enabled")
            if (
                detection_enabled is not None
                and detection_enabled != self._last_detection_enabled
            ):
                self._last_detection_enabled = detection_enabled
                self.action_log.log(
                    "state",
                    "Detector started"
                    if detection_enabled
                    else "Detector stopped",
                )

            model_loaded = status.get("model_loaded")
            if (
                model_loaded is True
                and self._last_model_loaded is False
            ):
                self.action_log.log(
                    "state", "Model reloaded"
                )
            if model_loaded is not None:
                self._last_model_loaded = model_loaded

            threshold = status.get("threshold")
            if (
                threshold is not None
                and threshold != self._last_threshold
            ):
                self._last_threshold = threshold
                self.action_log.log(
                    "detect",
                    f"Threshold updated to {threshold:g}",
                )

            self.detection_enabled = detection_enabled
            self.model_loaded = model_loaded
            if threshold is not None:
                self.threshold = threshold
            if status.get("samples_processed") is not None:
                self.samples_processed = status["samples_processed"]
            if status.get("inference_rate") is not None:
                self.inference_rate = status["inference_rate"]

            avg_ms = status.get("avg_processing_time_ms")
            if avg_ms is not None:
                self.avg_processing_time_ms = avg_ms
            elif ed_metrics.get("processing_time_ms") is not None:
                self.avg_processing_time_ms = ed_metrics["processing_time_ms"]

            error = status.get("reconstruction_error")
            if error is not None:
                self.score_history.append({
                    "t": now,
                    "value": error,
                    "anomaly": (
                        self.threshold is not None
                        and error > self.threshold
                    ),
                })
                self._trim_history(
                    self.score_history, MAX_SCORE_POINTS
                )

            cpu = container.get("cpu_percent")
            if cpu is not None:
                self.cpu_history.append({"t": now, "value": cpu})
                self._trim_history(self.cpu_history, MAX_RUNTIME_POINTS)

            mem = container.get("memory_used_bytes")
            if mem is not None:
                self.mem_history.append({"t": now, "value": mem})
                self._trim_history(self.mem_history, MAX_RUNTIME_POINTS)

            if avg_ms is not None:
                self.latency_history.append({"t": now, "value": avg_ms})
                self._trim_history(self.latency_history, MAX_RUNTIME_POINTS)

    def handle_decision(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()

        with self._lock:
            decision = payload.get("decision")
            risk = RISK_MAP.get(decision) if decision else None

            self.latest_decision = {
                "t": now,
                "decision": decision,
                "risk": risk,
                "anomaly_ratio": payload.get("anomaly_ratio"),
                "anomaly_rate": payload.get("anomaly_rate"),
                "confidence": payload.get("confidence"),
                "anomaly_count": payload.get("anomaly_count"),
                "window_seconds": payload.get("window_seconds"),
            }

            if risk is not None and risk != self._last_risk:
                self._last_risk = risk
                self.action_log.log(
                    "state",
                    f"Risk level {risk}",
                )
            if risk is not None:
                self.risk = risk

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    def recent_detections(self) -> list[dict]:
        with self._lock:
            return list(self.detections)

    def latest_detection(self) -> Optional[dict]:
        with self._lock:
            return self.latest

    def recent_scores(self) -> list[dict]:
        with self._lock:
            return list(self.score_history)

    def recent_runtime(self) -> dict:
        with self._lock:
            return {
                "cpu": list(self.cpu_history),
                "memory": list(self.mem_history),
                "latency": list(self.latency_history),
            }

    def anomaly_rate_percent(self) -> Optional[float]:
        with self._lock:
            ratio = (self.latest_decision or {}).get(
                "anomaly_ratio"
            )
            if ratio is not None:
                return round(ratio * 100.0, 1)
            return None

    def recent_actions(self) -> list[dict]:
        return self.action_log.recent()

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _trim_history(history: list, max_len: int) -> None:
        if len(history) > max_len:
            del history[: len(history) - max_len]


class DetectionController:
    """Translates Edge Detection UI actions into MQTT commands."""

    def __init__(
        self,
        store: DetectionStore,
        client: DashboardClient,
    ) -> None:
        self.store = store
        self.client = client

    def send_start(self) -> None:
        self.client.send_command("ed_start")
        self.store.action_log.log("state", "Detection start sent")

    def send_stop(self) -> None:
        self.client.send_command("ed_stop")
        self.store.action_log.log("state", "Detection stop sent")

    def send_reset(self) -> None:
        self.client.send_command("ed_reset")
        self.store.action_log.log("state", "Reset engine state sent")