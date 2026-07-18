import logging
import time

from cloud_storage import CloudStorage
from local_storage import LocalStorage

log = logging.getLogger(__name__)


class CacheManager:

    def __init__(
        self,
        local_storage: LocalStorage,
        cloud_storage: CloudStorage,
        retry_interval: float = 30.0,
        cleanup_interval: float = 300.0,
        cleanup_max_age: int = 3600,
    ):
        self.local_storage = local_storage
        self.cloud_storage = cloud_storage
        self.retry_interval = retry_interval
        self.cleanup_interval = cleanup_interval
        self.cleanup_max_age = cleanup_max_age
        self._last_retry = 0.0
        self._last_cleanup = 0.0

    def tick(self) -> None:
        now = time.time()

        if now - self._last_retry >= self.retry_interval:
            self._retry_pending()
            self._last_retry = now

        if now - self._last_cleanup >= self.cleanup_interval:
            self._cleanup()
            self._last_cleanup = now

    def _retry_pending(self) -> None:
        pending = self.local_storage.get_pending_batches()
        if not pending:
            return
        if not self.cloud_storage.is_available():
            log.debug(
                "Cloud unavailable, skipping retry of %d pending batches",
                len(pending),
            )
            return
        for batch_id in pending:
            data = self.local_storage.read(batch_id)
            if data is None:
                continue
            if self.cloud_storage.store(batch_id, data):
                self.local_storage.mark_synced(batch_id)
                log.info(
                    "Retry successful: batch %s synced to cloud",
                    batch_id,
                )

    def _cleanup(self) -> None:
        removed = self.local_storage.cleanup_synced(self.cleanup_max_age)
        if removed:
            log.info("Cache cleanup removed %d synced batches", removed)
