"""
CLI orchestrator for the Toggl Time Journal analysis module.

Loads data from data/toggl.db, runs all 6 analyzers in dependency order,
renders the HTML report via Jinja2, and writes it to disk.

Usage:
    python -m analysis [options]

Options:
    --output PATH       Path for the HTML report (default: analysis/output/report_YYYY-MM-DD.html)
    --only NAMES        Comma-separated analyzer names to run (e.g. longitudinal,rhythms)
    --start DATE        Only include entries on or after YYYY-MM-DD
    --end DATE          Only include entries on or before YYYY-MM-DD
    --no-open           Do not auto-open the report in the browser when done
    --quiet             Suppress progress output
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Analyzer name → module-level analyze() signature
# ---------------------------------------------------------------------------
_ANALYZER_NAMES = [
    "longitudinal",
    "rhythms",
    "changepoints",
    "correlations",
    "text_mining",
    "life_phases",
]

# Section ordering in the final report (same as _ANALYZER_NAMES, life_phases last)
_SECTION_ORDER = _ANALYZER_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


def _progress(step: str, quiet: bool) -> None:
    _log(f"  [{step}]", quiet)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    # Ensure stdout can handle Unicode (needed on Windows with cp1252 console)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="python -m analysis",
        description="Generate a deep-dive HTML analysis report from toggl.db",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        help="Output HTML file path (default: analysis/output/report_YYYY-MM-DD.html)",
    )
    parser.add_argument(
        "--only",
        metavar="NAMES",
        help=(
            "Comma-separated list of analyzer names to run. "
            f"Choices: {', '.join(_ANALYZER_NAMES)}"
        ),
    )
    parser.add_argument(
        "--start",
        metavar="DATE",
        help="Include entries on/after this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        metavar="DATE",
        help="Include entries on/before this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the report in the browser after generation",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress messages",
    )

    args = parser.parse_args(argv)

    # ── Validate --only ───────────────────────────────────────────────────
    selected: list[str] = _ANALYZER_NAMES
    if args.only:
        requested = [n.strip() for n in args.only.split(",") if n.strip()]
        unknown = [n for n in requested if n not in _ANALYZER_NAMES]
        if unknown:
            parser.error(
                f"Unknown analyzer(s): {', '.join(unknown)}. "
                f"Valid names: {', '.join(_ANALYZER_NAMES)}"
            )
        # Keep dependency order: always run text_mining before life_phases when both selected
        selected = [n for n in _SECTION_ORDER if n in requested]

    # ── Output path ───────────────────────────────────────────────────────
    repo_root = Path(__file__).parent.parent
    output_dir = repo_root / "analysis" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        out_path = output_dir / f"report_{date.today().isoformat()}.html"

    # ── Load data ─────────────────────────────────────────────────────────
    _log("\nToggl Time Journal — Deep Dive Analysis", args.quiet)
    _log("=" * 45, args.quiet)

    _progress("loading database metadata", args.quiet)
    from analysis.data_access import (
        get_db_meta,
        load_daily_series,
        load_entries,
        load_weekly_matrix,
    )

    try:
        meta = get_db_meta()
    except FileNotFoundError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    enriched = meta.get("enriched_entries", 0)
    total = meta.get("total_entries", 1) or 1
    meta["enriched_pct"] = 100.0 * enriched / total
    meta["title"] = "Toggl Deep Dive Analysis"
    meta["db_path"] = str(repo_root / "data" / "toggl.db")

    # Date-filter label for report header
    if args.start or args.end:
        parts = []
        if args.start:
            parts.append(f"from {args.start}")
        if args.end:
            parts.append(f"to {args.end}")
        meta["date_filter"] = " ".join(parts)
    else:
        meta["date_filter"] = None

    meta["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    _log(
        f"  Entries: {meta.get('total_entries', 0):,}  |  "
        f"Hours: {meta.get('total_hours', 0):,.0f}  |  "
        f"Range: {meta.get('earliest_date')} -> {meta.get('latest_date')}",
        args.quiet,
    )

    _progress("loading entries", args.quiet)
    entries = load_entries(start_date=args.start, end_date=args.end)

    _progress("loading daily series", args.quiet)
    daily = load_daily_series()  # daily always uses full range for context

    _progress("loading weekly matrix", args.quiet)
    weekly = load_weekly_matrix()

    if entries.empty:
        print("\nERROR: No entries found in database. Sync data first.", file=sys.stderr)
        sys.exit(1)

    # ── Run analyzers ─────────────────────────────────────────────────────
    _log("\nRunning analyzers:", args.quiet)

    results: list = []
    text_mining_result = None

    for name in selected:
        _progress(f"analyzer: {name}", args.quiet)

        if name == "longitudinal":
            from analysis.analyzers.longitudinal import analyze
            results.append(analyze(entries, daily, weekly))

        elif name == "rhythms":
            from analysis.analyzers.rhythms import analyze
            results.append(analyze(entries, daily, weekly))

        elif name == "changepoints":
            from analysis.analyzers.changepoints import analyze
            results.append(analyze(entries, daily, weekly))

        elif name == "correlations":
            from analysis.analyzers.correlations import analyze
            results.append(analyze(entries, daily, weekly))

        elif name == "text_mining":
            from analysis.analyzers.text_mining import analyze
            text_mining_result = analyze(entries, daily, weekly)
            results.append(text_mining_result)

        elif name == "life_phases":
            from analysis.analyzers.life_phases import analyze
            # Pass text_mining_result so life_phases can use LDA topic assignments.
            # If text_mining wasn't selected, text_mining_result stays None and
            # life_phases degrades gracefully.
            results.append(analyze(entries, daily, weekly, text_mining_result))

    # ── Render report ──────────────────────────────────────────────────────
    _progress("rendering HTML report", args.quiet)
    from analysis.report.renderer import render_report

    html = render_report(results, meta)

    _progress(f"writing -> {out_path}", args.quiet)
    out_path.write_text(html, encoding="utf-8")

    _log(f"\nReport written to: {out_path}", args.quiet)
    _log(f"  Size: {len(html) / 1024:.1f} KB", args.quiet)

    # ── Open in browser ────────────────────────────────────────────────────
    if not args.no_open:
        _log("  Opening in browser...", args.quiet)
        webbrowser.open(out_path.as_uri())

    _log("\nDone.", args.quiet)


if __name__ == "__main__":
    main()
