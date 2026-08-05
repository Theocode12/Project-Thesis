"""Edge Detection view data store.

Holds anomalies reported by the edge detector (topic ``anomaly/detected``)
together with its own action log. Read-only for now; a controller can be
added when the page grows commands.
"""

import threading
import time
from typing import Optional

from mqtt_client import ActionLog

MAX_DETECTIONS = 500


class DetectionStore:

    def __init__(self, action_log: Optional[ActionLog] = None) -> None:
        self._lock = threading.Lock()
        self.action_log = action_log or ActionLog()
        self.detections: list[dict] = []
        self.latest: Optional[dict] = None

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
                "detect",
                f"Anomaly detected{detail}",
            )

    def recent_detections(self) -> list[dict]:
        with self._lock:
            return list(self.detections)

    def latest_detection(self) -> Optional[dict]:
        with self._lock:
            return self.latest

    def recent_actions(self) -> list[dict]:
        return self.action_log.recent()
