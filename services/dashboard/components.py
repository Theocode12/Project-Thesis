"""Reusable dashboard components built on the Edge-Cloud design tokens.

Each render function emits self-contained HTML that is pushed through
``st.markdown(unsafe_allow_html=True)``. Components are intentionally
stateless so any service view can compose them.
"""

import html
import time
from datetime import datetime, UTC

from theme import STATUS_KINDS

_ESCAPE = html.escape


def _kind(kind: str) -> str:
    return kind if kind in STATUS_KINDS else "info"


def format_count(value: int) -> str:
    if value < 1_000:
        return f"{value:,}"
    for divisor, suffix in (
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ):
        if value >= divisor:
            scaled = value / divisor
            return f"{scaled:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{value:,}"


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #

def led(kind: str) -> str:
    return f'<span class="edge-led edge-led--{_kind(kind)}"></span>'


def pill(text: str, kind: str, led_on: bool = True) -> str:
    led_html = led(kind) if led_on else ""
    return (
        f'<span class="edge-pill edge-pill--{_kind(kind)}">'
        f"{led_html}{_ESCAPE(text)}</span>"
    )


def badge(key: str, value: str, accent: bool = False) -> str:
    cls = "edge-badge edge-badge--accent" if accent else "edge-badge"
    return (
        f'<span class="{cls}">'
        f'<span class="edge-key">{_ESCAPE(key)}</span>'
        f"{_ESCAPE(value)}</span>"
    )


# --------------------------------------------------------------------------- #
# layout blocks
# --------------------------------------------------------------------------- #

def page_head(title: str, subtitle: str, glyph: str, hud: list[str]) -> str:
    hud_html = '<div class="edge-hud">' + "".join(hud) + "</div>"
    return (
        '<div class="edge-pagehead">'
        f'<div><div class="edge-pagehead-title">'
        f'<span class="edge-glyph">{_ESCAPE(glyph)}</span>'
        f"{_ESCAPE(title)}</div>"
        f'<div class="edge-pagehead-sub">{_ESCAPE(subtitle)}</div></div>'
        f"{hud_html}</div>"
    )


def tile(
    label: str,
    value: str,
    note: str = "",
    tone: str = "",
    icon: str = "●",
) -> str:
    tone_cls = f" edge-tile--{tone}" if tone else ""
    note_html = (
        f'<div class="edge-tile-note">{_ESCAPE(note)}</div>'
        if note
        else ""
    )
    return (
        '<div class="edge-tile'
        f'{tone_cls}">'
        '<div class="edge-tile-head">'
        f'<span class="edge-tile-label">{_ESCAPE(label)}</span>'
        f'<span class="edge-tile-icon">{_ESCAPE(icon)}</span>'
        "</div>"
        f'<div class="edge-tile-value">{value}</div>'
        f"{note_html}</div>"
    )


def panel_open(title: str, meta: str = "") -> str:
    meta_html = (
        f'<span class="edge-meta">{_ESCAPE(meta)}</span>' if meta else ""
    )
    return (
        '<div class="edge-panel">'
        f'<div class="edge-panel-head">'
        f'<span class="edge-panel-title">{_ESCAPE(title)}</span>'
        f"{meta_html}</div>"
        '<div class="edge-panel-body">'
    )


def panel_close() -> str:
    return "</div></div>"


# --------------------------------------------------------------------------- #
# event timeline
# --------------------------------------------------------------------------- #

def format_event_time(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%H:%M:%S")


def event_timeline(events: list[dict]) -> str:
    if not events:
        return '<div class="edge-events-empty">No events recorded yet.</div>'
    rows = []
    for event in events:
        kind = _kind(event.get("kind", "info"))
        rows.append(
            '<div class="edge-event '
            f'edge-event--{kind}">'
            f'<span class="edge-event-time">'
            f"{format_event_time(event.get('ts', time.time()))}</span>"
            f'<span class="edge-event-dot"></span>'
            f'<span class="edge-event-text">{_ESCAPE(event.get("text", ""))}'
            "</span></div>"
        )
    return '<div class="edge-events">' + "".join(rows) + "</div>"


# --------------------------------------------------------------------------- #
# runtime metric sparkline
# --------------------------------------------------------------------------- #

def sparkline(
    values: list[float],
    width: int = 96,
    height: int = 28,
    color: str = "#39b6e8",
) -> str:
    """Render a compact Grafana-style sparkline as an inline SVG.

    Returns an empty placeholder when there is no data so the metric
    tile keeps a stable height.
    """
    if not values or width < 4 or height < 4:
        return (
            f'<svg width="{width}" height="{height}" '
            'class="edge-spark edge-spark--empty" '
            f'viewBox="0 0 {width} {height}"></svg>'
        )

    numeric = [v for v in values if v is not None]
    if not numeric:
        return (
            f'<svg width="{width}" height="{height}" '
            'class="edge-spark edge-spark--empty" '
            f'viewBox="0 0 {width} {height}"></svg>'
        )

    pad = 3
    span_w = width - pad * 2
    span_h = height - pad * 2

    if len(numeric) == 1:
        lo = hi = numeric[0]
    else:
        lo = min(numeric)
        hi = max(numeric)

    if hi - lo < 1e-9:
        lo -= 0.5
        hi += 0.5

    step = span_w / (len(numeric) - 1) if len(numeric) > 1 else 0
    points = []
    for i, v in enumerate(numeric):
        x = pad + i * step
        y = pad + span_h * (1.0 - (v - lo) / (hi - lo))
        points.append(f"{x:.1f},{y:.1f}")

    stroke = f'<polyline fill="none" stroke="{color}" stroke-width="1.4" '
    stroke += f'stroke-linejoin="round" points="{" ".join(points)}"/>'
    area = f'<polygon fill="{color}" fill-opacity="0.10" '
    area += f'points="{pad},{height - pad} {" ".join(points)} '
    area += f'{width - pad},{height - pad}"/>'

    return (
        f'<svg width="{width}" height="{height}" class="edge-spark" '
        f'viewBox="0 0 {width} {height}">{area}{stroke}</svg>'
    )
