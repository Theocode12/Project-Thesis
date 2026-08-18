"""Edge Detection service console.

Renders the operational console for the edge anomaly detection service:
detector state, orchestrator risk, inference throughput, the sparse
autoencoder reconstruction error (with threshold), compact runtime
sparklines and an event timeline. Machine controls drive the detector
over MQTT (``ed_start`` / ``ed_stop`` / ``ed_reset``).

Interaction model mirrors the Sensor Generator page: interactive
widgets live at the top level, the read-only display (header, metrics,
chart, runtime panel, timeline) is wrapped in fragments that re-run
every 0.5s, and the state-driven Start/Stop buttons run inside a 1s
fragment so their active styling tracks the live edge/status stream.

The view receives its store and client through the constructor
(dependency injection) and builds its own controller, keeping the
page's state and action log self-contained.
"""

from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import components as c
from detection_store import DetectionController, DetectionStore
from mqtt_client import DashboardClient
from theme import MONO

RISK_TONE = {
    "LOW": "run",
    "MEDIUM": "pause",
    "HIGH": "stop",
}

SPARK_COLORS = {
    "cpu": "#39b6e8",
    "memory": "#ffb020",
    "latency": "#2ec27e",
}


def _fmt_time(ts: float | None) -> str:
    if ts is None:
        return "—"
    return datetime.fromtimestamp(ts, UTC).strftime("%H:%M:%S")


def _now_str() -> str:
    return datetime.now(UTC).strftime("%H:%M:%S")


def _fmt_bytes(num: float) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            return f"{value:.1f}<small>{unit}</small>"
        value /= 1024.0
    return f"{value:.1f}<small>TB</small>"


def _fmt_pct(num: float) -> str:
    return f"{num:.3g}<small>%</small>"


def _fmt_ms(num: float) -> str:
    return f"{num:.3g}<small>ms</small>"


def scores_dataframe(scores: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame([
        {"t": point["t"], "value": point["value"], "anomaly": point["anomaly"]}
        for point in scores
    ])
    if not df.empty:
        df["t"] = pd.to_datetime(df["t"], unit="s")
    return df


def score_figure(df: pd.DataFrame, threshold: float | None) -> go.Figure:
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df["t"],
        y=df["value"],
        mode="lines",
        name="reconstruction error",
        line={"width": 1.4, "color": "#39b6e8"},
        hoverinfo="y",
    ))

    if threshold is not None:
        fig.add_trace(go.Scatter(
            x=[df["t"].iloc[0], df["t"].iloc[-1]],
            y=[threshold, threshold],
            mode="lines",
            name="threshold",
            line={"width": 1.2, "color": "#ffb020", "dash": "dash"},
            hoverinfo="skip",
        ))

    anomalies = df[df["anomaly"]]
    if not anomalies.empty:
        fig.add_trace(go.Scatter(
            x=anomalies["t"],
            y=anomalies["value"],
            mode="markers",
            name="anomaly",
            marker={"size": 6, "color": "#ef4e4e", "line": {
                "width": 1, "color": "#0b0f14",
            }},
            hoverinfo="y",
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
        showlegend=False,
    )
    return fig


class DetectionView:

    def __init__(
        self,
        store: DetectionStore,
        client: DashboardClient,
    ) -> None:
        self.store = store
        self.client = client
        self.controller = DetectionController(store, client)

    def _render_metrics(self) -> None:
        store = self.store
        connected = self.client.is_connected()

        running = store.detection_enabled
        state, state_tone = (
            ("RUNNING", "run")
            if running is True
            else (("STOPPED", "stop") if running is False else ("—", ""))
        )

        risk = store.risk or "—"
        risk_tone = RISK_TONE.get(store.risk, "")

        count = len(store.recent_detections())

        row1 = st.columns(4)
        row1[0].markdown(
            c.tile(
                "Detector state",
                state,
                note="anomaly evaluation",
                tone=state_tone,
                icon="◎",
            ),
            unsafe_allow_html=True,
        )
        row1[1].markdown(
            c.tile(
                "Current risk",
                risk,
                note="orchestrator decision",
                tone=risk_tone,
                icon="⚠",
            ),
            unsafe_allow_html=True,
        )
        row1[2].markdown(
            c.tile(
                "Inference rate",
                f"{store.inference_rate:.1f}<small>samples/s</small>",
                note="last 5s window",
                tone="info",
                icon="≈",
            ),
            unsafe_allow_html=True,
        )
        row1[3].markdown(
            c.tile(
                "Anomalies detected",
                c.format_count(count),
                note="since detector start",
                tone="accent",
                icon="Σ",
            ),
            unsafe_allow_html=True,
        )

        latency = store.avg_processing_time_ms
        row2 = st.columns(3)
        row2[0].markdown(
            c.tile(
                "Samples processed",
                c.format_count(store.samples_processed),
                note="evaluated at the edge",
                tone="info",
                icon="▮",
            ),
            unsafe_allow_html=True,
        )
        rate = store.anomaly_rate_percent()
        row2[1].markdown(
            c.tile(
                "Anomaly rate",
                f"{rate:.1f}<small>%</small>" if rate is not None else "—",
                note="orchestrator window",
                tone="stop" if rate is not None and rate > 50.0 else "",
                icon="%",
            ),
            unsafe_allow_html=True,
        )
        row2[2].markdown(
            c.tile(
                "Avg inference time",
                f"{latency:.1f}<small>ms</small>" if latency is not None else "—",
                note="edge detector processing",
                tone="info",
                icon="◷",
            ),
            unsafe_allow_html=True,
        )

    @st.fragment(run_every=1.0)
    def _render_controls(self) -> None:
        running = self.store.detection_enabled is True

        col_a = st.columns(2)
        if col_a[0].button(
            "Start",
            key="btn_ed_start",
            type="primary" if running else "secondary",
            width="stretch",
        ):
            self.controller.send_start()
        if col_a[1].button(
            "Stop",
            key="btn_ed_stop",
            type="secondary" if running else "primary",
            width="stretch",
        ):
            self.controller.send_stop()

        if running:
            st.caption("Detection active — evaluating every sample.")
        else:
            st.caption("Detection idle — awaiting start.")

    def _render_reset(self) -> None:
        if st.button("Reset Engine State", key="btn_ed_reset", width="stretch"):
            self.controller.send_reset()

    @st.fragment(run_every=0.5)
    def _render_chart(self) -> None:
        scores = self.store.recent_scores()
        if scores:
            df = scores_dataframe(scores)
            st.plotly_chart(
                score_figure(df, self.store.threshold),
                width="stretch",
                config={"displayModeBar": False, "scrollZoom": True},
            )
        else:
            st.markdown(
                '<div class="edge-events-empty">'
                "Waiting for detector telemetry…"
                "</div>",
                unsafe_allow_html=True,
            )

    @st.fragment(run_every=0.5)
    def _render_runtime(self) -> None:
        runtime = self.store.recent_runtime()

        def last_value(series: list[dict]) -> float | None:
            return series[-1]["value"] if series else None

        cpu = last_value(runtime["cpu"])
        mem = last_value(runtime["memory"])
        latency = last_value(runtime["latency"])

        def spark_values(series: list[dict]) -> list[float]:
            return [p["value"] for p in series]

        cpu_row = c.metric_row(
            "CPU usage",
            _fmt_pct(cpu) if cpu is not None else "—",
            c.sparkline(spark_values(runtime["cpu"]), color=SPARK_COLORS["cpu"]),
        )
        mem_row = c.metric_row(
            "Memory usage",
            _fmt_bytes(mem) if mem is not None else "—",
            c.sparkline(
                spark_values(runtime["memory"]), color=SPARK_COLORS["memory"]
            ),
        )
        lat_row = c.metric_row(
            "Avg inference time",
            _fmt_ms(latency) if latency is not None else "—",
            c.sparkline(
                spark_values(runtime["latency"]), color=SPARK_COLORS["latency"]
            ),
        )

        st.markdown(cpu_row + mem_row + lat_row, unsafe_allow_html=True)

    # --------------------------------------------------------------------- #
    # read-only display fragments (safe to re-run every 0.5s)
    # --------------------------------------------------------------------- #

    @st.fragment(run_every=0.5)
    def _render_live(self) -> None:
        store = self.store
        connected = self.client.is_connected()

        running = store.detection_enabled
        state = (
            "RUNNING" if running is True
            else ("STOPPED" if running is False else "IDLE")
        )
        state_tone = (
            "run" if running is True
            else ("stop" if running is False else "info")
        )

        hud = [
            c.pill(state, state_tone),
            c.badge(
                "Model",
                "LOADED" if store.model_loaded else "—",
                accent=store.model_loaded is True,
            ),
            c.pill(
                "MQTT " + ("LIVE" if connected else "DOWN"),
                "run" if connected else "stop",
            ),
        ]

        st.markdown(
            c.page_head(
                "Edge Detection",
                "Sparse Autoencoder · Edge Anomaly Detection Service",
                "ED",
                hud,
            ),
            unsafe_allow_html=True,
        )

        if not connected:
            st.markdown(
                '<div class="edge-banner edge-banner--warn">'
                "No live MQTT traffic detected — broker unreachable or "
                "detector silent. Commands may not be delivered."
                "</div>",
                unsafe_allow_html=True,
            )

        self._render_metrics()

    @st.fragment(run_every=0.5)
    def _render_timeline(self) -> None:
        st.markdown(
            c.panel_open("Event Timeline", "detector + orchestrator log"),
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
        self._render_live()

        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        col_main, col_side = st.columns([2.15, 1], gap="large")

        with col_main:
            with c.panel("Reconstruction Error", "sparse autoencoder score", key="detect_rec_error"):
                self._render_chart()

        with col_side:
            with c.panel("Machine Controls", key="detect_machine_controls"):
                self._render_controls()
                st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
                self._render_reset()

            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

            with c.panel("Runtime Metrics", "edge container", key="detect_runtime"):
                self._render_runtime()

        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        self._render_timeline()
