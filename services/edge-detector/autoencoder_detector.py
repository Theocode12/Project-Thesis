"""
autoencoder_detector.py

Edge Autoencoder Detector

Loads the trained Autoencoder, StandardScaler and anomaly threshold,
then performs inference on incoming MQTT samples.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

import joblib
import numpy as np
import torch
import pandas as pd

from detector import Detector
from autoencoder import SparseAutoEncoder

log = logging.getLogger(__name__)


class AutoEncoderDetector(Detector):

    def __init__(
        self,
        model_path: str,
        scaler_path: str,
        threshold_path: str,
        feature_columns: List[str],
    ) -> None:

        self.device = torch.device(
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        self.feature_columns = feature_columns

        # ----------------------------------------------------
        # Load Scaler
        # ----------------------------------------------------

        self.scaler = joblib.load(
            scaler_path
        )

        log.info(
            "Scaler loaded from %s",
            scaler_path
        )

        # ----------------------------------------------------
        # Load Threshold
        # ----------------------------------------------------

        with open(
            threshold_path,
            "r",
            encoding="utf-8"
        ) as fp:

            threshold_json = json.load(fp)

        self.threshold = float(
            threshold_json["threshold"]
        )

        log.info(
            "Threshold loaded: %.6f",
            self.threshold
        )

        # ----------------------------------------------------
        # Load Model
        # ----------------------------------------------------

        self.model = SparseAutoEncoder(
            input_size=52,
            hidden_size=128,
            latent_size=64,
            dropout=0.0,
        )

        self.model.load_state_dict(

            torch.load(
                model_path,
                map_location=self.device,
            )

        )

        self.model.to(
            self.device
        )

        self.model.eval()

        log.info(
            "Autoencoder loaded from %s",
            model_path
        )

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def detect(
        self,
        sample: Dict,
    ) -> Dict:

        try:

            features = self._extract_features(
                sample
            )

            reconstruction_error = (
                self._reconstruction_error(
                    features
                )
            )

            anomaly = (
                reconstruction_error
                > self.threshold
            )


            return {

                "anomaly": anomaly,

                "reconstruction_error": round(
                    reconstruction_error,
                    4
                ),

                "reason": (
                    "reconstruction_error"
                    if anomaly
                    else None
                ),

                "metric": "reconstruction_error",

                "value": float(
                    reconstruction_error
                ),

            }

        except Exception:

            log.exception(
                "Detection failed."
            )

            return {
                "anomaly": False,
                "reconstruction_error": 0.0,
                "reason": "detector_error",
                "metric": None,
                "value": None,
            }

    # --------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------

    def _extract_features(
        self,
        sample: Dict,
    ) -> pd.DataFrame:
        """
        Extract the model features from an MQTT sample.

        Returns a single-row DataFrame whose column names
        exactly match those used during training.
        """

        feature_dict = {

            column: float(sample[column])

            for column in self.feature_columns

        }

        return pd.DataFrame(
            [feature_dict],
            columns=self.feature_columns,
        )

    def _reconstruction_error(
        self,
        features: pd.DataFrame,
    ) -> float:
        """
        Compute the reconstruction MSE for a single sample.
        """

        scaled = self.scaler.transform(
            features
        )

        tensor = torch.tensor(
            scaled,
            dtype=torch.float32,
            device=self.device,
        )

        with torch.no_grad():

            reconstruction = self.model(
                tensor
            )

            mse = torch.mean(
                (tensor - reconstruction) ** 2
            ).item()

        return mse