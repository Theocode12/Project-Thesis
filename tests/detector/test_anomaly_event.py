import pytest

from anomaly_event import AnomalyEvent
from shared.mqtt_message_envelop import MQTTMessageEnvelope


@pytest.fixture
def sg_metrics():
    return {
        "container": {"cpu_percent": 5.0},
        "processing_started_at": 1000.0,
        "processing_ended_at": 1000.0005,
    }


@pytest.fixture
def ed_metrics():
    return {
        "container": {"cpu_percent": 20.0},
        "processing_started_at": 1000.0,
        "processing_ended_at": 1000.003,
        "inference_started_at": 1000.0,
        "inference_ended_at": 1000.003,
    }


class TestAnomalyEventCreate:

    def test_returns_mqtt_message_envelope(self, sg_metrics, ed_metrics):
        result = {
            "anomaly": True,
            "reason": "reconstruction_error",
            "metric": "reconstruction_error",
            "value": 0.05,
        }
        sample = {
            "faultNumber": 1,
            "simulationRun": 3,
            "sample": 50,
        }

        event = AnomalyEvent.create(
            result=result,
            sample=sample,
            sg_metrics=sg_metrics,
            ed_metrics=ed_metrics,
        )

        assert isinstance(event, MQTTMessageEnvelope)
        assert event.source == "edge-detector"

    def test_payload_contains_anomaly_info(self, sg_metrics, ed_metrics):
        result = {
            "anomaly": True,
            "reason": "reconstruction_error",
            "metric": "reconstruction_error",
            "value": 0.05,
        }
        sample = {
            "faultNumber": 2,
            "simulationRun": 5,
            "sample": 100,
        }

        event = AnomalyEvent.create(
            result=result,
            sample=sample,
            sg_metrics=sg_metrics,
            ed_metrics=ed_metrics,
        )

        assert event.payload["anomaly"] is True
        assert event.payload["reason"] == "reconstruction_error"
        assert event.payload["metric"] == "reconstruction_error"
        assert event.payload["value"] == 0.05

    def test_payload_contains_sample_fields(self, sg_metrics, ed_metrics):
        result = {
            "anomaly": False,
            "reason": None,
            "metric": None,
            "value": None,
        }
        sample = {
            "faultNumber": 3,
            "simulationRun": 7,
            "sample": 200,
        }

        event = AnomalyEvent.create(
            result=result,
            sample=sample,
            sg_metrics=sg_metrics,
            ed_metrics=ed_metrics,
        )

        assert event.payload["fault"] == 3
        assert event.payload["simulationRun"] == 7
        assert event.payload["sample"]["sample"] == 200

    def test_payload_carries_generator_and_detector_metrics(
        self, sg_metrics, ed_metrics
    ):
        result = {
            "anomaly": True,
            "reason": "test",
            "metric": "test",
            "value": 0.1,
        }
        sample = {"faultNumber": 0, "simulationRun": 1, "sample": 10}

        event = AnomalyEvent.create(
            result=result,
            sample=sample,
            sg_metrics=sg_metrics,
            ed_metrics=ed_metrics,
        )

        assert event.payload["sg_metrics"] == sg_metrics
        assert event.payload["ed_metrics"] == ed_metrics

    def test_handles_missing_metrics(self):
        result = {
            "anomaly": True,
            "reason": "test",
            "metric": "test",
            "value": 1.0,
        }
        sample = {}

        event = AnomalyEvent.create(result=result, sample=sample)

        assert event.payload["sg_metrics"] == {}
        assert event.payload["ed_metrics"] == {}

    def test_handles_missing_sample_fields(self):
        result = {
            "anomaly": True,
            "reason": "test",
            "metric": "test",
            "value": 1.0,
        }
        sample = {}

        event = AnomalyEvent.create(result=result, sample=sample)

        assert event.payload["fault"] is None
        assert event.payload["simulationRun"] is None
        assert event.payload["sample"] == {}

    def test_to_dict_includes_source_and_timestamp(self):
        result = {
            "anomaly": True,
            "reason": "test",
            "metric": "test",
            "value": 0.1,
        }
        sample = {"faultNumber": 0, "simulationRun": 1, "sample": 10}

        event = AnomalyEvent.create(result=result, sample=sample)
        d = event.to_dict()

        assert d["source"] == "edge-detector"
        assert "timestamp" in d
        assert "payload" in d
