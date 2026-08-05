import streamlit as st

import theme
from detection_store import DetectionStore
from detection_view import DetectionView
from mqtt_client import DashboardClient
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
VIEWS = {
    "Sensor Generator": (SensorGeneratorView, "sensor_store"),
    "Edge Detection": (DetectionView, "detection_store"),
}

TOPIC_CAPTION = "sensor/raw · sensor/status · anomaly/detected"


@st.cache_resource(show_spinner=False)
def _resources() -> dict:
    client = DashboardClient()

    sensor_store = SensorGeneratorStore()
    detection_store = DetectionStore()

    client.subscribe(MQTTOPIC.SENSOR_RAW, sensor_store.handle_raw)
    client.subscribe(MQTTOPIC.SENSOR_STATUS, sensor_store.handle_status)
    client.subscribe(MQTTOPIC.ANOMALY_DETECTED, detection_store.handle_anomaly)

    client.start()

    return {
        "client": client,
        "sensor_store": sensor_store,
        "detection_store": detection_store,
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
        st.caption(TOPIC_CAPTION)
        st.caption("Data source: Tennessee Eastman Process")
    return service


def main() -> None:
    service = service_rail()
    resources = _resources()

    view_cls, store_key = VIEWS[service]
    view = view_cls(store=resources[store_key], client=resources["client"])
    view.render()


main()
