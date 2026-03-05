# Active Context -- Toggl Time Tracking Dashboard

> Last updated: 2026-03-05 (post data enrichment phase)

## Project Overview

A Streamlit web dashboard that pulls 8-9 years of personal time tracking data from the Toggl Track API, stores it locally in SQLite, and provides interactive visualizations, retrospective views, and a chat interface. Full **cyberpunk neon aesthetic** throughout.

- **Owner:** Tukumalu91 (Toggl), tah-allotrope (GitHub)
- **Toggl Workspace ID:** 1446622
- **Data:** 56,696 entries, 10 years (2017-2026), 29 projects, 3 tags — ALL entries now enriched (native Toggl IDs, project_ids, tag_ids, client names, task names)
- **Stack:** Python 3.14.2, Streamlit, SQLite, Plotly, Pandas
- **Repo:** https://github.com/tah-allotrope/toggl-api (public)
- **Active branch:** `feature/data-enrichment-phase`

---

## Architecture

```
toggl-api/
├── .env                      # API token + DASHBOARD_PASSWORD (gitignored)
├── .env.example              # Template for new users
├── .gitignore                # Excludes .env, data/, __pycache__, *.db, .streamlit/secrets.toml
├── .streamlit/
│   └── config.toml           # Dark theme, cyan primary, monospace font
├── requirements.txt          # streamlit, requests, plotly, python-dotenv, pandas
├── app.py                    # Router: password auth + st.navigation + sync sidebar (incl. Enriched Sync)
├── src/
│   ├── __init__.py
│   ├── toggl_client.py       # Toggl API v9 + Reports v3 client; auto-detects Premium quota
│   ├── data_store.py         # SQLite CRUD + query functions; schema migration; dedup guard
│   ├── sync.py               # CSV sync (sync_all, sync_current_year) + JSON enrichment (sync_enriched_all)
│   ├── queries.py            # Pattern-matching chat engine (12 query types)
│   └── theme.py              # Cyberpunk neon CSS injection + color palette
├── pages/
│   ├── 0_Homepage.py        # Weekly Highlight journal (card-based, current ISO week)
│   ├── 1_Dashboard.py        # Heatmaps, project/tag breakdowns, multi-year views
│   ├── 2_Retrospect.py       # Year-over-year retrospective charts
│   └── 3_Chat.py             # Conversational interface with quick-action buttons
└── data/
    ├── raw/                  # Per-year JSON archives: {year}.json (CSV) + {year}_enriched.json (JSON)
    └── toggl.db              # SQLite database (gitignored)
```

---

## Key Technical Decisions

| Decision | Rationale |
|---|---|
| **Reports API v3 CSV export** (not paginated JSON) | 1 API call per year vs. hundreds of paginated requests. Stays well within 30 req/hr free-tier limit. |
| **Synthetic IDs** via SHA-256 hash of `start\|stop\|description\|project\|duration` | CSV export has no `Id` column. Used until enrichment sync replaces them with native Toggl IDs. |
| **Enrichment sync via Reports API v3 JSON** with `enrich_response=True` | Pulls full field set: native IDs, project_id, tag_ids, task data, client info, `at` timestamp. Only viable during Premium (600 req/hr). Free tier (30 req/hr) would take ~40 hours for 10 years. |
| **Native Toggl IDs replace synthetic IDs post-enrichment** | `toggl_id` column stores the native integer. `id` (PK) is now also the native integer for enriched rows. |
| **Migrate in-place** (ALTER TABLE, not parallel tables) | Idempotent `_apply_migrations()` runs on every startup — safe on existing DBs, no-op on new ones. |
| **Deduplication guard in `upsert_time_entries`** | CSV entries (toggl_id=None) are checked against existing enriched rows on `(start[:19], duration, description)` before insert. Prevents re-duplication after enrichment sync if CSV sync runs again. |
| **Rate limiter auto-detects Premium quota** | `RateLimiter.update_from_headers()` reads `X-Toggl-Quota-Remaining` and upgrades the ceiling from 30 to 600 req/hr automatically when on Premium. |
| **Tag hierarchies do not exist in Toggl** | Tags are flat `(id, name)` pairs. Stored with richer metadata: `creator_id`, `at`, `deleted_at`. |
| **Auto-sync on cold start** | Streamlit Cloud has ephemeral filesystems. App detects empty DB and runs full sync automatically. |
| **`st.secrets` fallback** | `toggl_client.py` checks `st.secrets["TOGGL_API_TOKEN"]` first, then falls back to `os.getenv`. Works on both local and Streamlit Cloud. |
| **`st.navigation` API for routing** | Entrypoint must remain `app.py`. `st.navigation` + `st.Page` lets us set custom sidebar labels. |
| **Password Protection** | Simple session-based password check in `app.py`. Uses `st.form` for Enter-to-submit. Custom CSS hides sidebar during login. |

---

## Toggl Data Profile

- **Projects (29):** Work, Home, Linh, Kin, Leisure, Health, Wealth, Intellect, Project Management, Housing, Wedding, Development, Prenatal, CompSus, Agentic (formerly "Academic"), and more. ~12,098h has "(No Project)".
- **Tags (3):** Highlight (3,443 entries), Deep (126), Grind (19). Some entries have multiple tags.
- **Tags stored as:** JSON arrays in SQLite (e.g. `["Highlight"]`). Tag IDs also stored in `tag_ids` column after enrichment.
- **Timezone:** User is UTC+7. CSV exports return naive local time (`2025-01-07T07:40:02`). JSON API returns tz-aware (`2025-01-07T07:40:02+07:00`).

---

## Schema: time_entries

| Column | Source | Notes |
|---|---|---|
| `id` | PK | Native Toggl integer for enriched rows; synthetic SHA-256 for CSV-only rows |
| `toggl_id` | Enrichment | Native Toggl entry ID; UNIQUE, NULL for CSV-only rows |
| `start`, `stop` | Both | ISO 8601 string; tz-aware for JSON, naive for CSV |
| `duration` | Both | Seconds |
| `description` | Both | |
| `project_id` | Enrichment | NULL for CSV-only rows |
| `project_name` | Both | Denormalized. "Academic" in CSV = "Agentic" in enriched (project was renamed) |
| `workspace_id` | Both | |
| `tags` | Both | JSON array of tag names |
| `tag_ids` | Enrichment | JSON array of tag IDs; `[]` for CSV-only rows |
| `billable` | Both | 0/1 |
| `at` | Enrichment | Last-modified timestamp; empty for CSV-only rows |
| `start_date`, `start_year`, `start_month`, `start_day`, `start_week` | Derived | Extracted from `start` |
| `duration_hours` | Derived | `duration / 3600.0` |
| `task_id`, `task_name` | Enrichment | NULL/empty for CSV-only rows |
| `client_name` | Enrichment | Denormalized via project→client chain |
| `user_id` | Enrichment | NULL for CSV-only rows |

---

## Execution Plan & Status

### Phase A-E: COMPLETE

*(Phase A: Bug Fixes, Phase B: Chat Engine, Phase C: Deployment, Phase D: Homepage Redesign, Phase E: Password Protection)*

### Phase F: Data Enrichment -- COMPLETE

| # | Task | Status |
|---|---|---|
| F1 | Rewrite `toggl_client.py`: rate limiter auto-detection, JSON fetch methods, enhanced flatten | Done |
| F2 | Rewrite `data_store.py`: schema migration, new tables (clients, tasks), enriched upserts | Done |
| F3 | Rewrite `sync.py`: `sync_enriched_all()`, fix double `conn.close()` bug | Done |
| F4 | Update `app.py`: Enriched Sync sidebar expander with progress bar | Done |
| F5 | Run enrichment sync: pulled all 10 years via JSON API, stored `{year}_enriched.json` | Done |
| F6 | Diagnose & fix deduplication: 56,555 CSV rows deleted, 56,696 enriched rows remain | Done |
| F7 | Implement dedup guard in `upsert_time_entries` to prevent future re-duplication | Done |

---

## Current State

### What just happened (Phase F)

1. Created branch `feature/data-enrichment-phase`.
2. Rewrote `toggl_client.py`, `data_store.py`, `sync.py` to add enrichment sync path.
3. Ran enrichment sync: 10 years of entries fetched via Reports API v3 JSON with `enrich_response=True`.
4. Discovered duplication: enriched rows (native IDs) and CSV rows (synthetic IDs) both survived because PKs differed.
5. Diagnosed 56,555 CSV duplicates — all had enriched counterparts. 387 "Academic" vs "Agentic" differences traced to a project rename (not missing data).
6. Deleted all 56,555 CSV rows. DB now has 56,696 clean enriched rows.
7. Added dedup guard to `upsert_time_entries`: CSV entries are skipped if an enriched counterpart already exists.

### What needs to happen next

1. **Merge `feature/data-enrichment-phase` to master** and push to deploy.
2. **On Streamlit Cloud cold start:** enrichment sync won't run automatically (too slow for Free tier). The CSV sync runs first; the dedup guard ensures enriched rows won't be doubled if enrichment is later re-run manually.
3. **Future: AI integration** — Gemini/Claude integration via `queries.py`, now possible with richer data (task names, client names, native IDs).

---

## Known Issues & Caveats

- **Streamlit Cloud cold start only runs CSV sync** (30 req/hr free tier). Enrichment requires manual trigger while on Premium. The dedup guard prevents re-duplication.
- **"Academic" project renamed to "Agentic"** in Toggl. Historical CSV entries used the old name; enriched rows use the current name. DB now has only "Agentic".
- **Secrets required for Cloud:** Ensure both `TOGGL_API_TOKEN` and `DASHBOARD_PASSWORD` are configured in Streamlit Cloud secrets.
- **Streamlit Cloud cannot change Main file path:** Must remain `app.py`.
- **RateLimiter stale timestamp edge case:** Can retain stale timestamps if sync is interrupted mid-year. Harmless but means the next request waits up to 1 hour unnecessarily. Mitigated by per-year checkpointing in `sync_enriched_all`.

---

## Chat Engine Query Types (queries.py)

*(Same as before — pattern-matching, 12 query types, designed for future AI integration)*

---

## Git Log (recent)

```
(latest) feat: data enrichment phase — JSON sync, schema migration, Premium fields
7dd2ec6 Add password protection to web dashboard
ec6018c Add minimalist AGENTS.md for AI agent context
291ac90 Restructure to st.navigation API for custom sidebar labels
d27e88e Added Dev Container Folder
f1a701e Redesign homepage as weekly Highlight journal
```
