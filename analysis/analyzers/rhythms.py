"""
Rhythm and routine analyzer.

Answers: When do I work, and how has that changed over time?
Covers hour-of-day distributions, day-of-week composition, sleep/wake proxies,
seasonal decomposition, weekend ratio evolution, and consistency scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
_C = {
    "bg": "#0a0a1a", "bg2": "#12122a", "bg3": "#1a1a3e",
    "cyan": "#00fff9", "magenta": "#ff00ff", "green": "#39ff14",
    "purple": "#bc13fe", "pink": "#ff2079", "gold": "#ffd700",
    "amber": "#ff9800", "text": "#e0e0ff", "muted": "#7878a8",
    "grid": "#1e1e4a", "border": "#2a2a5a",
}
_NEON = [
    _C["cyan"], _C["magenta"], _C["green"], _C["purple"], _C["pink"],
    _C["gold"], _C["amber"], "#00b4d8", "#e040fb", "#76ff03",
    "#7c4dff", "#18ffff", "#ff6e40", "#eeff41",
]
_LAYOUT = dict(
    paper_bgcolor=_C["bg"], plot_bgcolor=_C["bg2"],
    font=dict(color=_C["text"], family="monospace"),
    margin=dict(l=60, r=30, t=50, b=50),
)
_AXIS = dict(gridcolor=_C["grid"], zerolinecolor=_C["grid"])

_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass
class AnalysisResult:
    name: str
    title: str
    summary: dict[str, Any] = field(default_factory=dict)
    figures: list[go.Figure] = field(default_factory=list)
    tables: list[tuple[str, pd.DataFrame]] = field(default_factory=list)
    narrative: str = ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze(entries: pd.DataFrame, daily: pd.DataFrame, weekly: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(
        name="rhythms",
        title="Rhythms & Routines",
    )

    if entries.empty:
        result.narrative = "No data available."
        return result

    figs: list[go.Figure] = []
    tables: list[tuple[str, pd.DataFrame]] = []
    summary: dict[str, Any] = {}

    # 1. Hour-of-day distribution by year (small multiples)
    fig_hour, peak_hours = _hour_of_day_by_year(entries)
    figs.append(fig_hour)
    summary["most_common_start_hour"] = _most_common_hour(entries)

    # 2. Day-of-week composition by year
    fig_dow = _dow_by_year(entries)
    figs.append(fig_dow)

    # 3. Sleep/wake proxy (first/last entry per day rolling avg)
    fig_sleepwake, wake_trend, sleep_trend = _sleep_wake_proxy(daily, entries)
    figs.append(fig_sleepwake)
    if wake_trend is not None:
        summary["avg_first_entry_hour"] = f"{wake_trend:.1f}:00"
    if sleep_trend is not None:
        summary["avg_last_entry_hour"] = f"{sleep_trend:.1f}:00"

    # 4. Seasonal decomposition — monthly hours with trend
    fig_seasonal = _seasonal_decomposition(entries)
    figs.append(fig_seasonal)

    # 5. Weekend ratio evolution
    fig_weekend, mean_wknd = _weekend_ratio_evolution(daily)
    figs.append(fig_weekend)
    summary["mean_weekend_ratio"] = f"{mean_wknd:.0%}"

    # 6. Consistency score (CoV rolling)
    fig_consistency, mean_consistency = _consistency_score(daily)
    figs.append(fig_consistency)
    summary["mean_consistency_score"] = f"{mean_consistency:.2f}"

    # Peak hours table per year
    if peak_hours:
        ph_df = pd.DataFrame(
            [(yr, f"{hr}:00–{hr+1}:00") for yr, hr in sorted(peak_hours.items())],
            columns=["Year", "Peak Activity Hour"],
        )
        tables.append(("Peak Activity Hour by Year", ph_df))

    result.figures = figs
    result.tables = tables
    result.summary = summary

    # Narrative
    wknd_msg = (
        f"Weekend work accounts for {summary['mean_weekend_ratio']} of tracked time on average. "
    )
    result.narrative = (
        f"Most entries start around {summary.get('most_common_start_hour', '?')}:00. "
        + wknd_msg
        + f"Consistency score (lower = more regular): {summary['mean_consistency_score']}."
    )
    return result


# ---------------------------------------------------------------------------
# Individual analysis functions
# ---------------------------------------------------------------------------

def _most_common_hour(entries: pd.DataFrame) -> int:
    return int(entries["hour_of_day"].value_counts().idxmax())


def _hour_of_day_by_year(entries: pd.DataFrame) -> tuple[go.Figure, dict[int, int]]:
    """Line chart of entry-start hour distribution by year."""
    years = sorted(entries["start_year"].dropna().unique().astype(int).tolist())
    peak_hours: dict[int, int] = {}

    fig = go.Figure()
    for i, yr in enumerate(years):
        subset = entries[entries["start_year"] == yr]
        # Weighted by hours to reflect actual time commitment
        counts = subset.groupby("hour_of_day")["duration_hours"].sum().reindex(
            range(24), fill_value=0.0
        )
        # Normalize per year
        total = counts.sum()
        if total > 0:
            counts = counts / total * 100
        peak_hours[yr] = int(counts.idxmax())
        color = _NEON[i % len(_NEON)]
        fig.add_trace(go.Scatter(
            x=list(range(24)),
            y=counts.tolist(),
            mode="lines",
            name=str(yr),
            line=dict(color=color, width=1.5),
            hovertemplate=f"<b>{yr}</b> hour %{{x}}:00 — %{{y:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Work Hour Distribution by Year (% of hours at each hour)", font=dict(color=_C["cyan"])),
        height=400,
        xaxis=dict(title="Hour of day (0–23)", tickvals=list(range(0, 24, 2)),
                   ticktext=[f"{h}:00" for h in range(0, 24, 2)], gridcolor=_C["grid"]),
        yaxis=dict(title="% of tracked hours", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"], font=dict(size=10)),
        hovermode="x unified",
    )
    return fig, peak_hours


def _dow_by_year(entries: pd.DataFrame, top_n_years: int = 8) -> go.Figure:
    """Grouped bar chart of hours per day-of-week, one bar group per year."""
    years = sorted(entries["start_year"].dropna().unique().astype(int).tolist())
    if len(years) > top_n_years:
        # Show every N years to avoid clutter
        step = max(1, len(years) // top_n_years)
        years = years[::step]

    fig = go.Figure()
    for i, yr in enumerate(years):
        subset = entries[entries["start_year"] == yr]
        dow_hours = (
            subset.groupby("day_of_week")["duration_hours"]
            .sum()
            .reindex(range(7), fill_value=0.0)
        )
        # Normalize
        total = dow_hours.sum()
        pct = (dow_hours / total * 100) if total > 0 else dow_hours
        color = _NEON[i % len(_NEON)]
        fig.add_trace(go.Bar(
            x=_DOW,
            y=pct.tolist(),
            name=str(yr),
            marker_color=color,
            hovertemplate=f"<b>{yr}</b> %{{x}}: %{{y:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Day-of-Week Distribution by Year (% of annual hours)", font=dict(color=_C["magenta"])),
        height=400,
        barmode="group",
        xaxis=dict(title="Day of week"),
        yaxis=dict(title="% of hours"),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"], font=dict(size=10)),
    )
    return fig


def _sleep_wake_proxy(
    daily: pd.DataFrame,
    entries: pd.DataFrame,
) -> tuple[go.Figure, float | None, float | None]:
    """
    Plot rolling 90-day mean of first and last entry hour per day.
    This is a behavioral proxy — not actual sleep data.
    """
    if daily.empty:
        fig = go.Figure()
        fig.update_layout(**_LAYOUT, title=dict(text="Sleep/Wake Proxy (no data)"))
        return fig, None, None

    day_hours = (
        entries.groupby("start_date")
        .agg(
            first_hour=("hour_of_day", "min"),
            last_hour=("hour_of_day", "max"),
        )
        .reset_index()
    )
    day_hours["date_dt"] = pd.to_datetime(day_hours["start_date"])
    day_hours = day_hours.sort_values("date_dt").set_index("date_dt")

    r90_first = day_hours["first_hour"].rolling(90, min_periods=30).mean()
    r90_last = day_hours["last_hour"].rolling(90, min_periods=30).mean()

    mean_first = float(r90_first.mean()) if not r90_first.empty else None
    mean_last = float(r90_last.mean()) if not r90_last.empty else None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=r90_first.index, y=r90_first.values,
        mode="lines", name="First entry (wake proxy)",
        line=dict(color=_C["cyan"], width=2),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.1f}:00<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=r90_last.index, y=r90_last.values,
        mode="lines", name="Last entry (end proxy)",
        line=dict(color=_C["magenta"], width=2),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.1f}:00<extra></extra>",
    ))
    # Fill between
    fig.add_trace(go.Scatter(
        x=list(r90_first.index) + list(r90_first.index[::-1]),
        y=list(r90_first.values) + list(r90_last.values[::-1]),
        fill="toself",
        fillcolor="rgba(0,255,249,0.05)",
        line=dict(color="rgba(0,0,0,0)"),
        name="Active window",
        hoverinfo="skip",
    ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Work Start/End Proxy (90-day rolling avg of first/last entry)", font=dict(color=_C["cyan"])),
        height=360,
        yaxis=dict(
            title="Hour of day",
            tickvals=list(range(0, 25, 2)),
            ticktext=[f"{h}:00" for h in range(0, 25, 2)],
            range=[-0.5, 24.5],
            gridcolor=_C["grid"],
        ),
        xaxis=dict(title="", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"]),
        hovermode="x unified",
    )
    return fig, mean_first, mean_last


def _seasonal_decomposition(entries: pd.DataFrame) -> go.Figure:
    """Monthly hours with 12-month rolling trend overlay."""
    monthly = (
        entries.groupby("year_month")["duration_hours"]
        .sum()
        .sort_index()
    )
    monthly.index = pd.to_datetime(monthly.index + "-01")
    trend = monthly.rolling(12, center=True, min_periods=6).mean()

    # Seasonal index: month average / overall average
    month_avg = entries.groupby("start_month")["duration_hours"].sum() / \
        entries["start_year"].nunique()

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.65, 0.35],
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=["Monthly Hours + 12-Month Trend", "Seasonal Profile (avg hours by month)"],
    )

    # Monthly bars
    fig.add_trace(go.Bar(
        x=monthly.index, y=monthly.values,
        name="Monthly hours",
        marker_color=_C["muted"],
        opacity=0.6,
        hovertemplate="%{x|%Y-%m}: %{y:.0f}h<extra></extra>",
    ), row=1, col=1)

    # Trend line
    fig.add_trace(go.Scatter(
        x=trend.index, y=trend.values,
        mode="lines", name="12-month trend",
        line=dict(color=_C["cyan"], width=2.5),
        hovertemplate="%{x|%Y-%m}: %{y:.1f}h<extra></extra>",
    ), row=1, col=1)

    # Seasonal profile bar
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    fig.add_trace(go.Bar(
        x=month_names,
        y=[float(month_avg.get(m, 0)) for m in range(1, 13)],
        name="Avg hours/month",
        marker_color=_C["magenta"],
        hovertemplate="%{x}: %{y:.0f}h avg<extra></extra>",
    ), row=2, col=1)

    for ann in fig.layout.annotations:
        ann.font = dict(color=_C["muted"], size=11, family="monospace")

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Seasonal Patterns", font=dict(color=_C["gold"])),
        height=560,
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"]),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=_C["grid"], zerolinecolor=_C["grid"])
    fig.update_yaxes(gridcolor=_C["grid"], zerolinecolor=_C["grid"])
    return fig


def _weekend_ratio_evolution(daily: pd.DataFrame) -> tuple[go.Figure, float]:
    """Rolling 90-day weekend hours / total hours ratio."""
    if daily.empty:
        return go.Figure(), 0.0

    d = daily.copy().sort_values("date_dt").set_index("date_dt")
    weekend_series = d["is_weekend"].astype(float) * d["hours"]
    total_series = d["hours"]

    # 90-day rolling sums
    wknd_roll = weekend_series.rolling(90, min_periods=30).sum()
    total_roll = total_series.rolling(90, min_periods=30).sum()
    ratio = (wknd_roll / total_roll.replace(0, np.nan)).fillna(0.0)
    mean_ratio = float(ratio.mean())

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ratio.index, y=(ratio * 100).values,
        mode="lines", name="Weekend %",
        line=dict(color=_C["amber"], width=2),
        fill="tozeroy",
        fillcolor="rgba(255,152,0,0.07)",
        hovertemplate="%{x|%Y-%m-%d}: %{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=float(mean_ratio * 100), line_dash="dot", line_color=_C["muted"],
                  annotation_text=f"mean {mean_ratio:.0%}",
                  annotation_font_color=_C["muted"])

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Weekend Work Ratio (90-day rolling %)", font=dict(color=_C["amber"])),
        height=320,
        yaxis=dict(title="% of tracked hours on weekends", range=[0, 105], gridcolor=_C["grid"]),
        xaxis=dict(title="", gridcolor=_C["grid"]),
    )
    return fig, mean_ratio


def _consistency_score(daily: pd.DataFrame) -> tuple[go.Figure, float]:
    """
    Rolling 90-day coefficient of variation (std/mean) of daily hours.
    Lower = more regular routine; higher = more bursty.
    """
    if daily.empty:
        return go.Figure(), 0.0

    d = daily.sort_values("date_dt").set_index("date_dt")["hours"]
    # Include zero days for full daily series
    all_dates = pd.date_range(d.index.min(), d.index.max(), freq="D")
    full = d.reindex(all_dates, fill_value=0.0)

    rolling_mean = full.rolling(90, min_periods=30).mean()
    rolling_std = full.rolling(90, min_periods=30).std()
    cov = (rolling_std / rolling_mean.replace(0, np.nan)).fillna(0.0)
    mean_cov = float(cov.mean())

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cov.index, y=cov.values,
        mode="lines", name="CoV (irregularity)",
        line=dict(color=_C["pink"], width=2),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}<extra></extra>",
    ))
    fig.add_hline(y=mean_cov, line_dash="dot", line_color=_C["muted"],
                  annotation_text=f"mean {mean_cov:.2f}",
                  annotation_font_color=_C["muted"])

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Routine Consistency Score (CoV — lower = more regular)", font=dict(color=_C["pink"])),
        height=320,
        yaxis=dict(title="Coefficient of Variation", gridcolor=_C["grid"]),
        xaxis=dict(title="", gridcolor=_C["grid"]),
    )
    return fig, mean_cov
