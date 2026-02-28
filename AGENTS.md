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
- API client with sliding-window rate limiter (30 req/hr free tier)
- Sync engine: API → JSON archives → SQLite with derived columns
- Pattern-matching chat engine (regex-routed, designed for future AI integration)
- Theme system: CSS injection + custom Plotly template

## Conventions

- Type hints on all public functions
- Module-level docstrings on every `.py` file
- Tags stored as JSON arrays in SQLite
- Synthetic entry IDs via SHA-256 hash of `start|stop|description|project|duration`

## Environment

- Requires `TOGGL_API_TOKEN` (see `.env.example`)
- Deployed on Streamlit Community Cloud (ephemeral filesystem — app auto-syncs on cold start)
- `data/` directory is gitignored

## Known Issues

- `conn.close()` called twice in sync engine (latent bug)
- RateLimiter can retain stale timestamps if sync is interrupted

## Routing

When these docs exist, read them for domain-specific rules:

- `docs/TESTING.md` — test patterns and fixtures
- `docs/CONVENTIONS.md` — code style, type checking, linting
- `docs/SYNC.md` — sync engine internals and Toggl API quirks
