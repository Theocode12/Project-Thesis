"""System Overview view data store.

Aggregates cross-service telemetry into the platform-level observability
metrics consumed by the System Overview home page:

* Detection latency  — sensor generation → anomaly detection completion.
* Diagnosis latency  — cloud request start → diagnosis result publication.
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
from datetime import UTC, datetime
from typing import Optional

from mqtt_client import ActionLog

# Safety cap; normal trimming is time-based below.
MAX_LATENCY_POINTS = 20_000
LATENCY_RETENTION_SECONDS = 900.0
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
        self._pending_requests: dict[str, dict] = {}
        self._last_risk: Optional[str] = None

    # ------------------------------------------------------------------ #
    # ingest
    # ------------------------------------------------------------------ #

    def handle_anomaly(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()
        ed_metrics = payload.get("ed_metrics") or {}
        completed_ts = (
            _parse_ts(ed_metrics.get("inference_ended_at"))
            or _parse_ts(envelope.get("timestamp"))
            or now
        )
        sensor_ts = (
            _parse_ts(ed_metrics.get("sensor_published_at"))
            or _parse_ts(ed_metrics.get("received_at"))
        )

        with self._lock:
            self._seen = True
            if sensor_ts is None:
                return
            self._last_sensor_ts = sensor_ts
            latency_ms = (completed_ts - sensor_ts) * 1000.0
            if latency_ms < 0:
                return
            self.detection_latency.append({"t": now, "ms": latency_ms})
            self._trim_latency(self.detection_latency)

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

                batch_id = payload.get("batch_id")
                if not batch_id:
                    return

                or_metrics = payload.get("or_metrics") or {}
                request_started_at = (
                    _parse_ts(or_metrics.get("reporting_started_at"))
                    or decision_ts
                )
                sensor_ts = self._sensor_timestamp_for_batch(payload)
                self._pending_requests[str(batch_id)] = {
                    "request_started_at": request_started_at,
                    "sensor_ts": sensor_ts,
                }
                while len(self._pending_requests) > MAX_PENDING_REQUESTS:
                    oldest_batch_id = next(iter(self._pending_requests))
                    del self._pending_requests[oldest_batch_id]

                self.action_log.log(
                    "fault", "Cloud escalation | window sent for diagnosis"
                )

    def handle_result(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()
        result_ts = _parse_ts(envelope.get("timestamp")) or now

        with self._lock:
            self._seen = True
            batch_id = payload.get("batch_id")
            pending = (
                self._pending_requests.pop(str(batch_id), None)
                if batch_id
                else None
            )
            meta = payload.get("meta") or {}
            orchestrator_timestamps = (
                meta.get("orchestrator_timestamps") or {}
            )
            request_ts = _parse_ts(
                orchestrator_timestamps.get("reporting_started_at")
            )
            sensor_ts = self._sensor_timestamp_for_batch(meta)

            if pending is not None:
                request_ts = request_ts or pending["request_started_at"]
                sensor_ts = sensor_ts or pending["sensor_ts"]

            if request_ts is None:
                return

            latency_ms = (result_ts - request_ts) * 1000.0
            if latency_ms >= 0:
                self.diagnosis_latency.append({"t": now, "ms": latency_ms})
                self._trim_latency(self.diagnosis_latency)

            if sensor_ts is not None:
                e2e_ms = (result_ts - sensor_ts) * 1000.0
                if e2e_ms >= 0:
                    self.e2e_latency.append({"t": now, "ms": e2e_ms})
                    self._trim_latency(self.e2e_latency)

            diagnosis = payload.get("diagnosis") or "unknown"
            self.action_log.log(
                "fault", f"Diagnosis completed | {diagnosis}"
            )

    def _sensor_timestamp_for_batch(self, payload: dict) -> Optional[float]:
        timestamps = []
        for event in payload.get("event_audit") or []:
            ed_metrics = event.get("ed_metrics") or {}
            timestamp = (
                _parse_ts(ed_metrics.get("sensor_published_at"))
                or _parse_ts(ed_metrics.get("received_at"))
            )
            if timestamp is not None:
                timestamps.append(timestamp)

        if timestamps:
            return min(timestamps)

        if self._last_sensor_ts is not None:
            return self._last_sensor_ts

        return _parse_ts(
            (payload.get("sg_metrics") or {}).get("received_at")
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

    @staticmethod
    def _trim_latency(history: list[dict]) -> None:
        cutoff = time.time() - LATENCY_RETENTION_SECONDS
        while history and history[0]["t"] < cutoff:
            history.pop(0)

        # Keep a safety cap for pathological event rates while retaining the
        # full time window during normal operation.
        if len(history) > MAX_LATENCY_POINTS:
            del history[: len(history) - MAX_LATENCY_POINTS]


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"
