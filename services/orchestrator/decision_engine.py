import logging
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

log = logging.getLogger(__name__)


class DecisionEngine:

    def __init__(
        self,
        window_seconds: float = 10.0,
        high_ratio: float = 0.5,
        low_ratio: float = 0.1,
        fallback_stream_interval: float = 0.1,
    ):
        self.window_seconds = window_seconds
        self.high_ratio = high_ratio
        self.low_ratio = low_ratio
        self.fallback_stream_interval = fallback_stream_interval
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def add_anomaly(self, event: dict) -> None:
        with self._lock:
            self._events.append(event)

    def reset(self) -> None:
        with self._lock:
            self._events = []

    def buffer_size(self) -> int:
        with self._lock:
            return len(self._events)

    def evaluate(self) -> dict:
        with self._lock:
            events = self._events
            self._events = []

        window_end = time.time()
        window_start = window_end - self.window_seconds

        anomaly_count = len(events)

        if anomaly_count == 0:
            return self._build_decision(
                decision="normal",
                anomaly_count=0,
                total_samples=0.0,
                sensor_rate=0.0,
                anomaly_rate=0.0,
                ratio=0.0,
                batch=[],
                sg_metrics={},
                ed_metrics={},
                event_audit=[],
                window_start=window_start,
                window_end=window_end,
            )

        batch = []
        rates = []
        sg_metrics = {}
        ed_metrics = {}
        event_audit = []

        for event in events:
            sample = event.get("sample")
            if sample is not None:
                batch.append(sample)
            event_sg = event.get("sg_metrics") or {}
            if event_sg:
                sg_metrics = event_sg
            event_ed = event.get("ed_metrics") or {}
            if event_ed:
                ed_metrics = event_ed
            event_audit.append({
                "edge_published_at": event.get("edge_published_at"),
                "orchestrator_received_at": event.get(
                    "orchestrator_received_at"
                ),
                "sg_metrics": event_sg,
                "ed_metrics": event_ed,
            })
            interval = event_sg.get("stream_interval")
            if interval:
                rates.append(1.0 / float(interval))

        sensor_rate = (
            sum(rates) / len(rates)
            if rates
            else 1.0 / self.fallback_stream_interval
        )

        total_samples = sensor_rate * self.window_seconds
        ratio = (
            min(1.0, anomaly_count / total_samples)
            if total_samples > 0
            else 0.0
        )
        anomaly_rate = anomaly_count / self.window_seconds

        if ratio >= self.high_ratio:
            decision = "anomaly"
        elif ratio <= self.low_ratio:
            decision = "normal"
        else:
            decision = "uncertain"

        return self._build_decision(
            decision=decision,
            anomaly_count=anomaly_count,
            total_samples=total_samples,
            sensor_rate=sensor_rate,
            anomaly_rate=anomaly_rate,
            ratio=ratio,
            batch=batch,
            sg_metrics=sg_metrics,
            ed_metrics=ed_metrics,
            event_audit=event_audit,
            window_start=window_start,
            window_end=window_end,
        )

    def _build_decision(
        self,
        decision: str,
        anomaly_count: int,
        total_samples: float,
        sensor_rate: float,
        anomaly_rate: float,
        ratio: float,
        batch: list[dict],
        sg_metrics: dict,
        ed_metrics: dict,
        event_audit: list[dict],
        window_start: float,
        window_end: float,
    ) -> dict:
        return {
            "batch_id": f"batch_{uuid4().hex[:12]}",
            "decision": decision,
            "confidence": round(ratio, 4),
            "window_start": datetime.fromtimestamp(
                window_start, UTC
            ).isoformat(),
            "window_end": datetime.fromtimestamp(
                window_end, UTC
            ).isoformat(),
            "window_seconds": self.window_seconds,
            "anomaly_count": anomaly_count,
            "total_samples": round(total_samples, 2),
            "sensor_rate": round(sensor_rate, 4),
            "anomaly_rate": round(anomaly_rate, 4),
            "anomaly_ratio": round(ratio, 4),
            "batch": batch,
            "batch_size": len(batch),
            "sg_metrics": sg_metrics,
            "ed_metrics": ed_metrics,
            "event_audit": event_audit,
            "reported": False,
        }
