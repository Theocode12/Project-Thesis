import logging
import json

import requests

log = logging.getLogger(__name__)


class DiagnosisReporter:

    def __init__(
        self,
        endpoint: str = "",
        timeout: float = 5.0,
    ):
        self.endpoint = endpoint
        self.timeout = timeout
        self.last_request_payload_bytes = 0

    def is_configured(self) -> bool:
        return bool(self.endpoint)

    def report(
        self,
        batch: list[dict],
        meta: dict | None = None,
    ) -> bool:
        if not self.endpoint:
            self.last_request_payload_bytes = 0
            log.info(
                "Diagnosis endpoint not configured, skipping report"
            )
            return False

        payload = {
            "batch": batch,
            "meta": meta or {},
        }
        body = json.dumps(payload).encode("utf-8")
        self.last_request_payload_bytes = len(body)

        try:
            response = requests.post(
                self.endpoint,
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            log.info(
                "Diagnosis report sent | status=%s batch_size=%d",
                response.status_code,
                len(batch),
            )
            return True
        except Exception:
            log.exception("Failed to send diagnosis report")
            return False
