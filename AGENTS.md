# Toggl Time Journal

Personal time-tracking analytics dashboard that pulls 10 years of Toggl data into SQLite and renders interactive dashboards with a cyberpunk aesthetic.

## Stack

- **Language:** Python 3.10+ (uses `X | Y` union syntax)
- **Framework:** Streamlit (requires 1.52+ for `st.navigation`)
- **Data:** Pandas, Plotly, SQLite (stdlib `sqlite3`)
- **API:** Toggl Track API v9, Toggl Reports API v3
- **Package manager:** pip

## Commands

```bash
pip install -r requirements.txt   # Install dependencies
streamlit run app.py              # Run locally on :8501
```

No test framework. No linter. No type checker configured.

## Architecture

- 4 Streamlit pages behind `st.navigation` (Homepage, Dashboard, Retrospect, Chat)
- API client with sliding-window rate limiter (auto-detects Premium 600 req/hr from headers)
- Sync engine: CSV sync (fast, 1 call/year) + JSON enrichment sync (full field set, Premium)
- Pattern-matching chat engine (regex-routed, supports projects/tags/clients/tasks)
- Theme system: CSS injection + custom Plotly template
- Password-protected login via `DASHBOARD_PASSWORD`

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
