from shared.mqtt_message_envelop import (
    MQTTMessageEnvelope
)


class AnomalyEvent:

    @staticmethod
    def create(
        result: dict,
        sample: dict,
        sg_metrics: dict = None,
        ed_metrics: dict = None
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
            "sample": sample,
            "sg_metrics": sg_metrics or {},
            "ed_metrics": ed_metrics or {},
        }

        return MQTTMessageEnvelope.create(
            source="edge-detector",
            payload=payload
        )
