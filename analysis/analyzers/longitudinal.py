"""
Longitudinal life composition analyzer.

Answers: How has my time allocation shifted across years?
Produces stacked category composition charts, concentration index,
rolling statistics, session patterns, and active-days trends.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Cyberpunk color palette (mirrors src/theme.py without importing it)
# ---------------------------------------------------------------------------
_C = {
    "bg":       "#0a0a1a",
    "bg2":      "#12122a",
    "bg3":      "#1a1a3e",
    "cyan":     "#00fff9",
    "magenta":  "#ff00ff",
    "green":    "#39ff14",
    "purple":   "#bc13fe",
    "pink":     "#ff2079",
    "gold":     "#ffd700",
    "amber":    "#ff9800",
    "text":     "#e0e0ff",
    "muted":    "#7878a8",
    "grid":     "#1e1e4a",
    "border":   "#2a2a5a",
}

_NEON = [
    _C["cyan"], _C["magenta"], _C["green"], _C["purple"], _C["pink"],
    _C["gold"], _C["amber"], "#00b4d8", "#e040fb", "#76ff03",
    "#7c4dff", "#18ffff", "#ff6e40", "#eeff41", "#ea80fc",
    "#ff1744", "#00e5ff", "#69ff47", "#ffea00", "#ff6d00",
]

_LAYOUT = dict(
    paper_bgcolor=_C["bg"],
    plot_bgcolor=_C["bg2"],
    font=dict(color=_C["text"], family="monospace"),
    margin=dict(l=60, r=30, t=50, b=50),
)
_AXIS = dict(gridcolor=_C["grid"], zerolinecolor=_C["grid"])


def _apply_layout(fig: go.Figure, title: str = "", height: int = 420) -> go.Figure:
    fig.update_layout(**_LAYOUT, title=dict(text=title, font=dict(color=_C["cyan"])), height=height)
    return fig


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert a #rrggbb hex color string to rgba(r,g,b,alpha)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_color  # fallback: return as-is


# ---------------------------------------------------------------------------
# AnalysisResult protocol
# ---------------------------------------------------------------------------

@dataclass
class AnalysisResult:
    name: str
    title: str
    summary: dict[str, Any] = field(default_factory=dict)
    figures: list[go.Figure] = field(default_factory=list)
    tables: list[tuple[str, pd.DataFrame]] = field(default_factory=list)
    narrative: str = ""


# ---------------------------------------------------------------------------
# Helper: Herfindahl-Hirschman Index
# ---------------------------------------------------------------------------

def _hhi(shares: pd.Series) -> float:
    """Compute HHI from a series of values (auto-normalizes to shares)."""
    total = shares.sum()
    if total == 0:
        return 0.0
    s = shares / total
    return float((s ** 2).sum())


# ---------------------------------------------------------------------------
# Main analyzer entry point
# ---------------------------------------------------------------------------

def analyze(entries: pd.DataFrame, daily: pd.DataFrame, weekly: pd.DataFrame) -> AnalysisResult:
    """
    Run all longitudinal composition analyses.

    Parameters
    ----------
    entries : full entries DataFrame from data_access.load_entries()
    daily   : daily aggregation from data_access.load_daily_series()
    weekly  : weekly project pivot from data_access.load_weekly_matrix()
    """
    result = AnalysisResult(
        name="longitudinal",
        title="Life Composition & Longitudinal Trends",
    )

    if entries.empty:
        result.narrative = "No data available."
        return result

    figs: list[go.Figure] = []
    tables: list[tuple[str, pd.DataFrame]] = []
    summary: dict[str, Any] = {}

    # 1. Stacked composition chart — quarterly project share
    fig_comp, top_projects = _stacked_composition(entries, by="project_name", label="Project")
    figs.append(fig_comp)

    # 2. Stacked composition chart — quarterly tag share
    fig_tags, _ = _stacked_composition_tags(entries)
    figs.append(fig_tags)

    # 3. Concentration index (HHI) over time
    fig_hhi, hhi_series = _concentration_index(entries)
    figs.append(fig_hhi)
    summary["peak_focus_quarter"] = hhi_series.idxmax() if not hhi_series.empty else "N/A"
    summary["peak_focus_hhi"] = round(float(hhi_series.max()), 3) if not hhi_series.empty else 0.0
    summary["min_focus_quarter"] = hhi_series.idxmin() if not hhi_series.empty else "N/A"

    # 4. Rolling stats on daily hours
    fig_rolling = _rolling_stats(daily)
    figs.append(fig_rolling)

    # 5. Year-over-year monthly heatmap
    fig_heatmap = _yoy_monthly_heatmap(entries)
    figs.append(fig_heatmap)

    # 6. Session duration violin chart per year
    fig_violin = _session_duration_violin(entries)
    figs.append(fig_violin)

    # 7. Active days rate (rolling 90-day)
    fig_active, mean_active_rate = _active_days_rate(daily)
    figs.append(fig_active)
    summary["mean_active_days_pct"] = f"{mean_active_rate:.0%}"

    # 8. Category transition velocity table
    velocity_df = _transition_velocity(entries)
    if not velocity_df.empty:
        tables.append(("Top Rising & Falling Projects (Quarter-over-Quarter Share)", velocity_df))
        summary["fastest_rising"] = velocity_df[velocity_df["direction"] == "rising"]["project"].iloc[0] \
            if not velocity_df[velocity_df["direction"] == "rising"].empty else "N/A"
        summary["fastest_falling"] = velocity_df[velocity_df["direction"] == "falling"]["project"].iloc[0] \
            if not velocity_df[velocity_df["direction"] == "falling"].empty else "N/A"

    # Summary stats
    total_hours = float(entries["duration_hours"].sum())
    years = sorted(entries["start_year"].dropna().unique().astype(int).tolist())
    summary["total_hours"] = f"{total_hours:,.0f}"
    summary["years_tracked"] = len(years)
    summary["date_range"] = f"{entries['start_date'].min()} → {entries['start_date'].max()}"
    summary["top_project_all_time"] = (
        entries.groupby("project_name")["duration_hours"].sum().idxmax()
    )

    result.figures = figs
    result.tables = tables
    result.summary = summary
    result.narrative = (
        f"Across {len(years)} years ({years[0]}–{years[-1]}), "
        f"{total_hours:,.0f} total hours were tracked. "
        f"Peak concentration (most focused period) was {summary['peak_focus_quarter']} "
        f"(HHI={summary['peak_focus_hhi']}). "
        f"On average, time was tracked on {summary['mean_active_days_pct']} of days."
    )
    return result


# ---------------------------------------------------------------------------
# Individual analysis functions
# ---------------------------------------------------------------------------

def _stacked_composition(
    entries: pd.DataFrame,
    by: str = "project_name",
    label: str = "Project",
    top_n: int = 12,
) -> tuple[go.Figure, list[str]]:
    """100% stacked area chart of top-N category share by quarter."""
    top_cats = (
        entries.groupby(by)["duration_hours"]
        .sum()
        .nlargest(top_n)
        .index.tolist()
    )

    filtered = entries[entries[by].isin(top_cats)].copy()
    quarterly = (
        filtered.groupby(["quarter", by])["duration_hours"]
        .sum()
        .unstack(fill_value=0.0)
    )
    # Normalize to 100%
    row_totals = quarterly.sum(axis=1)
    pct = quarterly.div(row_totals, axis=0) * 100

    quarters = pct.index.tolist()
    fig = go.Figure()
    for i, cat in enumerate(top_cats):
        if cat not in pct.columns:
            continue
        color = _NEON[i % len(_NEON)]
        fig.add_trace(go.Scatter(
            x=quarters,
            y=pct[cat].tolist(),
            name=cat,
            stackgroup="one",
            mode="lines",
            line=dict(width=0.5, color=color),
            fillcolor=color,
            hovertemplate=f"<b>{cat}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text=f"{label} Composition Over Time (Quarterly %)", font=dict(color=_C["cyan"])),
        height=460,
        yaxis=dict(title="Share of tracked hours (%)", gridcolor=_C["grid"]),
        xaxis=dict(title="Quarter", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"], font=dict(size=10)),
        hovermode="x unified",
    )
    return fig, top_cats


def _stacked_composition_tags(
    entries: pd.DataFrame,
    top_n: int = 10,
) -> tuple[go.Figure, list[str]]:
    """100% stacked area chart of top-N tag share by quarter."""
    exploded = entries.explode("tags_list")
    exploded = exploded[exploded["tags_list"].notna() & (exploded["tags_list"] != "")]

    if exploded.empty:
        fig = go.Figure()
        _apply_layout(fig, "Tag Composition Over Time (no tag data)")
        return fig, []

    top_tags = (
        exploded.groupby("tags_list")["duration_hours"]
        .sum()
        .nlargest(top_n)
        .index.tolist()
    )
    filtered = exploded[exploded["tags_list"].isin(top_tags)]
    quarterly = (
        filtered.groupby(["quarter", "tags_list"])["duration_hours"]
        .sum()
        .unstack(fill_value=0.0)
    )
    row_totals = quarterly.sum(axis=1)
    pct = quarterly.div(row_totals, axis=0) * 100
    quarters = pct.index.tolist()

    fig = go.Figure()
    for i, tag in enumerate(top_tags):
        if tag not in pct.columns:
            continue
        color = _NEON[i % len(_NEON)]
        fig.add_trace(go.Scatter(
            x=quarters,
            y=pct[tag].tolist(),
            name=tag,
            stackgroup="one",
            mode="lines",
            line=dict(width=0.5, color=color),
            hovertemplate=f"<b>{tag}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Tag Composition Over Time (Quarterly %)", font=dict(color=_C["magenta"])),
        height=420,
        yaxis=dict(title="Share of tagged hours (%)", gridcolor=_C["grid"]),
        xaxis=dict(title="Quarter", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"], font=dict(size=10)),
        hovermode="x unified",
    )
    return fig, top_tags


def _concentration_index(entries: pd.DataFrame) -> tuple[go.Figure, pd.Series]:
    """Plot Herfindahl-Hirschman Index (HHI) of project concentration per quarter."""
    quarterly = (
        entries.groupby(["quarter", "project_name"])["duration_hours"]
        .sum()
        .unstack(fill_value=0.0)
    )
    hhi = quarterly.apply(_hhi, axis=1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hhi.index.tolist(),
        y=hhi.values.tolist(),
        mode="lines+markers",
        name="HHI",
        line=dict(color=_C["gold"], width=2),
        marker=dict(color=_C["gold"], size=5),
        hovertemplate="<b>%{x}</b><br>HHI: %{y:.3f}<extra></extra>",
    ))
    # Reference lines
    fig.add_hline(y=0.25, line_dash="dot", line_color=_C["muted"],
                  annotation_text="Moderate focus", annotation_font_color=_C["muted"])
    fig.add_hline(y=0.5, line_dash="dot", line_color=_C["amber"],
                  annotation_text="High focus", annotation_font_color=_C["amber"])

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Time Concentration Index (HHI) by Quarter", font=dict(color=_C["gold"])),
        height=360,
        yaxis=dict(title="HHI (0=dispersed, 1=fully focused)", range=[0, 1], gridcolor=_C["grid"]),
        xaxis=dict(title="Quarter", gridcolor=_C["grid"]),
    )
    return fig, hhi


def _rolling_stats(daily: pd.DataFrame) -> go.Figure:
    """30-day and 90-day rolling mean/std of daily tracked hours."""
    if daily.empty:
        fig = go.Figure()
        return _apply_layout(fig, "Rolling Statistics (no data)")

    d = daily.set_index("date_dt")["hours"].sort_index()
    r30 = d.rolling(30, min_periods=7).mean()
    r90 = d.rolling(90, min_periods=30).mean()
    r90_std = d.rolling(90, min_periods=30).std()

    fig = go.Figure()
    # Raw daily (faint)
    fig.add_trace(go.Scatter(
        x=d.index, y=d.values,
        mode="lines", name="Daily",
        line=dict(color=_C["muted"], width=0.8),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.1f}h<extra></extra>",
    ))
    # 90-day band
    upper = (r90 + r90_std).fillna(r90)
    lower = (r90 - r90_std).fillna(r90).clip(lower=0)
    fig.add_trace(go.Scatter(
        x=list(r90.index) + list(r90.index[::-1]),
        y=list(upper) + list(lower[::-1]),
        fill="toself",
        fillcolor="rgba(255,0,255,0.08)",
        line=dict(color="rgba(0,0,0,0)"),
        name="90-day ±1σ",
        showlegend=True,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=r90.index, y=r90.values,
        mode="lines", name="90-day avg",
        line=dict(color=_C["magenta"], width=2),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}h<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=r30.index, y=r30.values,
        mode="lines", name="30-day avg",
        line=dict(color=_C["cyan"], width=1.5, dash="dot"),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}h<extra></extra>",
    ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Daily Hours — Rolling Averages (30-day & 90-day)", font=dict(color=_C["cyan"])),
        height=400,
        yaxis=dict(title="Hours tracked", gridcolor=_C["grid"]),
        xaxis=dict(title="", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"]),
        hovermode="x unified",
    )
    return fig


def _yoy_monthly_heatmap(entries: pd.DataFrame) -> go.Figure:
    """Year × Month heatmap of total tracked hours."""
    pivot = (
        entries.groupby(["start_year", "start_month"])["duration_hours"]
        .sum()
        .unstack(fill_value=0.0)
    )
    # Ensure all 12 months present
    for m in range(1, 13):
        if m not in pivot.columns:
            pivot[m] = 0.0
    pivot = pivot[[m for m in range(1, 13)]]

    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    fig = go.Figure(go.Heatmap(
        z=pivot.values.tolist(),
        x=month_names,
        y=[str(int(y)) for y in pivot.index],
        colorscale=[
            [0.0, _C["bg2"]],
            [0.3, "#0d47a1"],
            [0.6, _C["cyan"]],
            [0.85, _C["magenta"]],
            [1.0, _C["gold"]],
        ],
        hoverongaps=False,
        hovertemplate="<b>%{y} %{x}</b><br>%{z:.0f}h<extra></extra>",
        showscale=True,
        colorbar=dict(
            tickfont=dict(color=_C["text"]),
            bgcolor=_C["bg3"],
            outlinecolor=_C["border"],
        ),
    ))
    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Year × Month Tracked Hours Heatmap", font=dict(color=_C["cyan"])),
        height=max(280, 40 * len(pivot) + 80),
        xaxis=dict(title="Month", gridcolor=_C["grid"]),
        yaxis=dict(title="Year", gridcolor=_C["grid"]),
    )
    return fig


def _session_duration_violin(entries: pd.DataFrame) -> go.Figure:
    """Violin plot of entry durations (minutes) per year."""
    df = entries.copy()
    df["duration_min"] = df["duration"] / 60
    # Cap at 8 hours for readability
    df = df[df["duration_min"] <= 480]
    years = sorted(df["start_year"].dropna().unique().astype(int).tolist())

    fig = go.Figure()
    for i, yr in enumerate(years):
        subset = df[df["start_year"] == yr]["duration_min"]
        color = _NEON[i % len(_NEON)]
        fig.add_trace(go.Violin(
            y=subset.tolist(),
            name=str(yr),
            box_visible=True,
            meanline_visible=True,
            line_color=color,
            fillcolor=_hex_to_rgba(color, 0.15) if color.startswith("#") else color,
            opacity=0.8,
            hoverinfo="name+y",
        ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Entry Duration Distribution by Year (minutes)", font=dict(color=_C["purple"])),
        height=420,
        yaxis=dict(title="Entry duration (min)", gridcolor=_C["grid"]),
        xaxis=dict(title="Year"),
        violingap=0.1,
        violinmode="group",
    )
    return fig


def _active_days_rate(daily: pd.DataFrame) -> tuple[go.Figure, float]:
    """Rolling 90-day percentage of days with any tracked time."""
    if daily.empty:
        fig = go.Figure()
        return _apply_layout(fig, "Active Days Rate (no data)"), 0.0

    # Build a full date range
    all_dates = pd.date_range(daily["date_dt"].min(), daily["date_dt"].max(), freq="D")
    tracked = pd.Series(1, index=pd.to_datetime(daily["date_dt"].values), dtype=float)
    full = tracked.reindex(all_dates, fill_value=0.0)

    rate = full.rolling(90, min_periods=30).mean()
    mean_rate = float(rate.mean())

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rate.index, y=rate.values * 100,
        mode="lines",
        name="Active days %",
        line=dict(color=_C["green"], width=2),
        fill="tozeroy",
        fillcolor="rgba(57,255,20,0.07)",
        hovertemplate="%{x|%Y-%m-%d}: %{y:.0f}%<extra></extra>",
    ))
    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Active Tracking Rate (90-day rolling %)", font=dict(color=_C["green"])),
        height=320,
        yaxis=dict(title="% of days tracked", range=[0, 105], gridcolor=_C["grid"]),
        xaxis=dict(title="", gridcolor=_C["grid"]),
    )
    return fig, mean_rate


def _transition_velocity(entries: pd.DataFrame, top_n: int = 5) -> pd.DataFrame:
    """
    Compute quarter-over-quarter change in project share.
    Returns a DataFrame of the top-N fastest rising and falling projects.
    """
    quarterly = (
        entries.groupby(["quarter", "project_name"])["duration_hours"]
        .sum()
        .unstack(fill_value=0.0)
    )
    row_totals = quarterly.sum(axis=1)
    pct = quarterly.div(row_totals, axis=0) * 100
    delta = pct.diff()  # quarter-over-quarter change in share

    # Mean absolute delta per project
    mean_delta = delta.mean()
    mean_positive = mean_delta[mean_delta > 0].nlargest(top_n)
    mean_negative = mean_delta[mean_delta < 0].nsmallest(top_n)

    rows = []
    for proj, val in mean_positive.items():
        rows.append({"project": proj, "avg_qoq_share_change": f"+{val:.2f}pp", "direction": "rising"})
    for proj, val in mean_negative.items():
        rows.append({"project": proj, "avg_qoq_share_change": f"{val:.2f}pp", "direction": "falling"})

    return pd.DataFrame(rows)
