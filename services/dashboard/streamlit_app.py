import streamlit as st

import theme
from mqtt_client import DashboardClient
from sensor_generator_view import render_sensor_generator

st.set_page_config(
    page_title="Edge–Cloud Orchestration · Console",
    page_icon="▣",
    layout="wide",
    initial_sidebar_state="expanded",
)

theme.inject()


@st.cache_resource(show_spinner=False)
def _dashboard_client() -> DashboardClient:
    client = DashboardClient()
    client.start()
    return client


def ensure_client() -> DashboardClient:
    st.session_state.setdefault("last_fault", 0)
    st.session_state.setdefault("last_run", None)
    st.session_state.setdefault("last_interval", 0.1)

    return _dashboard_client()


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
            ["Sensor Generator"],
            key="service_rail",
        )

        st.divider()
        st.caption("sensor/raw · sensor/status · system/control")
        st.caption("Data source: Tennessee Eastman Process")
    return service


def main() -> None:
    service = service_rail()
    client = ensure_client()

    if service == "Sensor Generator":
        render_sensor_generator(client)


main()
