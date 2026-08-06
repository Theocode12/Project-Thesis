"""
classifier.py

Pluggable classifier interface used by the Diagnosis Service.

The interface is intentionally minimal so a trained model can be dropped
in later without touching the surrounding plumbing. The default factory
returns the real ML predictor (Predictor); a heuristic stub that reports
the majority fault label carried by the streamed samples is kept around
as a fallback if the model artifacts cannot be loaded.
"""

import logging
from abc import ABC, abstractmethod
from collections import Counter
from typing import List

log = logging.getLogger(__name__)


class Classifier(ABC):

    @abstractmethod
    def predict(self, samples: List[dict]) -> dict:
        ...


class HeuristicClassifier(Classifier):

    def __init__(self) -> None:
        self.model = "heuristic"

    def predict(self, samples: List[dict]) -> dict:
        if not samples:
            return self._build_result(
                fault_number=None,
                counts={},
                sample_count=0,
            )

        counts = Counter(
            int(sample.get("faultNumber"))
            for sample in samples
            if "faultNumber" in sample
        )

        if not counts:
            return self._build_result(
                fault_number=None,
                counts={},
                sample_count=len(samples),
            )

        fault_number, count = counts.most_common(1)[0]

        return self._build_result(
            fault_number=fault_number,
            counts=dict(counts),
            sample_count=len(samples),
            confident_count=count,
        )

    def _build_result(
        self,
        fault_number,
        counts: dict,
        sample_count: int,
        confident_count: int = 0,
    ) -> dict:
        confidence = (
            round(confident_count / sample_count, 4)
            if sample_count > 0
            else 0.0
        )

        return {
            "fault_number": fault_number,
            "diagnosis": (
                f"fault_{fault_number}"
                if fault_number is not None
                else "unknown"
            ),
            "model": self.model,
            "confidence": confidence,
            "sample_count": sample_count,
            "prediction_counts": counts,
        }


def create_classifier() -> Classifier:
    from predictor import Predictor

    try:
        return Predictor()
    except Exception:
        log.exception(
            "Failed to initialise ML predictor; using heuristic fallback"
        )
        return HeuristicClassifier()
