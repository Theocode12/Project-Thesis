"""Sensor Generator view data store and command controller.

The store owns all sensor-generator state (raw samples, status, metrics,
processing history) plus its own action log, so the page keeps a
self-contained history. The controller turns UI actions into MQTT
commands, decoupling the view from the transport details.
"""

import threading
import time
from typing import Optional

from mqtt_client import ActionLog, DashboardClient

SAMPLE_WINDOW_SECONDS = 60.0
RATE_WINDOW_SECONDS = 5.0
MAX_SAMPLES = 2000


class SensorGeneratorStore:

    def __init__(self, action_log: Optional[ActionLog] = None) -> None:
        self._lock = threading.Lock()
        self.action_log = action_log or ActionLog()
        self.status: Optional[dict] = None
        self.metrics: Optional[dict] = None
        self.samples: list[dict] = []
        self.processing_history: list[dict] = []
        self.sample_rate: float = 0.0
        self.message_count: int = 0
        self._last_running: Optional[bool] = None
        self._last_fault: Optional[int] = None
        self._last_stream_interval: Optional[float] = None

    def handle_raw(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        sample = payload.get("sample")
        now = time.time()

        with self._lock:
            if sample is not None:
                self.samples.append({
                    "t": now,
                    "fault": sample.get("_stream", {}).get("fault"),
                    "run": sample.get("_stream", {}).get("run"),
                    "values": sample,
                })
                self.message_count += 1
                if self.message_count == 1:
                    self.action_log.log(
                        "stream", "Raw sensor stream established"
                    )
                self._trim_samples()

            self._update_metrics(payload, now)
            self._update_rate()

    def handle_status(self, envelope: dict) -> None:
        payload = envelope.get("payload", {})
        now = time.time()

        with self._lock:
            self.status = {
                "status": payload.get("status"),
                "received_at": now,
            }
            status = payload.get("status") or {}

            running = status.get("running")
            if running is not None and running != self._last_running:
                self._last_running = running
                self.action_log.log(
                    "state",
                    "Generator started" if running else "Generator paused",
                )

            fault = status.get("fault")
            if fault is not None and fault != self._last_fault:
                self._last_fault = fault
                self.action_log.log(
                    "fault", f"Fault scenario changed to {fault}"
                )

            self._update_metrics(payload, now)

    def _update_metrics(self, payload: dict, now: float) -> None:
        if "sg_metrics" not in payload:
            return

        self.metrics = {
            "sg_metrics": payload.get("sg_metrics"),
            "received_at": now,
        }
        processing_time = (
            payload.get("sg_metrics") or {}
        ).get("processing_time_ms")
        if processing_time is not None:
            self.processing_history.append({
                "t": now,
                "processing_time_ms": processing_time,
            })
            self._trim_processing_history()

        stream_interval = (
            payload.get("sg_metrics") or {}
        ).get("stream_interval")
        if (
            stream_interval is not None
            and stream_interval != self._last_stream_interval
        ):
            self._last_stream_interval = stream_interval
            self.action_log.log(
                "interval",
                f"Stream interval set to {stream_interval:g}s",
            )

    def channels(self) -> list[str]:
        with self._lock:
            if not self.samples:
                return []
            return [
                key
                for key in self.samples[-1]["values"].keys()
                if not key.startswith("_")
            ]

    def get_status(self) -> Optional[dict]:
        with self._lock:
            return self.status

    def get_metrics(self) -> Optional[dict]:
        with self._lock:
            return self.metrics

    def recent_samples(self) -> list[dict]:
        with self._lock:
            return list(self.samples)

    def recent_processing_times(self) -> list[dict]:
        with self._lock:
            return list(self.processing_history)

    def recent_actions(self) -> list[dict]:
        return self.action_log.recent()

    def get_message_count(self) -> int:
        with self._lock:
            return self.message_count

    def _trim_samples(self) -> None:
        cutoff = time.time() - SAMPLE_WINDOW_SECONDS
        while self.samples and self.samples[0]["t"] < cutoff:
            self.samples.pop(0)

        if len(self.samples) > MAX_SAMPLES:
            self.samples = self.samples[-MAX_SAMPLES:]

    def _trim_processing_history(self) -> None:
        cutoff = time.time() - SAMPLE_WINDOW_SECONDS
        while (
            self.processing_history
            and self.processing_history[0]["t"] < cutoff
        ):
            self.processing_history.pop(0)

    def _update_rate(self) -> None:
        now = time.time()
        cutoff = now - RATE_WINDOW_SECONDS
        count = sum(1 for sample in self.samples if sample["t"] >= cutoff)
        self.sample_rate = round(count / RATE_WINDOW_SECONDS, 2)


class SensorGeneratorController:
    """Translates Sensor Generator UI actions into MQTT commands."""

    def __init__(
        self,
        store: SensorGeneratorStore,
        client: DashboardClient,
    ) -> None:
        self.store = store
        self.client = client

    def send_start(self) -> None:
        self.client.send_command("sg_start")
        self.store.action_log.log("state", "Start command sent")

    def send_stop(self) -> None:
        self.client.send_command("sg_stop")
        self.store.action_log.log("state", "Pause command sent")

    def send_reset(self) -> None:
        self.client.send_command("sg_reset")
        self.store.action_log.log("state", "Reset command sent")

    def send_halt(self) -> None:
        self.client.send_command("sg_stop")
        self.client.send_command("sg_reset")
        self.store.action_log.log(
            "state", "Stop command sent (halted and rewound)"
        )

    def send_set_fault(self, fault: int) -> None:
        self.client.send_command("sg_set_fault", fault=fault)
        self.store.action_log.log("fault", f"Fault scenario set to {fault}")

    def send_set_stream(self, fault: int, run: int) -> None:
        self.client.send_command(
            "sg_set_stream",
            fault=fault,
            run=run,
        )
        self.store.action_log.log(
            "fault",
            f"Stream switched to fault_{fault} run_{run}",
        )

    def send_set_stream_interval(self, interval: float) -> None:
        self.client.send_command(
            "sg_set_stream_interval",
            interval=interval,
        )
        self.store.action_log.log(
            "interval", f"Stream interval set to {interval:g}s"
        )

    def send_set_status_interval(self, interval: float) -> None:
        self.client.send_command(
            "sg_set_status_interval",
            interval=interval,
        )
