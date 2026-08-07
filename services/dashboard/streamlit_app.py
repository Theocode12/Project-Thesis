import streamlit as st

import theme
from detection_store import DetectionStore
from detection_view import DetectionView
from diagnosis_store import DiagnosisStore
from diagnosis_view import DiagnosisView
from mqtt_client import DashboardClient
from overview_store import OverviewStore
from overview_view import OverviewView
from sensor_store import SensorGeneratorStore
from sensor_generator_view import SensorGeneratorView
from shared.mqtt_topics import MQTTOPIC

st.set_page_config(
    page_title="Edge–Cloud Orchestration · Console",
    page_icon="▣",
    layout="wide",
    initial_sidebar_state="expanded",
)

theme.inject()

# Each service view is composed from its own data store + a shared client.
# "System Overview" is the home page and therefore the default selection.
VIEWS = {
    "System Overview": (OverviewView, "overview_store"),
    "Sensor Generator": (SensorGeneratorView, "sensor_store"),
    "Edge Detection": (DetectionView, "detection_store"),
    "Diagnosis": (DiagnosisView, "diagnosis_store"),
}


@st.cache_resource(show_spinner=False)
def _resources() -> dict:
    client = DashboardClient()

    sensor_store = SensorGeneratorStore()
    detection_store = DetectionStore()
    diagnosis_store = DiagnosisStore()

    overview_store = OverviewStore(
        sensor_store=sensor_store,
        detection_store=detection_store,
        diagnosis_store=diagnosis_store,
    )

    client.subscribe(MQTTOPIC.SENSOR_RAW, sensor_store.handle_raw)
    client.subscribe(MQTTOPIC.SENSOR_STATUS, sensor_store.handle_status)
    client.subscribe(MQTTOPIC.ANOMALY_DETECTED, detection_store.handle_anomaly)
    client.subscribe(MQTTOPIC.EDGE_STATUS, detection_store.handle_edge_status)
    client.subscribe(
        MQTTOPIC.ORCHESTRATOR_DECISION, detection_store.handle_decision
    )
    client.subscribe(MQTTOPIC.CLASSIFIER_STATUS, diagnosis_store.handle_status)
    client.subscribe(
        MQTTOPIC.CLASSIFICATION_RESULT, diagnosis_store.handle_result
    )
    client.subscribe(
        MQTTOPIC.CLASSIFICATION_REQUEST, diagnosis_store.handle_request
    )

    client.subscribe(MQTTOPIC.ANOMALY_DETECTED, overview_store.handle_anomaly)
    client.subscribe(
        MQTTOPIC.ORCHESTRATOR_DECISION, overview_store.handle_decision
    )
    client.subscribe(
        MQTTOPIC.CLASSIFICATION_RESULT, overview_store.handle_result
    )

    client.start()

    return {
        "client": client,
        "overview_store": overview_store,
        "sensor_store": sensor_store,
        "detection_store": detection_store,
        "diagnosis_store": diagnosis_store,
    }


def service_rail() -> str:
    with st.sidebar:
        st.markdown(
            '<div class="edge-rail-brand">EDGE<span>·</span>CLOUD</div>'
            '<div class="edge-rail-sub">Orchestration Console</div>',
            unsafe_allow_html=True,
        )
        st.divider()

        service = st.radio(
            "Service",
            list(VIEWS),
            key="service_rail",
        )

        st.divider()
        st.caption("Data source: Tennessee Eastman Process")
    return service


def main() -> None:
    service = service_rail()
    resources = _resources()

    view_cls, store_key = VIEWS[service]
    view = view_cls(store=resources[store_key], client=resources["client"])
    view.render()


main()
