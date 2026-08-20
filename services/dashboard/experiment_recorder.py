"""Persistent experiment recording for dashboard-observed MQTT events."""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


EVENT_FILES = {
    "anomaly/detected": "anomaly_events.jsonl",
    "orchestrator/decision": "orchestration_events.jsonl",
    "classification/result": "classification_results.jsonl",
}

METRIC_TOPICS = {
    "sensor/status",
    "detector/status",
    "classifier/status",
}

METRIC_SERVICES = {
    "sensor/status": "sensor-generator",
    "detector/status": "detector",
    "classifier/status": "classifier",
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ExperimentRecorder:
    """Write selected MQTT events to one durable directory per experiment."""

    def __init__(self, root: str | Path = "/app/experiments") -> None:
        self.root = Path(root)
        self._lock = threading.Lock()
        self._queue: queue.Queue[tuple[str, dict] | None] = queue.Queue(
            maxsize=10000
        )
        self._writer: threading.Thread | None = None
        self._files: dict[str, Any] = {}
        self._experiment_id: str | None = None
        self._directory: Path | None = None
        self._phase = "unassigned"
        self._counts: dict[str, int] = {}
        self._sequence = 0
        self._dropped = 0
        self._accepting = False

    @property
    def active(self) -> bool:
        with self._lock:
            return self._experiment_id is not None

    @property
    def experiment_id(self) -> str | None:
        with self._lock:
            return self._experiment_id

    @property
    def directory(self) -> Path | None:
        with self._lock:
            return self._directory

    def start(self, metadata: dict[str, Any]) -> str:
        with self._lock:
            if self._experiment_id is not None:
                raise RuntimeError("An experiment is already active")

            experiment_id = str(metadata.get("experiment_id") or "").strip()
            if not experiment_id:
                experiment_id = datetime.now(UTC).strftime(
                    "%Y%m%dT%H%M%SZ"
                )
            if any(character in experiment_id for character in '/\\:*?"<>|'):
                raise ValueError("experiment_id contains an invalid path character")

            directory = self.root / experiment_id
            directory.mkdir(parents=True, exist_ok=False)
            self._files = {
                name: (directory / name).open("a", encoding="utf-8")
                for name in (
                    "anomaly_events.jsonl",
                    "orchestration_events.jsonl",
                    "classification_results.jsonl",
                    "service_metrics.jsonl",
                    "commands.jsonl",
                )
            }
            self._experiment_id = experiment_id
            self._directory = directory
            self._phase = str(metadata.get("phase") or "warmup")
            self._counts = {}
            self._sequence = 0
            self._dropped = 0
            self._accepting = True
            self._writer = threading.Thread(
                target=self._write_loop,
                name="experiment-recorder",
                daemon=True,
            )
            self._writer.start()

            started_at = _now_iso()
            manifest = {
                **metadata,
                "experiment_id": experiment_id,
                "started_at": started_at,
                "status": "running",
                "phase": self._phase,
                "phase_changes": [
                    {"phase": self._phase, "timestamp": started_at}
                ],
                "files": list(self._files),
            }
            self._write_json(directory / "manifest.json", manifest)
            return experiment_id

    def set_phase(self, phase: str, metadata: dict[str, Any] | None = None) -> None:
        phase_record = {"phase": phase, "timestamp": _now_iso(), **(metadata or {})}
        with self._lock:
            if self._experiment_id is None:
                return
            self._phase = phase
            directory = self._directory
            manifest_path = directory / "manifest.json" if directory else None
            if manifest_path is not None:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["phase"] = phase
                manifest.setdefault("phase_changes", []).append(phase_record)
                self._write_json(manifest_path, manifest)
        self.record_command("phase", phase_record)

    def record_command(
        self,
        action: str,
        parameters: dict[str, Any] | None = None,
        broker: str | None = None,
    ) -> None:
        record = {
            "action": action,
            "parameters": parameters or {},
            "broker": broker,
        }
        self._enqueue("commands.jsonl", record)

    def record_event(
        self,
        topic: str,
        envelope: dict,
        broker: str,
    ) -> None:
        if topic not in EVENT_FILES and topic not in METRIC_TOPICS:
            return

        with self._lock:
            phase = self._phase
            sequence = self._sequence
            self._sequence += 1

        record = {
            "sequence": sequence,
            "experiment_id": self.experiment_id,
            "topic": topic,
            "broker": broker,
            "phase": phase,
            "source": envelope.get("source"),
            "collector_timestamp": time.time(),
            "collector_timestamp_iso": _now_iso(),
            "publisher_timestamp": envelope.get("timestamp"),
            "payload_bytes": len(
                json.dumps(envelope.get("payload", {}), separators=(",", ":"))
                .encode("utf-8")
            ),
            "payload": envelope.get("payload", {}),
        }
        filename = EVENT_FILES.get(topic, "service_metrics.jsonl")
        if topic in METRIC_SERVICES:
            record["service"] = METRIC_SERVICES[topic]
        self._enqueue(filename, record, topic=topic)

        if topic == "orchestrator/decision":
            payload = envelope.get("payload") or {}
            metrics = payload.get("or_metrics")
            if metrics:
                self._enqueue(
                    "service_metrics.jsonl",
                    {
                        **record,
                        "service": "orchestrator",
                        "metrics": metrics,
                    },
                    topic="orchestrator",
                )

    def stop(self, status: str = "completed") -> Path | None:
        with self._lock:
            directory = self._directory
            writer = self._writer
            if self._experiment_id is None or directory is None:
                return None
            self._accepting = False
            self._queue.put(None)

        if writer is not None:
            writer.join(timeout=10)

        with self._lock:
            for handle in self._files.values():
                handle.close()
            summary = {
                "experiment_id": self._experiment_id,
                "status": status,
                "ended_at": _now_iso(),
                "event_counts": dict(self._counts),
                "dropped_records": self._dropped,
            }
            self._write_json(directory / "summary.json", summary)
            manifest_path = directory / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update({"status": status, "ended_at": summary["ended_at"]})
            self._write_json(manifest_path, manifest)
            self._files = {}
            self._writer = None
            self._experiment_id = None
            self._directory = None
            return directory

    def _enqueue(
        self,
        filename: str,
        record: dict,
        topic: str | None = None,
    ) -> None:
        with self._lock:
            if self._experiment_id is None or not self._accepting:
                return
            try:
                self._queue.put_nowait((filename, record))
                if topic:
                    self._counts[topic] = self._counts.get(topic, 0) + 1
            except queue.Full:
                self._dropped += 1

    def _write_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                break
            filename, record = item
            with self._lock:
                handle = self._files.get(filename)
            if handle is not None:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
                handle.flush()
            self._queue.task_done()

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        path.write_text(
            json.dumps(value, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
