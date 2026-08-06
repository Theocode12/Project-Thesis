"""Design tokens and visual language for the Edge-Cloud console.

This module is the shared foundation for every service dashboard
(sensor generator, MQTT broker, edge detection, cloud diagnosis,
orchestrator). New service views should reuse the tokens and component
classes defined here instead of inventing their own styling.
"""

MONO = (
    "'Cascadia Mono', 'JetBrains Mono', 'IBM Plex Mono', 'Consolas', "
    "'SFMono-Regular', 'Menlo', monospace"
)

SANS = (
    "'Inter', 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
)

COLORS = {
    "bg": "#0b0f14",
    "bg_alt": "#0e131a",
    "panel": "#11161d",
    "panel_alt": "#151c25",
    "panel_hover": "#18212c",
    "border": "#1d2731",
    "border_strong": "#2b3a48",
    "text": "#e8eef5",
    "text_secondary": "#93a1b1",
    "text_muted": "#5c6b7a",
    "accent": "#ffb020",
    "run": "#2ec27e",
    "pause": "#f5a623",
    "stop": "#ef4e4e",
    "info": "#39b6e8",
    "violet": "#8b7cf6",
    "grid": "#1a222c",
    "overlay": "rgba(11, 15, 20, 0.72)",
}

STATUS_KINDS = {
    "run": COLORS["run"],
    "pause": COLORS["pause"],
    "stop": COLORS["stop"],
    "info": COLORS["info"],
    "fault": COLORS["stop"],
    "mqtt": COLORS["info"],
    "interval": COLORS["pause"],
    "stream": COLORS["run"],
    "detect": COLORS["stop"],
}

CSS = f"""
:root {{
    --edge-bg: {COLORS["bg"]};
    --edge-bg-alt: {COLORS["bg_alt"]};
    --edge-panel: {COLORS["panel"]};
    --edge-panel-alt: {COLORS["panel_alt"]};
    --edge-border: {COLORS["border"]};
    --edge-border-strong: {COLORS["border_strong"]};
    --edge-text: {COLORS["text"]};
    --edge-text-2: {COLORS["text_secondary"]};
    --edge-text-3: {COLORS["text_muted"]};
    --edge-accent: {COLORS["accent"]};
    --edge-run: {COLORS["run"]};
    --edge-pause: {COLORS["pause"]};
    --edge-stop: {COLORS["stop"]};
    --edge-info: {COLORS["info"]};
    --edge-mono: {MONO};
    --edge-sans: {SANS};
}}

html, body, [data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] .main {{
    background-color: var(--edge-bg);
    color: var(--edge-text);
    font-family: var(--edge-sans);
}}

[data-testid="stHeader"] {{
    background: transparent;
}}

.block-container {{
    padding-top: 1.4rem;
    padding-bottom: 2.5rem;
    max-width: 1500px;
}}

/* ---------- service rail ---------- */

.edge-rail {{
    border-right: 1px solid var(--edge-border);
    background: linear-gradient(180deg, var(--edge-bg-alt), var(--edge-bg));
    height: 100%;
}}

.edge-rail-brand {{
    font-family: var(--edge-mono);
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--edge-text);
    padding: 0.9rem 1rem 0.4rem 1rem;
}}

.edge-rail-brand span {{
    color: var(--edge-accent);
}}

.edge-rail-sub {{
    font-size: 0.7rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--edge-text-3);
    padding: 0 1rem 0.9rem 1rem;
}}

/* ---------- page header ---------- */

.edge-pagehead {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
    padding: 0.15rem 0 0.7rem 0;
}}

.edge-pagehead-title {{
    font-size: 1.05rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: var(--edge-text);
    display: flex;
    align-items: center;
    gap: 0.55rem;
}}

.edge-pagehead-title .edge-glyph {{
    font-family: var(--edge-mono);
    color: var(--edge-accent);
    font-weight: 700;
}}

.edge-pagehead-sub {{
    font-size: 0.74rem;
    color: var(--edge-text-3);
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-top: 0.2rem;
}}

.edge-hud {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
}}

/* ---------- badges / pills ---------- */

.edge-badge {{
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    border: 1px solid var(--edge-border-strong);
    border-radius: 4px;
    background: var(--edge-panel);
    padding: 0.3rem 0.65rem;
    font-family: var(--edge-mono);
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--edge-text-2);
    white-space: nowrap;
}}

.edge-badge .edge-key {{
    color: var(--edge-text-3);
}}

.edge-badge--accent {{
    color: var(--edge-accent);
    border-color: var(--edge-accent);
}}

.edge-pill {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    border-radius: 999px;
    padding: 0.32rem 0.85rem;
    font-family: var(--edge-mono);
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    border: 1px solid;
}}

.edge-pill .edge-led {{
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 8px 1px currentColor;
}}

/* ---------- status LED ---------- */

.edge-led {{
    display: inline-block;
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 50%;
    flex: none;
}}

.edge-led--run {{ background: var(--edge-run); box-shadow: 0 0 8px 1px var(--edge-run); }}
.edge-led--pause {{ background: var(--edge-pause); box-shadow: 0 0 8px 1px var(--edge-pause); }}
.edge-led--stop {{ background: var(--edge-stop); box-shadow: 0 0 8px 1px var(--edge-stop); }}
.edge-led--info {{ background: var(--edge-info); box-shadow: 0 0 8px 1px var(--edge-info); }}

.edge-pill--run {{ color: var(--edge-run); border-color: var(--edge-run); background: rgba(46, 194, 126, 0.08); }}
.edge-pill--pause {{ color: var(--edge-pause); border-color: var(--edge-pause); background: rgba(245, 166, 35, 0.08); }}
.edge-pill--stop {{ color: var(--edge-stop); border-color: var(--edge-stop); background: rgba(239, 78, 78, 0.08); }}
.edge-pill--info {{ color: var(--edge-info); border-color: var(--edge-info); background: rgba(57, 182, 232, 0.08); }}

/* ---------- metric tiles ---------- */

.edge-tile {{
    border: 1px solid var(--edge-border);
    border-radius: 6px;
    background: var(--edge-panel);
    padding: 0.7rem 0.85rem 0.75rem 0.85rem;
    min-height: 4.6rem;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 0.3rem;
}}

.edge-tile:hover {{
    border-color: var(--edge-border-strong);
    background: var(--edge-panel-hover, #18212c);
}}

.edge-tile-head {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.4rem;
}}

.edge-tile-label {{
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--edge-text-3);
}}

.edge-tile-icon {{
    font-size: 0.6rem;
    color: var(--edge-text-3);
    font-family: var(--edge-mono);
}}

.edge-tile-value {{
    font-family: var(--edge-mono);
    font-size: 1.45rem;
    font-weight: 700;
    line-height: 1.05;
    color: var(--edge-text);
    letter-spacing: -0.02em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.edge-tile-value small {{
    font-size: 0.78rem;
    color: var(--edge-text-3);
    font-weight: 600;
    letter-spacing: 0;
    margin-left: 0.25rem;
}}

.edge-tile-note {{
    font-size: 0.68rem;
    color: var(--edge-text-3);
    font-family: var(--edge-mono);
    letter-spacing: 0.03em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}

.edge-tile--accent {{ border-top: 2px solid var(--edge-accent); }}
.edge-tile--run {{ border-top: 2px solid var(--edge-run); }}
.edge-tile--stop {{ border-top: 2px solid var(--edge-stop); }}
.edge-tile--info {{ border-top: 2px solid var(--edge-info); }}

.edge-tile--accent .edge-tile-value {{ color: var(--edge-accent); }}
.edge-tile--run .edge-tile-value {{ color: var(--edge-run); }}
.edge-tile--stop .edge-tile-value {{ color: var(--edge-stop); }}
.edge-tile--info .edge-tile-value {{ color: var(--edge-info); }}

/* ---------- runtime metric row with sparkline ---------- */

.edge-metric {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.55rem 0.85rem;
    border: 1px solid var(--edge-border);
    border-radius: 6px;
    background: var(--edge-panel);
    margin-bottom: 0.5rem;
}}

.edge-metric:last-child {{
    margin-bottom: 0;
}}

.edge-metric-label {{
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--edge-text-3);
    margin-bottom: 0.15rem;
}}

.edge-metric-value {{
    font-family: var(--edge-mono);
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--edge-text);
    line-height: 1.1;
    white-space: nowrap;
}}

.edge-metric-value small {{
    font-size: 0.68rem;
    color: var(--edge-text-3);
    font-weight: 600;
    letter-spacing: 0;
    margin-left: 0.2rem;
}}

.edge-spark {{
    display: block;
    flex: none;
}}

/* ---------- latest diagnosis card ---------- */

.edge-diagnosis {{
    display: flex;
    flex-direction: column;
    gap: 1.15rem;
    padding: 0.4rem 0.1rem 0.2rem 0.1rem;
}}

.edge-diagnosis-main {{
    display: flex;
    align-items: center;
    gap: 1.6rem;
}}

.edge-diagnosis-fault {{
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    min-width: 8rem;
}}

.edge-diagnosis-label {{
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--edge-text-3);
}}

.edge-diagnosis-number {{
    font-family: var(--edge-mono);
    font-size: 3.4rem;
    font-weight: 700;
    line-height: 1;
    color: var(--edge-text);
    letter-spacing: -0.02em;
}}

.edge-diagnosis--run .edge-diagnosis-number {{ color: var(--edge-run); }}
.edge-diagnosis--pause .edge-diagnosis-number {{ color: var(--edge-pause); }}
.edge-diagnosis--stop .edge-diagnosis-number {{ color: var(--edge-stop); }}
.edge-diagnosis--info .edge-diagnosis-number {{ color: var(--edge-info); }}

.edge-diagnosis-detail {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.55rem;
    border-left: 1px solid var(--edge-border);
    padding-left: 1.4rem;
}}

.edge-diagnosis-row {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
}}

.edge-diagnosis-row-label {{
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--edge-text-3);
}}

.edge-diagnosis-code {{
    font-family: var(--edge-mono);
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--edge-text);
    letter-spacing: 0.02em;
}}

.edge-diagnosis-confidence {{
    font-family: var(--edge-mono);
    font-size: 1.7rem;
    font-weight: 700;
    line-height: 1;
    color: var(--edge-text);
}}

.edge-diagnosis-confidence small {{
    font-size: 0.85rem;
    color: var(--edge-text-3);
    margin-left: 0.15rem;
}}

.edge-diagnosis--run .edge-diagnosis-confidence {{ color: var(--edge-run); }}
.edge-diagnosis--pause .edge-diagnosis-confidence {{ color: var(--edge-pause); }}
.edge-diagnosis--stop .edge-diagnosis-confidence {{ color: var(--edge-stop); }}
.edge-diagnosis--info .edge-diagnosis-confidence {{ color: var(--edge-info); }}

.edge-diagnosis-time {{
    font-family: var(--edge-mono);
    font-size: 0.66rem;
    color: var(--edge-text-3);
    letter-spacing: 0.06em;
}}

.edge-diagnosis-bar {{
    height: 0.55rem;
    background: var(--edge-panel-alt);
    border: 1px solid var(--edge-border);
    border-radius: 999px;
    overflow: hidden;
}}

.edge-diagnosis-fill {{
    height: 100%;
    border-radius: 999px;
    transition: width 0.4s ease;
}}

.edge-diagnosis--run .edge-diagnosis-fill {{ background: var(--edge-run); box-shadow: 0 0 10px rgba(46, 194, 126, 0.4); }}
.edge-diagnosis--pause .edge-diagnosis-fill {{ background: var(--edge-pause); box-shadow: 0 0 10px rgba(245, 166, 35, 0.4); }}
.edge-diagnosis--stop .edge-diagnosis-fill {{ background: var(--edge-stop); box-shadow: 0 0 10px rgba(239, 78, 78, 0.4); }}
.edge-diagnosis--info .edge-diagnosis-fill {{ background: var(--edge-info); }}

.edge-diagnosis-empty {{
    padding: 1.6rem 1rem;
    text-align: center;
    color: var(--edge-text-3);
    font-family: var(--edge-mono);
    font-size: 0.78rem;
}}

/* ---------- panels ---------- */

.edge-panel {{
    border: 1px solid var(--edge-border);
    border-radius: 6px;
    background: var(--edge-panel);
    overflow: hidden;
}}

.edge-panel-head {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    padding: 0.55rem 0.9rem;
    border-bottom: 1px solid var(--edge-border);
    background: var(--edge-panel-alt);
}}

.edge-panel-title {{
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    color: var(--edge-text-2);
    display: flex;
    align-items: center;
    gap: 0.45rem;
}}

.edge-panel-title::before {{
    content: "";
    width: 0.3rem;
    height: 0.3rem;
    background: var(--edge-accent);
    border-radius: 50%;
}}

.edge-panel-head .edge-meta {{
    font-size: 0.66rem;
    color: var(--edge-text-3);
    font-family: var(--edge-mono);
    letter-spacing: 0.05em;
}}

.edge-panel-body {{
    padding: 0.9rem;
}}

/* Container-based panels: native Streamlit widgets wrapped in a themed box.
   These panel regions render inside a keyed st.container(border=True), which
   emits an [data-testid="stVerticalBlockBorderWrapper"]. The :has() rule
   draws the themed box around any container whose first child is the panel
   head, so it applies to every panel region without per-key selectors. */
[data-testid="stVerticalBlockBorderWrapper"]:has(.edge-panel-head) {{
    border: 1px solid var(--edge-border) !important;
    border-radius: 6px;
    background: var(--edge-panel);
    overflow: hidden;
}}

[data-testid="stVerticalBlockBorderWrapper"]:has(.edge-panel-head)
    [data-testid="stVerticalBlock"] {{
    padding: 0.9rem;
    row-gap: 0.55rem;
}}

[data-testid="stVerticalBlockBorderWrapper"]:has(.edge-panel-head)
    [data-testid="stVerticalBlock"]
    .edge-panel-head {{
    margin: -0.9rem -0.9rem 0.9rem -0.9rem;
    border-bottom: 1px solid var(--edge-border);
}}

/* ---------- misc ---------- */

.edge-divider {{
    height: 1px;
    background: var(--edge-border);
    margin: 0.1rem 0;
}}

/* ---------- event timeline ---------- */

.edge-events {{
    display: flex;
    flex-direction: column;
    max-height: 22rem;
    overflow-y: auto;
}}

.edge-event {{
    display: grid;
    grid-template-columns: 5.2rem 0.6rem 1fr;
    gap: 0.6rem;
    padding: 0.42rem 0.9rem;
    border-bottom: 1px solid var(--edge-border);
    align-items: baseline;
}}

.edge-event:last-child {{
    border-bottom: none;
}}

.edge-event-time {{
    font-family: var(--edge-mono);
    font-size: 0.66rem;
    color: var(--edge-text-3);
    white-space: nowrap;
}}

.edge-event-dot {{
    width: 0.45rem;
    height: 0.45rem;
    border-radius: 50%;
    background: var(--edge-info);
    align-self: center;
}}

.edge-event--mqtt .edge-event-dot {{ background: var(--edge-info); }}
.edge-event--state .edge-event-dot {{ background: var(--edge-run); }}
.edge-event--fault .edge-event-dot {{ background: var(--edge-stop); }}
.edge-event--interval .edge-event-dot {{ background: var(--edge-pause); }}
.edge-event--stream .edge-event-dot {{ background: var(--edge-run); }}
.edge-event--detect .edge-event-dot {{ background: var(--edge-stop); }}

.edge-event-text {{
    font-size: 0.78rem;
    color: var(--edge-text-2);
    font-family: var(--edge-sans);
}}

.edge-events-empty {{
    padding: 1rem 0.9rem;
    color: var(--edge-text-3);
    font-size: 0.74rem;
    font-family: var(--edge-mono);
}}

/* ---------- banner / alert ---------- */

.edge-banner {{
    border-radius: 4px;
    border: 1px solid;
    padding: 0.55rem 0.85rem;
    font-size: 0.76rem;
    letter-spacing: 0.03em;
    color: var(--edge-text-2);
    margin: 0.25rem 0 0.5rem 0;
    font-family: var(--edge-mono);
}}

.edge-banner--warn {{
    border-color: var(--edge-pause);
    color: var(--edge-pause);
    background: rgba(245, 166, 35, 0.07);
}}

.edge-banner--error {{
    border-color: var(--edge-stop);
    color: var(--edge-stop);
    background: rgba(239, 78, 78, 0.07);
}}

/* ---------- streamlit widget reskin ---------- */

[data-testid="stSidebar"] {{
    background: var(--edge-bg-alt);
    border-right: 1px solid var(--edge-border);
}}

[data-testid="stSidebar"] .block-container {{
    padding-top: 1rem;
}}

[data-testid="stSidebar"] hr {{
    border-color: var(--edge-border);
}}

[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stRadio label {{
    color: var(--edge-text-2) !important;
}}

[data-testid="stRadio"] label {{
    font-size: 0.78rem;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    font-weight: 700;
}}

[data-testid="stRadio"] > div {{ gap: 0.15rem; }}

[data-testid="stButton"] button {{
    border-radius: 4px;
    border: 1px solid var(--edge-border-strong);
    background: var(--edge-panel-alt);
    color: var(--edge-text);
    font-family: var(--edge-mono);
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding: 0.52rem 0.35rem;
    height: 2.3rem;
    min-height: 2.3rem;
    transition: background 0.12s ease, border-color 0.12s ease;
}}

[data-testid="stButton"] button:hover {{
    border-color: var(--edge-accent);
    color: var(--edge-accent);
}}

[data-testid="stButton"] button:active {{
    background: rgba(255, 176, 32, 0.25);
    border-color: var(--edge-accent);
    color: var(--edge-accent);
}}

[data-testid="stButton"] button[kind="primary"] {{
    background: rgba(255, 176, 32, 0.12);
    border-color: var(--edge-accent);
    color: var(--edge-accent);
}}

[data-testid="stButton"] button[kind="primary"]:hover {{
    background: rgba(255, 176, 32, 0.2);
}}

[data-baseweb="select"] > div {{
    background: var(--edge-panel-alt) !important;
    border-color: var(--edge-border-strong) !important;
}}

[data-baseweb="select"] div {{
    color: var(--edge-text) !important;
    font-family: var(--edge-mono);
    font-size: 0.76rem;
}}

[data-baseweb="select"] [data-testid="stSelectboxLabel"] p {{
    color: var(--edge-text-2);
}}

[data-testid="stSelectbox"] label p,
[data-testid="stMultiSelect"] label p,
[data-testid="stSlider"] label p {{
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--edge-text-3);
}}

[data-testid="stSlider"] [data-baseweb="slider"] div {{
    background: var(--edge-border-strong);
}}

[data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {{
    background: var(--edge-accent);
    border-color: var(--edge-accent);
}}

[data-testid="stMultiSelect"] [data-baseweb="tag"] {{
    background: rgba(255, 176, 32, 0.14) !important;
    color: var(--edge-accent) !important;
    border-radius: 3px !important;
    font-family: var(--edge-mono);
    font-size: 0.7rem;
}}

[data-testid="stPopoverButton"] {{
    background: var(--edge-panel-alt);
    border: 1px solid var(--edge-border-strong);
    border-radius: 4px;
    color: var(--edge-text-2);
    font-family: var(--edge-mono);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}}

[data-testid="stHorizontalBlock"] {{ gap: 0.8rem; }}

[data-testid="stExpander"] details {{
    background: var(--edge-panel);
    border: 1px solid var(--edge-border);
    border-radius: 6px;
}}

[data-testid="stExpander"] summary {{
    color: var(--edge-text-2);
    font-family: var(--edge-mono);
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}}

[data-testid="stCaptionContainer"] p {{
    color: var(--edge-text-3);
    font-size: 0.7rem;
}}

section[data-testid="stMainBlockContainer"] > div:first-child > div:first-child > div {{
    border: none;
}}
"""


def inject() -> None:
    import streamlit as st

    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def status_color(kind: str) -> str:
    return STATUS_KINDS.get(kind, COLORS["info"])
