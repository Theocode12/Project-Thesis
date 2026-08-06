import numpy as np
import pytest

pytest.importorskip("torch")

from classifier import Classifier
from predictor import Predictor


def make_sample(fault_number=0):
    sample = {f"xmeas_{i}": 0.0 for i in range(1, 42)}
    sample.update({f"xmv_{i}": 0.0 for i in range(1, 12)})
    sample["faultNumber"] = fault_number
    return sample


@pytest.fixture
def predictor():
    return Predictor()


def known_classes(predictor):
    return {int(c) for c in predictor.label_encoder.classes_}


class TestPredictorContract:

    def test_is_a_classifier(self, predictor):
        assert isinstance(predictor, Classifier)

    def test_empty_batch_unknown(self, predictor):
        result = predictor.predict([])

        assert result["fault_number"] is None
        assert result["diagnosis"] == "unknown"
        assert result["sample_count"] == 0
        assert result["prediction_counts"] == {}
        assert result["confidence"] == 0.0

    def test_single_sample_confidence_one(self, predictor):
        result = predictor.predict([make_sample()])

        assert result["sample_count"] == 1
        assert result["fault_number"] in known_classes(predictor)
        assert result["confidence"] == 1.0
        assert result["prediction_counts"] == {
            result["fault_number"]: 1
        }
        assert result["diagnosis"] == f"fault_{result['fault_number']}"
        assert result["model"] == predictor.model

    def test_missing_features_do_not_crash(self, predictor):
        result = predictor.predict(
            [{"xmeas_1": 5.0}, {"xmv_3": 1.0}]
        )

        assert result["sample_count"] == 2
        assert result["fault_number"] in known_classes(predictor)

    def test_feature_columns_match_scaler(self, predictor):
        assert len(predictor.feature_columns) == len(
            predictor.scaler.mean_
        )


class TestMajorityVote:

    def test_majority_fault_is_selected(self, predictor, monkeypatch):
        monkeypatch.setattr(
            predictor,
            "_run_inference",
            lambda features: np.array([7.0, 7.0, 4.0]),
        )

        result = predictor.predict(
            [make_sample(), make_sample(), make_sample()]
        )

        assert result["fault_number"] == 7
        assert result["confidence"] == pytest.approx(2 / 3, abs=1e-3)
        assert result["prediction_counts"] == {7: 2, 4: 1}
        assert result["diagnosis"] == "fault_7"


class TestAccuracy:

    def test_accuracy_with_ground_truth(self, predictor, monkeypatch):
        monkeypatch.setattr(
            predictor,
            "_run_inference",
            lambda features: np.array([7.0, 7.0, 4.0]),
        )

        result = predictor.predict(
            [make_sample(7), make_sample(7), make_sample(4)]
        )

        assert result["accuracy"] == pytest.approx(1.0, abs=1e-3)
        assert result["correct_count"] == 3
        assert result["ground_truth_available"] == 3

    def test_accuracy_partial(self, predictor):
        accuracy = predictor._accuracy(
            [make_sample(7), make_sample(3), make_sample(4)],
            np.array([7.0, 7.0, 4.0]),
        )

        assert accuracy["accuracy"] == pytest.approx(2 / 3, abs=1e-3)
        assert accuracy["correct_count"] == 2
        assert accuracy["ground_truth_available"] == 3

    def test_accuracy_none_without_labels(self, predictor):
        accuracy = predictor._accuracy(
            [{"xmeas_1": 1.0}, {"xmeas_2": 2.0}],
            np.array([7.0, 7.0]),
        )

        assert accuracy["accuracy"] is None
        assert accuracy["correct_count"] == 0
        assert accuracy["ground_truth_available"] == 0

    def test_accuracy_skips_unusable_labels(self, predictor):
        accuracy = predictor._accuracy(
            [
                make_sample(7),
                {**make_sample(), "faultNumber": None},
                {**make_sample(), "faultNumber": float("nan")},
                make_sample(4),
            ],
            np.array([7.0, 7.0, 7.0, 4.0]),
        )

        assert accuracy["accuracy"] == pytest.approx(1.0, abs=1e-3)
        assert accuracy["correct_count"] == 2
        assert accuracy["ground_truth_available"] == 2

    def test_empty_batch_has_no_accuracy(self, predictor):
        result = predictor.predict([])

        assert result["accuracy"] is None
        assert result["correct_count"] == 0
        assert result["ground_truth_available"] == 0
