import logging
from os import getenv

from batch_manager import BatchManager
from cache_manager import CacheManager
from cloud_storage import LocalDirectoryCloudStorage
from data_management_service import DataManagementService
from local_storage import LocalStorage

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("app")


def main() -> None:
    log.info("Starting data-management service")

    batch_manager = BatchManager(
        target_batch_count=int(getenv("TARGET_BATCH_COUNT", "10")),
        min_interval=float(getenv("MIN_BATCH_INTERVAL", "2.0")),
        max_interval=float(getenv("MAX_BATCH_INTERVAL", "30.0")),
    )

    cloud_storage = LocalDirectoryCloudStorage(
        directory=getenv("CLOUD_STORAGE_DIR", "cloud_uploads"),
    )

    local_storage = LocalStorage(
        cache_dir=getenv("LOCAL_CACHE_DIR", "local_cache"),
    )

    cache_manager = CacheManager(
        local_storage=local_storage,
        cloud_storage=cloud_storage,
        retry_interval=float(getenv("CACHE_RETRY_INTERVAL", "30.0")),
        cleanup_interval=float(getenv("CACHE_CLEANUP_INTERVAL", "300.0")),
        cleanup_max_age=int(getenv("CACHE_CLEANUP_MAX_AGE", "3600")),
    )

    mqtt_service = MQTTService(
        MQTTConfig(client_id="data-management")
    )

    service = DataManagementService(
        batch_manager=batch_manager,
        cloud_storage=cloud_storage,
        local_storage=local_storage,
        cache_manager=cache_manager,
        mqtt_service=mqtt_service,
    )

    log.info("Data-management service initialised")

    try:
        service.start()
        service.run()
    except KeyboardInterrupt:
        log.info("Shutdown requested")
        service.stop()
        log.info("Data-management service stopped")


if __name__ == "__main__":
    main()
