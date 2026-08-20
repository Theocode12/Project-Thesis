import streamlit as st

import theme
from detection_store import DetectionStore
from detection_view import DetectionView
from diagnosis_store import DiagnosisStore
from diagnosis_view import DiagnosisView
from experiment_recorder import ExperimentRecorder
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
    "Detection": (DetectionView, "detection_store"),
    "Diagnosis": (DiagnosisView, "diagnosis_store"),
}


@st.cache_resource(show_spinner=False)
def _resources() -> dict:
    recorder = ExperimentRecorder()
    client = DashboardClient(event_recorder=recorder)

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
    client.subscribe(MQTTOPIC.DETECTOR_STATUS, detection_store.handle_detector_status)
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

    recorder_topics = (
        MQTTOPIC.ANOMALY_DETECTED,
        MQTTOPIC.ORCHESTRATOR_DECISION,
        MQTTOPIC.CLASSIFICATION_RESULT,
        MQTTOPIC.SENSOR_STATUS,
        MQTTOPIC.DETECTOR_STATUS,
        MQTTOPIC.CLASSIFIER_STATUS,
    )
    for topic in recorder_topics:
        client.subscribe(
            topic,
            lambda envelope, topic=topic: recorder.record_event(
                topic.value,
                envelope,
                client.broker_name_for_topic(topic),
            ),
        )

    client.start()

    return {
        "client": client,
        "overview_store": overview_store,
        "sensor_store": sensor_store,
        "detection_store": detection_store,
        "diagnosis_store": diagnosis_store,
        "recorder": recorder,
    }


def experiment_controls(resources: dict) -> None:
    recorder = resources["recorder"]
    client = resources["client"]

    with st.sidebar.expander("Experiment Recorder", expanded=False):
        if recorder.active:
            st.caption(f"Recording: {recorder.experiment_id}")
            phase = st.selectbox(
                "Current phase",
                ["warmup", "normal", "fault", "recovery", "stress"],
                key="experiment_phase",
            )
            if st.button("Mark phase", key="experiment_mark_phase", width="stretch"):
                recorder.set_phase(phase)
                st.success(f"Phase marked: {phase}")
            if st.button("Stop recording", key="experiment_stop", width="stretch"):
                directory = recorder.stop()
                st.success(f"Saved: {directory}")
            return

        experiment_id = st.text_input("Experiment ID", key="experiment_id")
        scenario = st.text_input("Scenario", value="baseline", key="experiment_scenario")
        fault = st.number_input("Fault", min_value=0, value=0, step=1, key="experiment_fault")
        run = st.number_input("TEP run", min_value=1, value=1, step=1, key="experiment_run")
        interval = st.number_input(
            "Stream interval (seconds)",
            min_value=0.0,
            value=0.1,
            step=0.1,
            key="experiment_interval",
        )
        repetition = st.number_input(
            "Repetition", min_value=1, value=1, step=1, key="experiment_repetition"
        )
        if st.button("Start recording", key="experiment_start", width="stretch"):
            recorder.start(
                {
                    "experiment_id": experiment_id,
                    "deployment_mode": client.mode,
                    "scenario": scenario,
                    "fault": fault,
                    "tep_run": run,
                    "stream_interval_seconds": interval,
                    "repetition": repetition,
                    "phase": "warmup",
                }
            )
            st.success("Recording started")


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
    experiment_controls(resources)

    view_cls, store_key = VIEWS[service]
    view = view_cls(store=resources[store_key], client=resources["client"])
    view.render()


main()
