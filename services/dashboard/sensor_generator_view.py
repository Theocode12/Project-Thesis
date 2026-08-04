"""Sensor Generator service console.

Renders the operational console for the TEP sensor generator: stream
state, active fault scenario, publish volume, adjustable machine
controls and a live, selectable variable chart backed by an event log.

Interaction model: interactive widgets (buttons / selects / sliders /
multiselects) live at the top level so they respond to clicks reliably.
Only the read-only display (metrics, chart, timeline) is wrapped in a
fragment that re-runs every 0.5s. Streamlit ``run_every`` fragments are
unreliable hosts for interactive widgets, so they are deliberately kept
out of them.
"""

from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import components as c
from mqtt_client import DashboardClient
from theme import MONO

FAULTS = list(range(21))
RUNS = list(range(1, 501))
DATASET_NAME = "TEP"

# Persistent widget keys so 0.5s fragment re-runs don't reset state.
K_FAULT = "vsg_fault"
K_RUN = "vsg_run"
K_INTERVAL = "vsg_interval"
K_XMEAS = "vsg_xmeas"
K_XMV = "vsg_xmv"

XMEAS_COLORS = [
    "#ffa94d", "#ff6b6b", "#e599f7", "#cc5de8",
    "#5c7cfa", "#748ffc", "#91a7ff", "#9775fa",
]
XMV_COLORS = ["#20c997", "#38d9a9", "#63e6be", "#0ca678", "#12b886"]


def _fmt_time(ts: float | None) -> str:
    if ts is None:
        return "—"
    return datetime.fromtimestamp(ts, UTC).strftime("%H:%M:%S")


def _read_state(client: DashboardClient) -> dict:
    status = (client.store.get_status() or {}).get("status") or {}
    return {
        "running": status.get("running"),
        "fault": status.get("fault"),
        "run": status.get("run"),
        "loaded": status.get("loaded", False),
    }


def _live_config(
    client: DashboardClient,
) -> tuple[int | None, int | None, float | None]:
    status = (client.store.get_status() or {}).get("status") or {}
    sg = (client.store.get_metrics() or {}).get("sg_metrics") or {}
    fault = status.get("fault")
    run = status.get("run")
    if fault is None or run is None:
        samples = client.store.recent_samples()
        if samples:
            stream = samples[-1].get("values", {}).get("_stream") or {}
            if fault is None:
                fault = stream.get("fault")
            if run is None:
                run = stream.get("run")
    return fault, run, sg.get("stream_interval")


def _sync_live_controls(client: DashboardClient) -> bool:
    fault, run, interval = _live_config(client)
    changed = False

    if not st.session_state.get("vsg_touched_fault") and fault is not None:
        if st.session_state.get(K_FAULT) != fault:
            st.session_state[K_FAULT] = fault
            st.session_state["last_fault"] = fault
            changed = True

    if not st.session_state.get("vsg_touched_run") and run is not None:
        run_str = str(run)
        if st.session_state.get(K_RUN) != run_str:
            st.session_state[K_RUN] = run_str
            st.session_state["last_run"] = run
            changed = True

    if not st.session_state.get("vsg_touched_interval") and interval is not None:
        interval = round(min(15.0, max(0.0, interval)), 1)
        if st.session_state.get(K_INTERVAL) != interval:
            st.session_state[K_INTERVAL] = interval
            st.session_state["last_interval"] = interval
            changed = True

    return changed


def _overall_state(running: bool | None) -> tuple[str, str]:
    if running is True:
        return "Running", "run"
    if running is False:
        return "Paused", "pause"
    return "Idle", "info"


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
    xmeas: list[str],
    xmv: list[str],
) -> go.Figure:
    fig = go.Figure()
    meas_colors = {ch: XMEAS_COLORS[i % len(XMEAS_COLORS)] for i, ch in enumerate(xmeas)}
    mv_colors = {ch: XMV_COLORS[i % len(XMV_COLORS)] for i, ch in enumerate(xmv)}

    for channel in xmeas:
        if channel in df.columns:
            fig.add_trace(go.Scatter(
                x=df["t"],
                y=df[channel],
                mode="lines",
                name=channel,
                line={"width": 1.4, "color": meas_colors[channel]},
            ))
    for channel in xmv:
        if channel in df.columns:
            fig.add_trace(go.Scatter(
                x=df["t"],
                y=df[channel],
                mode="lines",
                name=channel,
                line={
                    "width": 1.8,
                    "color": mv_colors[channel],
                    "dash": "dot",
                },
            ))

    fig.update_layout(
        height=420,
        margin={"l": 12, "r": 8, "t": 8, "b": 12},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": MONO, "color": "#93a1b1", "size": 11},
        xaxis={
            "gridcolor": "#1d2731",
            "zeroline": False,
            "showline": False,
        },
        yaxis={
            "gridcolor": "#1d2731",
            "zeroline": False,
            "showline": False,
        },
        hovermode="x unified",
        hoverlabel={
            "bgcolor": "#151c25",
            "bordercolor": "#2b3a48",
            "font": {"family": MONO, "color": "#e8eef5", "size": 11},
        },
        legend={
            "orientation": "h",
            "y": 1.06,
            "x": 0,
            "font": {"family": MONO, "color": "#93a1b1", "size": 10},
        },
    )
    return fig


def _render_metrics(client: DashboardClient, state: dict) -> None:
    store = client.store
    metrics = store.get_metrics() or {}
    sg = metrics.get("sg_metrics") or {}

    running = state["running"]
    fault = state["fault"]
    run = state["run"]
    connected = store.is_connected()
    rate = store.sample_rate
    interval = sg.get("stream_interval")
    last_at = store.last_message_at

    run_tone = (
        "run" if running is True
        else ("pause" if running is False else "info")
    )

    fault_txt = f"F{fault}" if fault is not None else "—"
    fault_note = (
        f"fault_{fault} · run {run}" if fault is not None else "no dataset loaded"
    )
    dataset_note = (
        f"fault_{fault} · run_{run}"
        if fault is not None and run is not None
        else "awaiting stream"
    )

    row1 = st.columns(4)
    row1[0].markdown(
        c.tile(
            "Generator state",
            str(state["label"]).upper(),
            note="streaming" if running else "idle",
            tone=run_tone,
            icon="◎",
        ),
        unsafe_allow_html=True,
    )
    row1[1].markdown(
        c.tile(
            "Fault scenario",
            fault_txt.upper(),
            note=fault_note,
            tone=run_tone if fault is not None else "",
            icon="⚠",
        ),
        unsafe_allow_html=True,
    )
    row1[2].markdown(
        c.tile(
            "Publish rate",
            f"{rate:.1f}<small>msg/s</small>",
            note="last 5s window",
            tone="info",
            icon="≈",
        ),
        unsafe_allow_html=True,
    )
    row1[3].markdown(
        c.tile(
            "Messages published",
            f"{store.get_message_count():,}",
            note="published to sensor/raw",
            tone="accent",
            icon="Σ",
        ),
        unsafe_allow_html=True,
    )

    row2 = st.columns(4)
    row2[0].markdown(
        c.tile(
            "Sampling interval",
            f"{interval:.2f}<small>s</small>" if interval is not None else "—",
            note="between samples",
            tone="info",
            icon="▮",
        ),
        unsafe_allow_html=True,
    )
    row2[1].markdown(
        c.tile(
            "MQTT link",
            "CONNECTED" if connected else "OFFLINE",
            note="sensor/raw · sensor/status",
            tone="run" if connected else "stop",
            icon="↔",
        ),
        unsafe_allow_html=True,
    )
    row2[2].markdown(
        c.tile(
            "Dataset",
            DATASET_NAME,
            note=dataset_note,
            tone="info",
            icon="◇",
        ),
        unsafe_allow_html=True,
    )
    row2[3].markdown(
        c.tile(
            "Last published",
            _fmt_time(last_at),
            note=_now_str(),
            tone="",
            icon="◷",
        ),
        unsafe_allow_html=True,
    )


def _now_str() -> str:
    return datetime.now(UTC).strftime("%H:%M:%S")


def _render_controls(client: DashboardClient, state: dict) -> None:
    running = state["running"]

    row_a, row_b = st.columns(2)
    with row_a:
        col_a = st.columns(2)
        if col_a[0].button("Start", key="btn_start", type="primary", width="stretch"):
            client.send_start()
        if col_a[1].button("Pause", key="btn_pause", width="stretch"):
            client.send_stop()
    with row_b:
        col_b = st.columns(2)
        if col_b[0].button("Stop", key="btn_stop", width="stretch"):
            client.send_halt()
        if col_b[1].button("Reset", key="btn_reset", width="stretch"):
            client.send_reset()

    if running:
        st.caption("Stream active — samples flowing to sensor/raw.")
    else:
        st.caption("Stream idle — awaiting start or dataset selection.")


def _render_fault(client: DashboardClient) -> None:
    selected_fault = st.selectbox(
        "Fault scenario",
        FAULTS,
        index=0,
        key=K_FAULT,
        help="Select a TEP fault scenario to stream.",
    )
    if st.session_state.get("last_fault") != selected_fault:
        st.session_state["vsg_touched_fault"] = True
        client.send_set_fault(selected_fault)
        st.session_state["last_fault"] = selected_fault
        st.session_state["last_run"] = None

    run_options = ["Auto (random)"] + [str(r) for r in RUNS]
    selected_run = st.selectbox(
        "Run",
        run_options,
        key=K_RUN,
        help="Pin a specific simulation run, or let the generator pick randomly.",
    )
    if selected_run != "Auto (random)":
        pinned_run = int(selected_run)
        if st.session_state.get("last_run") != pinned_run:
            st.session_state["vsg_touched_run"] = True
            client.send_set_stream(selected_fault, pinned_run)
            st.session_state["last_run"] = pinned_run
    else:
        if st.session_state.get("last_run") is not None:
            st.session_state["vsg_touched_run"] = True
        st.session_state["last_run"] = None


def _render_stream_interval(client: DashboardClient) -> None:
    interval = st.slider(
        "Stream interval (s)",
        min_value=0.0,
        max_value=15.0,
        value=0.1,
        step=0.1,
        key=K_INTERVAL,
    )
    if st.session_state.get("last_interval") != interval:
        st.session_state["vsg_touched_interval"] = True
        client.send_set_stream_interval(interval)
        st.session_state["last_interval"] = interval
    st.caption("Delay between published samples.")


def _render_chart_pickers(client: DashboardClient) -> None:
    channels = client.store.channels()
    xmeas = sorted([ch for ch in channels if ch.startswith("xmeas_")])
    xmv = sorted([ch for ch in channels if ch.startswith("xmv_")])

    if not xmeas and not xmv:
        st.caption("Waiting for sensor data before variables can be plotted…")
        return

    cx, cm = st.columns(2)
    with cx:
        st.multiselect(
            "Measured variables (xmeas)",
            xmeas,
            default=xmeas[:6],
            key=K_XMEAS,
        )
    with cm:
        st.multiselect(
            "Manipulated variables (xmv)",
            xmv,
            default=xmv[:3],
            key=K_XMV,
        )


# --------------------------------------------------------------------------- #
# read-only display fragments (safe to re-run every 0.5s)
# --------------------------------------------------------------------------- #

@st.fragment(run_every=0.5)
def _render_live(client: DashboardClient) -> None:
    if _sync_live_controls(client):
        st.rerun()

    state = _read_state(client)
    state["label"], state["tone"] = _overall_state(state["running"])

    connected = client.store.is_connected()

    hud = [
        c.pill(state["label"], state["tone"]),
        c.badge(
            "Fault",
            f'F{state["fault"]}' if state["fault"] is not None else "—",
            accent=state["fault"] not in (None, 0),
        ),
        c.pill(
            "MQTT " + ("LIVE" if connected else "DOWN"),
            "run" if connected else "stop",
        ),
    ]

    st.markdown(
        c.page_head(
            "Sensor Generator",
            "Tennessee Eastman Process · Edge–Cloud Inference Orchestration",
            "SG",
            hud,
        ),
        unsafe_allow_html=True,
    )

    if not connected:
        st.markdown(
            '<div class="edge-banner edge-banner--warn">'
            "No live MQTT traffic detected — broker unreachable or "
            "generator silent. Commands may not be delivered."
            "</div>",
            unsafe_allow_html=True,
        )

    _render_metrics(client, state)


@st.fragment(run_every=0.5)
def _render_chart(client: DashboardClient) -> None:
    xmeas = list(st.session_state.get(K_XMEAS, []))
    xmv = list(st.session_state.get(K_XMV, []))
    selected = xmeas + xmv

    samples = client.store.recent_samples()
    if samples and selected:
        df = build_sensor_dataframe(samples, selected)
        st.plotly_chart(
            sensor_figure(df, xmeas, xmv),
            width="stretch",
            config={"displayModeBar": False, "scrollZoom": True},
        )
    else:
        st.markdown(
            '<div class="edge-events-empty">Waiting for sensor samples…</div>',
            unsafe_allow_html=True,
        )


@st.fragment(run_every=0.5)
def _render_timeline(client: DashboardClient) -> None:
    st.markdown(
        c.panel_open("Event Timeline", "action log"),
        unsafe_allow_html=True,
    )
    st.markdown(
        c.event_timeline(client.store.recent_events()),
        unsafe_allow_html=True,
    )
    st.markdown(c.panel_close(), unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #

def render_sensor_generator(client: DashboardClient) -> None:
    _sync_live_controls(client)

    _render_live(client)

    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    col_main, col_side = st.columns([2.15, 1], gap="large")

    with col_main:
        st.markdown(
            c.panel_open("Live Process Variables"),
            unsafe_allow_html=True,
        )
        _render_chart_pickers(client)
        st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
        _render_chart(client)
        st.markdown(c.panel_close(), unsafe_allow_html=True)

    with col_side:
        st.markdown(
            c.panel_open("Machine Controls"),
            unsafe_allow_html=True,
        )
        _render_controls(client, _read_state(client))
        st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
        _render_fault(client)
        st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
        _render_stream_interval(client)
        st.markdown(c.panel_close(), unsafe_allow_html=True)

    st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

    _render_timeline(client)