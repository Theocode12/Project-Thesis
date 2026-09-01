"""
classifier.py

Pluggable classifier interface used by the Diagnosis Service.

The interface is intentionally minimal so a trained model can be dropped
in without touching the surrounding plumbing. The factory returns the ML
predictor (Predictor).
"""

from abc import ABC, abstractmethod
from typing import List


class Classifier(ABC):

    @abstractmethod
    def predict(self, samples: List[dict]) -> dict:
        ...


def create_classifier() -> Classifier:
    from predictor import Predictor

    return Predictor()
