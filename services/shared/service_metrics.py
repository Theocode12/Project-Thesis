import time
from datetime import UTC, datetime
from typing import Optional

from .container_metrics import (
    ContainerMetricsCollector,
)

SERVICE_PREFIXES = {
    "sensor-generator": "sg",
    "edge-detector": "ed",
    "classifier": "cl",
    "edge-classifier": "ec",
    "cloud-classifier": "cc",
    "orchestrator": "or",
    "dashboard": "db",
    "data-management": "dm",
}


class ServiceMetrics:

    def __init__(
        self,
        service_name: str,
        collector: Optional[ContainerMetricsCollector] = None,
    ) -> None:

        self.service_name = service_name
        self.collector = (
            collector or ContainerMetricsCollector()
        )
        self._processing_started_at: Optional[float] = None
        self._received_at: Optional[str] = None

    @property
    def metrics_key(self) -> str:
        prefix = SERVICE_PREFIXES.get(
            str(self.service_name),
            str(self.service_name).replace(
                "-",
                "_",
            ),
        )
        return f"{prefix}_metrics"

    def start_processing(
        self,
        received_at: Optional[str] = None,
    ) -> None:
        self._processing_started_at = time.perf_counter()
        self._received_at = received_at

    def end_processing(self) -> Optional[float]:
        if self._processing_started_at is None:
            return None
        milliseconds = (
            time.perf_counter()
            - self._processing_started_at
        ) * 1000.0
        self._processing_started_at = None
        return round(milliseconds, 3)

    def snapshot(
        self,
        extra: Optional[dict] = None,
    ) -> dict:

        metrics = {
            "container": (
                self.collector.snapshot().to_dict()
            ),
            "processing_time_ms": self.end_processing(),
            "processed_at": datetime.now(
                UTC
            ).isoformat(),
        }

        if self._received_at is not None:
            metrics["received_at"] = self._received_at
            self._received_at = None

        if extra:
            metrics.update(extra)

        return metrics

    def wrap(
        self,
        data_key: str,
        data: dict,
        extra: Optional[dict] = None,
    ) -> dict:
        return {
            data_key: data,
            self.metrics_key: self.snapshot(extra),
        }
