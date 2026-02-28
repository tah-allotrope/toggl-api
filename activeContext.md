# Active Context -- Toggl Time Tracking Dashboard

> Last updated: 2026-02-28

## Project Overview

A Streamlit web dashboard that pulls 8-9 years of personal time tracking data from the Toggl Track API, stores it locally in SQLite, and provides interactive visualizations, retrospective views, and a chat interface. Full **cyberpunk neon aesthetic** throughout.

- **Owner:** Tukumalu91 (Toggl), tah-allotrope (GitHub)
- **Toggl Workspace ID:** 1446622
- **Data:** 56,585 entries, 10 years (2017-2026), 29 projects, 3 tags, ~54,600 total hours
- **Stack:** Python 3.14.2, Streamlit, SQLite, Plotly, Pandas
- **Repo:** https://github.com/tah-allotrope/toggl-api (public)

---

## Architecture

```
toggl-api/
├── .env                      # API token (gitignored)
├── .env.example              # Template for new users
├── .gitignore                # Excludes .env, data/, __pycache__, *.db, .streamlit/secrets.toml
├── .streamlit/
│   └── config.toml           # Dark theme, cyan primary, monospace font
├── requirements.txt          # streamlit, requests, plotly, python-dotenv, pandas
├── app.py                    # Home page + sidebar sync controls + auto-sync on cold start
├── src/
│   ├── __init__.py
│   ├── toggl_client.py       # Toggl API v9 + Reports v3 client with rate limiter
│   ├── data_store.py         # SQLite CRUD + query functions
│   ├── sync.py               # Orchestrates CSV export -> SQLite ingestion per year
│   ├── queries.py            # Pattern-matching chat engine (12 query types)
│   └── theme.py              # Cyberpunk neon CSS injection + color palette
├── pages/
│   ├── 1_Dashboard.py        # Heatmaps, project/tag breakdowns, multi-year views
│   ├── 2_Retrospect.py       # Year-over-year retrospective charts
│   └── 3_Chat.py             # Conversational interface with quick-action buttons
└── data/
    ├── raw/                  # Per-year JSON archives (2017-2026)
    └── toggl.db              # SQLite database (gitignored)
```

---

## Key Technical Decisions

| Decision | Rationale |
|---|---|
| **Reports API v3 CSV export** (not paginated JSON) | 1 API call per year vs. hundreds of paginated requests. Stays well within 30 req/hr free-tier limit. |
| **Synthetic IDs** via SHA-256 hash of `start\|stop\|description\|project\|duration` | CSV export has no `Id` column. `stop_iso` added in A8 to prevent collisions. |
| **Auto-sync on cold start** | Streamlit Cloud has ephemeral filesystems. App detects empty DB and runs full sync automatically. |
| **`st.secrets` fallback** | `toggl_client.py` checks `st.secrets["TOGGL_API_TOKEN"]` first, then falls back to `os.getenv`. Works on both local and Streamlit Cloud. |
| **No AI API yet** | Architecture ready -- `queries.py` `answer_question()` is the extension point for Claude/Gemini integration later. |
| **Streamlit Community Cloud** (not Firebase) | Simplest deployment for a Streamlit app. Free tier sufficient. |

---

## Toggl Data Profile

- **Projects (29):** Work, Home, Linh, Kin, Leisure, Health, Wealth, Intellect, Project Management, Housing, Wedding, Development, Prenatal, CompSus, and more. ~12,098h has "(No Project)".
- **Tags (3):** Highlight (3,443 entries), Deep (126), Grind (19). Some entries have multiple tags (e.g. `["Deep", "Highlight"]`).
- **Tags stored as:** JSON arrays in SQLite (e.g. `["Highlight"]`).

---

## Execution Plan & Status

### Phase A: Bug Fixes & Polish -- COMPLETE

| # | Task | Status |
|---|---|---|
| A1 | Fix heatmap ISO week/year mismatch | Done |
| A2 | Fill missing weeks in heatmap grid | Done |
| A3 | Multi-year heatmap in "All Time" mode (small multiples) | Done |
| A4 | Extend NEON_SEQUENCE to 15+ colors | Done |
| A5 | Per-year error handling in sync loop | Done |
| A6 | Fix st.rerun() hiding success message | Done |
| A7 | Auto-sync on cold start for Streamlit Cloud | Done |
| A8 | Include stop_iso in synthetic ID to prevent collisions | Done |

### Phase B: Chat Engine Improvements -- COMPLETE

| # | Task | Status |
|---|---|---|
| B9 | Add "top projects" query handler | Done |
| B10 | Add tag query support + get_entries_by_tag | Done |
| B11 | Fuzzy project name matching without "project" prefix | Done |
| B12 | Fix greedy "total" keyword intercepting scoped queries | Done |
| B13 | Expand search_entries to search tags + project_name | Done |
| B14 | Add "top tags" query handler | Done |
| B15 | Update help text + onboarding with all query types | Done |

### Phase C: Deployment -- IN PROGRESS

| # | Task | Status |
|---|---|---|
| C16 | Git init + first commit | Done |
| C17 | Push to GitHub | Done |
| C18 | Deploy on Streamlit Community Cloud | **In Progress** |
| C19 | Verify deployment works end-to-end | Pending |

---

## Current State (where we left off)

### What just happened
1. Completed B15: Updated `3_Chat.py` onboarding message with all 12 query types organized in 3 categories + added 2 new quick-action buttons (Top Projects, Top Tags).
2. Completed C16-C17: Initialized git repo, made initial commit (14 files, 2,715 lines), pushed to GitHub.
3. Added `st.secrets` fallback in `toggl_client.py` and `app.py` for Streamlit Cloud compatibility.
4. Changed repo from private to public (Streamlit Cloud couldn't find private repo).
5. Skipped local DB re-sync (cloud deployment will auto-sync with corrected IDs on cold start).

### What needs to happen next
1. **C18: Deploy on Streamlit Community Cloud** -- User is currently deploying. Steps:
   - Go to [share.streamlit.io](https://share.streamlit.io), sign in with GitHub
   - New app > `tah-allotrope/toggl-api`, branch `master`, main file `app.py`
   - Advanced settings > add secret: `TOGGL_API_TOKEN = "88e42840e75d373a6fd9fa3f0ddd5fb3"`
   - Deploy
2. **C19: Verify deployment** -- First load takes 1-2 min (auto-sync). Check all 4 pages work.
3. **Future: AI integration** -- `queries.py` `answer_question()` is the extension point.

---

## Known Issues & Caveats

- **Local DB has stale IDs:** The synthetic ID formula changed in A8 (added `stop_iso`). The local `data/toggl.db` still has old IDs. Incremental syncs locally could create duplicates. A full re-sync would fix this, but was skipped since cloud deployment auto-syncs fresh.
- **LSP false positives:** pandas type stubs cause warnings on `.rename(columns=...)`, `sort_values(ascending=False)`, `.nunique()`, `.notna()`, `.groupby()` on DataFrames from groupby/filter chains. These are NOT runtime errors.
- **Rate limiter stale timestamps:** If a sync is interrupted, the `RateLimiter` class can retain stale timestamps that block subsequent requests for the full hourly quota. The initial bulk sync was done with raw `requests` to work around this.
- **Streamlit Cloud ephemeral filesystem:** The SQLite DB is lost on every cold start. Auto-sync (A7) handles this, but first load always takes ~1-2 minutes.

---

## Chat Engine Query Types (queries.py)

The pattern-matching engine supports 12 query types:

| Query Type | Example | Handler |
|---|---|---|
| Top projects | "top projects", "top projects in 2024" | `_answer_top_projects` |
| Top tags | "top tags" | `_answer_top_tags` |
| Tag details | "tag Highlight", "tagged Deep in 2024" | `_answer_tag` |
| Specific date | "what did I do on March 15, 2023" | `_answer_specific_date` |
| Date across years | "what did I do on March 15" | `_answer_date_across_years` |
| Week view | "this week", "last week", "week 12" | `_answer_week` |
| Today/Yesterday | "today", "yesterday" | `_answer_date_across_years` |
| Year summary | "how was 2024" | `_answer_year` |
| Month summary | "in February 2024" | `_answer_month` |
| Year comparison | "compare 2023 and 2024" | `_answer_compare` |
| Total stats | "total hours", "all time" | `_answer_totals` |
| Keyword search | "search meditation" | `_answer_search` |
| Bare project name | "Work", "Health" | `_answer_project` |
| Explicit project | "project Work in 2024" | `_answer_project` |

---

## Git Log

```
8f40690 Add st.secrets fallback for Streamlit Cloud deployment
ee514fa Initial commit: Toggl time tracking dashboard with cyberpunk neon theme
```
