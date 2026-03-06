"""
Activity correlation and network analyzer.

Answers: Which activities crowd each other out? What are my actual trade-offs?
Covers weekly co-occurrence matrix, crowding-out analysis, trade-off pairs,
KMeans week archetypes, lead/lag cross-correlations, and a network graph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from sklearn.cluster import KMeans
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

_MIN_PROJECTS = 4
_N_ARCHETYPES = 7
_TOP_N = 20


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
        name="correlations",
        title="Activity Correlations & Trade-Offs",
    )

    if weekly.empty or weekly.shape[1] < _MIN_PROJECTS:
        result.narrative = "Insufficient project data for correlation analysis."
        return result

    figs: list[go.Figure] = []
    tables: list[tuple[str, pd.DataFrame]] = []
    summary: dict[str, Any] = {}

    # Drop columns that are almost always zero (< 5% non-zero weeks)
    nonzero_frac = (weekly > 0).mean()
    active_projects = nonzero_frac[nonzero_frac >= 0.05].index.tolist()
    w = weekly[active_projects].copy()

    if w.shape[1] < _MIN_PROJECTS:
        result.narrative = "Too few consistently-tracked projects for correlation analysis."
        return result

    # 1. Correlation heatmap
    corr_matrix = w.corr()
    fig_corr = _correlation_heatmap(corr_matrix)
    figs.append(fig_corr)

    # 2. Crowding-out analysis for top-5 projects
    top5_projects = w.sum().nlargest(5).index.tolist()
    fig_crowding = _crowding_out(w, top5_projects)
    figs.append(fig_crowding)

    # 3. Trade-off pairs (most negative correlations)
    tradeoff_df, fig_scatter = _tradeoff_pairs(w, corr_matrix, n=5)
    figs.append(fig_scatter)
    tables.append(("Top Trade-Off Pairs (Negative Correlations)", tradeoff_df))
    if not tradeoff_df.empty:
        top_pair = tradeoff_df.iloc[0]
        summary["strongest_tradeoff"] = f"{top_pair['Project A']} ↔ {top_pair['Project B']} (r={top_pair['Correlation']})"

    # 4. Week archetypes (KMeans)
    if _HAS_SKLEARN:
        archetype_labels, archetype_profiles, fig_archetype = _week_archetypes(w, weekly)
        figs.append(fig_archetype)
        tables.append(("Week Archetype Profiles", archetype_profiles))
        summary["n_archetypes"] = len(archetype_profiles)
    else:
        summary["n_archetypes"] = 0

    # 5. Lead/lag cross-correlations
    fig_lag = _lead_lag_chart(w, corr_matrix)
    figs.append(fig_lag)

    # 6. Network graph
    fig_network = _network_graph(w, corr_matrix)
    figs.append(fig_network)

    summary["projects_analyzed"] = len(active_projects)
    summary["weeks_analyzed"] = len(w)

    result.figures = figs
    result.tables = tables
    result.summary = summary
    result.narrative = (
        f"Analyzed {len(active_projects)} consistently-tracked projects across "
        f"{len(w)} weeks. "
        + (f"Strongest trade-off: {summary.get('strongest_tradeoff', 'N/A')}." if summary.get('strongest_tradeoff') else "")
    )
    return result


# ---------------------------------------------------------------------------
# Individual analyses
# ---------------------------------------------------------------------------

def _correlation_heatmap(corr_matrix: pd.DataFrame) -> go.Figure:
    """Heatmap of pairwise project hour correlations."""
    labels = corr_matrix.columns.tolist()
    z = corr_matrix.values.tolist()

    fig = go.Figure(go.Heatmap(
        z=z, x=labels, y=labels,
        colorscale=[
            [0.0,  _C["magenta"]],
            [0.5,  _C["bg2"]],
            [1.0,  _C["cyan"]],
        ],
        zmid=0, zmin=-1, zmax=1,
        hovertemplate="<b>%{y}</b> × <b>%{x}</b><br>r = %{z:.2f}<extra></extra>",
        colorbar=dict(
            title=dict(text="Pearson r", font=dict(color=_C["text"])),
            tickfont=dict(color=_C["text"]),
            bgcolor=_C["bg3"],
            outlinecolor=_C["border"],
        ),
    ))
    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Weekly Project Co-Occurrence Correlation Matrix", font=dict(color=_C["cyan"])),
        height=max(400, 28 * len(labels) + 100),
        xaxis=dict(tickangle=-45, tickfont=dict(size=9)),
        yaxis=dict(tickfont=dict(size=9)),
    )
    return fig


def _crowding_out(w: pd.DataFrame, spotlight_projects: list[str]) -> go.Figure:
    """
    For each spotlight project: compare mean hours of other projects
    during high vs. low weeks for that project.
    """
    others = [c for c in w.columns if c not in spotlight_projects]
    if not others:
        fig = go.Figure()
        fig.update_layout(**_LAYOUT, title=dict(text="Crowding-out (insufficient data)"))
        return fig

    n = len(spotlight_projects)
    fig = make_subplots(
        rows=1, cols=n,
        subplot_titles=spotlight_projects,
        shared_yaxes=False,
    )

    for col_i, proj in enumerate(spotlight_projects, 1):
        q75 = w[proj].quantile(0.75)
        q25 = w[proj].quantile(0.25)
        high_weeks = w[w[proj] >= q75]
        low_weeks = w[w[proj] <= q25]

        # Top-6 most affected others
        deltas = {}
        for other in others[:_TOP_N]:
            high_mean = high_weeks[other].mean() if len(high_weeks) > 2 else 0.0
            low_mean = low_weeks[other].mean() if len(low_weeks) > 2 else 0.0
            deltas[other] = high_mean - low_mean

        delta_s = pd.Series(deltas).sort_values()
        top_crowded = pd.concat([delta_s.head(4), delta_s.tail(3)])

        colors = [_C["magenta"] if v < 0 else _C["cyan"] for v in top_crowded.values]
        fig.add_trace(go.Bar(
            x=top_crowded.values.tolist(),
            y=top_crowded.index.tolist(),
            orientation="h",
            marker_color=colors,
            name=proj,
            showlegend=False,
            hovertemplate=f"When <b>{proj}</b> spikes: %{{y}} %{{x:+.1f}}h/wk<extra></extra>",
        ), row=1, col=col_i)

    for ann in fig.layout.annotations:
        ann.font = dict(color=_C["muted"], size=10, family="monospace")

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Crowding-Out Effect: What Gets Displaced When a Project Spikes?", font=dict(color=_C["magenta"])),
        height=420,
        hovermode="y unified",
    )
    fig.update_xaxes(gridcolor=_C["grid"], zerolinecolor=_C["grid"])
    fig.update_yaxes(tickfont=dict(size=9))
    return fig


def _tradeoff_pairs(
    w: pd.DataFrame,
    corr_matrix: pd.DataFrame,
    n: int = 5,
) -> tuple[pd.DataFrame, go.Figure]:
    """Find and visualize the most negatively correlated project pairs."""
    # Upper triangle only
    pairs = []
    cols = corr_matrix.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr_matrix.iloc[i, j]
            pairs.append((cols[i], cols[j], round(float(r), 3)))

    pairs.sort(key=lambda x: x[2])  # ascending = most negative first
    top_neg = pairs[:n]
    top_pos = sorted(pairs, key=lambda x: -x[2])[:3]

    rows = []
    for a, b, r in top_neg:
        rows.append({"Project A": a, "Project B": b, "Correlation": r, "Type": "Trade-off"})
    for a, b, r in top_pos:
        rows.append({"Project A": a, "Project B": b, "Correlation": r, "Type": "Aligned"})

    table = pd.DataFrame(rows)

    # Scatter subplots for top-3 negative pairs
    n_plots = min(3, len(top_neg))
    if n_plots == 0:
        fig = go.Figure()
        fig.update_layout(**_LAYOUT, title=dict(text="Trade-off Pairs (no data)"))
        return table, fig

    fig = make_subplots(
        rows=1, cols=n_plots,
        subplot_titles=[f"{a} vs {b} (r={r})" for a, b, r in top_neg[:n_plots]],
    )
    for i, (a, b, r) in enumerate(top_neg[:n_plots], 1):
        fig.add_trace(go.Scatter(
            x=w[a].tolist(), y=w[b].tolist(),
            mode="markers",
            marker=dict(color=_C["magenta"], size=4, opacity=0.5),
            name=f"{a} vs {b}",
            showlegend=False,
            hovertemplate=f"{a}: %{{x:.1f}}h<br>{b}: %{{y:.1f}}h<extra></extra>",
        ), row=1, col=i)

    for ann in fig.layout.annotations:
        ann.font = dict(color=_C["muted"], size=9, family="monospace")

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Top Trade-Off Pairs (Weekly Hours Scatter)", font=dict(color=_C["magenta"])),
        height=360,
    )
    fig.update_xaxes(gridcolor=_C["grid"], tickfont=dict(size=8))
    fig.update_yaxes(gridcolor=_C["grid"], tickfont=dict(size=8))
    return table, fig


def _week_archetypes(
    w: pd.DataFrame,
    weekly_full: pd.DataFrame,
    n_clusters: int = _N_ARCHETYPES,
) -> tuple[pd.Series, pd.DataFrame, go.Figure]:
    """
    KMeans clustering of weeks into archetypes based on project hour profiles.
    """
    scaler = StandardScaler()
    w_scaled = scaler.fit_transform(w.fillna(0.0))

    # Auto-select k if fewer weeks than requested
    k = min(n_clusters, len(w) // 5, 10)
    if k < 2:
        fig = go.Figure()
        fig.update_layout(**_LAYOUT, title=dict(text="Week Archetypes (insufficient data)"))
        return pd.Series(dtype=int), pd.DataFrame(), fig

    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(w_scaled)
    label_series = pd.Series(labels, index=w.index, name="archetype")

    # Profile each archetype
    w_labeled = w.copy()
    w_labeled["archetype"] = labels
    w_labeled["year_week"] = weekly_full.index if len(weekly_full) == len(w) else w.index

    profiles = (
        w_labeled.drop(columns=["archetype", "year_week"], errors="ignore")
        .groupby(w_labeled["archetype"])
        .mean()
        .round(2)
    )

    # Name each archetype by its top-2 projects
    archetype_names: dict[int, str] = {}
    for arch_id in range(k):
        top2 = profiles.loc[arch_id].nlargest(2).index.tolist()
        archetype_names[arch_id] = " + ".join(t[:18] for t in top2) or f"Archetype {arch_id}"

    # Count frequency per year
    w_labeled["year"] = [
        idx[:4] if isinstance(idx, str) else str(idx)[:4]
        for idx in w_labeled.index
    ]
    freq_by_year = (
        w_labeled.groupby(["year", "archetype"])
        .size()
        .unstack(fill_value=0)
        .rename(columns=archetype_names)
    )

    # Rename profiles index
    # Ensure unique archetype names
    seen: dict[str, int] = {}
    unique_names: dict[int, str] = {}
    for arch_id, name in archetype_names.items():
        if name in seen:
            seen[name] += 1
            unique_names[arch_id] = f"{name} ({seen[name]})"
        else:
            seen[name] = 0
            unique_names[arch_id] = name
    archetype_names = unique_names

    profiles.index = [archetype_names.get(i, str(i)) for i in profiles.index]

    # Stacked bar: archetype frequency by year
    fig = go.Figure()
    for i in range(len(freq_by_year.columns)):
        arch_name = archetype_names.get(i, str(i))
        col_data = freq_by_year.iloc[:, i]
        fig.add_trace(go.Bar(
            x=freq_by_year.index.tolist(),
            y=col_data.tolist(),
            name=arch_name[:30],
            marker_color=_NEON[i % len(_NEON)],
            hovertemplate=f"<b>{arch_name}</b> %{{x}}: %{{y}} weeks<extra></extra>",
        ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Week Archetypes by Year (KMeans Clustering)", font=dict(color=_C["green"])),
        height=420,
        barmode="stack",
        xaxis=dict(title="Year"),
        yaxis=dict(title="Number of weeks"),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"], font=dict(size=9)),
    )
    return label_series, profiles, fig


def _lead_lag_chart(w: pd.DataFrame, corr_matrix: pd.DataFrame, max_lag: int = 4) -> go.Figure:
    """
    Cross-correlogram for top-5 most interesting project pairs (mixed positive/negative).
    """
    cols = corr_matrix.columns.tolist()
    pairs_neg = []
    pairs_pos = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr_matrix.iloc[i, j]
            if abs(r) > 0.15:
                if r < 0:
                    pairs_neg.append((cols[i], cols[j], r))
                else:
                    pairs_pos.append((cols[i], cols[j], r))

    pairs_neg.sort(key=lambda x: x[2])
    selected = pairs_neg[:2] + sorted(pairs_pos, key=lambda x: -x[2])[:2]

    if not selected:
        fig = go.Figure()
        fig.update_layout(**_LAYOUT, title=dict(text="Lead/Lag (insufficient correlated pairs)"))
        return fig

    lags = list(range(-max_lag, max_lag + 1))
    fig = go.Figure()
    for i, (a, b, _) in enumerate(selected):
        xcorr = []
        for lag in lags:
            if lag == 0:
                r = w[a].corr(w[b])
            elif lag > 0:
                r = w[a][:-lag].corr(w[b].shift(-lag)[:-lag])
            else:
                r = w[a][-lag:].corr(w[b].shift(-lag)[-lag:])
            xcorr.append(float(r) if not np.isnan(r) else 0.0)

        color = _NEON[i % len(_NEON)]
        fig.add_trace(go.Scatter(
            x=lags, y=xcorr,
            mode="lines+markers",
            name=f"{a[:12]} / {b[:12]}",
            line=dict(color=color, width=1.5),
            marker=dict(color=color, size=6),
            hovertemplate=f"<b>{a} / {b}</b> lag %{{x}} wks: r=%{{y:.3f}}<extra></extra>",
        ))

    fig.add_hline(y=0, line_color=_C["muted"], line_width=1)
    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Lead/Lag Cross-Correlations (weeks offset)", font=dict(color=_C["gold"])),
        height=380,
        xaxis=dict(title="Lag (weeks)", tickvals=lags, gridcolor=_C["grid"]),
        yaxis=dict(title="Pearson r", range=[-1, 1], gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"], font=dict(size=9)),
        hovermode="x unified",
    )
    return fig


def _network_graph(w: pd.DataFrame, corr_matrix: pd.DataFrame, min_r: float = 0.2) -> go.Figure:
    """
    Plotly network graph: nodes = projects (sized by total hours),
    edges = significant correlations, colored by sign.
    """
    # Node sizes proportional to total hours
    node_sizes = w.sum()
    max_size = node_sizes.max()
    nodes = corr_matrix.columns.tolist()

    # Use a simple circular layout
    n = len(nodes)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False)
    node_x = np.cos(angles).tolist()
    node_y = np.sin(angles).tolist()
    pos = {node: (node_x[i], node_y[i]) for i, node in enumerate(nodes)}

    edge_traces: list[go.Scatter] = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            r = corr_matrix.iloc[i, j]
            if abs(r) < min_r:
                continue
            a, b = nodes[i], nodes[j]
            color = _C["cyan"] if r > 0 else _C["magenta"]
            width = max(0.5, abs(r) * 4)
            edge_traces.append(go.Scatter(
                x=[pos[a][0], pos[b][0], None],
                y=[pos[a][1], pos[b][1], None],
                mode="lines",
                line=dict(color=color, width=width),
                hoverinfo="skip",
                showlegend=False,
            ))

    # Node sizes scaled to 8–40px
    sizes = [max(8, min(40, float(node_sizes.get(nd, 0)) / max_size * 40)) for nd in nodes]

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=nodes,
        textposition="top center",
        textfont=dict(size=9, color=_C["text"]),
        marker=dict(
            size=sizes,
            color=_C["gold"],
            line=dict(color=_C["border"], width=1),
        ),
        hovertemplate="<b>%{text}</b><br>Total hours: %{customdata:.0f}<extra></extra>",
        customdata=[float(node_sizes.get(nd, 0)) for nd in nodes],
        showlegend=False,
    )

    # Legend entries for edge colors
    dummy_pos = go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color=_C["cyan"], width=2),
        name="Positive correlation",
    )
    dummy_neg = go.Scatter(
        x=[None], y=[None], mode="lines",
        line=dict(color=_C["magenta"], width=2),
        name="Negative correlation",
    )

    fig = go.Figure(data=edge_traces + [node_trace, dummy_pos, dummy_neg])
    fig.update_layout(
        **_LAYOUT,
        title=dict(text=f"Activity Network Graph (|r| ≥ {min_r})", font=dict(color=_C["cyan"])),
        height=560,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"]),
    )
    return fig
