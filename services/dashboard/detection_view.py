"""Edge Detection service console.

Displays anomalies reported by the edge detector on ``anomaly/detected``:
latest detection, running totals and a per-view action log. Read-only for
now; command controls can be added later behind a controller.
"""

from datetime import UTC, datetime

import pandas as pd
import streamlit as st

import components as c
from detection_store import DetectionStore
from mqtt_client import DashboardClient

METRIC_LABELS = {
    "reconstruction_error": "Reconstruction error",
    "z_score": "Z-score",
}


def _fmt_time(ts: float | None) -> str:
    if ts is None:
        return "—"
    return datetime.fromtimestamp(ts, UTC).strftime("%H:%M:%S")


def detections_dataframe(detections: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame([
        {
            "t": detection["t"],
            "metric": detection.get("metric") or "—",
            "value": detection.get("value"),
            "reason": detection.get("reason") or "",
            "fault": detection.get("fault"),
            "run": detection.get("run"),
        }
        for detection in detections
    ])
    if not df.empty:
        df["t"] = pd.to_datetime(df["t"], unit="s")
    return df


class DetectionView:

    def __init__(
        self,
        store: DetectionStore,
        client: DashboardClient,
    ) -> None:
        self.store = store
        self.client = client

    def _render_metrics(self, latest: dict | None) -> None:
        connected = self.client.is_connected()
        count = len(self.store.recent_detections())

        metric = (latest or {}).get("metric")
        value = (latest or {}).get("value")
        reason = (latest or {}).get("reason")

        row1 = st.columns(4)
        row1[0].markdown(
            c.tile(
                "Detector state",
                "ARMED" if connected else "DOWN",
                note="anomaly/detected",
                tone="run" if connected else "stop",
                icon="◎",
            ),
            unsafe_allow_html=True,
        )
        row1[1].markdown(
            c.tile(
                "Anomalies detected",
                c.format_count(count),
                note="since dashboard start",
                tone="accent",
                icon="Σ",
            ),
            unsafe_allow_html=True,
        )
        row1[2].markdown(
            c.tile(
                "Latest metric",
                str(metric).upper() if metric else "—",
                note=reason or "no detections yet",
                tone="stop" if latest else "",
                icon="▣",
            ),
            unsafe_allow_html=True,
        )
        row1[3].markdown(
            c.tile(
                "Latest value",
                f"{value:.4g}" if value is not None else "—",
                note=_fmt_time((latest or {}).get("t")),
                tone="stop" if latest else "",
                icon="≈",
            ),
            unsafe_allow_html=True,
        )

    @st.fragment(run_every=0.5)
    def _render_live(self) -> None:
        latest = self.store.latest_detection()
        connected = self.client.is_connected()

        hud = [
            c.pill(
                "MQTT " + ("LIVE" if connected else "DOWN"),
                "run" if connected else "stop",
            ),
            c.badge(
                "Detections",
                str(len(self.store.recent_detections())),
                accent=latest is not None,
            ),
        ]

        st.markdown(
            c.page_head(
                "Edge Detection",
                "Autoencoder anomaly monitoring · Edge–Cloud Inference Orchestration",
                "ED",
                hud,
            ),
            unsafe_allow_html=True,
        )

        if not connected:
            st.markdown(
                '<div class="edge-banner edge-banner--warn">'
                "No live MQTT traffic detected — broker unreachable or "
                "detector silent."
                "</div>",
                unsafe_allow_html=True,
            )

        self._render_metrics(latest)

    @st.fragment(run_every=0.5)
    def _render_detections(self) -> None:
        detections = self.store.recent_detections()
        st.markdown(
            c.panel_open("Recent Detections", "anomaly/detected"),
            unsafe_allow_html=True,
        )
        if not detections:
            st.markdown(
                '<div class="edge-events-empty">No anomalies reported yet.</div>',
                unsafe_allow_html=True,
            )
        else:
            df = detections_dataframe(detections[-20:])
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
            )
        st.markdown(c.panel_close(), unsafe_allow_html=True)

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

    def render(self) -> None:
        self._render_live()

        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        self._render_detections()

        st.markdown("<div style='height:0.75rem'></div>", unsafe_allow_html=True)

        self._render_timeline()
