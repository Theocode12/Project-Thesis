from shared.mqtt_message_envelop import (
    MQTTMessageEnvelope
)


class AnomalyEvent:

    @staticmethod
    def create(
        result: dict,
        sample: dict
    ) -> MQTTMessageEnvelope:

        payload = {
            "anomaly": result["anomaly"],
            "reason": result["reason"],
            "metric": result["metric"],
            "value": result["value"],
            "fault": sample.get(
                "faultNumber"
            ),
            "simulationRun": sample.get(
                "simulationRun"
            ),
            "sample": sample.get(
                "sample"
            )
        }

        return MQTTMessageEnvelope.create(
            source="edge-detector",
            payload=payload
        )