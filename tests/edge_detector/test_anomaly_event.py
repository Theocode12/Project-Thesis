import pytest

from anomaly_event import AnomalyEvent
from shared.mqtt_message_envelop import MQTTMessageEnvelope


class TestAnomalyEventCreate:

    def test_returns_mqtt_message_envelope(self):
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

        event = AnomalyEvent.create(result=result, sample=sample)

        assert isinstance(event, MQTTMessageEnvelope)
        assert event.source == "edge-detector"

    def test_payload_contains_anomaly_info(self):
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

        event = AnomalyEvent.create(result=result, sample=sample)

        assert event.payload["anomaly"] is True
        assert event.payload["reason"] == "reconstruction_error"
        assert event.payload["metric"] == "reconstruction_error"
        assert event.payload["value"] == 0.05

    def test_payload_contains_sample_fields(self):
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

        event = AnomalyEvent.create(result=result, sample=sample)

        assert event.payload["fault"] == 3
        assert event.payload["simulationRun"] == 7
        assert event.payload["sample"] == 200

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
        assert event.payload["sample"] is None

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
