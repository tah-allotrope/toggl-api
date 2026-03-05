# Implementation Plan — Post Data Enrichment

> Created: 2026-03-05
> Branch: `feature/data-enrichment-phase` (ready to merge)
> DB state: 56,696 enriched entries, all CSV duplicates removed, dedup guard in place

---

## Phase G: Ship the Branch

**Prerequisite for everything below. Do this first.**

| # | Task | Notes |
|---|---|---|
| G1 | Commit the two uncommitted changes | `data_store.py` (dedup guard), `activeContext.md` (updated docs) |
| G2 | Merge `feature/data-enrichment-phase` into `master` | `git merge feature/data-enrichment-phase` |
| G3 | Push to GitHub | Triggers Streamlit Cloud auto-deploy |
| G4 | Verify Streamlit Cloud cold-start behaviour | Empty DB → CSV sync runs → `sync_all()` → no enriched data yet. Expected: enrichment coverage shows 0%. That is correct. |
| G5 | Confirm Streamlit Cloud secrets | `TOGGL_API_TOKEN` and `DASHBOARD_PASSWORD` must be present in app secrets |

---

## Phase H: Dashboard Upgrades (use enriched data)

The enrichment sync added `project_id`, `tag_ids`, `task_name`, `client_name`, `user_id`.
None of these new fields are surfaced in the UI yet.

### H1 — Client breakdown view

Add a "Time by Client" section to `pages/1_Dashboard.py` alongside the existing "Time by Project" section.

- Query: `GROUP BY client_name` on `time_entries`
- Chart: horizontal bar (same style as project bar) — `client_name` vs `duration_hours`
- Filter: respect the existing Single Year / All Time / Custom Range selector
- `client_name` is empty (`""`) for entries with no project/client chain — label these `"(No Client)"`

### H2 — Task breakdown view

Add a "Time by Task" section below the client section.

- Query: `GROUP BY task_name` where `task_name != ''`
- Chart: horizontal bar
- Only show if tasks exist (`get_tasks_df(conn)` returns non-empty)
- If no tasks exist (Free tier, post-Premium), show a `st.caption("No task data — requires enrichment sync")`

### H3 — Enrichment coverage metric in sidebar

The enrichment progress bar already exists in `app.py` (line 144–152). Upgrade it:

- Replace the plain `st.progress` with a compact metric row: `"56,696 / 56,696 (100%)"` format
- Add a sub-caption showing the `last_enriched_sync` timestamp
- Keep the "Run Enriched Sync" button

### H4 — Project detail drill-down

Currently clicking a project in the bar chart does nothing. Add a project detail expander:

- `st.selectbox` below the project bar chart to pick a project
- Show: total hours, entry count, date range, top descriptions, linked tasks (if any), client name
- All data is already available in the DB — no new API calls needed

---

## Phase I: Retrospect Page Upgrades

`pages/2_Retrospect.py` currently does year-over-year comparisons. Enrichment enables richer retrospect.

### I1 — "On this day" task context

The existing "on this day" view (`get_entries_for_date_across_years`) returns entries but no task info.
Add a `task_name` column to the displayed entries where non-empty.

### I2 — Tag quality upgrade

Tags are currently matched by JSON string search (`LIKE '%"Highlight"%'`).
Now that `tag_ids` are populated, add a secondary lookup by `tag_ids` for entries where the
JSON name search would miss (e.g. renamed tags). Low priority — tag names haven't changed.

---

## Phase J: Chat Engine Upgrades

`src/queries.py` is a regex router. It cannot use enriched fields. Two directions:

### J1 — Extend regex engine to cover new fields (quick wins)

Add these query types to `answer_question()`:

| Query pattern | Handler |
|---|---|
| `"client Work"` / `"how much time on client X"` | `_answer_client(conn, client_name, year)` |
| `"what tasks did I do"` / `"top tasks"` | `_answer_top_tasks(conn, year)` |
| `"task X"` / `"hours on task X"` | `_answer_task(conn, task_name, year)` |

Implementation is identical in structure to `_answer_project` / `_answer_tag`.

### J2 — AI integration via Gemini or Claude (bigger lift)

The `_help_message` already says: *"For AI-powered analysis, an AI API integration can be added later."*

When ready:

1. Add `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`) to `.env` and Streamlit secrets
2. Replace `answer_question()` dispatch with an LLM call that:
   - Receives the question + a compact DB schema summary as system context
   - Generates a SQLite query
   - Executes it via `conn.execute()`
   - Returns a formatted result
3. Keep the regex engine as a fast fallback for known patterns (avoids API latency on simple queries)

Suggested library: `google-generativeai` for Gemini, or `anthropic` for Claude.
The DB is small enough (~56k rows) that natural-language → SQL works well without RAG.

---

## Phase K: Streamlit Cloud Enrichment Workaround

**Problem:** Streamlit Cloud has an ephemeral filesystem. On cold start, the DB is empty and `sync_all()` runs (CSV path, ~30 API calls). But enrichment data is lost — it's not in the CSV.

**Options (pick one):**

### K1 — Accept the limitation (simplest, recommended for now)

- CSV sync on cold start is correct behaviour for Free tier
- Enrichment sync is a one-off operation run manually while on Premium
- The DB can be re-enriched at any time by clicking "Run Enriched Sync" in the sidebar
- Document this caveat in the sidebar UI (a `st.caption` below the enrichment progress bar)

### K2 — Persist enriched JSON to a remote store

- After `sync_enriched_all()`, upload all `{year}_enriched.json` files to Cloudflare R2 or similar
- On cold start, before `sync_all()`, check if enriched archives exist in R2 and download them
- Then call a `sync_from_archives(enriched=True)` path that reads local JSON instead of calling the API
- Requires: `rclone` or `boto3`, R2 bucket, R2 credentials in Streamlit secrets
- **Effort:** medium. Most of the code already exists (`{year}_enriched.json` archives are written by `sync_enriched_all()`)

### K3 — Store the DB itself in R2

- After each sync, upload `toggl.db` to R2
- On cold start, download `toggl.db` before mounting the app
- Requires: a startup hook (Streamlit Cloud does not natively support pre-start scripts — would need a wrapper script or `@st.cache_resource` with lazy download)
- **Effort:** medium-high. DB can grow to 50MB+ but is well within R2 free tier

---

## Phase L: Code Hygiene (low priority)

These are not blocking anything but should be done before the codebase grows further.

| # | Task | File | Notes |
|---|---|---|---|
| L1 | Fix RateLimiter stale timestamp edge case | `src/toggl_client.py` | On interrupted sync, stale timestamps remain in the sliding window. Add a `clear_stale()` method called at the start of each year's fetch. |
| L2 | Add `sync_enriched_current_year()` | `src/sync.py` | Incremental enrichment: re-fetch only the current year's entries via JSON. Useful for keeping enriched data current without a full 2-hour re-run. |
| L3 | `get_entries_df` default column set | `src/data_store.py` | Currently selects `*`. Add an optional `columns` param to avoid pulling unused enrichment columns on every dashboard query. |
| L4 | Remove `conn.close()` from callers that use `get_connection()` inside a `with` block | Various pages | Minor leak risk. Wrap `get_connection()` in a context manager. |

---

## Dependency Order

```
G (merge) → H (dashboard) → I (retrospect)
           ↘ J1 (chat regex) → J2 (AI, optional)
           ↘ K (cloud persistence, pick one)
           ↘ L (hygiene, anytime)
```

Everything in H, I, J1 can be done independently in any order after G.
K should be done before any active use of the deployed app (enriched data will be lost on cold start otherwise).

---

## Quick-start for next session

```bash
git checkout feature/data-enrichment-phase
git status  # should show data_store.py and activeContext.md as modified
# Commit those two files, then merge to master
```

DB is clean: 56,696 enriched entries, `toggl_id IS NOT NULL` for all rows, dedup guard active.
