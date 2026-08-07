"""System Overview view data store.

Aggregates cross-service telemetry into the platform-level observability
metrics consumed by the System Overview home page:

* Detection latency  — sensor generation → anomaly detection completion.
* Diagnosis latency  — diagnosis request → diagnosis completion.
* End-to-end latency — sensor generation → final diagnosis published.
* Cloud communication — bytes escalated to the cloud diagnosis service.
* Runtime summary     — diagnosis requests, escalations, queue depth, risk.

The store subscribes to ``anomaly/detected``, ``orchestrator/decision`` and
``classification/result`` directly. Runtime (CPU / memory) series and health
counters are read from the existing per-service stores, which are injected
through the constructor so the overview never duplicates their ingestion
logic.
"""

import json
import os
import threading
import time
from collections import deque
from datetime import UTC, datetime
from typing import Optional

from mqtt_client import ActionLog

MAX_LATENCY_POINTS = 200
MAX_PENDING_REQUESTS = 16

RISK_MAP = {
    "normal": "LOW",
    "uncertain": "MEDIUM",
    "anomaly": "HIGH",
}

QUEUE_WARN_DEPTH = 10

DEPLOYMENT_MODES = ("edge", "cloud", "hybrid")


def _parse_ts(value) -> Optional[float]:
    """Parse an ISO-8601 timestamp (or epoch float) into epoch seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return None


def _batch_bytes(batch) -> int:
    """Serialized size in bytes of an escalated batch (cloud payload).

    An empty batch carries no sample data, so it contributes zero bytes to
    the "data sent to cloud" total.
    """
    if not batch:
        return 0
    try:
        return len(json.dumps(batch).encode("utf-8"))
    except Exception:
        return 0


class OverviewStore:

    def __init__(
        self,
        action_log: Optional[ActionLog] = None,
        sensor_store=None,
        detection_store=None,
        diagnosis_store=None,
    ) -> None:
        self._lock = threading.Lock()
        self.action_log = action_log or ActionLog()
        self._sensor_store = sensor_store
        self._detection_store = detection_store
        self._diagnosis_store = diagnosis_store

        self.started_at = time.time()
        self.connected: bool = False
        self._seen: bool = False

        # rolling latency streams ({t, ms})
        self.detection_latency: list[dict] = []
        self.diagnosis_latency: list[dict] = []
        self.e2e_latency: list[dict] = []

        # orchestrator / cloud communication
        self.risk: Optional[str] = None
        self.latest_decision: Optional[dict] = None
        self.anomaly_decisions: int = 0
        self.escalations: int = 0
        self.bytes_sent_to_cloud: int = 0

        self._last_sensor_ts: Optional[float] = None
        self._pending_requests: deque = deque()
        self._last_risk: Optional[str] = None

    # ------------------------------------------------------------------ #
    # ingest
    # ------------------------------------------------------------------ #

    def handle_anomaly(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()
        completed_ts = _parse_ts(envelope.get("timestamp")) or now
        sensor_ts = _parse_ts((payload.get("ed_metrics") or {}).get(
            "received_at"
        ))

        with self._lock:
            self._seen = True
            if sensor_ts is None:
                return
            self._last_sensor_ts = sensor_ts
            latency_ms = (completed_ts - sensor_ts) * 1000.0
            if latency_ms < 0:
                return
            self.detection_latency.append({"t": now, "ms": latency_ms})
            self._trim(self.detection_latency, MAX_LATENCY_POINTS)

    def handle_decision(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()
        decision_ts = _parse_ts(envelope.get("timestamp")) or now
        decision = payload.get("decision")
        risk = RISK_MAP.get(decision)
        reported = bool(payload.get("reported"))
        batch = payload.get("batch") or []

        with self._lock:
            self._seen = True
            self.latest_decision = {
                "t": now,
                "decision": decision,
                "risk": risk,
                "reported": reported,
                "anomaly_ratio": payload.get("anomaly_ratio"),
                "anomaly_count": payload.get("anomaly_count"),
                "window_seconds": payload.get("window_seconds"),
            }

            if risk is not None:
                self.risk = risk
                if risk != self._last_risk:
                    self._last_risk = risk
                    self.action_log.log("state", f"Risk level {risk}")

            if decision == "anomaly":
                self.anomaly_decisions += 1

            if decision == "anomaly" and reported:
                self.escalations += 1
                self.bytes_sent_to_cloud += _batch_bytes(batch)

                sensor_ts = self._last_sensor_ts
                if sensor_ts is None:
                    sensor_ts = _parse_ts(
                        (payload.get("sg_metrics") or {}).get("received_at")
                    )
                self._pending_requests.append((decision_ts, sensor_ts))
                while len(self._pending_requests) > MAX_PENDING_REQUESTS:
                    self._pending_requests.popleft()

                self.action_log.log(
                    "fault", "Cloud escalation | window sent for diagnosis"
                )

    def handle_result(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()
        result_ts = _parse_ts(envelope.get("timestamp")) or now

        with self._lock:
            self._seen = True
            if not self._pending_requests:
                return
            request_ts, sensor_ts = self._pending_requests.popleft()

            latency_ms = (result_ts - request_ts) * 1000.0
            if latency_ms >= 0:
                self.diagnosis_latency.append({"t": now, "ms": latency_ms})
                self._trim(self.diagnosis_latency, MAX_LATENCY_POINTS)

            if sensor_ts is not None:
                e2e_ms = (result_ts - sensor_ts) * 1000.0
                if e2e_ms >= 0:
                    self.e2e_latency.append({"t": now, "ms": e2e_ms})
                    self._trim(self.e2e_latency, MAX_LATENCY_POINTS)

            diagnosis = payload.get("diagnosis") or "unknown"
            self.action_log.log(
                "fault", f"Diagnosis completed | {diagnosis}"
            )

    # ------------------------------------------------------------------ #
    # reads
    # ------------------------------------------------------------------ #

    def sensor_store(self):
        return self._sensor_store

    def detection_store(self):
        return self._detection_store

    def diagnosis_store(self):
        return self._diagnosis_store

    def recent_latencies(self) -> dict:
        with self._lock:
            return {
                "detection": list(self.detection_latency),
                "diagnosis": list(self.diagnosis_latency),
                "e2e": list(self.e2e_latency),
            }

    def cloud_escalations(self) -> int:
        with self._lock:
            return self.escalations

    def anomaly_decisions_count(self) -> int:
        with self._lock:
            return self.anomaly_decisions

    def data_sent_to_cloud(self) -> int:
        with self._lock:
            return self.bytes_sent_to_cloud

    def diagnosis_requests(self) -> int:
        if self._diagnosis_store is None:
            return 0
        return self._diagnosis_store.batch_count

    def queue_depth(self) -> int:
        if self._diagnosis_store is None:
            return 0
        return self._diagnosis_store.queue_depth

    def current_risk(self) -> Optional[str]:
        with self._lock:
            return self.risk

    def runtime_series(self) -> dict:
        """Runtime CPU/memory histories for edge detection + cloud diagnosis."""
        if self._detection_store is not None:
            edge = self._detection_store.recent_runtime()
        else:
            edge = {"cpu": [], "memory": [], "latency": []}
        if self._diagnosis_store is not None:
            cloud = self._diagnosis_store.recent_runtime()
        else:
            cloud = {"cpu": [], "memory": [], "latency": []}
        return {"edge": edge, "cloud": cloud}

    def deployment_mode(self) -> str:
        """Active deployment mode from DEPLOYMENT_MODE (Edge/Cloud/Hybrid)."""
        mode = os.getenv("DEPLOYMENT_MODE", "").strip().lower()
        if mode in DEPLOYMENT_MODES:
            return mode.upper()
        return "UNKNOWN"

    def system_health(self) -> tuple[str, str]:
        """Derive platform health -> (label, tone)."""
        if not self.connected:
            return "CRITICAL", "stop"

        risk = self.current_risk()
        queue = self.queue_depth()
        backed_up = queue >= QUEUE_WARN_DEPTH

        detection = self._detection_store
        diagnosis = self._diagnosis_store

        if risk in ("HIGH", "MEDIUM") or backed_up:
            return "WARNING", "pause"

        if not self._seen:
            return "WARNING", "pause"

        if detection is not None and detection.detection_enabled is False:
            return "WARNING", "pause"
        if diagnosis is not None and diagnosis.running is False:
            return "WARNING", "pause"

        return "HEALTHY", "run"

    def recent_actions(self) -> list[dict]:
        return self.action_log.recent()

    def measurement_window(self) -> str:
        """Human-friendly window label for the cloud communication card."""
        elapsed = max(0.0, time.time() - self.started_at)
        return _format_duration(elapsed)

    def uptime_str(self) -> str:
        started = datetime.fromtimestamp(self.started_at, UTC)
        return started.strftime("%H:%M:%S")

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _trim(history: list, max_len: int) -> None:
        if len(history) > max_len:
            del history[: len(history) - max_len]


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"
