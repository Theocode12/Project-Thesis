import logging

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

    def is_configured(self) -> bool:
        return bool(self.endpoint)

    def report(
        self,
        batch: list[dict],
        meta: dict | None = None,
    ) -> bool:
        if not self.endpoint:
            log.info(
                "Diagnosis endpoint not configured, skipping report"
            )
            return False

        payload = {
            "batch": batch,
            "meta": meta or {},
        }

        try:
            response = requests.post(
                self.endpoint,
                json=payload,
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
