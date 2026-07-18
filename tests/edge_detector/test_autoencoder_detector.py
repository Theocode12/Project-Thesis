import json
from unittest.mock import MagicMock, patch

import pytest

torch = pytest.importorskip("torch")

from autoencoder_detector import AutoEncoderDetector


@pytest.fixture
def mock_model():
    model = MagicMock()
    model.return_value = torch.tensor([[0.0, 0.0]])
    return model


@pytest.fixture
def mock_scaler():
    scaler = MagicMock()
    scaler.transform.return_value = [[1.0, 2.0]]
    return scaler


@pytest.fixture
def threshold_path(tmp_path):
    path = tmp_path / "threshold.json"
    with open(path, "w") as f:
        json.dump({"threshold": 0.01}, f)
    return str(path)


@pytest.fixture
def feature_columns():
    return ["xmeas_1", "xmeas_2"]


from autoencoder import SparseAutoEncoder


@pytest.fixture
def valid_state_dict(feature_columns):
    model = SparseAutoEncoder(
        input_size=len(feature_columns),
        hidden_size=128,
        latent_size=64,
        dropout=0.0,
    )
    return model.state_dict()


class TestAutoEncoderDetectorInit:

    @patch("autoencoder_detector.joblib.load")
    @patch("autoencoder_detector.torch.load")
    def test_init_loads_artifacts(
        self, mock_torch_load, mock_joblib_load,
        threshold_path, feature_columns, valid_state_dict,
    ):
        mock_joblib_load.return_value = MagicMock()
        mock_torch_load.return_value = valid_state_dict

        detector = AutoEncoderDetector(
            model_path="fake_model.pt",
            scaler_path="fake_scaler.pkl",
            threshold_path=threshold_path,
            feature_columns=feature_columns,
        )

        assert detector.feature_columns == feature_columns
        assert detector.threshold == 0.01
        assert detector.device == torch.device("cpu")


class TestAutoEncoderDetectorDetect:

    @patch("autoencoder_detector.AutoEncoderDetector._reconstruction_error")
    def test_returns_anomaly_when_above_threshold(
        self, mock_rec_error, threshold_path, feature_columns,
        valid_state_dict,
    ):
        mock_rec_error.return_value = 0.05

        with (
            patch("autoencoder_detector.joblib.load") as mock_jl,
            patch("autoencoder_detector.torch.load") as mock_tl,
        ):
            mock_jl.return_value = MagicMock()
            mock_tl.return_value = valid_state_dict
            detector = AutoEncoderDetector(
                model_path="m.pt",
                scaler_path="s.pkl",
                threshold_path=threshold_path,
                feature_columns=feature_columns,
            )

        result = detector.detect({"xmeas_1": 1.0, "xmeas_2": 2.0})

        assert result["anomaly"] is True
        assert result["reason"] == "reconstruction_error"
        assert result["metric"] == "reconstruction_error"

    @patch("autoencoder_detector.AutoEncoderDetector._reconstruction_error")
    def test_returns_no_anomaly_when_below_threshold(
        self, mock_rec_error, threshold_path, feature_columns,
        valid_state_dict,
    ):
        mock_rec_error.return_value = 0.001

        with (
            patch("autoencoder_detector.joblib.load") as mock_jl,
            patch("autoencoder_detector.torch.load") as mock_tl,
        ):
            mock_jl.return_value = MagicMock()
            mock_tl.return_value = valid_state_dict
            detector = AutoEncoderDetector(
                model_path="m.pt",
                scaler_path="s.pkl",
                threshold_path=threshold_path,
                feature_columns=feature_columns,
            )

        result = detector.detect({"xmeas_1": 1.0, "xmeas_2": 2.0})

        assert result["anomaly"] is False
        assert result["reason"] is None

    def test_returns_default_on_exception(
        self, threshold_path, feature_columns, valid_state_dict,
    ):
        with (
            patch("autoencoder_detector.joblib.load") as mock_jl,
            patch("autoencoder_detector.torch.load") as mock_tl,
        ):
            mock_jl.return_value = MagicMock()
            mock_tl.return_value = valid_state_dict
            detector = AutoEncoderDetector(
                model_path="m.pt",
                scaler_path="s.pkl",
                threshold_path=threshold_path,
                feature_columns=feature_columns,
            )

        result = detector.detect({"bad_field": "not_float"})

        assert result["anomaly"] is False
        assert result["reason"] == "detector_error"


class TestAutoEncoderDetectorExtractFeatures:

    @patch("autoencoder_detector.joblib.load")
    @patch("autoencoder_detector.torch.load")
    def test_extracts_feature_columns(
        self, mock_tl, mock_jl, threshold_path, feature_columns,
        valid_state_dict,
    ):
        mock_jl.return_value = MagicMock()
        mock_tl.return_value = valid_state_dict
        detector = AutoEncoderDetector(
            model_path="m.pt",
            scaler_path="s.pkl",
            threshold_path=threshold_path,
            feature_columns=feature_columns,
        )

        sample = {"xmeas_1": 1.5, "xmeas_2": 2.5, "extra": 99.0}
        df = detector._extract_features(sample)

        assert list(df.columns) == feature_columns
        assert df.iloc[0]["xmeas_1"] == 1.5
        assert df.iloc[0]["xmeas_2"] == 2.5

    @patch("autoencoder_detector.joblib.load")
    @patch("autoencoder_detector.torch.load")
    def test_defaults_missing_columns_to_zero(
        self, mock_tl, mock_jl, threshold_path, feature_columns,
        valid_state_dict,
    ):
        mock_jl.return_value = MagicMock()
        mock_tl.return_value = valid_state_dict
        detector = AutoEncoderDetector(
            model_path="m.pt",
            scaler_path="s.pkl",
            threshold_path=threshold_path,
            feature_columns=feature_columns,
        )

        df = detector._extract_features({})
        assert df.iloc[0]["xmeas_1"] == 0.0
        assert df.iloc[0]["xmeas_2"] == 0.0
