import logging
import time

from decision_engine import DecisionEngine
from reporting import DiagnosisReporter

from shared.mqtt_message_envelop import MQTTMessageEnvelope
from shared.mqtt_service import MQTTService
from shared.mqtt_topics import MQTTOPIC
from shared.service_metrics import ServiceMetrics

log = logging.getLogger(__name__)


class OrchestratorService:

    def __init__(
        self,
        decision_engine: DecisionEngine,
        reporter: DiagnosisReporter,
        mqtt_service: MQTTService,
        metrics: ServiceMetrics = None,
    ):
        self.decision_engine = decision_engine
        self.reporter = reporter
        self.mqtt_service = mqtt_service
        self.metrics = (
            metrics or ServiceMetrics(
                service_name="orchestrator"
            )
        )
        self.running = False
        self.evaluation_enabled = True
        self._last_eval = 0.0
        self._action_map = {
            "start": self._cmd_start,
            "stop": self._cmd_stop,
            "reset": self._cmd_reset,
        }

    def start(self) -> None:
        self.mqtt_service.connect()
        self.mqtt_service.subscribe(
            MQTTOPIC.ANOMALY_DETECTED, self.handle_anomaly
        )
        self.mqtt_service.subscribe(
            MQTTOPIC.SYSTEM_CONTROL, self.handle_command
        )
        self.mqtt_service.start()
        self.running = True
        log.info("Orchestrator service started")

    def stop(self) -> None:
        self.running = False
        self.mqtt_service.stop()
        log.info("Orchestrator service stopped")

    def handle_command(self, payload: dict) -> None:
        if not payload:
            log.warning("Received empty payload")
            return

        action = payload.get("action")
        handler = self._action_map.get(action)

        if handler is None:
            log.warning("Unknown action: %s", action)
            return

        log.info("Handling command: %s", action)
        handler(payload)

    def _cmd_start(self, payload: dict) -> None:
        self.evaluation_enabled = True
        log.info("Evaluation enabled")

    def _cmd_stop(self, payload: dict) -> None:
        self.evaluation_enabled = False
        log.info("Evaluation disabled")

    def _cmd_reset(self, payload: dict) -> None:
        self.decision_engine.reset()
        log.info("Decision engine reset")

    def handle_anomaly(self, payload: dict) -> None:
        try:
            if not self.evaluation_enabled:
                return
            inner = payload.get("payload") or {}
            self.decision_engine.add_anomaly(inner)
        except Exception:
            log.exception("Error processing anomaly event")

    def run(self) -> None:
        log.info(
            "Entering run loop | window_seconds=%.1fs",
            self.decision_engine.window_seconds,
        )

        self._last_eval = time.time()

        while self.running:
            try:
                now = time.time()
                if (
                    self.evaluation_enabled
                    and (now - self._last_eval)
                    >= self.decision_engine.window_seconds
                ):
                    self._evaluate()
                    self._last_eval = now

                time.sleep(0.1)

            except Exception:
                log.exception("Error in run loop")

    def _evaluate(self) -> None:
        self.metrics.start_processing()

        decision = self.decision_engine.evaluate()

        if decision["decision"] == "anomaly":
            decision["reported"] = self.reporter.report(
                decision["batch"],
                meta={
                    "window_start": decision["window_start"],
                    "window_end": decision["window_end"],
                    "fault": decision["fault"],
                    "anomaly_ratio": decision["anomaly_ratio"],
                },
            )

        self._publish_decision(decision)

        log.info(
            "Decision %s | ratio=%.4f, anomalies=%d, total=%.1f, "
            "rate=%.2f/s, fault=%s, reported=%s",
            decision["decision"],
            decision["anomaly_ratio"],
            decision["anomaly_count"],
            decision["total_samples"],
            decision["sensor_rate"],
            decision["fault"],
            decision["reported"],
        )

    def _publish_decision(self, decision: dict) -> None:
        payload = {
            "decision": decision["decision"],
            "confidence": decision["confidence"],
            "window_start": decision["window_start"],
            "window_end": decision["window_end"],
            "window_seconds": decision["window_seconds"],
            "anomaly_count": decision["anomaly_count"],
            "total_samples": decision["total_samples"],
            "sensor_rate": decision["sensor_rate"],
            "anomaly_rate": decision["anomaly_rate"],
            "anomaly_ratio": decision["anomaly_ratio"],
            "fault": decision["fault"],
            "batch_size": decision["batch_size"],
            "reported": decision["reported"],
            "or_metrics": self.metrics.snapshot(),
        }

        message = MQTTMessageEnvelope.create(
            source="orchestrator",
            payload=payload,
        )
        self.mqtt_service.publish(
            MQTTOPIC.ORCHESTRATOR_DECISION,
            message.to_dict(),
        )
