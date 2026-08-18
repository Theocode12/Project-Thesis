from enum import Enum

class ServiceName(str, Enum):

    SENSOR_GENERATOR = "sensor-generator"
    DETECTOR = "detector"
    ORCHESTRATOR = "orchestrator"
    CLASSIFIER = "classifier"
    DASHBOARD = "dashboard"
    DATA_MANAGEMENT = "data-management"
