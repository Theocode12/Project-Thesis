import json
import logging
import os
import shutil
from datetime import datetime, UTC

log = logging.getLogger(__name__)


class LocalStorage:

    def __init__(self, cache_dir: str = "local_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self._index_path = os.path.join(cache_dir, ".index.json")
        self._load_index()

    def _load_index(self) -> None:
        if os.path.exists(self._index_path):
            with open(self._index_path, "r") as f:
                self._index = json.load(f)
        else:
            self._index = {}

    def _save_index(self) -> None:
        tmp = self._index_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._index, f)
        shutil.move(tmp, self._index_path)

    def save(self, batch_id: str, data: list[dict]) -> None:
        path = os.path.join(self.cache_dir, f"{batch_id}.json")
        with open(path, "w") as f:
            json.dump(data, f)
        self._index[batch_id] = {
            "state": "pending",
            "timestamp": datetime.now(UTC).isoformat(),
            "count": len(data),
        }
        self._save_index()
        log.info(
            "Saved batch %s to local cache (%d samples)",
            batch_id,
            len(data),
        )

    def read(self, batch_id: str) -> list[dict] | None:
        path = os.path.join(self.cache_dir, f"{batch_id}.json")
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            log.exception("Failed to read batch %s from local cache", batch_id)
            return None

    def mark_synced(self, batch_id: str) -> None:
        if batch_id in self._index:
            self._index[batch_id]["state"] = "synced"
            self._save_index()

    def get_pending_batches(self) -> dict[str, dict]:
        return {
            bid: info
            for bid, info in self._index.items()
            if info["state"] == "pending"
        }

    def cleanup_synced(self, max_age_seconds: int = 3600) -> int:
        now = datetime.now(UTC)
        to_remove = []
        for batch_id, info in self._index.items():
            if info["state"] == "synced":
                ts = datetime.fromisoformat(info["timestamp"])
                if (now - ts).total_seconds() > max_age_seconds:
                    to_remove.append(batch_id)
        for batch_id in to_remove:
            path = os.path.join(self.cache_dir, f"{batch_id}.json")
            if os.path.exists(path):
                os.remove(path)
            del self._index[batch_id]
        if to_remove:
            self._save_index()
            log.info(
                "Cleaned up %d synced batches from local cache",
                len(to_remove),
            )
        return len(to_remove)
