"""
Text mining and NLP analyzer.

Answers: What do 10 years of entry descriptions reveal?
Covers TF-IDF, LDA topic modeling, NMF topic modeling,
topic prevalence over time, sentiment drift, and vocabulary evolution.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

try:
    from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
    from sklearn.decomposition import NMF, LatentDirichletAllocation
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    _HAS_VADER = True
except ImportError:
    _HAS_VADER = False

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
# Embedded English stop words (no NLTK download required)
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "up", "about", "into", "through", "during",
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "shall", "can", "need", "dare", "ought", "used", "it", "its", "this",
    "that", "these", "those", "i", "me", "my", "we", "our", "you", "your",
    "he", "his", "she", "her", "they", "their", "what", "which", "who",
    "when", "where", "why", "how", "all", "each", "every", "both", "few",
    "more", "most", "other", "some", "such", "no", "not", "only", "same",
    "than", "too", "very", "just", "also", "so", "if", "then", "now", "re",
    "call", "work", "meeting", "meet", "review", "check", "update", "misc",
    "etc", "new", "vs", "via", "per", "set", "get", "follow", "follow up",
    "email", "emails", "slack", "zoom", "call", "calls", "time",
})

_N_TOPICS = 12


@dataclass
class AnalysisResult:
    name: str
    title: str
    summary: dict[str, Any] = field(default_factory=dict)
    figures: list[go.Figure] = field(default_factory=list)
    tables: list[tuple[str, pd.DataFrame]] = field(default_factory=list)
    narrative: str = ""
    # Extra: topic assignments per entry (used by life_phases)
    entry_topic_labels: pd.Series | None = None       # NMF dominant topic per entry
    entry_topic_probs: np.ndarray | None = None        # LDA probability matrix


@dataclass
class TopicModel:
    model_type: str           # "NMF" or "LDA"
    topics: list[dict]        # [{id, keywords, label}]


def analyze(entries: pd.DataFrame, daily: pd.DataFrame, weekly: pd.DataFrame) -> AnalysisResult:
    result = AnalysisResult(
        name="text_mining",
        title="Description Text Mining",
    )

    if not _HAS_SKLEARN:
        result.narrative = "scikit-learn not installed. Run: pip install scikit-learn"
        return result

    # Load corpus from entries directly (no separate DB call needed)
    corpus_df = entries[
        entries["description"].notna() & (entries["description"].str.strip() != "")
    ].copy()
    corpus_df["description"] = corpus_df["description"].str.strip()
    corpus_df = corpus_df.reset_index(drop=True)

    if len(corpus_df) < 50:
        result.narrative = "Insufficient description data for text mining (< 50 entries with text)."
        return result

    docs = corpus_df["description"].tolist()
    cleaned_docs = [_clean_text(d) for d in docs]

    figs: list[go.Figure] = []
    tables: list[tuple[str, pd.DataFrame]] = []
    summary: dict[str, Any] = {}

    # -----------------------------------------------------------------------
    # TF-IDF + NMF
    # -----------------------------------------------------------------------
    tfidf_vec = TfidfVectorizer(
        min_df=5, max_df=0.85,
        ngram_range=(1, 2),
        max_features=2000,
        stop_words=list(_STOP_WORDS),
        preprocessor=lambda x: x,  # already cleaned
    )
    try:
        X_tfidf = tfidf_vec.fit_transform(cleaned_docs)
    except ValueError:
        result.narrative = "TF-IDF vectorization failed (too few unique terms)."
        return result

    n_topics = min(_N_TOPICS, X_tfidf.shape[1] // 2)
    nmf = NMF(n_components=n_topics, random_state=42, max_iter=500)
    W_nmf = nmf.fit_transform(X_tfidf)
    nmf_topics = _extract_topics(nmf, tfidf_vec, "NMF")

    # NMF dominant topic per entry
    entry_topic_labels = pd.Series(W_nmf.argmax(axis=1), index=corpus_df.index)

    # -----------------------------------------------------------------------
    # Count matrix + LDA
    # -----------------------------------------------------------------------
    count_vec = CountVectorizer(
        min_df=5, max_df=0.85,
        ngram_range=(1, 2),
        max_features=2000,
        stop_words=list(_STOP_WORDS),
        preprocessor=lambda x: x,
    )
    try:
        X_count = count_vec.fit_transform(cleaned_docs)
    except ValueError:
        X_count = None

    if X_count is not None:
        lda = LatentDirichletAllocation(
            n_components=n_topics, random_state=42,
            max_iter=10, learning_method="online",
        )
        W_lda = lda.fit_transform(X_count)
        lda_topics = _extract_topics(lda, count_vec, "LDA")
        entry_topic_probs = W_lda   # used by life_phases
    else:
        lda_topics = []
        entry_topic_probs = None

    # -----------------------------------------------------------------------
    # Topic tables
    # -----------------------------------------------------------------------
    for model_type, topics in [("NMF", nmf_topics), ("LDA", lda_topics)]:
        if topics:
            rows = [
                {"Topic": f"T{t['id']:02d}", "Keywords": ", ".join(t["keywords"][:8])}
                for t in topics
            ]
            tables.append((f"{model_type} Topic Model — {n_topics} Topics", pd.DataFrame(rows)))

    # -----------------------------------------------------------------------
    # Topic prevalence over time (NMF)
    # -----------------------------------------------------------------------
    corpus_df["nmf_topic"] = entry_topic_labels.values
    fig_topic_time = _topic_prevalence(corpus_df, nmf_topics, "NMF Topic Prevalence Over Time")
    figs.append(fig_topic_time)

    # -----------------------------------------------------------------------
    # Sentiment drift
    # -----------------------------------------------------------------------
    if _HAS_VADER:
        fig_sentiment, mean_sentiment = _sentiment_drift(corpus_df)
        figs.append(fig_sentiment)
        summary["mean_sentiment"] = f"{mean_sentiment:+.3f}"
    else:
        summary["mean_sentiment"] = "N/A (vaderSentiment not installed)"

    # -----------------------------------------------------------------------
    # Vocabulary evolution
    # -----------------------------------------------------------------------
    vocab_df, fig_vocab = _vocabulary_evolution(corpus_df, tfidf_vec)
    figs.append(fig_vocab)
    tables.append(("Vocabulary Evolution — Emerging & Fading Terms by Year", vocab_df))

    # -----------------------------------------------------------------------
    # Description length trends
    # -----------------------------------------------------------------------
    fig_length = _description_length_trend(corpus_df)
    figs.append(fig_length)

    # -----------------------------------------------------------------------
    # Top TF-IDF terms overall
    # -----------------------------------------------------------------------
    top_terms_df = _top_terms_table(X_tfidf, tfidf_vec, n=30)
    tables.append(("Top 30 Terms by TF-IDF Score", top_terms_df))

    summary["corpus_size"] = len(corpus_df)
    summary["unique_terms"] = X_tfidf.shape[1]
    summary["n_topics"] = n_topics
    summary["top_nmf_topic"] = nmf_topics[0]["keywords"][:4] if nmf_topics else []

    result.figures = figs
    result.tables = tables
    result.summary = summary
    result.entry_topic_labels = entry_topic_labels
    result.entry_topic_probs = entry_topic_probs
    result.narrative = (
        f"Analyzed {len(corpus_df):,} entry descriptions ({summary['unique_terms']:,} unique terms). "
        f"Extracted {n_topics} topics via NMF and LDA. "
        + (f"Mean sentiment: {summary['mean_sentiment']}." if _HAS_VADER else "")
    )
    return result


# ---------------------------------------------------------------------------
# Text preprocessing
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Lowercase, remove punctuation, filter stop words and short tokens."""
    text = text.lower()
    text = re.sub(r"https?://\S+", " ", text)
    text = text.translate(str.maketrans(string.punctuation, " " * len(string.punctuation)))
    tokens = [
        t for t in text.split()
        if len(t) >= 3 and t not in _STOP_WORDS and not t.isdigit()
    ]
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# Topic extraction helper
# ---------------------------------------------------------------------------

def _extract_topics(
    model: Any,
    vectorizer: Any,
    model_type: str,
    n_top_words: int = 12,
) -> list[dict]:
    feature_names = vectorizer.get_feature_names_out()
    topics = []
    for topic_id, component in enumerate(model.components_):
        top_indices = component.argsort()[-n_top_words:][::-1]
        keywords = [feature_names[i] for i in top_indices]
        topics.append({"id": topic_id, "keywords": keywords, "model": model_type})
    return topics


# ---------------------------------------------------------------------------
# Topic prevalence over time
# ---------------------------------------------------------------------------

def _topic_prevalence(
    corpus_df: pd.DataFrame,
    topics: list[dict],
    title: str,
) -> go.Figure:
    """Stacked area chart of NMF topic share of hours by quarter."""
    corpus_df = corpus_df.copy()

    # Hours per topic per quarter
    quarterly = (
        corpus_df.groupby(["quarter", "nmf_topic"])["duration_hours"]
        .sum()
        .unstack(fill_value=0.0)
    )
    row_totals = quarterly.sum(axis=1)
    pct = quarterly.div(row_totals, axis=0) * 100

    # Build keyword labels for each topic id
    topic_labels = {
        t["id"]: f"T{t['id']:02d}: {', '.join(t['keywords'][:3])}"
        for t in topics
    }

    fig = go.Figure()
    for col in sorted(pct.columns):
        color = _NEON[col % len(_NEON)]
        label = topic_labels.get(col, f"Topic {col}")
        fig.add_trace(go.Scatter(
            x=pct.index.tolist(),
            y=pct[col].tolist(),
            name=label[:40],
            stackgroup="one",
            mode="lines",
            line=dict(width=0.5, color=color),
            hovertemplate=f"<b>{label}</b><br>%{{x}}: %{{y:.1f}}%<extra></extra>",
        ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text=title, font=dict(color=_C["purple"])),
        height=460,
        yaxis=dict(title="% of hours in that topic", gridcolor=_C["grid"]),
        xaxis=dict(title="Quarter", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"], font=dict(size=9)),
        hovermode="x unified",
    )
    return fig


# ---------------------------------------------------------------------------
# Sentiment drift
# ---------------------------------------------------------------------------

def _sentiment_drift(corpus_df: pd.DataFrame) -> tuple[go.Figure, float]:
    """Rolling 90-day mean VADER compound sentiment. Scores a sample for speed."""
    analyzer = SentimentIntensityAnalyzer()

    def score(text: str) -> float:
        return float(analyzer.polarity_scores(str(text))["compound"])

    corpus_df = corpus_df.copy().sort_values("start_date")

    # Sample up to 4000 entries for scoring (VADER is slow on 50k+)
    _MAX_SENTIMENT_ENTRIES = 4000
    if len(corpus_df) > _MAX_SENTIMENT_ENTRIES:
        sample_df = corpus_df.sample(_MAX_SENTIMENT_ENTRIES, random_state=42).sort_values("start_date")
    else:
        sample_df = corpus_df

    sample_df = sample_df.copy()
    sample_df["sentiment"] = sample_df["description"].apply(score)
    sample_df["start_dt_local"] = pd.to_datetime(sample_df["start_date"])
    sample_df = sample_df.sort_values("start_dt_local")

    # Rolling 90-day window on the sample
    rolling = (
        sample_df.set_index("start_dt_local")["sentiment"]
        .rolling("90D", min_periods=20)
        .mean()
    )
    mean_sentiment = float(sample_df["sentiment"].mean())

    # Yearly mean line
    yearly = sample_df.groupby("start_year")["sentiment"].mean()

    fig = make_subplots(
        rows=2, cols=1, row_heights=[0.65, 0.35],
        shared_xaxes=True, vertical_spacing=0.08,
        subplot_titles=["90-Day Rolling Sentiment (VADER Compound)", "Yearly Average Sentiment"],
    )

    fig.add_trace(go.Scatter(
        x=rolling.index, y=rolling.values,
        mode="lines", name="90-day sentiment",
        line=dict(color=_C["cyan"], width=2),
        fill="tozeroy",
        fillcolor="rgba(0,255,249,0.06)",
        hovertemplate="%{x|%Y-%m-%d}: %{y:+.3f}<extra></extra>",
    ), row=1, col=1)
    fig.add_hline(y=0, line_color=_C["muted"], line_width=1, row=1, col=1)

    colors = [_C["cyan"] if v >= 0 else _C["magenta"] for v in yearly.values]
    fig.add_trace(go.Bar(
        x=[str(int(y)) for y in yearly.index],
        y=yearly.values.tolist(),
        marker_color=colors,
        name="Yearly avg",
        hovertemplate="%{x}: %{y:+.3f}<extra></extra>",
    ), row=2, col=1)
    fig.add_hline(y=0, line_color=_C["muted"], line_width=1, row=2, col=1)

    for ann in fig.layout.annotations:
        ann.font = dict(color=_C["muted"], size=11, family="monospace")

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Sentiment Drift in Entry Descriptions", font=dict(color=_C["cyan"])),
        height=540,
        yaxis=dict(title="VADER compound (-1 to +1)", gridcolor=_C["grid"]),
        legend=dict(bgcolor=_C["bg3"], bordercolor=_C["border"]),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor=_C["grid"])
    fig.update_yaxes(gridcolor=_C["grid"])
    return fig, mean_sentiment


# ---------------------------------------------------------------------------
# Vocabulary evolution
# ---------------------------------------------------------------------------

def _vocabulary_evolution(
    corpus_df: pd.DataFrame,
    tfidf_vec: Any,
    top_per_year: int = 8,
) -> tuple[pd.DataFrame, go.Figure]:
    """Track which terms appear/disappear across years."""
    years = sorted(corpus_df["start_year"].dropna().unique().astype(int).tolist())

    year_top_terms: dict[int, set[str]] = {}
    for yr in years:
        subset = corpus_df[corpus_df["start_year"] == yr]["description"].tolist()
        if not subset:
            continue
        try:
            local_vec = TfidfVectorizer(
                min_df=2, max_df=0.9, max_features=200,
                stop_words=list(_STOP_WORDS),
                preprocessor=lambda x: x,
            )
            X = local_vec.fit_transform([_clean_text(d) for d in subset])
            scores = X.sum(axis=0).A1
            top_idx = scores.argsort()[-top_per_year:][::-1]
            terms = set(local_vec.get_feature_names_out()[i] for i in top_idx)
        except Exception:
            terms = set()
        year_top_terms[yr] = terms

    rows = []
    for i, yr in enumerate(years):
        current = year_top_terms.get(yr, set())
        prev = year_top_terms.get(yr - 1, set()) if i > 0 else set()
        future = year_top_terms.get(yr + 1, set()) if i < len(years) - 1 else set()

        emerging = sorted(current - prev)[:5]
        fading = sorted(prev - current - future)[:5] if prev else []

        rows.append({
            "Year": yr,
            "Emerging Terms": ", ".join(emerging) if emerging else "—",
            "Fading Terms": ", ".join(fading) if fading else "—",
        })

    vocab_df = pd.DataFrame(rows)

    # Simple heatmap: term presence per year for top-30 total terms
    all_terms: dict[str, int] = {}
    for terms in year_top_terms.values():
        for t in terms:
            all_terms[t] = all_terms.get(t, 0) + 1

    top_terms = sorted(all_terms, key=lambda x: -all_terms[x])[:25]
    matrix = pd.DataFrame(
        {yr: [1 if t in year_top_terms.get(yr, set()) else 0 for t in top_terms]
         for yr in years},
        index=top_terms,
    )

    fig = go.Figure(go.Heatmap(
        z=matrix.values.tolist(),
        x=[str(y) for y in years],
        y=top_terms,
        colorscale=[[0.0, _C["bg2"]], [1.0, _C["green"]]],
        hovertemplate="<b>%{y}</b> in %{x}<extra></extra>",
        showscale=False,
    ))
    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Term Presence by Year (Top-25 Terms)", font=dict(color=_C["green"])),
        height=max(300, 22 * len(top_terms) + 80),
        xaxis=dict(title="Year", tickangle=-45),
        yaxis=dict(tickfont=dict(size=9)),
    )
    return vocab_df, fig


# ---------------------------------------------------------------------------
# Description length trend
# ---------------------------------------------------------------------------

def _description_length_trend(corpus_df: pd.DataFrame) -> go.Figure:
    """Mean word count per entry description by quarter."""
    corpus_df = corpus_df.copy()
    corpus_df["word_count"] = corpus_df["description"].str.split().str.len()
    quarterly = corpus_df.groupby("quarter")["word_count"].mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=quarterly.index.tolist(),
        y=quarterly.values.tolist(),
        mode="lines+markers",
        name="Avg words/entry",
        line=dict(color=_C["amber"], width=2),
        marker=dict(color=_C["amber"], size=5),
        hovertemplate="%{x}: %{y:.1f} words avg<extra></extra>",
    ))

    fig.update_layout(
        **_LAYOUT,
        title=dict(text="Average Description Length Over Time (words per entry)", font=dict(color=_C["amber"])),
        height=320,
        yaxis=dict(title="Average word count", gridcolor=_C["grid"]),
        xaxis=dict(title="Quarter", gridcolor=_C["grid"]),
    )
    return fig


# ---------------------------------------------------------------------------
# Top terms table
# ---------------------------------------------------------------------------

def _top_terms_table(X_tfidf: Any, tfidf_vec: Any, n: int = 30) -> pd.DataFrame:
    """Return top-N terms by mean TF-IDF score across the corpus."""
    scores = np.asarray(X_tfidf.mean(axis=0)).ravel()
    feature_names = tfidf_vec.get_feature_names_out()
    top_idx = scores.argsort()[-n:][::-1]
    rows = [
        {"Term": feature_names[i], "Mean TF-IDF": round(float(scores[i]), 4)}
        for i in top_idx
    ]
    return pd.DataFrame(rows)
