"""
predictor.py

Production ML classifier for the Diagnosis Service.

Wraps a trained PyTorch FaultClassifier MLP together with the matching
StandardScaler and LabelEncoder artifacts and produces a majority-vote
prediction over a batch of streamed TEP samples.

The returned dict follows the contract expected by DiagnosisService:

    {
        "fault_number": int | None,
        "diagnosis": "fault_<n>" | "unknown",
        "model": "<model name>",
        "confidence": float,          # majority fraction of the batch
        "sample_count": int,
        "prediction_counts": {int: int},
    }
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Dict, Iterable, List

import joblib
import numpy as np
import pandas as pd
import torch

from classifier import Classifier
from fault_classifier import FaultClassifier

log = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).resolve().parent / "models"

DEFAULT_MODEL_PATH = MODEL_DIR / "classifier.pt"
DEFAULT_SCALER_PATH = MODEL_DIR / "scaler.pkl"
DEFAULT_LABEL_ENCODER_PATH = MODEL_DIR / "label_encoder.pkl"
DEFAULT_FEATURE_COLUMNS_PATH = MODEL_DIR / "feature_columns.json"

MODEL_NAME = "fault_classifier_pytorch"


class Predictor(Classifier):
    """Classifies a batch of TEP samples with a trained MLP."""

    def __init__(
        self,
        model_path: Path | str = DEFAULT_MODEL_PATH,
        scaler_path: Path | str = DEFAULT_SCALER_PATH,
        label_encoder_path: Path | str = DEFAULT_LABEL_ENCODER_PATH,
        feature_columns_path: Path | str = DEFAULT_FEATURE_COLUMNS_PATH,
    ) -> None:
        # `model` stays a string so the DiagnosisService error path
        # (`getattr(classifier, "model", "unknown")`) can report it.
        self.model = MODEL_NAME

        self.device = torch.device(
            "cuda" if torch.cuda.is_available() else "cpu"
        )

        with open(feature_columns_path, "r", encoding="utf-8") as fp:
            self.feature_columns: List[str] = json.load(fp)

        self.scaler = joblib.load(scaler_path)
        self.label_encoder = joblib.load(label_encoder_path)

        self._model = FaultClassifier(
            input_dim=len(self.feature_columns),
            num_classes=len(self.label_encoder.classes_),
        )
        self._model.load_state_dict(
            torch.load(model_path, map_location=self.device)
        )
        self._model.to(self.device)
        self._model.eval()

        log.info(
            "Predictor initialised | features=%d classes=%d device=%s",
            len(self.feature_columns),
            len(self.label_encoder.classes_),
            self.device,
        )

    def predict(self, samples: List[dict]) -> Dict:
        if not samples:
            return self._build_result(
                fault_number=None,
                counts={},
                sample_count=0,
            )

        features = self._extract_features(samples)
        predictions = self._run_inference(features)
        counts = self._aggregate(predictions)
        accuracy = self._accuracy(samples, predictions)

        if not counts:
            return self._build_result(
                fault_number=None,
                counts={},
                sample_count=len(samples),
                accuracy=accuracy,
            )

        majority = max(counts, key=counts.get)
        return self._build_result(
            fault_number=majority,
            counts=counts,
            sample_count=len(samples),
            confident_count=counts[majority],
            accuracy=accuracy,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_features(self, samples: List[dict]) -> np.ndarray:
        rows = [
            {
                column: _safe_float(sample.get(column))
                for column in self.feature_columns
            }
            for sample in samples
        ]
        frame = pd.DataFrame(rows, columns=self.feature_columns)
        return self.scaler.transform(frame)

    def _run_inference(self, features: np.ndarray) -> np.ndarray:
        tensor = torch.tensor(
            features, dtype=torch.float32, device=self.device
        )
        with torch.no_grad():
            logits = self._model(tensor)
        class_indices = logits.argmax(dim=1).cpu().numpy()
        return self.label_encoder.inverse_transform(class_indices)

    @staticmethod
    def _aggregate(predictions: Iterable) -> Dict[int, int]:
        counts: Dict[int, int] = {}
        for label in predictions:
            fault = int(label)
            counts[fault] = counts.get(fault, 0) + 1
        return counts

    @staticmethod
    def _accuracy(
        samples: List[dict],
        predictions: Iterable,
    ) -> Dict:
        """Compare per-sample predictions against ground-truth labels.

        The streamed TEP samples carry the injected ``faultNumber``, so
        accuracy can be measured live. Samples without a usable label are
        skipped. Returns ``{"accuracy", "correct_count",
        "ground_truth_available"}`` with ``accuracy`` as ``None`` when no
        ground truth is present.
        """
        correct = 0
        available = 0

        for sample, label in zip(samples, predictions):
            raw = sample.get("faultNumber")
            if raw is None:
                continue
            try:
                ground_truth = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(ground_truth):
                continue
            available += 1
            if int(label) == int(ground_truth):
                correct += 1

        return {
            "accuracy": (
                round(correct / available, 4)
                if available > 0
                else None
            ),
            "correct_count": correct,
            "ground_truth_available": available,
        }

    def _build_result(
        self,
        fault_number,
        counts: Dict[int, int],
        sample_count: int,
        confident_count: int = 0,
        accuracy: Dict = None,
    ) -> Dict:
        confidence = (
            round(confident_count / sample_count, 4)
            if sample_count > 0
            else 0.0
        )

        result = {
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
            "accuracy": None,
            "correct_count": 0,
            "ground_truth_available": 0,
        }

        if accuracy:
            result.update(accuracy)

        return result


def _safe_float(value) -> float:
    """Coerce a streamed value to float, tolerating missing or bad values."""
    if value is None:
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(result):
        return 0.0
    return result
