from enum import Enum


class MQTTOPIC(str, Enum):

    SENSOR_RAW = "sensor/raw"

    SENSOR_STATUS = "sensor/status"

    SYSTEM_CONTROL = "system/control"

    ANOMALY_DETECTED = "anomaly/detected"

    CLASSIFICATION_REQUEST = (
        "classification/request"
    )

    CLASSIFICATION_RESULT = (
        "classification/result"
    )

    ORCHESTRATOR_DECISION = (
        "orchestrator/decision"
    )