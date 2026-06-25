from abc import ABC, abstractmethod


class Detector(ABC):

    @abstractmethod
    def detect(
        self,
        sample: dict
    ) -> dict:
        pass


class DummyDetector(Detector):

    def __init__(
        self,
        threshold: float = 0.5
    ):
        self.threshold = threshold

    def detect(
        self,
        sample: dict
    ) -> dict:

        value = sample.get(
            "xmeas_1",
            0
        )

        anomaly = value > self.threshold

        return {
            "anomaly": anomaly,
            "confidence": 0.95 if anomaly else 0.0,
            "reason": (
                "threshold_exceeded"
                if anomaly
                else None
            ),
            "metric": "xmeas_1",
            "value": value
        }