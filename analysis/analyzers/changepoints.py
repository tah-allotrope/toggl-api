"""
Changepoint detection analyzer.

Answers: When did my behavior fundamentally and statistically shift?
Uses ruptures (PELT + Binseg) for regime detection across multiple
behavioral signals. Aggregates multi-signal transitions into named
"transition events" with before/after statistics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    import ruptures as rpt
    _HAS_RUPTURES = True
except ImportError:
    _HAS_RUPTURES = False

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
_C = {
    "bg": "#0a0a1a", "bg2": "#12122a", "bg3": "#1a1a3e",
    "cyan": "#00fff9", "magenta": "#ff00ff", "green": "#39ff14",
    "purple": "#bc13fe", "pink": "#ff2079", "gold": "#ffd700",
    "amber": "#ff9800", "text": "#e0e0ff", "muted": "#7878a8",
    "grid": "#1e1e4a", "border": "#2a2a5a", "red": "#ff3131",
}
_LAYOUT = dict(
    paper_bgcolor=_C["bg"], plot_bgcolor=_C["bg2"],
    font=dict(color=_C["text"], family="monospace"),
    margin=dict(l=60, r=30, t=50, b=50),
)
_AXIS = dict(gridcolor=_C["grid"], zerolinecolor=_C["grid"])


@dataclass
class TransitionEvent:
    date: str                              # YYYY-MM-DD
    signals_count: int                     # how many signals fired here
    confidence: str                        # "high" / "medium" / "low"
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    name: str
    title: str
    summary: dict[str, Any] = field(default_factory=dict)
    figures: list[go.Figure] = field(default_factory=list)
    tables: list[tuple[str, pd.DataFrame]] = field(default_factory=list)
    narrative: str = ""
    transition_events: list[TransitionEvent] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze(entries: pd.DataFrame, daily: pd.DataFrame, weekly: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(
        name="changepoints",
        title="Transition Detection & Regime Shifts",
    )

    if daily.empty or not _HAS_RUPTURES:
        if not _HAS_RUPTURES:
            result.narrative = (
                "ruptures library not installed. "
                "Run: pip install ruptures"
            )
        else:
            result.narrative = "No daily data available."
        return result

    # Build weekly aggregates (more stable signal than daily)
    weekly_agg = _build_weekly_aggregates(entries, daily)
    if weekly_agg.empty:
        result.narrative = "Insufficient data for changepoint detection."
        return result

    # -----------------------------------------------------------------------
    # Detect changepoints on each signal independently
    # -----------------------------------------------------------------------
    signals = {
        "Weekly Hours":          weekly_agg["hours"].values,
        "Project Diversity":     weekly_agg["unique_projects"].values,
        "Active Days / Week":    weekly_agg["active_days"].values,
        "Avg Entry Duration":    weekly_agg["avg_duration_min"].values,
        "Weekend Ratio":         weekly_agg["weekend_ratio"].values,
    }

    all_cp_indices: dict[str, list[int]] = {}
    for sig_name, signal in signals.items():
        cps = _detect_pelt(signal)
        all_cp_indices[sig_name] = cps

    # Convert indices → dates
    weeks = weekly_agg["year_week"].tolist()
    week_dates = weekly_agg["week_start"].tolist()

    all_cp_dates: dict[str, list[str]] = {
        sig: [str(week_dates[i]) if i < len(week_dates) else "" for i in indices]
        for sig, indices in all_cp_indices.items()
    }

    # -----------------------------------------------------------------------
    # Aggregate into transition events (cluster within 4-week window)
    # -----------------------------------------------------------------------
    transition_events = _aggregate_transitions(all_cp_dates, week_dates, weekly_agg, entries)
    result.transition_events = transition_events

    # -----------------------------------------------------------------------
    # Binseg cross-check (fixed n=8)
    # -----------------------------------------------------------------------
    binseg_dates = _detect_binseg(weekly_agg["hours"].values, week_dates, n=8)

    # -----------------------------------------------------------------------
    # Figures
    # -----------------------------------------------------------------------
    fig_timeline = _annotated_timeline(daily, transition_events, binseg_dates)
    result.figures.append(fig_timeline)

    fig_multi = _multi_signal_chart(weekly_agg, all_cp_indices, signals)
    result.figures.append(fig_multi)

    # -----------------------------------------------------------------------
    # Transition summary table
    # -----------------------------------------------------------------------
    if transition_events:
        rows = []
        for ev in transition_events:
            rows.append({
                "Date": ev.date,
                "Signals": ev.signals_count,
                "Confidence": ev.confidence,
                "Before — Avg Hrs/Wk": f"{ev.before.get('avg_hours_wk', 0):.1f}",
                "After — Avg Hrs/Wk": f"{ev.after.get('avg_hours_wk', 0):.1f}",
                "Before — Top Project": ev.before.get("top_project", "—"),
                "After — Top Project": ev.after.get("top_project", "—"),
            })
        table_df = pd.DataFrame(rows)
        result.tables.append(("Detected Transition Events", table_df))

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    high_conf = [e for e in transition_events if e.confidence == "high"]
    result.summary = {
        "total_transitions_detected": len(transition_events),
        "high_confidence_transitions": len(high_conf),
        "ruptures_available": _HAS_RUPTURES,
        "most_recent_transition": transition_events[-1].date if transition_events else "N/A",
        "earliest_transition": transition_events[0].date if transition_events else "N/A",
    }
    result.narrative = (
        f"Changepoint detection identified {len(transition_events)} behavioral "
        f"transition events, {len(high_conf)} with high confidence (≥3 signals). "
        f"Earliest detected transition: {result.summary['earliest_transition']}. "
        f"Most recent: {result.summary['most_recent_transition']}."
    )
    return result


# ---------------------------------------------------------------------------
# Signal preparation
# ---------------------------------------------------------------------------

def _build_weekly_aggregates(entries: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    """Build a weekly aggregate signal DataFrame."""
    df = entries.copy()
    df["week_start"] = df["start_dt"].dt.to_period("W").apply(lambda p: p.start_time.date())

    weekly = (
        df.groupby("week_start")
        .agg(
            hours=("duration_hours", "sum"),
            entry_count=("id", "count"),
            unique_projects=("project_name", "nunique"),
            avg_duration_min=("duration", lambda x: x.mean() / 60),
            weekend_hours=("duration_hours", lambda x: x[df.loc[x.index, "is_weekend"]].sum()),
        )
        .reset_index()
    )

    # Weekend ratio
    weekly["weekend_ratio"] = (
        weekly["weekend_hours"] / weekly["hours"].replace(0, np.nan)
    ).fillna(0.0)

    # Active days from daily series
    if not daily.empty:
        daily_c = daily.copy()
        daily_c["week_start"] = pd.to_datetime(daily_c["date_dt"]).dt.to_period("W").apply(
            lambda p: p.start_time.date()
        )
        active = daily_c.groupby("week_start").size().rename("active_days").reset_index()
        weekly = weekly.merge(active, on="week_start", how="left")
        weekly["active_days"] = weekly["active_days"].fillna(0).astype(int)
    else:
        weekly["active_days"] = 5

    # ISO year-week label
    weekly["week_start"] = pd.to_datetime(weekly["week_start"])
    weekly["year_week"] = (
        weekly["week_start"].dt.isocalendar().year.astype(str)
        + "-W"
        + weekly["week_start"].dt.isocalendar().week.astype(int).astype(str).str.zfill(2)
    )

    # Fill NaN signals with forward fill then 0
    for col in ["hours", "unique_projects", "avg_duration_min", "weekend_ratio", "active_days"]:
        weekly[col] = weekly[col].fillna(0.0)

    return weekly.sort_values("week_start").reset_index(drop=True)


# ---------------------------------------------------------------------------
# PELT detection
# ---------------------------------------------------------------------------

def _detect_pelt(signal: np.ndarray, n_penalties: int = 5) -> list[int]:
    """
    Run PELT at multiple penalty values; return indices stable across ≥3 penalties.
    Indices refer to positions in the signal array (start of new segment).
    """
    if not _HAS_RUPTURES or len(signal) < 20:
        return []

    # Normalize
    s = signal.astype(float)
    std = s.std()
    if std == 0:
        return []
    s_norm = (s - s.mean()) / std

    min_pen = 1.0
    max_pen = 10.0
    penalties = np.linspace(min_pen, max_pen, n_penalties).tolist()

    cp_votes: dict[int, int] = {}
    for pen in penalties:
        try:
            algo = rpt.Pelt(model="rbf", min_size=4, jump=1).fit(s_norm.reshape(-1, 1))
            bkps = algo.predict(pen=pen)
            for bp in bkps[:-1]:  # last element is len(signal)
                cp_votes[bp] = cp_votes.get(bp, 0) + 1
        except Exception:
            continue

    # Keep changepoints that appear in at least 3 out of n_penalties runs
    threshold = max(2, n_penalties // 2)
    stable = sorted([idx for idx, votes in cp_votes.items() if votes >= threshold])
    return stable


# ---------------------------------------------------------------------------
# Binseg cross-check
# ---------------------------------------------------------------------------

def _detect_binseg(
    signal: np.ndarray,
    dates: list,
    n: int = 8,
) -> list[str]:
    """Binary segmentation with fixed number of breakpoints."""
    if not _HAS_RUPTURES or len(signal) < n * 2:
        return []
    s = signal.astype(float)
    std = s.std()
    if std == 0:
        return []
    s_norm = (s - s.mean()) / std
    try:
        algo = rpt.Binseg(model="l2", min_size=4).fit(s_norm.reshape(-1, 1))
        bkps = algo.predict(n_bkps=min(n, len(signal) // 8))
        return [str(dates[min(i, len(dates) - 1)].date() if hasattr(dates[0], "date") else dates[i])
                for i in bkps[:-1] if i < len(dates)]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Transition event aggregation
# ---------------------------------------------------------------------------

def _aggregate_transitions(
    cp_dates_by_signal: dict[str, list[str]],
    week_dates: list,
    weekly_agg: pd.DataFrame,
    entries: pd.DataFrame,
    cluster_weeks: int = 4,
) -> list[TransitionEvent]:
    """
    Cluster nearby changepoints across signals into unified transition events.
    """
    # Collect all (date_str, signal_name) tuples
    all_events: list[tuple[datetime, str]] = []
    for sig_name, dates in cp_dates_by_signal.items():
        for d in dates:
            if d:
                try:
                    all_events.append((pd.to_datetime(d), sig_name))
                except Exception:
                    pass

    if not all_events:
        return []

    all_events.sort(key=lambda x: x[0])
    cluster_delta = timedelta(weeks=cluster_weeks)

    # Greedy clustering
    clusters: list[list[tuple[datetime, str]]] = []
    current_cluster: list[tuple[datetime, str]] = [all_events[0]]
    for ev in all_events[1:]:
        if ev[0] - current_cluster[-1][0] <= cluster_delta:
            current_cluster.append(ev)
        else:
            clusters.append(current_cluster)
            current_cluster = [ev]
    clusters.append(current_cluster)

    # Build TransitionEvent objects
    transition_events: list[TransitionEvent] = []
    for cluster in clusters:
        # Representative date = median date in cluster
        cluster_dates = [e[0] for e in cluster]
        rep_date = sorted(cluster_dates)[len(cluster_dates) // 2]
        n_signals = len(set(e[1] for e in cluster))
        confidence = "high" if n_signals >= 3 else ("medium" if n_signals == 2 else "low")

        # Before/after stats
        window = timedelta(weeks=8)
        before_start = rep_date - window
        after_end = rep_date + window

        # entries["start_dt"] is tz-aware UTC; localize comparison timestamps
        before_start_utc = before_start.tz_localize("UTC") if before_start.tzinfo is None else before_start
        rep_date_utc     = rep_date.tz_localize("UTC")     if rep_date.tzinfo is None     else rep_date
        after_end_utc    = after_end.tz_localize("UTC")    if after_end.tzinfo is None    else after_end

        before_entries = entries[
            (entries["start_dt"] >= before_start_utc) &
            (entries["start_dt"] < rep_date_utc)
        ]
        after_entries = entries[
            (entries["start_dt"] >= rep_date_utc) &
            (entries["start_dt"] < after_end_utc)
        ]

        def _stats(df: pd.DataFrame) -> dict[str, Any]:
            if df.empty:
                return {}
            avg_hrs = df["duration_hours"].sum() / max(1, (df["start_date"].nunique()))
            top_proj = df.groupby("project_name")["duration_hours"].sum().idxmax() \
                if not df.empty else "—"
            unique_proj = df["project_name"].nunique()
            top_tags = (
                df.explode("tags_list")["tags_list"]
                .value_counts()
                .head(3)
                .index.tolist()
            )
            # Weekly hours average
            n_weeks = max(1, (df["start_date"].nunique() / 7))
            avg_hours_wk = df["duration_hours"].sum() / n_weeks
            return {
                "avg_hours_day": round(avg_hrs, 2),
                "avg_hours_wk": round(avg_hours_wk, 2),
                "top_project": top_proj,
                "unique_projects": unique_proj,
                "top_tags": top_tags,
            }

        transition_events.append(TransitionEvent(
            date=rep_date.strftime("%Y-%m-%d"),
            signals_count=n_signals,
            confidence=confidence,
            before=_stats(before_entries),
            after=_stats(after_entries),
        ))

    return sorted(transition_events, key=lambda e: e.date)


# ---------------------------------------------------------------------------
# Figure: annotated timeline
# ---------------------------------------------------------------------------

def _annotated_timeline(
    daily: pd.DataFrame,
    events: list[TransitionEvent],
    binseg_dates: list[str],
) -> go.Figure:
    """Daily hours time series with vertical lines at each transition event."""
    d = daily.set_index("date_dt")["hours"].sort_index()
    r90 = d.rolling(90, min_periods=30).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=d.index, y=d.values, mode="lines",
        name="Daily hours", line=dict(color=_C["muted"], width=0.8),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.1f}h<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=r90.index, y=r90.values, mode="lines",
        name="90-day avg", line=dict(color=_C["cyan"], width=2),
        hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}h<extra></extra>",
    ))

    # Binseg lines (softer)
    for d_str in binseg_dates:
        fig.add_vline(
            x=pd.to_datetime(d_str).timestamp() * 1000,
            line_dash="dot", line_color=_C["muted"], line_width=1,
            annotation_text="binseg", annotation_font_color=_C["muted"],
            annotation_font_size=9,
        )

    # PELT consensus events
    color_map = {"high": _C["magenta"], "medium": _C["amber"], "low": _C["green"]}
    for ev in events:
        color = color_map.get(ev.confidence, _C["muted"])
        fig.add_vline(
            x=pd.to_datetime(ev.date).timestamp() * 1000,
            line_dash="dash", line_color=color, line_width=1.5,
            annotation_text=f"{ev.date}<br>({ev.signals_count} sig)",
            annotation_font_color=color,
            annotation_font_size=9,
            annotation_position="top left",
        )

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Behavioral Transition Timeline (PELT Changepoints)", font=dict(color=_C["magenta"])),
        height=480,
        yaxis=dict(title="Hours tracked", gridcolor=_C["grid"]),
        xaxis=dict(title="", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"]),
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Figure: multi-signal subplots
# ---------------------------------------------------------------------------

def _multi_signal_chart(
    weekly_agg: pd.DataFrame,
    cp_indices: dict[str, list[int]],
    signals: dict[str, np.ndarray],
) -> go.Figure:
    """Small-multiples of each signal with its changepoints marked."""
    sig_names = list(signals.keys())
    n = len(sig_names)
    colors = [_C["cyan"], _C["magenta"], _C["green"], _C["gold"], _C["purple"]]
    x = weekly_agg["week_start"].tolist()

    fig = make_subplots(
        rows=n, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=sig_names,
    )

    for i, (sig_name, signal) in enumerate(signals.items(), 1):
        color = colors[(i - 1) % len(colors)]
        fig.add_trace(go.Scatter(
            x=x, y=signal.tolist(),
            mode="lines", name=sig_name,
            line=dict(color=color, width=1.5),
            showlegend=False,
            hovertemplate=f"<b>{sig_name}</b> %{{x|%Y-%m-%d}}: %{{y:.2f}}<extra></extra>",
        ), row=i, col=1)

        for idx in cp_indices.get(sig_name, []):
            if idx < len(x):
                fig.add_vline(
                    x=x[idx].timestamp() * 1000 if hasattr(x[idx], "timestamp") else 0,
                    line_dash="dash", line_color=_C["red"], line_width=1,
                    row=i, col=1,
                )

    # Style annotation titles
    for ann in fig.layout.annotations:
        ann.font = dict(color=_C["muted"], size=11, family="monospace")

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Multi-Signal Changepoint Analysis", font=dict(color=_C["cyan"])),
        height=160 * n + 60,
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=_C["grid"], zerolinecolor=_C["grid"])
    fig.update_yaxes(gridcolor=_C["grid"], zerolinecolor=_C["grid"])
    return fig
