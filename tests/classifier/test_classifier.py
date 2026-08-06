import pytest

from classifier import (
    Classifier,
    HeuristicClassifier,
    create_classifier,
)


@pytest.fixture
def classifier():
    return HeuristicClassifier()


def make_samples(faults):
    return [
        {"faultNumber": fault, "xmeas_1": 1.0}
        for fault in faults
    ]


class TestHeuristicClassifier:

    def test_majority_fault_is_selected(self, classifier):
        samples = make_samples([7, 7, 7, 3, 3])

        result = classifier.predict(samples)

        assert result["fault_number"] == 7
        assert result["diagnosis"] == "fault_7"
        assert result["model"] == "heuristic"
        assert result["sample_count"] == 5
        assert result["prediction_counts"] == {7: 3, 3: 2}
        assert result["confidence"] == 0.6

    def test_single_fault_confidence_one(self, classifier):
        result = classifier.predict(make_samples([1, 1, 1]))

        assert result["fault_number"] == 1
        assert result["diagnosis"] == "fault_1"
        assert result["confidence"] == 1.0

    def test_empty_batch_unknown(self, classifier):
        result = classifier.predict([])

        assert result["fault_number"] is None
        assert result["diagnosis"] == "unknown"
        assert result["confidence"] == 0.0
        assert result["sample_count"] == 0
        assert result["prediction_counts"] == {}

    def test_missing_fault_number_unknown(self, classifier):
        samples = [{"xmeas_1": 1.0}, {"xmeas_2": 2.0}]

        result = classifier.predict(samples)

        assert result["fault_number"] is None
        assert result["diagnosis"] == "unknown"
        assert result["sample_count"] == 2

    def test_mixed_missing_and_present(self, classifier):
        samples = [
            {"xmeas_1": 1.0},
            {"faultNumber": 5},
            {"faultNumber": 5},
        ]

        result = classifier.predict(samples)

        assert result["fault_number"] == 5
        assert result["diagnosis"] == "fault_5"
        assert result["confidence"] == pytest.approx(2 / 3, abs=1e-3)


class TestCreateClassifier:

    def test_returns_a_classifier(self):
        classifier = create_classifier()

        assert isinstance(classifier, Classifier)
