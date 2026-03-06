"""
Report renderer for the analysis module.

Converts a list of AnalysisResult objects into a single self-contained HTML
string by serializing Plotly figures (via plotly.io) and DataFrames (via
pandas .to_html()), then rendering them through the Jinja2 template at
analysis/report/template.html.

Public API:
    render_report(results, meta) -> str
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.io as pio

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    _HAS_JINJA = True
except ImportError:
    _HAS_JINJA = False

# ---------------------------------------------------------------------------
# Template location
# ---------------------------------------------------------------------------
_TEMPLATE_DIR = Path(__file__).parent
_TEMPLATE_NAME = "template.html"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fig_to_html(fig: Any) -> str:
    """Convert a Plotly Figure to an embeddable HTML div (no full page)."""
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs=False,   # Plotly.js loaded once from CDN in template
        config={"displayModeBar": True, "responsive": True},
    )


def _df_to_html(df: pd.DataFrame, max_rows: int = 50) -> str:
    """Convert a DataFrame to a styled HTML table string."""
    display_df = df.head(max_rows)
    html = display_df.to_html(
        index=True,
        border=0,
        classes="data-table",
        na_rep="—",
        float_format=lambda x: f"{x:.3g}",
    )
    return html


def _coerce_summary_values(summary: dict) -> dict:
    """Ensure all summary values are JSON-safe Python scalars for Jinja."""
    clean: dict[str, Any] = {}
    for k, v in summary.items():
        if isinstance(v, float):
            clean[k] = f"{v:.3g}"
        elif hasattr(v, "item"):
            # numpy scalar
            clean[k] = v.item()
        else:
            clean[k] = v
    return clean


# ---------------------------------------------------------------------------
# Result DTO used inside the template
# (We don't mutate the caller's AnalysisResult — build a separate view dict)
# ---------------------------------------------------------------------------

def _build_view(result: Any) -> dict:
    """Produce a template-friendly dict from any AnalysisResult dataclass."""
    figures_html = [_fig_to_html(f) for f in (result.figures or [])]

    tables_html = []
    for label, df in (result.tables or []):
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        tables_html.append((label, _df_to_html(df)))

    summary = _coerce_summary_values(result.summary or {})

    return {
        "name": result.name,
        "title": result.title,
        "summary": summary,
        "narrative": (result.narrative or "").strip(),
        "figures_html": figures_html,
        "tables_html": tables_html,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_report(results: list[Any], meta: dict) -> str:
    """
    Render the full HTML report.

    Parameters
    ----------
    results : list of AnalysisResult dataclass instances (any analyzer)
    meta    : dict from data_access.get_db_meta(), augmented by run.py with:
                  title         -- str
                  generated_at  -- str (formatted datetime)
                  db_path       -- str
                  enriched_pct  -- float
                  date_filter   -- str | None

    Returns
    -------
    str — complete HTML document ready to write to disk
    """
    if not _HAS_JINJA:
        raise ImportError(
            "jinja2 is required for report rendering. "
            "Run: pip install jinja2>=3.1.0"
        )

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template(_TEMPLATE_NAME)

    # Build view dicts for each result
    views = [_build_view(r) for r in results]

    # Augment meta with safe defaults
    full_meta = {
        "title": "Deep Dive Analysis",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "db_path": "data/toggl.db",
        "total_entries": 0,
        "total_hours": 0.0,
        "earliest_date": "—",
        "latest_date": "—",
        "years_tracked": 0,
        "unique_projects": 0,
        "enriched_pct": 0.0,
        "date_filter": None,
        **{k: v for k, v in meta.items() if v is not None},
    }

    # Coerce numpy/pandas scalars in meta
    for k, v in full_meta.items():
        if hasattr(v, "item"):
            full_meta[k] = v.item()

    return template.render(results=views, meta=full_meta)
