import time
from typing import Optional

from .container_metrics import (
    ContainerMetricsCollector,
)

SERVICE_PREFIXES = {
    "sensor-generator": "sg",
    "detector": "det",
    "classifier": "cl",
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
        self._timestamps: dict[str, float] = {}
        self._received_at: Optional[float] = None

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
        received_at: Optional[float] = None,
    ) -> None:
        self._timestamps = {"processing_started_at": time.time()}
        self._received_at = received_at

    def mark(self, name: str) -> float:
        timestamp = time.time()
        self._timestamps[name] = timestamp
        return timestamp

    def snapshot(
        self,
        extra: Optional[dict] = None,
    ) -> dict:

        timestamps = dict(self._timestamps)
        if "processing_started_at" in timestamps:
            timestamps["processing_ended_at"] = time.time()

        metrics = {
            "container": (
                self.collector.snapshot().to_dict()
            ),
            **timestamps,
        }

        if self._received_at is not None:
            metrics["received_at"] = self._received_at
            self._received_at = None

        self._timestamps = {}

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
