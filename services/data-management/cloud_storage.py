import json
import logging
import os
from abc import ABC, abstractmethod

log = logging.getLogger(__name__)


class CloudStorage(ABC):

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def store(self, batch_id: str, data: list[dict]) -> bool:
        ...


class LocalDirectoryCloudStorage(CloudStorage):

    def __init__(self, directory: str = "cloud_uploads"):
        self.directory = directory
        os.makedirs(directory, exist_ok=True)

    def is_available(self) -> bool:
        return os.access(self.directory, os.W_OK)

    def store(self, batch_id: str, data: list[dict]) -> bool:
        try:
            path = os.path.join(self.directory, f"{batch_id}.json")
            with open(path, "w") as f:
                json.dump(data, f)
            log.info(
                "Stored batch %s to cloud storage (%d samples)",
                batch_id,
                len(data),
            )
            return True
        except Exception:
            log.exception("Failed to store batch %s to cloud storage", batch_id)
            return False
