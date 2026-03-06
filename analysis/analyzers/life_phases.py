"""
Life phase segmentation analyzer.

Answers: What were the distinct eras of my tracked life?
Synthesizes signals from all other analyzers into automatically
detected and labeled life phase epochs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    import ruptures as rpt
    _HAS_RUPTURES = True
except ImportError:
    _HAS_RUPTURES = False

try:
    from sklearn.preprocessing import StandardScaler
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

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

_INTENSITY_LABELS = {
    (0.0, 1.5):  "Low-Track",
    (1.5, 3.0):  "Moderate",
    (3.0, 5.0):  "Active",
    (5.0, 7.5):  "Intensive",
    (7.5, 99.0): "Peak",
}


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert a #rrggbb hex color string to rgba(r,g,b,alpha)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"rgba({r},{g},{b},{alpha})"
    return hex_color


@dataclass
class LifePhase:
    label: str
    start: str
    end: str
    duration_days: int
    avg_hours_day: float
    focus_hhi: float
    top_projects: list[str]
    top_topics: list[str]
    weekend_ratio: float
    consistency: float
    intensity: str


@dataclass
class AnalysisResult:
    name: str
    title: str
    summary: dict[str, Any] = field(default_factory=dict)
    figures: list[go.Figure] = field(default_factory=list)
    tables: list[tuple[str, pd.DataFrame]] = field(default_factory=list)
    narrative: str = ""
    phases: list[LifePhase] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze(
    entries: pd.DataFrame,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    text_mining_result: Any = None,   # analysis.analyzers.text_mining.AnalysisResult
) -> AnalysisResult:
    result = AnalysisResult(
        name="life_phases",
        title="Life Phase Segmentation",
    )

    if entries.empty or not _HAS_RUPTURES or not _HAS_SKLEARN:
        missing = []
        if not _HAS_RUPTURES:
            missing.append("ruptures")
        if not _HAS_SKLEARN:
            missing.append("scikit-learn")
        if missing:
            result.narrative = f"Missing dependencies: {', '.join(missing)}"
        else:
            result.narrative = "No data available."
        return result

    # -----------------------------------------------------------------------
    # Build weekly feature matrix
    # -----------------------------------------------------------------------
    feature_df = _build_feature_matrix(entries, daily, weekly, text_mining_result)
    if feature_df.empty or len(feature_df) < 20:
        result.narrative = "Insufficient data for life phase detection (< 20 weeks)."
        return result

    # -----------------------------------------------------------------------
    # Multivariate changepoint detection
    # -----------------------------------------------------------------------
    phase_boundaries = _detect_phase_boundaries(feature_df)

    # -----------------------------------------------------------------------
    # Characterize each phase
    # -----------------------------------------------------------------------
    phases = _characterize_phases(entries, feature_df, phase_boundaries, text_mining_result)
    result.phases = phases

    # -----------------------------------------------------------------------
    # Figures
    # -----------------------------------------------------------------------
    if phases:
        fig_gantt = _gantt_chart(phases, daily)
        result.figures.append(fig_gantt)

        fig_radar = _radar_chart(phases)
        result.figures.append(fig_radar)

        fig_comparison = _phase_comparison_chart(phases)
        result.figures.append(fig_comparison)

    # -----------------------------------------------------------------------
    # Phase comparison table
    # -----------------------------------------------------------------------
    if phases:
        rows = []
        for p in phases:
            rows.append({
                "Phase": p.label,
                "Start": p.start,
                "End": p.end,
                "Duration": f"{p.duration_days // 30}mo",
                "Avg Hrs/Day": f"{p.avg_hours_day:.1f}",
                "Intensity": p.intensity,
                "Focus (HHI)": f"{p.focus_hhi:.2f}",
                "Weekend %": f"{p.weekend_ratio:.0%}",
                "Top Projects": " | ".join(p.top_projects[:2]),
            })
        result.tables.append(("Life Phase Profiles", pd.DataFrame(rows)))

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    result.summary = {
        "n_phases": len(phases),
        "earliest_phase": phases[0].label if phases else "N/A",
        "latest_phase": phases[-1].label if phases else "N/A",
        "most_intensive_phase": max(phases, key=lambda p: p.avg_hours_day).label if phases else "N/A",
        "most_focused_phase": max(phases, key=lambda p: p.focus_hhi).label if phases else "N/A",
    }

    result.narrative = (
        f"Detected {len(phases)} distinct life phases. "
        f"Most intensive: '{result.summary['most_intensive_phase']}'. "
        f"Most focused: '{result.summary['most_focused_phase']}'."
    )
    return result


# ---------------------------------------------------------------------------
# Feature matrix construction
# ---------------------------------------------------------------------------

def _build_feature_matrix(
    entries: pd.DataFrame,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    text_mining_result: Any,
) -> pd.DataFrame:
    """Build a weekly normalized feature vector DataFrame."""
    df = entries.copy()
    df["week_start"] = df["start_dt"].dt.to_period("W").apply(lambda p: p.start_time.date())

    def _hhi(s: pd.Series) -> float:
        total = s.sum()
        if total == 0:
            return 0.0
        shares = s / total
        return float((shares ** 2).sum())

    def _shannon(s: pd.Series) -> float:
        total = s.sum()
        if total == 0:
            return 0.0
        shares = (s / total).replace(0, np.nan).dropna()
        return float(-np.sum(shares * np.log(shares + 1e-10)))

    rows = []
    for week_start, grp in df.groupby("week_start"):
        proj_hours = grp.groupby("project_name")["duration_hours"].sum()
        total_hours = proj_hours.sum()
        hhi = _hhi(proj_hours)
        entropy = _shannon(proj_hours)
        top_conc = float(proj_hours.max() / total_hours) if total_hours > 0 else 0.0
        weekend_ratio = float(grp["is_weekend"].mean())
        avg_dur = float(grp["duration"].mean() / 60)  # minutes
        n_active = grp["start_date"].nunique()

        rows.append({
            "week_start": str(week_start),
            "total_hours": total_hours,
            "hhi": hhi,
            "entropy": entropy,
            "top_project_concentration": top_conc,
            "weekend_ratio": weekend_ratio,
            "avg_duration_min": avg_dur,
            "active_days": n_active,
            "unique_projects": grp["project_name"].nunique(),
        })

    feat = pd.DataFrame(rows).sort_values("week_start").reset_index(drop=True)

    # Add dominant LDA topic per week if available
    if (text_mining_result is not None
            and text_mining_result.entry_topic_probs is not None
            and text_mining_result.entry_topic_labels is not None):
        # Map entry index back to week_start
        # text_mining_result.entry_topic_labels is a Series indexed by corpus_df rows
        corpus_entries = entries[
            entries["description"].notna() & (entries["description"].str.strip() != "")
        ].copy().reset_index(drop=True)
        corpus_entries["nmf_topic"] = text_mining_result.entry_topic_labels.values

        corpus_entries["week_start"] = corpus_entries["start_dt"].dt.to_period("W").apply(
            lambda p: str(p.start_time.date())
        )
        dominant_topic_per_week = (
            corpus_entries.groupby("week_start")["nmf_topic"]
            .agg(lambda x: x.value_counts().idxmax())
        )
        feat = feat.join(dominant_topic_per_week.rename("dominant_topic"), on="week_start", how="left")
        feat["dominant_topic"] = feat["dominant_topic"].fillna(-1).astype(int)
    else:
        feat["dominant_topic"] = 0

    return feat


# ---------------------------------------------------------------------------
# Boundary detection
# ---------------------------------------------------------------------------

def _detect_phase_boundaries(feature_df: pd.DataFrame) -> list[int]:
    """
    Run PELT on each feature dimension, then aggregate.
    A week is a phase boundary if ≥3 features have a changepoint within ±2 weeks.
    """
    scaler = StandardScaler()
    feature_cols = [
        "total_hours", "hhi", "entropy", "top_project_concentration",
        "weekend_ratio", "avg_duration_min", "active_days",
    ]
    X = feature_df[feature_cols].fillna(0.0).values
    X_scaled = scaler.fit_transform(X)

    all_cp_votes = np.zeros(len(feature_df), dtype=int)

    for dim in range(X_scaled.shape[1]):
        signal = X_scaled[:, dim].reshape(-1, 1)
        try:
            algo = rpt.Pelt(model="rbf", min_size=6, jump=1).fit(signal)
            # Use a moderate penalty
            bkps = algo.predict(pen=3.0)
            for bp in bkps[:-1]:
                # Vote within ±2 weeks window
                for offset in range(-2, 3):
                    idx = bp + offset
                    if 0 <= idx < len(all_cp_votes):
                        all_cp_votes[idx] += 1
        except Exception:
            continue

    # Phase boundary = week with ≥3 signal votes (excluding first/last 4 weeks)
    boundaries = [
        i for i in range(4, len(feature_df) - 4)
        if all_cp_votes[i] >= 3
    ]

    # Suppress boundaries within 6 weeks of each other (keep highest-vote one)
    if not boundaries:
        return []

    merged = [boundaries[0]]
    for b in boundaries[1:]:
        if b - merged[-1] >= 6:
            merged.append(b)
        elif all_cp_votes[b] > all_cp_votes[merged[-1]]:
            merged[-1] = b

    return merged


# ---------------------------------------------------------------------------
# Phase characterization
# ---------------------------------------------------------------------------

def _intensity_label(avg_hours: float) -> str:
    for (lo, hi), label in _INTENSITY_LABELS.items():
        if lo <= avg_hours < hi:
            return label
    return "Unknown"


def _characterize_phases(
    entries: pd.DataFrame,
    feature_df: pd.DataFrame,
    boundaries: list[int],
    text_mining_result: Any,
) -> list[LifePhase]:
    """Build a LifePhase object for each detected segment."""
    week_starts = feature_df["week_start"].tolist()
    all_dates = [pd.to_datetime(w) for w in week_starts]

    # Segment indices: add start and end
    segment_starts = [0] + boundaries
    segment_ends = boundaries + [len(feature_df)]

    # Prepare LDA topic keywords if available
    topic_keywords: dict[int, str] = {}
    if text_mining_result is not None and hasattr(text_mining_result, "tables"):
        for label, tbl in text_mining_result.tables:
            if "NMF" in label and not tbl.empty:
                for _, row in tbl.iterrows():
                    topic_id_str = row.get("Topic", "T00")[1:]
                    try:
                        tid = int(topic_id_str)
                        keywords = row.get("Keywords", "")
                        topic_keywords[tid] = keywords.split(",")[0].strip() if keywords else f"topic {tid}"
                    except ValueError:
                        pass

    phases: list[LifePhase] = []
    for seg_start, seg_end in zip(segment_starts, segment_ends):
        seg_feat = feature_df.iloc[seg_start:seg_end]
        if seg_feat.empty:
            continue

        seg_start_date = all_dates[seg_start]
        seg_end_date = all_dates[min(seg_end - 1, len(all_dates) - 1)]
        duration_days = (seg_end_date - seg_start_date).days + 7

        # Filter entries for this period
        seg_entries = entries[
            (entries["start_dt"] >= seg_start_date) &
            (entries["start_dt"] <= seg_end_date + pd.Timedelta(days=7))
        ]

        if seg_entries.empty:
            continue

        avg_hours_day = float(
            seg_entries["duration_hours"].sum() / max(1, seg_entries["start_date"].nunique())
        )
        focus_hhi = float(seg_feat["hhi"].mean())
        weekend_ratio = float(seg_feat["weekend_ratio"].mean())

        # Consistency as inverse of CoV
        daily_hours = seg_entries.groupby("start_date")["duration_hours"].sum()
        cov = float(daily_hours.std() / daily_hours.mean()) if daily_hours.mean() > 0 else 1.0
        consistency = max(0.0, 1.0 - min(1.0, cov))

        top_projects = (
            seg_entries.groupby("project_name")["duration_hours"]
            .sum()
            .nlargest(3)
            .index.tolist()
        )

        # Dominant topics
        dominant_topic_ids = (
            seg_feat["dominant_topic"]
            .value_counts()
            .head(3)
            .index.tolist()
        )
        top_topics = [
            topic_keywords.get(int(tid), f"Topic {tid}")
            for tid in dominant_topic_ids
            if tid >= 0
        ]

        intensity = _intensity_label(avg_hours_day)

        # Auto-label: intensity + top project + top topic if available
        proj_label = top_projects[0][:20] if top_projects else "Mixed"
        topic_label = f" / {top_topics[0][:15]}" if top_topics else ""
        label = f"{intensity}: {proj_label}{topic_label}"

        phases.append(LifePhase(
            label=label,
            start=seg_start_date.strftime("%Y-%m-%d"),
            end=seg_end_date.strftime("%Y-%m-%d"),
            duration_days=duration_days,
            avg_hours_day=avg_hours_day,
            focus_hhi=focus_hhi,
            top_projects=top_projects,
            top_topics=top_topics,
            weekend_ratio=weekend_ratio,
            consistency=consistency,
            intensity=intensity,
        ))

    return phases


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _gantt_chart(phases: list[LifePhase], daily: pd.DataFrame) -> go.Figure:
    """
    Timeline / Gantt chart: phases as colored horizontal bands,
    overlaid on the daily hours time series.
    """
    fig = go.Figure()

    # Background phase bands
    for i, phase in enumerate(phases):
        color = _NEON[i % len(_NEON)]
        fig.add_vrect(
            x0=phase.start, x1=phase.end,
            fillcolor=color,
            opacity=0.06,
            line_width=0,
            annotation_text=f"{phase.label[:25]}…" if len(phase.label) > 25 else phase.label,
            annotation_position="top left",
            annotation_font=dict(size=9, color=color),
        )
        fig.add_vline(
            x=phase.start,
            line_color=color, line_width=1, line_dash="dot",
        )

    # Daily hours line
    if not daily.empty:
        d = daily.sort_values("date_dt")
        r90 = d.set_index("date_dt")["hours"].rolling(90, min_periods=30).mean()
        fig.add_trace(go.Scatter(
            x=d["date_dt"].tolist(), y=d["hours"].tolist(),
            mode="lines", name="Daily hours",
            line=dict(color=_C["muted"], width=0.8),
            hovertemplate="%{x|%Y-%m-%d}: %{y:.1f}h<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=r90.index.tolist(), y=r90.values.tolist(),
            mode="lines", name="90-day avg",
            line=dict(color=_C["text"], width=2),
            hovertemplate="%{x|%Y-%m-%d}: %{y:.2f}h<extra></extra>",
        ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Life Phase Timeline", font=dict(color=_C["gold"])),
        height=500,
        yaxis=dict(title="Hours tracked", gridcolor=_C["grid"]),
        xaxis=dict(title="", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"]),
        hovermode="x unified",
    )
    return fig


def _radar_chart(phases: list[LifePhase], max_phases: int = 8) -> go.Figure:
    """Spider/radar chart comparing phases on normalized metrics."""
    # Limit to most recent max_phases to keep readable
    display_phases = phases[-max_phases:] if len(phases) > max_phases else phases

    categories = ["Intensity", "Focus (HHI)", "Consistency", "Weekend %", "Diversity"]

    # Normalize values to 0–1
    max_hours = max((p.avg_hours_day for p in phases), default=1.0)

    fig = go.Figure()
    for i, phase in enumerate(display_phases):
        values = [
            min(1.0, phase.avg_hours_day / max(max_hours, 0.01)),
            phase.focus_hhi,
            phase.consistency,
            phase.weekend_ratio,
            1.0 - phase.focus_hhi,  # diversity = inverse of focus
        ]
        values += [values[0]]  # close the loop
        color = _NEON[i % len(_NEON)]
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=categories + [categories[0]],
            fill="toself",
            name=phase.label[:30],
            line=dict(color=color),
            fillcolor=_hex_to_rgba(color, 0.08) if color.startswith("#") else color,
            opacity=0.8,
        ))

    fig.update_layout(
        paper_bgcolor=_C["bg"],
        plot_bgcolor=_C["bg2"],
        font=dict(color=_C["text"], family="monospace"),
        title=dict(text="Phase Comparison Radar", font=dict(color=_C["gold"])),
        height=520,
        polar=dict(
            bgcolor=_C["bg2"],
            radialaxis=dict(
                visible=True, range=[0, 1],
                gridcolor=_C["grid"], linecolor=_C["border"],
                tickfont=dict(color=_C["muted"], size=9),
            ),
            angularaxis=dict(
                gridcolor=_C["grid"], linecolor=_C["border"],
                tickfont=dict(color=_C["text"]),
            ),
        ),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"], font=dict(size=9)),
        margin=dict(l=80, r=80, t=80, b=50),
    )
    return fig


def _phase_comparison_chart(phases: list[LifePhase]) -> go.Figure:
    """Grouped horizontal bar chart of key metrics per phase."""
    labels = [p.label[:30] for p in phases]

    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=["Avg Hours/Day", "Focus (HHI)", "Weekend Ratio %"],
    )

    def _bars(values: list[float], color: str, col: int, text_fmt: str = "{:.1f}"):
        fig.add_trace(go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=color,
            text=[text_fmt.format(v) for v in values],
            textposition="inside",
            textfont=dict(color=_C["bg"], size=9),
            showlegend=False,
            hovertemplate="%{y}: %{x}<extra></extra>",
        ), row=1, col=col)

    _bars([p.avg_hours_day for p in phases], _C["cyan"], 1)
    _bars([p.focus_hhi for p in phases], _C["gold"], 2, "{:.2f}")
    _bars([p.weekend_ratio * 100 for p in phases], _C["amber"], 3, "{:.0f}%")

    for ann in fig.layout.annotations:
        ann.font = dict(color=_C["muted"], size=10, family="monospace")

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Phase-by-Phase Metric Comparison", font=dict(color=_C["cyan"])),
        height=max(320, 50 * len(phases) + 120),
    )
    fig.update_xaxes(gridcolor=_C["grid"])
    fig.update_yaxes(gridcolor=_C["grid"], tickfont=dict(size=9))
    return fig
