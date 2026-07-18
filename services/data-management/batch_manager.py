import logging
import threading
import time

log = logging.getLogger(__name__)


class BatchManager:

    def __init__(
        self,
        target_batch_count: int = 10,
        min_interval: float = 2.0,
        max_interval: float = 30.0,
    ):
        self.target_batch_count = target_batch_count
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._buffer: list[dict] = []
        self._timestamps: list[float] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._current_interval = max_interval

    def add_sample(self, sample: dict) -> None:
        with self._lock:
            self._buffer.append(sample)
            self._timestamps.append(time.time())
            self._prune_timestamps()
            self._recalculate_interval()

    def _prune_timestamps(self) -> None:
        cutoff = time.time() - 60
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def _recalculate_interval(self) -> None:
        if len(self._timestamps) < 2:
            self._current_interval = self.max_interval
            return
        duration = self._timestamps[-1] - self._timestamps[0]
        if duration <= 0:
            self._current_interval = self.max_interval
            return
        rate = len(self._timestamps) / duration
        target_interval = (
            self.target_batch_count / rate if rate > 0 else self.max_interval
        )
        self._current_interval = max(
            self.min_interval, min(self.max_interval, target_interval)
        )

    @property
    def current_interval(self) -> float:
        return self._current_interval

    def should_flush(self) -> bool:
        with self._lock:
            if not self._buffer:
                return False
            return (time.time() - self._last_flush) >= self._current_interval

    def flush(self) -> list[dict]:
        with self._lock:
            batch = self._buffer
            self._buffer = []
            self._last_flush = time.time()
        return batch

    @property
    def buffer_size(self) -> int:
        with self._lock:
            return len(self._buffer)

    def get_rate(self) -> float:
        with self._lock:
            if len(self._timestamps) < 2:
                return 0.0
            duration = self._timestamps[-1] - self._timestamps[0]
            if duration <= 0:
                return 0.0
            return len(self._timestamps) / duration
