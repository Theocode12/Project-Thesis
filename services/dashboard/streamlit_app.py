import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from mqtt_client import DashboardClient

FAULTS = list(range(21))
RUNS = list(range(1, 501))
DEFAULT_CHANNELS = [f"xmeas_{i}" for i in range(1, 9)]
SENSOR_WINDOW_SECONDS = 60.0


def ensure_client() -> DashboardClient | None:

    if "dashboard_client" not in st.session_state:
        st.session_state.setdefault("last_fault", 0)
        st.session_state.setdefault("last_run", None)
        st.session_state.setdefault("last_stream_interval", 0.1)
        st.session_state.setdefault("last_status_interval", 5.0)

        try:
            client = DashboardClient()
            client.start()
            st.session_state["dashboard_client"] = client
        except Exception as exc:
            st.sidebar.error(f"MQTT connection failed: {exc}")
            st.session_state["dashboard_client"] = None

    return st.session_state["dashboard_client"]


def build_sensor_dataframe(
    samples: list[dict],
    channels: list[str],
) -> pd.DataFrame:
    rows = []
    for sample in samples:
        rows.append({
            "t": sample["t"],
            **{
                channel: sample["values"].get(channel)
                for channel in channels
            },
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["t"] = pd.to_datetime(df["t"], unit="s")
    return df


def sensor_figure(
    df: pd.DataFrame,
    channels: list[str],
) -> go.Figure:
    fig = go.Figure()
    for channel in channels:
        if channel in df.columns:
            fig.add_trace(go.Scatter(
                x=df["t"],
                y=df[channel],
                mode="lines",
                name=channel,
            ))
    fig.update_layout(
        height=400,
        margin={"l": 40, "r": 10, "t": 10, "b": 30},
        legend={"orientation": "h", "y": 1.1},
        xaxis_title="Time",
        yaxis_title="Value",
    )
    return fig


def gauge_figure(
    value: float | None,
    title: str,
    minimum: float,
    maximum: float,
) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value if value is not None else 0,
        number={
            "suffix": "%",
            "valueformat": ".1f",
        },
        title={"text": title},
        gauge={
            "axis": {"range": [minimum, maximum]},
            "bar": {"color": "#4C9BE8"},
        },
    ))
    fig.update_layout(height=220, margin={"l": 20, "r": 20, "t": 40, "b": 10})
    return fig


def processing_figure(history: list[dict]) -> go.Figure:
    fig = go.Figure(go.Scatter(
        x=[pd.to_datetime(item["t"], unit="s") for item in history],
        y=[item["processing_time_ms"] for item in history],
        mode="lines",
        name="Processing time",
    ))
    fig.update_layout(
        height=220,
        margin={"l": 40, "r": 10, "t": 10, "b": 30},
        xaxis_title="Time",
        yaxis_title="ms",
    )
    return fig


def format_bytes(value: int | None) -> str:
    if value is None:
        return "-"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_uptime(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


@st.fragment(run_every=0.5)
def render_sensor_generator(client: DashboardClient) -> None:

    st.header("Sensor Generator")

    status = client.store.get_status()
    metrics = client.store.get_metrics()
    samples = client.store.recent_samples()
    processing_history = client.store.recent_processing_times()

    status_info = (status or {}).get("status") or {}
    running = status_info.get("running")
    fault = status_info.get("fault")
    run = status_info.get("run")
    position = status_info.get("position")
    loaded = status_info.get("loaded")

    sg_metrics = (metrics or {}).get("sg_metrics") or {}
    container = sg_metrics.get("container") or {}
    stream_interval = sg_metrics.get("stream_interval")
    status_interval = sg_metrics.get("status_interval")

    last_at = client.store.last_message_at
    freshness = time.time() - last_at if last_at is not None else None

    col_status, col_control = st.columns([2, 1], gap="large")

    with col_status:
        st.subheader("Stream Status")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Running", "Yes" if running else "Paused")
        c2.metric("Fault", fault if fault is not None else "-")
        c3.metric("Run", run if run is not None else "-")
        c4.metric("Row", position if position is not None else "-")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Stream interval",
            f"{stream_interval}s" if stream_interval is not None else "-",
        )
        c2.metric("Measured rate", f"{client.store.sample_rate}/s")
        c3.metric(
            "Freshness",
            f"{freshness:.1f}s" if freshness is not None else "-",
        )
        c4.metric("Loaded", "Yes" if loaded else "No")

    with col_control:
        st.subheader("Controls")

        b1, b2, b3 = st.columns(3)
        if b1.button("Start", use_container_width=True):
            client.send_start()
        if b2.button("Stop", use_container_width=True):
            client.send_stop()
        if b3.button("Reset", use_container_width=True):
            client.send_reset()

        selected_fault = st.selectbox(
            "Fault",
            FAULTS,
            index=0,
            key="fault_select",
        )
        if st.session_state.get("last_fault") != selected_fault:
            client.send_set_fault(selected_fault)
            st.session_state["last_fault"] = selected_fault
            st.session_state["last_run"] = None

        run_options = ["Auto (random)"] + [str(r) for r in RUNS]
        selected_run = st.selectbox(
            "Run",
            run_options,
            key="run_select",
        )
        if selected_run != "Auto (random)":
            pinned_run = int(selected_run)
            if st.session_state.get("last_run") != pinned_run:
                client.send_set_stream(selected_fault, pinned_run)
                st.session_state["last_run"] = pinned_run
        else:
            st.session_state["last_run"] = None

        stream_interval_input = st.slider(
            "Stream interval (s)",
            min_value=0.02,
            max_value=2.0,
            value=0.1,
            step=0.01,
            key="stream_interval_slider",
        )
        if st.session_state.get("last_stream_interval") != stream_interval_input:
            client.send_set_stream_interval(stream_interval_input)
            st.session_state["last_stream_interval"] = stream_interval_input

        status_interval_input = st.slider(
            "Status interval (s)",
            min_value=1,
            max_value=30,
            value=5,
            step=1,
            key="status_interval_slider",
        )
        if st.session_state.get("last_status_interval") != status_interval_input:
            client.send_set_status_interval(status_interval_input)
            st.session_state["last_status_interval"] = status_interval_input

    st.subheader("Live Sensors")

    channels = client.store.channels()
    if not channels:
        st.info("Waiting for sensor data...")
    else:
        default_channels = [
            channel
            for channel in DEFAULT_CHANNELS
            if channel in channels
        ] or channels[:8]

        selected_channels = st.multiselect(
            "Channels",
            channels,
            default=default_channels,
        )

        if samples and selected_channels:
            df = build_sensor_dataframe(samples, selected_channels)
            st.plotly_chart(
                sensor_figure(df, selected_channels),
                use_container_width=True,
            )
        else:
            st.info("No sensor samples received yet.")

    st.subheader("Container Metrics")

    col_gauge_1, col_gauge_2 = st.columns(2)
    col_gauge_1.plotly_chart(
        gauge_figure(container.get("cpu_percent"), "CPU", 0, 100),
        use_container_width=True,
    )
    col_gauge_2.plotly_chart(
        gauge_figure(container.get("memory_percent"), "Memory", 0, 100),
        use_container_width=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Memory used", format_bytes(container.get("memory_used_bytes")))
    c2.metric("Uptime", format_uptime(container.get("uptime_seconds")))
    c3.metric("Processes", container.get("process_count"))

    st.subheader("Processing Time")

    if processing_history:
        st.plotly_chart(
            processing_figure(processing_history),
            use_container_width=True,
        )
    else:
        st.info("Waiting for processing time data...")


st.set_page_config(
    page_title="Adaptive Edge-Cloud Orchestration",
    layout="wide",
)

client = ensure_client()

with st.sidebar:
    st.title("Edge-Cloud Orchestration")
    service = st.radio(
        "Service",
        ["Sensor Generator"],
    )
    st.caption("MQTT: sensor/raw, sensor/status, system/control")

if client is None:
    st.stop()

if service == "Sensor Generator":
    render_sensor_generator(client)
