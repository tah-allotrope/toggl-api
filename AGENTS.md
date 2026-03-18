# Toggl Time Journal

Personal time-tracking analytics dashboard that pulls 10 years of Toggl data into SQLite and renders interactive dashboards with a cyberpunk aesthetic.

## Stack

- **Language:** Python 3.10+ (uses `X | Y` union syntax)
- **Framework:** Streamlit (requires 1.52+ for `st.navigation`)
- **Data:** Pandas, Plotly, SQLite (stdlib `sqlite3`)
- **API:** Toggl Track API v9, Toggl Reports API v3
- **Package manager:** pip

## Commands

### Legacy Streamlit Stack
```bash
pip install -r requirements.txt   # Install dependencies
streamlit run app.py              # Run locally on :8501
python -m analysis                # Generate deep-dive HTML report
python -m analysis --only longitudinal,rhythms   # Run specific analyzers
python -m analysis --start 2020-01-01 --end 2024-12-31  # Date-filtered report
python -m analysis --output path/to/report.html --no-open --quiet
```

### New Supabase + Web Stack
```bash
# Backend / Database
supabase start
supabase db reset
python scripts/sync_to_supabase.py --mode quick

# Frontend
cd web
npm install
npm run dev
```

No test framework. No linter. No type checker configured.

## Architecture

**[MIGRATION IN PROGRESS] The project is currently operating in a dual mode:**
1. **Legacy Streamlit path:** Local SQLite database, password-protected UI.
2. **New Supabase + Web path:** Supabase Postgres, Edge Functions, React/Vite frontend with Supabase Auth.

### Legacy Streamlit
- 4 Streamlit pages behind `st.navigation` (Homepage, Dashboard, Retrospect, Chat)
- API client with sliding-window rate limiter (auto-detects Premium 600 req/hr from headers)
- Sync engine: CSV sync (fast, 1 call/year) + JSON enrichment sync (full field set, Premium)
- Pattern-matching chat engine (regex-routed, supports projects/tags/clients/tasks)
- Theme system: CSS injection + custom Plotly template
- Password-protected login via `DASHBOARD_PASSWORD`

### New Supabase + Web Stack
- React + TypeScript + Vite frontend
- Supabase Postgres for data persistence with RLS policies
- Edge Function (`chat-query`) for regex-routed chat responses
- User authenticates via Supabase Auth (email/password)
- Direct frontend read access to Postgres via views and RPCs
- Server-side Python scripts (`scripts/sync_to_supabase.py`) running in GitHub Actions for daily `quick` sync and manual `full`/`enriched` sync
- Only service-role can insert/update database records

## Analysis Module (`analysis/`)

Standalone CLI module — zero coupling to `src/` or Streamlit. Reads `data/toggl.db` directly
and produces a single self-contained cyberpunk-themed HTML report.

### Analyzers (run in this order)
1. `longitudinal.py` — stacked composition, HHI concentration, rolling stats, YoY heatmap, session violin
2. `rhythms.py` — hour-of-day heatmap, day-of-week, sleep/wake proxy, seasonal decomp, weekend ratio
3. `changepoints.py` — PELT + Binseg via `ruptures`, multi-signal, transition events, annotated timeline
4. `correlations.py` — correlation heatmap, crowding-out, KMeans week archetypes, lead/lag cross-corr
5. `text_mining.py` — TF-IDF, NMF + LDA topics, topic prevalence, VADER sentiment, vocab evolution
6. `life_phases.py` — multivariate PELT on weekly feature matrix, auto-labels phases, Gantt + radar

### Key files
- `analysis/data_access.py` — `load_entries()`, `load_daily_series()`, `load_weekly_matrix()`, `get_db_meta()`
- `analysis/run.py` — argparse CLI orchestrator
- `analysis/__main__.py` — enables `python -m analysis`
- `analysis/report/renderer.py` — `render_report(results, meta) -> str`
- `analysis/report/template.html` — Jinja2 cyberpunk HTML template
- `analysis/output/` — gitignored; reports written here by default

### Conventions
- Each analyzer defines its own `AnalysisResult` dataclass: `name`, `title`, `summary`, `figures`, `tables`, `narrative`
- Colors re-declared locally in each file as `_C` dict — do NOT import from `src/theme.py`
- `ruptures` and `scikit-learn` guarded with try/except; module degrades gracefully if missing
- `life_phases.analyze()` accepts optional `text_mining_result` for LDA topic cross-referencing

## Data Model

- **time_entries**: core table with enrichment columns (toggl_id, project_id, tag_ids, task_name, client_name, user_id)
- **projects**: with Premium fields (rate, currency, fixed_fee, estimated_hours)
- **tags**: with creator_id, at, deleted_at
- **clients**: id, name, workspace_id, archived
- **tasks**: Premium task assignments per project
- **sync_meta**: key-value store for sync timestamps

## Conventions

- Type hints on all public functions
- Module-level docstrings on every `.py` file
- Tags stored as JSON arrays in SQLite
- Native Toggl IDs used post-enrichment; synthetic SHA-256 IDs for CSV-only entries
- `managed_connection()` context manager preferred for short-lived DB access

## Environment

- Requires `TOGGL_API_TOKEN` and `DASHBOARD_PASSWORD` (see `.env.example`)
- Deployed on Streamlit Community Cloud (ephemeral filesystem — app auto-syncs on cold start)
- Enriched data lost on cold start; must re-run enrichment sync manually
- `data/` directory is gitignored
