"""Sensor Generator service console.

Renders the operational console for the TEP sensor generator: stream
state, active fault scenario, publish volume, adjustable machine
controls and a live, selectable variable chart backed by an event log.

Interaction model: interactive widgets (selects / sliders /
multiselects) live at the top level so they respond to clicks reliably.
The read-only display (metrics, chart, timeline) is wrapped in fragments
that re-run every 0.5s. Only the state-driven Start/Stop buttons run
inside a 1s fragment so their active styling tracks the live MQTT status;
the Reset button stays static at the top level since it never re-styles.

The view receives its store and client through the constructor
(dependency injection) and builds its own controller, keeping the
page's state and action log self-contained.
"""

from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import components as c
from mqtt_client import DashboardClient
from sensor_store import SensorGeneratorController, SensorGeneratorStore
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


def _now_str() -> str:
    return datetime.now(UTC).strftime("%H:%M:%S")


def _read_state(store: SensorGeneratorStore) -> dict:
    status = (store.get_status() or {}).get("status") or {}
    return {
        "running": status.get("running"),
        "fault": status.get("fault"),
        "run": status.get("run"),
        "position": status.get("position"),
        "loaded": status.get("loaded", False),
    }


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


class SensorGeneratorView:

    def __init__(
        self,
        store: SensorGeneratorStore,
        client: DashboardClient,
    ) -> None:
        self.store = store
        self.client = client
        self.controller = SensorGeneratorController(store, client)

    def _render_metrics(self, state: dict) -> None:
        store = self.store
        metrics = store.get_metrics() or {}
        sg = metrics.get("sg_metrics") or {}

        running = state["running"]
        fault = state["fault"]
        run = state["run"]
        connected = self.client.is_connected()
        rate = store.sample_rate
        interval = sg.get("stream_interval")
        last_at = self.client.last_message_at

        run_tone = (
            "run" if running is True
            else ("pause" if running is False else "info")
        )

        fault_txt = f"F{fault}" if fault is not None else "—"
        fault_note = (
            f"fault_{fault} · run {run}" if fault is not None else "no dataset loaded"
        )
        position = state["position"]
        dataset_note = (
            f"fault_{fault} · run_{run} · row {position}"
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
                c.format_count(store.get_message_count()),
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

    @st.fragment(run_every=1.0)
    def _render_controls(self) -> None:
        running = _read_state(self.store)["running"]

        col_a = st.columns(2)
        if col_a[0].button(
            "Start",
            key="btn_start",
            type="primary" if running is True else "secondary",
            width="stretch",
        ):
            self.controller.send_start()
        if col_a[1].button(
            "Stop",
            key="btn_stop",
            type="primary" if running is not True else "secondary",
            width="stretch",
        ):
            self.controller.send_halt()

        if running:
            st.caption("Stream active — samples flowing to sensor/raw.")
        else:
            st.caption("Stream idle — awaiting start or dataset selection.")

    def _render_reset(self) -> None:
        if st.button("Reset", key="btn_reset", width="stretch"):
            self.controller.send_reset()

    def _render_fault(self) -> None:
        last_fault = st.session_state.get("last_fault", 0)
        if not (0 <= last_fault < len(FAULTS)):
            last_fault = 0

        selected_fault = st.selectbox(
            "Fault scenario",
            FAULTS,
            index=last_fault,
            key=K_FAULT,
            help="Select a TEP fault scenario to stream.",
        )
        if st.session_state.get("last_fault") != selected_fault:
            self.controller.send_set_fault(selected_fault)
            st.session_state["last_fault"] = selected_fault
            st.session_state["last_run"] = None
            st.session_state[K_RUN] = "Auto (random)"

        run_options = ["Auto (random)"] + [str(r) for r in RUNS]
        last_run = st.session_state.get("last_run")
        run_index = last_run if last_run is not None and 1 <= last_run <= RUNS[-1] else 0
        selected_run = st.selectbox(
            "Run",
            run_options,
            index=run_index,
            key=K_RUN,
            help="Pin a specific simulation run, or let the generator pick randomly.",
        )
        if selected_run != "Auto (random)":
            pinned_run = int(selected_run)
            if st.session_state.get("last_run") != pinned_run:
                self.controller.send_set_stream(selected_fault, pinned_run)
                st.session_state["last_run"] = pinned_run
        else:
            st.session_state["last_run"] = None

    def _render_stream_interval(self) -> None:
        last_interval = st.session_state.get("last_interval", 0.1)
        interval = st.slider(
            "Stream interval (s)",
            min_value=0.0,
            max_value=15.0,
            value=min(15.0, max(0.0, last_interval)),
            step=0.1,
            key=K_INTERVAL,
        )
        if st.session_state.get("last_interval") != interval:
            self.controller.send_set_stream_interval(interval)
            st.session_state["last_interval"] = interval
        st.caption("Delay between published samples.")

    def _render_chart_pickers(self) -> None:
        channels = self.store.channels()
        xmeas = sorted([ch for ch in channels if ch.startswith("xmeas_")])
        xmv = sorted([ch for ch in channels if ch.startswith("xmv_")])

        if not xmeas and not xmv:
            st.caption("Waiting for sensor data before variables can be plotted…")
            return

        last_xmeas = [ch for ch in st.session_state.get("last_xmeas", []) if ch in xmeas]
        last_xmv = [ch for ch in st.session_state.get("last_xmv", []) if ch in xmv]

        cx, cm = st.columns(2)
        with cx:
            picked_xmeas = st.multiselect(
                "Measured variables (xmeas)",
                xmeas,
                default=last_xmeas or xmeas[:6],
                key=K_XMEAS,
            )
        with cm:
            picked_xmv = st.multiselect(
                "Manipulated variables (xmv)",
                xmv,
                default=last_xmv or xmv[:3],
                key=K_XMV,
            )

        if picked_xmeas != st.session_state.get("last_xmeas"):
            st.session_state["last_xmeas"] = picked_xmeas
        if picked_xmv != st.session_state.get("last_xmv"):
            st.session_state["last_xmv"] = picked_xmv

    # --------------------------------------------------------------------- #
    # read-only display fragments (safe to re-run every 0.5s)
    # --------------------------------------------------------------------- #

    @st.fragment(run_every=0.5)
    def _render_live(self) -> None:
        state = _read_state(self.store)
        state["label"], state["tone"] = _overall_state(state["running"])

        connected = self.client.is_connected()

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

        self._render_metrics(state)

    @st.fragment(run_every=0.5)
    def _render_chart(self) -> None:
        xmeas = list(st.session_state.get(K_XMEAS, []))
        xmv = list(st.session_state.get(K_XMV, []))
        selected = xmeas + xmv

        samples = self.store.recent_samples()
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
    def _render_timeline(self) -> None:
        st.markdown(
            c.panel_open("Event Timeline", "action log"),
            unsafe_allow_html=True,
        )
        st.markdown(
            c.event_timeline(self.store.recent_actions()),
            unsafe_allow_html=True,
        )
        st.markdown(c.panel_close(), unsafe_allow_html=True)

    # --------------------------------------------------------------------- #
    # entry point
    # --------------------------------------------------------------------- #

    def render(self) -> None:
        st.session_state.setdefault("last_fault", 0)
        st.session_state.setdefault("last_run", None)
        st.session_state.setdefault("last_interval", 0.1)

        self._render_live()

        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        col_main, col_side = st.columns([2.15, 1], gap="large")

        with col_main:
            st.markdown(
                c.panel_open("Live Process Variables"),
                unsafe_allow_html=True,
            )
            self._render_chart_pickers()
            st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
            self._render_chart()
            st.markdown(c.panel_close(), unsafe_allow_html=True)

        with col_side:
            st.markdown(
                c.panel_open("Machine Controls"),
                unsafe_allow_html=True,
            )
            self._render_controls()
            self._render_reset()
            st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
            self._render_fault()
            st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
            self._render_stream_interval()
            st.markdown(c.panel_close(), unsafe_allow_html=True)

        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        self._render_timeline()
