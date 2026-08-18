from enum import Enum


class MQTTOPIC(str, Enum):

    SENSOR_RAW = "sensor/raw"

    SENSOR_STATUS = "sensor/status"

    SYSTEM_CONTROL = "system/control"

    ANOMALY_DETECTED = "anomaly/detected"

    DETECTOR_STATUS = "detector/status"

    CLASSIFICATION_REQUEST = (
        "classification/request"
    )

    CLASSIFICATION_RESULT = (
        "classification/result"
    )

    CLASSIFIER_STATUS = (
        "classifier/status"
    )

    ORCHESTRATOR_DECISION = (
        "orchestrator/decision"
    )
