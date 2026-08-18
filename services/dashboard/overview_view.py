"""System Overview home console.

The platform-level observability dashboard for the Edge–Cloud Inference
Orchestration platform. It aggregates cross-service telemetry into a live
evaluation view: detection / diagnosis / end-to-end latency, CPU and memory
    usage for the detector and classifier services, cloud
communication statistics and a runtime summary.

This page is intentionally read-only — it is an observability and
evaluation dashboard, not a control panel. All interactive behaviour is
limited to chart inspection (modebar tools and a click-to-expand modal).

Interaction model mirrors the other service views: the whole page lives in
a single fragment that re-runs every 0.5s, and clicking "Expand" on any
chart opens a large modal (``st.dialog``) for detailed inspection.
"""

from datetime import UTC, datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import components as c
from mqtt_client import DashboardClient
from overview_store import OverviewStore
from theme import MONO

EDGE_CPU_COLOR = "#39b6e8"
CLOUD_CPU_COLOR = "#8b7cf6"
EDGE_MEM_COLOR = "#ffb020"
CLOUD_MEM_COLOR = "#2ec27e"
LATENCY_COLOR = "#39b6e8"
AVG_COLOR = "#93a1b1"

_MB = 1024.0 * 1024.0

# Recent window (seconds) shown by the detection/diagnosis latency overlay so a
# stale stream can no longer stretch the shared time axis.
LATENCY_OVERLAY_WINDOW = 900.0


# --------------------------------------------------------------------------- #
# dataframes
# --------------------------------------------------------------------------- #

def _latency_df(points: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(points)
    if not df.empty:
        df["t"] = pd.to_datetime(df["t"], unit="s")
    return df


def _series_df(points: list[dict], scale: float = 1.0) -> pd.DataFrame:
    """Convert {t, value} runtime points into a plottable dataframe.

    ``scale`` lets byte series be converted to MB before plotting.
    """
    if not points:
        return pd.DataFrame(columns=["t", "y"])
    df = pd.DataFrame([
        {"t": point["t"], "y": point["value"] / scale}
        for point in points
    ])
    df["t"] = pd.to_datetime(df["t"], unit="s")
    return df


def _x_range(*series: list[dict]):
    times = [point["t"] for s in series for point in s]
    if not times:
        return None
    lo, hi = min(times), max(times)
    pad = max(5.0, (hi - lo) * 0.05)
    return [
        datetime.fromtimestamp(lo - pad, UTC),
        datetime.fromtimestamp(hi + pad, UTC),
    ]


def _recent_window(
    *series: list[dict],
    window_seconds: float = LATENCY_OVERLAY_WINDOW,
):
    """Rolling x-range anchored to the newest data point across all series."""
    times = [point["t"] for s in series for point in s]
    if not times:
        return None
    hi = max(times)
    pad = max(5.0, window_seconds * 0.02)
    return [
        datetime.fromtimestamp(hi - window_seconds, UTC),
        datetime.fromtimestamp(hi + pad, UTC),
    ]


# --------------------------------------------------------------------------- #
# figure builders
# --------------------------------------------------------------------------- #

def configure_layout(
    fig: go.Figure,
    y_title: str = "",
    y2_title: str = "",
    y2_color: str = "",
    x_range=None,
    legend: bool = True,
    height: int = 300,
) -> go.Figure:
    xaxis = {
        "gridcolor": "#1d2731",
        "zeroline": False,
        "showline": False,
        "tickformat": "%H:%M:%S",
        "rangeslider": {"visible": False},
    }
    if x_range is not None:
        xaxis["range"] = x_range
    layout = {
        "height": height,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": MONO, "color": "#93a1b1", "size": 11},
        "xaxis": xaxis,
        "yaxis": {
            "gridcolor": "#1d2731",
            "zeroline": False,
            "showline": False,
            "title": y_title or None,
        },
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": "#151c25",
            "bordercolor": "#2b3a48",
            "font": {"family": MONO, "color": "#e8eef5", "size": 11},
        },
        "legend": {
            "orientation": "h",
            "y": 1.08,
            "x": 0,
            "font": {"family": MONO, "color": "#93a1b1", "size": 10},
        },
        "showlegend": legend,
    }
    if y2_title:
        title = {
            "text": y2_title,
            "font": {"family": MONO, "size": 10},
        }
        if y2_color:
            title["font"]["color"] = y2_color
        layout["yaxis2"] = {
            "title": title,
            "side": "right",
            "overlaying": "y",
            "gridcolor": "rgba(0,0,0,0)",
            "zeroline": False,
            "showline": False,
            "tickfont": {"family": MONO, "size": 10, "color": "#93a1b1"},
        }
        layout["margin"] = {"l": 8, "r": 24, "t": 8, "b": 8}
    else:
        layout["margin"] = {"l": 8, "r": 8, "t": 8, "b": 8}
    fig.update_layout(**layout)
    return fig


def _latency_trace(
    fig: go.Figure,
    df: pd.DataFrame,
    name: str,
    color: str,
    yaxis: str = "y",
) -> None:
    """Add a solid latency line plus its dashed rolling-average line."""
    if df.empty:
        return
    fig.add_trace(go.Scatter(
        x=df["t"],
        y=df["ms"],
        mode="lines",
        name=name,
        line={"width": 1.6, "color": color},
        hovertemplate="%{y:.1f} ms<extra></extra>",
        yaxis=yaxis,
    ))
    window = max(2, min(20, len(df) // 4))
    if window > 2:
        avg = df["ms"].rolling(window).mean()
        fig.add_trace(go.Scatter(
            x=df["t"],
            y=avg,
            mode="lines",
            name=f"{name} · {window}-pt avg",
            line={"width": 1.1, "color": AVG_COLOR, "dash": "dot"},
            hovertemplate="%{y:.1f} ms<extra></extra>",
            yaxis=yaxis,
        ))


def latency_figure(
    df: pd.DataFrame,
    color: str = LATENCY_COLOR,
    y_title: str = "latency (ms)",
    x_range=None,
) -> go.Figure:
    fig = go.Figure()
    _latency_trace(fig, df, "latency", color)
    return configure_layout(fig, y_title=y_title, x_range=x_range)


def dual_latency_figure(
    det_df: pd.DataFrame,
    diag_df: pd.DataFrame,
    x_range=None,
) -> go.Figure:
    fig = go.Figure()
    _latency_trace(fig, det_df, "Detection", EDGE_CPU_COLOR, yaxis="y")
    _latency_trace(fig, diag_df, "Diagnosis", CLOUD_CPU_COLOR, yaxis="y2")
    return configure_layout(
        fig,
        y_title="detection latency (ms)",
        y2_title="diagnosis latency (ms)",
        y2_color=CLOUD_CPU_COLOR,
        x_range=x_range,
    )


def resource_figure(
    df: pd.DataFrame,
    y_title: str,
    color: str,
    name: str,
    x_range=None,
    height: int = 260,
) -> go.Figure:
    fig = go.Figure()
    if not df.empty:
        fig.add_trace(go.Scatter(
            x=df["t"],
            y=df["y"],
            mode="lines",
            name=name,
            line={"width": 1.5, "color": color},
            hovertemplate="%{y:.2f}<extra></extra>",
        ))
    return configure_layout(fig, y_title=y_title, x_range=x_range, height=height)


def dual_resource_figure(
    edge_df: pd.DataFrame,
    cloud_df: pd.DataFrame,
    y_title: str,
    name_edge: str,
    color_edge: str,
    name_cloud: str,
    color_cloud: str,
    x_range=None,
    height: int = 260,
) -> go.Figure:
    fig = go.Figure()
    if not edge_df.empty:
        fig.add_trace(go.Scatter(
            x=edge_df["t"],
            y=edge_df["y"],
            mode="lines",
            name=name_edge,
            line={"width": 1.5, "color": color_edge},
            hovertemplate="%{y:.2f}<extra></extra>",
        ))
    if not cloud_df.empty:
        fig.add_trace(go.Scatter(
            x=cloud_df["t"],
            y=cloud_df["y"],
            mode="lines",
            name=name_cloud,
            line={"width": 1.5, "color": color_cloud},
            hovertemplate="%{y:.2f}<extra></extra>",
        ))
    return configure_layout(fig, y_title=y_title, x_range=x_range, height=height)


def chart_config(filename: str) -> dict:
    """Plotly modebar config: zoom, pan, box/lasso, reset, PNG export."""
    return {
        "displaylogo": False,
        "scrollZoom": True,
        "responsive": True,
        "toImageButtonOptions": {
            "format": "png",
            "filename": filename,
            "scale": 2,
            "width": 1280,
            "height": 720,
        },
    }


# --------------------------------------------------------------------------- #
# formatters
# --------------------------------------------------------------------------- #

def _fmt_ms(num) -> str:
    return f"{num:.1f}<small>ms</small>" if num is not None else "—"


def _fmt_pct(num) -> str:
    return f"{num:.1f}<small>%</small>" if num is not None else "—"


def _fmt_mb(num) -> str:
    return f"{num:.1f}<small>MB</small>" if num is not None else "—"


def _now_str() -> str:
    return datetime.now(UTC).strftime("%H:%M:%S")


def _latency_span_readout(det_points: list[dict], diag_points: list[dict]) -> str:
    """Temporary diagnostic: raw span/magnitude of each latency stream.

    Used to verify the overlay fix on the live run. Remove once confirmed.
    """
    def _desc(points: list[dict], label: str) -> str:
        if not points:
            return f"{label}: 0 pts"
        ms = [p["ms"] for p in points]
        newest = max(p["t"] for p in points)
        oldest = min(p["t"] for p in points)
        age = newest - oldest
        return (
            f"{label}: {len(points)} pts · "
            f"t {age/60.0:.1f}m span · ms {min(ms):.1f}→{max(ms):.1f}"
        )
    return " · ".join(
        (_desc(det_points, "det"), _desc(diag_points, "diag"))
    )


# --------------------------------------------------------------------------- #
# modal chart inspector
# --------------------------------------------------------------------------- #

@st.dialog("Chart Inspector", width="large")
def _chart_dialog(slug: str, title: str, build) -> None:
    st.caption(f"{title} · live rolling window · publication scale")
    fig = build()
    st.plotly_chart(
        fig,
        width="stretch",
        config=chart_config(f"overview_{slug}"),
    )
    close = st.columns([5, 1])
    close[0].caption("Export as PNG from the modebar (top-right) for reports.")
    if close[1].button("Close", key=f"btn_close_{slug}"):
        st.session_state.pop("ov_modal", None)
        st.rerun()


class OverviewView:

    def __init__(
        self,
        store: OverviewStore,
        client: DashboardClient,
    ) -> None:
        self.store = store
        self.client = client

    # ------------------------------------------------------------------ #
    # metric helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _current(points: list[dict], key: str = "ms"):
        return points[-1][key] if points else None

    @staticmethod
    def _average(points: list[dict], key: str = "ms"):
        if not points:
            return None
        return sum(point[key] for point in points) / len(points)

    @staticmethod
    def _peak(points: list[dict], key: str = "ms"):
        if not points:
            return None
        return max(point[key] for point in points)

    # ------------------------------------------------------------------ #
    # read-only display fragments
    # ------------------------------------------------------------------ #

    def _render_header(self) -> None:
        connected = self.client.is_connected()
        self.store.connected = connected

        health_label, health_tone = self.store.system_health()

        hud = [
            c.pill(health_label, health_tone),
            c.pill(
                "MQTT " + ("CONNECTED" if connected else "DOWN"),
                "run" if connected else "stop",
            ),
            c.badge(
                "Deployment",
                self.store.deployment_mode(),
                accent=self.store.deployment_mode() != "UNKNOWN",
            ),
        ]

        st.markdown(
            c.page_head(
                "System Overview",
                "Edge–Cloud Inference Orchestration Platform",
                "OV",
                hud,
            ),
            unsafe_allow_html=True,
        )

        if not connected:
            st.markdown(
                '<div class="edge-banner edge-banner--warn">'
                "No live MQTT traffic detected — broker unreachable or "
                "services silent. Metrics below reflect the last data seen."
                "</div>",
                unsafe_allow_html=True,
            )

    def _render_overview_cards(self) -> None:
        sensor = self.store.sensor_store()
        detection = self.store.detection_store()
        diagnosis = self.store.diagnosis_store()
        connected = self.client.is_connected()

        sg_status = (sensor.get_status() or {}).get("status") or {} if sensor else {}
        sg_running = sg_status.get("running")
        sg_label, sg_tone = (
            ("RUNNING", "run")
            if sg_running is True
            else (("PAUSED", "pause") if sg_running is False else ("IDLE", "info"))
        )
        fault = sg_status.get("fault")

        det_running = detection.detection_enabled if detection else None
        det_label, det_tone = (
            ("RUNNING", "run")
            if det_running is True
            else (("STOPPED", "stop") if det_running is False else ("IDLE", "info"))
        )
        det_model = detection.model_loaded if detection else None

        cl_running = diagnosis.running if diagnosis else None
        cl_label, cl_tone = (
            ("RUNNING", "run")
            if cl_running is True
            else (("STOPPED", "stop") if cl_running is False else ("IDLE", "info"))
        )
        cl_model = diagnosis.model if diagnosis else None

        row = st.columns(4)
        row[0].markdown(
            c.tile(
                "Sensor stream",
                sg_label,
                note=f"fault F{fault}" if fault is not None else "awaiting stream",
                tone=sg_tone,
                icon="◎",
            ),
            unsafe_allow_html=True,
        )
        row[1].markdown(
            c.tile(
                "Edge detection",
                det_label,
                note="model loaded" if det_model else "model unavailable",
                tone=det_tone,
                icon="⚠",
            ),
            unsafe_allow_html=True,
        )
        row[2].markdown(
            c.tile(
                "Cloud diagnosis",
                cl_label,
                note=str(cl_model) if cl_model else "model unavailable",
                tone=cl_tone,
                icon="◆",
            ),
            unsafe_allow_html=True,
        )
        row[3].markdown(
            c.tile(
                "MQTT broker",
                "CONNECTED" if connected else "OFFLINE",
                note="system/control · all topics",
                tone="run" if connected else "stop",
                icon="↔",
            ),
            unsafe_allow_html=True,
        )

    def _render_latency_panel(
        self,
        slug: str,
        title: str,
        meta: str,
        points: list[dict],
        color: str,
        y_title: str,
        tiles: list[tuple[str, str, str, str]],
        extra_columns: int = 0,
    ) -> None:
        with c.panel(title, meta, key=f"ov_lat_{slug}"):
            df = _latency_df(points)
            st.plotly_chart(
                latency_figure(
                    df,
                    color=color,
                    y_title=y_title,
                    x_range=_recent_window(points),
                ),
                width="stretch",
                config=chart_config(f"overview_{slug}"),
            )

            cols = st.columns(len(tiles))
            for col, (label, value, note, tone) in zip(cols, tiles):
                col.markdown(
                    c.tile(label, value, note=note, tone=tone),
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
            row = st.columns([5, 1])
            row[0].caption(
                "Rolling stream · sensor generation → result published"
            )
            if row[1].button("Expand", key=f"btn_expand_{slug}", width="stretch"):
                st.session_state["ov_modal"] = slug

    @staticmethod
    def _render_tile_group(
        label: str,
        color: str,
        tiles: list[tuple[str, str, str, str]],
    ) -> None:
        st.markdown(
            f'<div class="edge-meta" style="margin-bottom:0.3rem">'
            f'<span style="color:{color}">●</span> {label}</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(3)
        for col, (tlabel, tvalue, tnote, ttone) in zip(cols, tiles):
            col.markdown(
                c.tile(tlabel, tvalue, note=tnote, tone=ttone),
                unsafe_allow_html=True,
            )

    def _render_latency_section(self, mode: str) -> None:
        lat = self.store.recent_latencies()

        # --- Detection / Diagnosis Latency ----------------------------- #
        det_points = lat["detection"]
        diag_points = lat["diagnosis"]
        det_current = self._current(det_points)
        det_avg = self._average(det_points)
        det_peak = self._peak(det_points)
        diag_current = self._current(diag_points)
        diag_avg = self._average(diag_points)
        diag_peak = self._peak(diag_points)

        if mode == "Overlay":
            with c.panel(
                "Detection & Diagnosis Latency",
                "sensor generation → anomaly detection · cloud request → result publication",
                key="ov_lat_det_diag",
            ):
                st.plotly_chart(
                    dual_latency_figure(
                        _latency_df(det_points),
                        _latency_df(diag_points),
                        x_range=_recent_window(det_points, diag_points),
                    ),
                    width="stretch",
                    config=chart_config("overview_det_diag_latency"),
                )
                st.caption(_latency_span_readout(det_points, diag_points))
                self._render_tile_group(
                    "Detection",
                    EDGE_CPU_COLOR,
                    [
                        ("Current", _fmt_ms(det_current), "latest detection", "info"),
                        ("Average", _fmt_ms(det_avg), "rolling mean", "info"),
                        ("Peak", _fmt_ms(det_peak), "window maximum", "stop"),
                    ],
                )
                self._render_tile_group(
                    "Diagnosis",
                    CLOUD_CPU_COLOR,
                    [
                        ("Current", _fmt_ms(diag_current), "latest result", "info"),
                        ("Average", _fmt_ms(diag_avg), "rolling mean", "info"),
                        ("Peak", _fmt_ms(diag_peak), "window maximum", "stop"),
                    ],
                )
                st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
                row = st.columns([5, 1])
                row[0].caption(
                    "Rolling stream · detection and diagnosis on shared axes"
                )
                if row[1].button(
                    "Expand", key="btn_expand_det_diag_latency", width="stretch"
                ):
                    st.session_state["ov_modal"] = "det_diag_latency"
        else:
            self._render_latency_panel(
                "detection_latency",
                "Detection Latency",
                "sensor generation → anomaly detection",
                det_points,
                color="#39b6e8",
                y_title="detection latency (ms)",
                tiles=[
                    ("Current", _fmt_ms(det_current), "latest detection", "info"),
                    ("Average", _fmt_ms(det_avg), "rolling mean", "info"),
                    ("Peak", _fmt_ms(det_peak), "window maximum", "stop"),
                ],
            )

            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

            self._render_latency_panel(
                "diagnosis_latency",
                "Diagnosis Latency",
                "cloud request start → result publication",
                diag_points,
                color="#8b7cf6",
                y_title="diagnosis latency (ms)",
                tiles=[
                    ("Current", _fmt_ms(diag_current), "latest result", "info"),
                    ("Average", _fmt_ms(diag_avg), "rolling mean", "info"),
                    ("Peak", _fmt_ms(diag_peak), "window maximum", "stop"),
                ],
            )

            st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        # --- End-to-End Latency ---------------------------------------- #
        e2e_points = lat["e2e"]
        e2e_current = self._current(e2e_points)
        e2e_avg = self._average(e2e_points)
        e2e_peak = self._peak(e2e_points)

        runtime = self.store.runtime_series()
        edge_cpu_points = runtime["edge"]["cpu"]
        edge_cpu = edge_cpu_points[-1]["value"] if edge_cpu_points else None

        self._render_latency_panel(
            "e2e_latency",
            "End-to-End Latency",
            "sensor generation → final diagnosis published",
            e2e_points,
            color="#2ec27e",
            y_title="latency (ms)",
            tiles=[
                ("Current", _fmt_ms(e2e_current), "latest diagnosis", "info"),
                ("Average", _fmt_ms(e2e_avg), "rolling mean", "info"),
                ("Peak", _fmt_ms(e2e_peak), "window maximum", "stop"),
            ],
        )

    def _render_resource_section(
        self,
        mode: str,
        title: str,
        meta: str,
        y_title: str,
        unit_scale: float,
        color_edge: str,
        color_cloud: str,
        fmt,
        key: str,
    ) -> None:
        runtime = self.store.runtime_series()
        edge_points = runtime["edge"][key]
        cloud_points = runtime["cloud"][key]
        x_range = _x_range(edge_points, cloud_points)

        edge_df = _series_df(edge_points, scale=unit_scale)
        cloud_df = _series_df(cloud_points, scale=unit_scale)

        edge_current = self._current(edge_points, key="value")
        edge_avg = self._average(edge_points, key="value")
        edge_peak = self._peak(edge_points, key="value")
        cloud_current = self._current(cloud_points, key="value")
        cloud_avg = self._average(cloud_points, key="value")
        cloud_peak = self._peak(cloud_points, key="value")

        edge_tiles = [
            ("Current", fmt(edge_current / unit_scale) if edge_current is not None else "—", "latest sample", "info"),
            ("Average", fmt(edge_avg / unit_scale) if edge_avg is not None else "—", "rolling mean", "info"),
            ("Peak", fmt(edge_peak / unit_scale) if edge_peak is not None else "—", "window maximum", "stop"),
        ]
        cloud_tiles = [
            ("Current", fmt(cloud_current / unit_scale) if cloud_current is not None else "—", "latest sample", "info"),
            ("Average", fmt(cloud_avg / unit_scale) if cloud_avg is not None else "—", "rolling mean", "info"),
            ("Peak", fmt(cloud_peak / unit_scale) if cloud_peak is not None else "—", "window maximum", "stop"),
        ]

        if mode == "Overlay":
            slug = f"{slugify(title)}_usage"
            with c.panel(title, meta, key=f"ov_{slug}"):
                st.plotly_chart(
                    dual_resource_figure(
                        edge_df,
                        cloud_df,
                        y_title=y_title,
                        name_edge="Detector",
                        color_edge=color_edge,
                        name_cloud="Classifier",
                        color_cloud=color_cloud,
                        x_range=x_range,
                    ),
                    width="stretch",
                    config=chart_config(f"overview_{slug}"),
                )
                self._render_tile_group("Detector", color_edge, edge_tiles)
                self._render_tile_group("Classifier", color_cloud, cloud_tiles)
                st.markdown('<div class="edge-divider"></div>', unsafe_allow_html=True)
                row = st.columns([5, 1])
                row[0].caption(
                    "Overlaid container metrics · shared time window"
                )
                if row[1].button("Expand", key=f"btn_expand_{slug}", width="stretch"):
                    st.session_state["ov_modal"] = slug
            return

        with c.panel(title, meta, key=f"ov_{slugify(title)}"):
            col_edge, col_cloud = st.columns(2)
            self._render_resource_column(
                col_edge,
                f"{slugify(title)}_edge",
                "Detector",
                edge_df,
                y_title,
                color_edge,
                x_range,
                edge_tiles,
            )
            self._render_resource_column(
                col_cloud,
                f"{slugify(title)}_cloud",
                "Classifier",
                cloud_df,
                y_title,
                color_cloud,
                x_range,
                cloud_tiles,
            )

    def _render_resource_column(
        self,
        col,
        slug: str,
        label: str,
        df: pd.DataFrame,
        y_title: str,
        color: str,
        x_range,
        tiles: list[tuple[str, str, str, str]],
    ) -> None:
        with col:
            with c.panel(label, "live container metrics", key=f"ov_res_{slug}"):
                st.plotly_chart(
                    resource_figure(
                        df,
                        y_title=y_title,
                        color=color,
                        name=label,
                        x_range=x_range,
                    ),
                    width="stretch",
                    config=chart_config(f"overview_{slug}"),
                )
                tcols = st.columns(3)
                for tcol, (tlabel, tvalue, tnote, ttone) in zip(tcols, tiles):
                    tcol.markdown(
                        c.tile(tlabel, tvalue, note=tnote, tone=ttone),
                        unsafe_allow_html=True,
                    )
                if st.button("Expand", key=f"btn_expand_{slug}", width="stretch"):
                    st.session_state["ov_modal"] = slug

    def _render_cloud_communication(self) -> None:
        data = self.store.data_sent_to_cloud()
        escalations = self.store.cloud_escalations()

        with c.panel(
            "Cloud Communication",
            "edge → cloud data transfer",
            key="ov_cloud_comm",
        ):
            row = st.columns([1.6, 1, 1])
            row[0].markdown(
                c.tile(
                    "Total data sent to cloud",
                    c.format_bytes(data),
                    note="escalated anomaly windows",
                    tone="accent",
                    icon="↑",
                ),
                unsafe_allow_html=True,
            )
            row[1].markdown(
                c.tile(
                    "Cloud escalations",
                    c.format_count(escalations),
                    note="anomaly windows escalated",
                    tone="info",
                    icon="Σ",
                ),
                unsafe_allow_html=True,
            )
            row[2].markdown(
                c.tile(
                    "Measurement window",
                    self.store.measurement_window(),
                    note=f"since {self.store.uptime_str()}",
                    tone="info",
                    icon="◷",
                ),
                unsafe_allow_html=True,
            )
            st.caption(
                "Units are auto-scaled (KB / MB / GB) and measured over the "
                "visible window so the value always has context."
            )

    def _render_runtime_summary(self) -> None:
        with c.panel(
            "Runtime Summary",
            "platform counters",
            key="ov_runtime_summary",
        ):
            risk = self.store.current_risk() or "—"
            risk_tone = {
                "LOW": "run",
                "MEDIUM": "pause",
                "HIGH": "stop",
            }.get(risk, "info")

            queue = self.store.queue_depth()
            queue_tone = "stop" if queue >= 10 else ("pause" if queue > 0 else "info")

            row = st.columns(4)
            row[0].markdown(
                c.tile(
                    "Total diagnosis requests",
                    c.format_count(self.store.diagnosis_requests()),
                    note="batches processed",
                    tone="accent",
                    icon="Σ",
                ),
                unsafe_allow_html=True,
            )
            row[1].markdown(
                c.tile(
                    "Total cloud escalations",
                    c.format_count(self.store.cloud_escalations()),
                    note="windows escalated",
                    tone="info",
                    icon="↑",
                ),
                unsafe_allow_html=True,
            )
            row[2].markdown(
                c.tile(
                    "Current queue depth",
                    f"{queue}",
                    note="pending diagnosis jobs",
                    tone=queue_tone,
                    icon="≡",
                ),
                unsafe_allow_html=True,
            )
            row[3].markdown(
                c.tile(
                    "Current risk state",
                    risk,
                    note="orchestrator decision",
                    tone=risk_tone,
                    icon="⚠",
                ),
                unsafe_allow_html=True,
            )

    # ------------------------------------------------------------------ #
    # modal dispatch
    # ------------------------------------------------------------------ #

    def _dispatch_modal(self) -> None:
        slug = st.session_state.get("ov_modal")
        if not slug:
            return

        lat = self.store.recent_latencies()
        runtime = self.store.runtime_series()

        builders = {
            "det_diag_latency": lambda: dual_latency_figure(
                _latency_df(lat["detection"]),
                _latency_df(lat["diagnosis"]),
                x_range=_recent_window(lat["detection"], lat["diagnosis"]),
            ),
            "detection_latency": lambda: latency_figure(
                _latency_df(lat["detection"]),
                color="#39b6e8",
                y_title="detection latency (ms)",
                x_range=_recent_window(lat["detection"]),
            ),
            "diagnosis_latency": lambda: latency_figure(
                _latency_df(lat["diagnosis"]),
                color="#8b7cf6",
                y_title="diagnosis latency (ms)",
                x_range=_recent_window(lat["diagnosis"]),
            ),
            "e2e_latency": lambda: latency_figure(
                _latency_df(lat["e2e"]),
                color="#2ec27e",
                y_title="latency (ms)",
                x_range=_recent_window(lat["e2e"]),
            ),
            "cpu_usage": lambda: dual_resource_figure(
                _series_df(runtime["edge"]["cpu"]),
                _series_df(runtime["cloud"]["cpu"]),
                y_title="CPU usage (%)",
                        name_edge="Detector",
                color_edge=EDGE_CPU_COLOR,
                        name_cloud="Classifier",
                color_cloud=CLOUD_CPU_COLOR,
                x_range=_x_range(runtime["edge"]["cpu"], runtime["cloud"]["cpu"]),
            ),
            "memory_usage": lambda: dual_resource_figure(
                _series_df(runtime["edge"]["memory"], scale=_MB),
                _series_df(runtime["cloud"]["memory"], scale=_MB),
                y_title="memory usage (MB)",
                name_edge="Detector",
                color_edge=EDGE_MEM_COLOR,
                name_cloud="Classifier",
                color_cloud=CLOUD_MEM_COLOR,
                x_range=_x_range(runtime["edge"]["memory"], runtime["cloud"]["memory"]),
            ),
            "cpu_usage_edge": lambda: resource_figure(
                _series_df(runtime["edge"]["cpu"]),
                y_title="CPU usage (%)",
                color=EDGE_CPU_COLOR,
                        name="Detector",
                x_range=_x_range(runtime["edge"]["cpu"], runtime["cloud"]["cpu"]),
            ),
            "cpu_usage_cloud": lambda: resource_figure(
                _series_df(runtime["cloud"]["cpu"]),
                y_title="CPU usage (%)",
                color=CLOUD_CPU_COLOR,
                        name="Classifier",
                x_range=_x_range(runtime["edge"]["cpu"], runtime["cloud"]["cpu"]),
            ),
            "memory_usage_edge": lambda: resource_figure(
                _series_df(runtime["edge"]["memory"], scale=_MB),
                y_title="memory usage (MB)",
                color=EDGE_MEM_COLOR,
                        name="Detector",
                x_range=_x_range(runtime["edge"]["memory"], runtime["cloud"]["memory"]),
            ),
            "memory_usage_cloud": lambda: resource_figure(
                _series_df(runtime["cloud"]["memory"], scale=_MB),
                y_title="memory usage (MB)",
                color=CLOUD_MEM_COLOR,
                        name="Classifier",
                x_range=_x_range(runtime["edge"]["memory"], runtime["cloud"]["memory"]),
            ),
        }

        titles = {
            "det_diag_latency": "Detection & Diagnosis Latency",
            "detection_latency": "Detection Latency",
            "diagnosis_latency": "Diagnosis Latency",
            "e2e_latency": "End-to-End Latency",
            "cpu_usage": "CPU Usage",
            "memory_usage": "Memory Usage",
            "cpu_usage_edge": "Detector CPU Usage",
            "cpu_usage_cloud": "Classifier CPU Usage",
            "memory_usage_edge": "Detector Memory Usage",
            "memory_usage_cloud": "Classifier Memory Usage",
        }

        builder = builders.get(slug)
        if builder is None:
            return
        _chart_dialog(slug, titles.get(slug, slug), builder)

    # ------------------------------------------------------------------ #
    # entry point
    # ------------------------------------------------------------------ #

    @st.fragment(run_every=0.5)
    def render(self) -> None:
        self._render_header()

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

        self._render_overview_cards()

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        mode = st.segmented_control(
            "Graph layout",
            options=["Separate", "Overlay"],
            default="Separate",
            key="ov_graph_mode",
        )

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

        self._render_latency_section(mode)

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        self._render_resource_section(
            mode,
            title="CPU Usage",
            meta="detector · classifier",
            y_title="CPU usage (%)",
            unit_scale=1.0,
            color_edge=EDGE_CPU_COLOR,
            color_cloud=CLOUD_CPU_COLOR,
            fmt=_fmt_pct,
            key="cpu",
        )

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        self._render_resource_section(
            mode,
            title="Memory Usage",
            meta="detector · classifier",
            y_title="memory usage (MB)",
            unit_scale=_MB,
            color_edge=EDGE_MEM_COLOR,
            color_cloud=CLOUD_MEM_COLOR,
            fmt=_fmt_mb,
            key="memory",
        )

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        self._render_cloud_communication()

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        self._render_runtime_summary()

        self._dispatch_modal()


def slugify(title: str) -> str:
    return title.lower().replace(" ", "_")
