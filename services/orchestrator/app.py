import logging
from os import getenv

from decision_engine import DecisionEngine
from orchestrator_service import OrchestratorService
from reporting import DiagnosisReporter

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("app")


def main() -> None:
    log.info("Starting orchestrator service")

    decision_engine = DecisionEngine(
        window_seconds=float(getenv("EVAL_WINDOW_SECONDS", "10")),
        high_ratio=float(getenv("ANOMALY_HIGH_RATIO", "0.5")),
        low_ratio=float(getenv("ANOMALY_LOW_RATIO", "0.1")),
        fallback_stream_interval=float(
            getenv("FALLBACK_STREAM_INTERVAL", "0.1")
        ),
    )

    reporter = DiagnosisReporter(
        endpoint=getenv("DIAGNOSIS_ENDPOINT", ""),
        timeout=float(getenv("DIAGNOSIS_TIMEOUT", "5.0")),
    )

    mqtt_service = MQTTService(
        MQTTConfig(client_id="orchestrator")
    )

    service = OrchestratorService(
        decision_engine=decision_engine,
        reporter=reporter,
        mqtt_service=mqtt_service,
    )

    log.info("Orchestrator service initialised")

    try:
        service.start()
        service.run()
    except KeyboardInterrupt:
        log.info("Shutdown requested")
        service.stop()
        log.info("Orchestrator service stopped")


if __name__ == "__main__":
    main()
