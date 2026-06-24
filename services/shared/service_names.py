from enum import Enum

class ServiceName(str, Enum):

    SENSOR_GENERATOR = "sensor-generator"
    EDGE_DETECTOR = "edge-detector"
    ORCHESTRATOR = "orchestrator"
    EDGE_CLASSIFIER = "edge-classifier"
    CLOUD_CLASSIFIER = "cloud-classifier"
    DASHBOARD = "dashboard"