"""
Cyberpunk Neon theme for the Toggl Time Journal.

Call apply_theme() at the top of every page to inject CSS and register
the custom Plotly template. Idempotent -- safe to call multiple times.
"""

import streamlit as st
import plotly.io as pio
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Color palette -- single source of truth
# ---------------------------------------------------------------------------
COLORS = {
    "bg":           "#0a0a1a",
    "bg2":          "#12122a",
    "bg3":          "#1a1a3e",
    "cyan":         "#00fff9",
    "magenta":      "#ff00ff",
    "green":        "#39ff14",
    "purple":       "#bc13fe",
    "pink":         "#ff2079",
    "gold":         "#ffd700",
    "amber":        "#ff9800",
    "red":          "#ff3131",
    "text":         "#e0e0ff",
    "text_muted":   "#7878a8",
    "grid":         "#1e1e4a",
    "border":       "#2a2a5a",
}

# Categorical color sequence for Plotly charts (cycling)
NEON_SEQUENCE = [
    COLORS["cyan"],
    COLORS["magenta"],
    COLORS["green"],
    COLORS["purple"],
    COLORS["pink"],
    COLORS["gold"],
    COLORS["amber"],
    COLORS["red"],
    "#00b4d8",   # softer cyan
    "#e040fb",   # softer magenta
    "#76ff03",   # lime
    "#7c4dff",   # deep purple
    "#18ffff",   # light cyan
    "#ff6e40",   # deep orange
    "#eeff41",   # yellow-green
    "#ea80fc",   # light purple
]

# Continuous color scales for intensity charts
SCALE_CYAN_MAGENTA = [
    [0.0, "#0a0a1a"],
    [0.2, "#0d2d5e"],
    [0.4, "#1a5276"],
    [0.6, "#00b4d8"],
    [0.8, "#00fff9"],
    [1.0, "#ff00ff"],
]

SCALE_NEON_HEATMAP = [
    [0.0, "#0a0a1a"],
    [0.15, "#0d1b3e"],
    [0.3, "#0d3d6b"],
    [0.5, "#00778a"],
    [0.7, "#00c9b7"],
    [0.85, "#00fff9"],
    [1.0, "#39ff14"],
]

SCALE_MAGENTA_FIRE = [
    [0.0, "#0a0a1a"],
    [0.25, "#3d0a5e"],
    [0.5, "#8a0e7b"],
    [0.75, "#ff00ff"],
    [1.0, "#ff2079"],
]

SCALE_CYAN_MONO = [
    [0.0, "#0a0a1a"],
    [0.25, "#0a2a3a"],
    [0.5, "#0d5e7a"],
    [0.75, "#00b4d8"],
    [1.0, "#00fff9"],
]

SCALE_PURPLE_GOLD = [
    [0.0, "#0a0a1a"],
    [0.25, "#2a0a5e"],
    [0.5, "#bc13fe"],
    [0.75, "#ff9800"],
    [1.0, "#ffd700"],
]


# ---------------------------------------------------------------------------
# CSS injection
# ---------------------------------------------------------------------------
_NEON_CSS = f"""
<style>
/* ===== GLOBAL ===== */
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');

html, body, [class*="css"] {{
    font-family: 'Share Tech Mono', monospace !important;
}}

/* ===== HEADER BAR ===== */
header[data-testid="stHeader"] {{
    background: linear-gradient(180deg, {COLORS["bg"]} 0%, transparent 100%) !important;
    backdrop-filter: blur(8px);
}}

/* ===== MAIN AREA ===== */
.stApp {{
    background: radial-gradient(ellipse at 20% 50%, #0d1b3e 0%, {COLORS["bg"]} 70%) !important;
}}

/* subtle scan-line overlay */
.stApp::before {{
    content: "";
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(0, 255, 249, 0.015) 2px,
        rgba(0, 255, 249, 0.015) 4px
    );
    pointer-events: none;
    z-index: 999;
}}

/* ===== SIDEBAR ===== */
section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {COLORS["bg2"]} 0%, {COLORS["bg"]} 100%) !important;
    border-right: 1px solid {COLORS["cyan"]}44 !important;
    box-shadow: 2px 0 20px {COLORS["cyan"]}15;
}}

section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stSelectbox label {{
    color: {COLORS["cyan"]} !important;
    text-shadow: 0 0 6px {COLORS["cyan"]}66;
}}

/* ===== HEADINGS ===== */
h1 {{
    color: {COLORS["cyan"]} !important;
    text-shadow:
        0 0 7px {COLORS["cyan"]}88,
        0 0 20px {COLORS["cyan"]}44,
        0 0 40px {COLORS["cyan"]}22 !important;
    letter-spacing: 2px !important;
    border-bottom: 1px solid {COLORS["cyan"]}33;
    padding-bottom: 10px !important;
}}

h2 {{
    color: {COLORS["magenta"]} !important;
    text-shadow:
        0 0 7px {COLORS["magenta"]}88,
        0 0 15px {COLORS["magenta"]}33 !important;
    letter-spacing: 1px !important;
}}

h3 {{
    color: {COLORS["green"]} !important;
    text-shadow: 0 0 7px {COLORS["green"]}66 !important;
}}

h4 {{
    color: {COLORS["purple"]} !important;
    text-shadow: 0 0 5px {COLORS["purple"]}66 !important;
}}

/* ===== METRICS ===== */
[data-testid="stMetric"] {{
    background: linear-gradient(135deg, {COLORS["bg2"]} 0%, {COLORS["bg3"]} 100%) !important;
    border: 1px solid {COLORS["cyan"]}33 !important;
    border-radius: 8px !important;
    padding: 16px !important;
    box-shadow:
        0 0 10px {COLORS["cyan"]}15,
        inset 0 0 20px {COLORS["bg"]}88 !important;
    transition: box-shadow 0.3s ease, border-color 0.3s ease;
}}

[data-testid="stMetric"]:hover {{
    border-color: {COLORS["cyan"]}88 !important;
    box-shadow:
        0 0 20px {COLORS["cyan"]}30,
        0 0 40px {COLORS["cyan"]}10,
        inset 0 0 20px {COLORS["bg"]}88 !important;
}}

[data-testid="stMetric"] label {{
    color: {COLORS["text_muted"]} !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    font-size: 0.75rem !important;
}}

[data-testid="stMetric"] [data-testid="stMetricValue"] {{
    color: {COLORS["cyan"]} !important;
    text-shadow: 0 0 10px {COLORS["cyan"]}55 !important;
    font-size: 1.8rem !important;
}}

[data-testid="stMetric"] [data-testid="stMetricDelta"] {{
    color: {COLORS["green"]} !important;
}}

/* ===== BUTTONS ===== */
.stButton > button {{
    background: transparent !important;
    color: {COLORS["cyan"]} !important;
    border: 1px solid {COLORS["cyan"]}66 !important;
    border-radius: 4px !important;
    text-transform: uppercase !important;
    letter-spacing: 1.5px !important;
    font-family: 'Share Tech Mono', monospace !important;
    transition: all 0.3s ease !important;
    text-shadow: 0 0 5px {COLORS["cyan"]}44;
}}

.stButton > button:hover {{
    background: {COLORS["cyan"]}15 !important;
    border-color: {COLORS["cyan"]} !important;
    box-shadow: 0 0 15px {COLORS["cyan"]}33, inset 0 0 15px {COLORS["cyan"]}11 !important;
    text-shadow: 0 0 8px {COLORS["cyan"]}88;
}}

.stButton > button:active {{
    background: {COLORS["cyan"]}25 !important;
    box-shadow: 0 0 25px {COLORS["cyan"]}55 !important;
}}

/* ===== EXPANDERS ===== */
[data-testid="stExpander"] {{
    background: {COLORS["bg2"]} !important;
    border: 1px solid {COLORS["border"]} !important;
    border-radius: 6px !important;
    box-shadow: 0 0 8px {COLORS["purple"]}10;
    transition: border-color 0.3s ease;
}}

[data-testid="stExpander"]:hover {{
    border-color: {COLORS["purple"]}66 !important;
}}

[data-testid="stExpander"] summary {{
    color: {COLORS["purple"]} !important;
}}

/* ===== DATAFRAMES ===== */
[data-testid="stDataFrame"] {{
    border: 1px solid {COLORS["border"]} !important;
    border-radius: 6px !important;
    overflow: hidden;
}}

/* ===== TABS ===== */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0px;
    border-bottom: 1px solid {COLORS["border"]} !important;
}}

.stTabs [data-baseweb="tab"] {{
    color: {COLORS["text_muted"]} !important;
    border-bottom: 2px solid transparent;
    padding: 8px 20px !important;
    font-family: 'Share Tech Mono', monospace !important;
    transition: all 0.2s ease;
}}

.stTabs [data-baseweb="tab"]:hover {{
    color: {COLORS["cyan"]} !important;
    text-shadow: 0 0 5px {COLORS["cyan"]}44;
}}

.stTabs [aria-selected="true"] {{
    color: {COLORS["cyan"]} !important;
    border-bottom: 2px solid {COLORS["cyan"]} !important;
    text-shadow: 0 0 8px {COLORS["cyan"]}66 !important;
    box-shadow: 0 2px 10px {COLORS["cyan"]}22;
}}

/* ===== CHAT ===== */
[data-testid="stChatMessage"] {{
    background: {COLORS["bg2"]} !important;
    border: 1px solid {COLORS["border"]} !important;
    border-radius: 8px !important;
}}

.stChatInputContainer {{
    border-color: {COLORS["cyan"]}44 !important;
}}

/* ===== SELECTBOX / INPUTS ===== */
.stSelectbox [data-baseweb="select"],
.stTextInput input,
.stDateInput input {{
    background-color: {COLORS["bg2"]} !important;
    border-color: {COLORS["border"]} !important;
    color: {COLORS["text"]} !important;
    font-family: 'Share Tech Mono', monospace !important;
}}

.stSelectbox [data-baseweb="select"]:focus-within,
.stTextInput input:focus,
.stDateInput input:focus {{
    border-color: {COLORS["cyan"]} !important;
    box-shadow: 0 0 8px {COLORS["cyan"]}33 !important;
}}

/* ===== PROGRESS BAR ===== */
.stProgress > div > div {{
    background: linear-gradient(90deg, {COLORS["cyan"]}, {COLORS["magenta"]}) !important;
    box-shadow: 0 0 10px {COLORS["cyan"]}44;
}}

/* ===== ALERTS / INFO BOXES ===== */
.stAlert {{
    background: {COLORS["bg2"]} !important;
    border-left: 4px solid {COLORS["cyan"]} !important;
    color: {COLORS["text"]} !important;
}}

/* ===== SCROLLBAR ===== */
::-webkit-scrollbar {{
    width: 8px;
    height: 8px;
}}
::-webkit-scrollbar-track {{
    background: {COLORS["bg"]};
}}
::-webkit-scrollbar-thumb {{
    background: {COLORS["border"]};
    border-radius: 4px;
}}
::-webkit-scrollbar-thumb:hover {{
    background: {COLORS["cyan"]}66;
    box-shadow: 0 0 6px {COLORS["cyan"]}33;
}}

/* ===== DIVIDERS ===== */
hr {{
    border-color: {COLORS["cyan"]}22 !important;
    box-shadow: 0 0 5px {COLORS["cyan"]}11;
}}

/* ===== MARKDOWN BOLD/LINKS ===== */
strong, b {{
    color: {COLORS["cyan"]} !important;
}}

a {{
    color: {COLORS["magenta"]} !important;
    text-shadow: 0 0 4px {COLORS["magenta"]}44;
}}

a:hover {{
    color: {COLORS["pink"]} !important;
    text-shadow: 0 0 8px {COLORS["pink"]}66;
}}
</style>
"""


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------
def _build_plotly_template() -> go.layout.Template:
    """Build a cyberpunk-neon Plotly template."""
    return go.layout.Template(
        layout=go.Layout(
            font=dict(family="Share Tech Mono, monospace", color=COLORS["text"], size=12),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(10,10,26,0.6)",
            title=dict(font=dict(color=COLORS["cyan"], size=16)),
            xaxis=dict(
                gridcolor=COLORS["grid"],
                linecolor=COLORS["border"],
                zerolinecolor=COLORS["border"],
                tickfont=dict(color=COLORS["text_muted"]),
                title=dict(font=dict(color=COLORS["text_muted"])),
            ),
            yaxis=dict(
                gridcolor=COLORS["grid"],
                linecolor=COLORS["border"],
                zerolinecolor=COLORS["border"],
                tickfont=dict(color=COLORS["text_muted"]),
                title=dict(font=dict(color=COLORS["text_muted"])),
            ),
            legend=dict(
                bgcolor="rgba(0,0,0,0)",
                font=dict(color=COLORS["text_muted"]),
                bordercolor=COLORS["border"],
                borderwidth=1,
            ),
            colorway=NEON_SEQUENCE,
            hoverlabel=dict(
                bgcolor=COLORS["bg2"],
                bordercolor=COLORS["cyan"],
                font=dict(color=COLORS["text"], family="Share Tech Mono, monospace"),
            ),
        )
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
_theme_applied = False


def apply_theme():
    """Inject CSS and register Plotly template. Call once per page."""
    global _theme_applied
    st.markdown(_NEON_CSS, unsafe_allow_html=True)

    if not _theme_applied:
        template = _build_plotly_template()
        pio.templates["cyberpunk"] = template
        pio.templates.default = "cyberpunk"
        _theme_applied = True


def neon_chart_layout(fig: go.Figure, height: int = 400) -> go.Figure:
    """Apply common neon layout tweaks to any Plotly figure."""
    fig.update_layout(
        height=height,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=True,
    )
    return fig
