"""Diagnosis Service console.

Renders the operational console for the cloud fault diagnosis service:
classifier state, loaded model, queue depth, throughput metrics, the latest
diagnosis result (centrepiece), compact runtime sparklines, an event
timeline and machine controls over MQTT (``cl_start`` / ``cl_stop`` /
``cl_reset``).

    Interaction model mirrors the Detection page: the read-only display
(header, metrics, latest diagnosis, runtime panel, timeline) is wrapped in
fragments that re-run every 0.5s, and the state-driven Start/Stop buttons
run inside a 1s fragment so their active styling tracks the live
``classifier/status`` heartbeat.

The view receives its store and client through the constructor
(dependency injection) and builds its own controller, keeping the page's
state and action log self-contained.
"""

from datetime import UTC, datetime

import streamlit as st

import components as c
from diagnosis_store import DiagnosisController, DiagnosisStore
from mqtt_client import DashboardClient

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


class DiagnosisView:

    def __init__(
        self,
        store: DiagnosisStore,
        client: DashboardClient,
    ) -> None:
        self.store = store
        self.client = client
        self.controller = DiagnosisController(store, client)

    def _render_status_cards(self) -> None:
        store = self.store
        connected = self.client.is_connected()

        running = store.running
        state, state_tone = (
            ("RUNNING", "run")
            if running is True
            else (("STOPPED", "stop") if running is False else ("—", ""))
        )

        model = store.model or "—"
        queue = store.queue_depth
        queue_tone = (
            "stop"
            if store.queue_backed_up()
            else ("pause" if queue > 0 else "info")
        )

        row = st.columns(4)
        row[0].markdown(
            c.tile(
                "Classifier status",
                state,
                note="Ready to classify",
                tone=state_tone,
                icon="◎",
            ),
            unsafe_allow_html=True,
        )
        row[1].markdown(
            c.tile(
                "Model",
                model,
                note=(
                    "PyTorch"
                    if store.model_loaded is not None
                    else "no model yet"
                ),
                tone="info" if store.model_loaded is True else "",
                icon="◆",
            ),
            unsafe_allow_html=True,
        )
        row[2].markdown(
            c.tile(
                "Queue depth",
                f"{queue}",
                note="pending diagnosis jobs",
                tone=queue_tone,
                icon="≡",
            ),
            unsafe_allow_html=True,
        )
        row[3].markdown(
            c.tile(
                "MQTT link",
                "CONNECTED" if connected else "OFFLINE",
                note="classifier/status",
                tone="run" if connected else "stop",
                icon="↔",
            ),
            unsafe_allow_html=True,
        )

    def _render_metrics(self) -> None:
        store = self.store
        avg_ms = store.avg_processing_time_ms

        row = st.columns(4)
        row[0].markdown(
            c.tile(
                "Classifications",
                c.format_count(store.classifications_processed),
                note="processed",
                tone="accent",
                icon="Σ",
            ),
            unsafe_allow_html=True,
        )
        row[1].markdown(
            c.tile(
                "Batch count",
                c.format_count(store.batch_count),
                note="completed",
                tone="info",
                icon="▮",
            ),
            unsafe_allow_html=True,
        )
        row[2].markdown(
            c.tile(
                "Classification rate",
                f"{store.classification_rate:.1f}<small>cls/s</small>",
                note="last 5s window",
                tone="info",
                icon="≈",
            ),
            unsafe_allow_html=True,
        )
        row[3].markdown(
            c.tile(
                "Avg processing time",
                f"{avg_ms:.1f}<small>ms</small>"
                if avg_ms is not None
                else "—",
                note="per classification",
                tone="info",
                icon="◷",
            ),
            unsafe_allow_html=True,
        )

    # --------------------------------------------------------------------- #
    # read-only display fragments (safe to re-run every 0.5s)
    # --------------------------------------------------------------------- #

    def _render_live(self) -> None:
        store = self.store
        connected = self.client.is_connected()

        running = store.running
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
                "MQTT " + ("CONNECTED" if connected else "DOWN"),
                "run" if connected else "stop",
            ),
        ]

        st.markdown(
            c.page_head(
                "Diagnosis",
                "PyTorch Fault Classifier · Diagnosis Service",
                "DG",
                hud,
            ),
            unsafe_allow_html=True,
        )

        if not connected:
            st.markdown(
                '<div class="edge-banner edge-banner--warn">'
                "No live MQTT traffic detected — broker unreachable or "
                "classifier silent. Commands may not be delivered."
                "</div>",
                unsafe_allow_html=True,
            )

        self._render_status_cards()
        self._render_metrics()

    def _render_latest(self) -> None:
        latest = self.store.latest_diagnosis()
        if latest is None:
            st.markdown(
                c.diagnosis_card(None, None, None),
                unsafe_allow_html=True,
            )
            return
        st.markdown(
            c.diagnosis_card(
                latest.get("fault_number"),
                latest.get("diagnosis"),
                latest.get("confidence"),
                latest.get("t"),
            ),
            unsafe_allow_html=True,
        )

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
            "Avg processing time",
            _fmt_ms(latency) if latency is not None else "—",
            c.sparkline(
                spark_values(runtime["latency"]),
                color=SPARK_COLORS["latency"],
            ),
        )

        st.markdown(cpu_row + mem_row + lat_row, unsafe_allow_html=True)

    def _render_timeline(self) -> None:
        st.markdown(
            c.panel_open("Event Timeline", "diagnosis service log"),
            unsafe_allow_html=True,
        )
        st.markdown(
            c.event_timeline(self.store.recent_actions()),
            unsafe_allow_html=True,
        )
        st.markdown(c.panel_close(), unsafe_allow_html=True)

    # --------------------------------------------------------------------- #
    # state-driven controls (re-run every 1s to track the heartbeat)
    # --------------------------------------------------------------------- #

    def _render_controls(self) -> None:
        running = self.store.running is True

        col_a = st.columns(2)
        if col_a[0].button(
            "Start",
            key="btn_cl_start",
            type="primary" if running else "secondary",
            width="stretch",
        ):
            self.controller.send_start()
        if col_a[1].button(
            "Stop",
            key="btn_cl_stop",
            type="secondary" if running else "primary",
            width="stretch",
        ):
            self.controller.send_stop()

        if running:
            st.caption("Classifier active — awaiting diagnosis requests.")
        else:
            st.caption("Classifier idle — awaiting start.")

    def _render_reset(self) -> None:
        if st.button(
            "Reset Statistics", key="btn_cl_reset", width="stretch"
        ):
            self.controller.send_reset()

    # --------------------------------------------------------------------- #
    # entry point
    # --------------------------------------------------------------------- #

    def render(self) -> None:
        self._render_live()

        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        col_main, col_side = st.columns([2.15, 1], gap="large")

        with col_main:
            with c.panel("Latest Diagnosis", "fault classifier result", key="diag_latest"):
                self._render_latest()

        with col_side:
            with c.panel("Machine Controls", key="diag_machine_controls"):
                self._render_controls()
                st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
                self._render_reset()

            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

            with c.panel("Runtime Metrics", "classifier container", key="diag_runtime"):
                self._render_runtime()

        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        self._render_timeline()
