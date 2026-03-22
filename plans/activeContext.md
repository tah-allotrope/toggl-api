# Active Context

Date: 2026-03-22
Project: Toggl Time Journal (Supabase + Web migration path)

## Progress Recorded

- Implemented sync script API alignment in `scripts/sync_to_supabase.py` to use real `TogglClient` methods (`get_projects`, `get_tags`, `get_clients`, `get_all_tasks`, `fetch_year_csv`, `fetch_year_entries_json`).
- Fixed enriched sync flow in `scripts/sync_to_supabase.py` to run year-by-year and normalize JSON entries before DB upsert.
- Added minimal duplicate-reconciliation in `scripts/supabase_db.py`:
  - If `toggl_id` already exists, update that row.
  - Else try matching legacy CSV row (`toggl_id IS NULL`) by `start`, `stop`, `duration`, `description`, `project_name` and update that row id.
- Fixed SQL RPC date filter bug in `supabase/migrations/20260318_000003_views_and_rpc.sql` by renaming params to `p_start_date`/`p_end_date` and using them explicitly.
- Updated frontend RPC calls in `web/src/lib/api.ts` to use `p_start_date`/`p_end_date`.
- Added bearer/JWT enforcement in `supabase/functions/chat-query/index.ts` using Supabase Auth `getUser()` and `401` responses for unauthenticated access.
- Restored homepage behavior parity in `web/src/pages/Homepage.tsx` to current ISO week filtering (Mon-Sun), exact `Highlight` tag inclusion, chronological display.
- Fixed strict TS unused React import issues in:
  - `web/src/main.tsx`
  - `web/src/pages/Dashboard.tsx`
  - `web/src/pages/Retrospect.tsx`
  - `web/src/pages/Chat.tsx`
- Hardened mixed CSV/enriched dedupe with a canonical entry key:
  - Added `build_canonical_entry_key()` and UTC timestamp normalization in `scripts/transform_toggl.py`.
  - Added `canonical_key` to transformed CSV and JSON entries.
  - Recomputed canonical keys in enriched sync after project/task/client names are restored in `scripts/sync_to_supabase.py`.
- Strengthened Postgres reconciliation in `scripts/supabase_db.py`:
  - After native `toggl_id` lookup, enriched rows now try matching by `canonical_key` before the older field-by-field fallback.
  - `canonical_key` now persists on every `time_entries` upsert.
- Added migration-backed dedupe support:
  - Extended initial schema in `supabase/migrations/20260318_000001_init_schema.sql` with `time_entries.canonical_key` plus supporting indexes.
  - Added forward migration `supabase/migrations/20260322_000004_time_entry_canonical_key.sql` to backfill canonical keys on existing databases.
- Added `scripts/verify_dedupe_reconciliation.py` to seed one CSV-style fixture row plus one enriched fixture row and assert they reconcile into a single logical Postgres row.

## This Session (2026-03-19)

- Attempted Supabase CLI installation via Chocolatey - package not found
- Downloaded Supabase CLI binary directly - Docker unavailable (required for `supabase start`)
- Created **demo/offline mode** for web app to function without backend:
  - Modified `web/src/lib/supabase.ts` to detect missing credentials and return mock data
  - Added gradient banner in `web/src/main.tsx` showing "DEMO MODE" when running without Supabase
  - Added `isRunningInDemoMode()` export in `web/src/lib/api.ts`
  - Mock data includes: time entries, project/tag breakdowns, on-this-day history, chat responses
  - Demo mode activates automatically when `VITE_SUPABASE_URL` is missing or points to localhost
- Fixed TypeScript build error (line too long in supabase.ts mock builder)
- Successfully built and started dev server at **http://localhost:5174/**

## This Session (2026-03-22)

- Implemented canonical dedupe hardening so CSV exports and enriched JSON syncs can converge on the same logical row even when timestamp formatting differs (`Z` vs `+00:00`).
- Added a migration-safe path for existing databases via `supabase/migrations/20260322_000004_time_entry_canonical_key.sql` instead of requiring a destructive reset.
- Added a targeted verification script for duplicate reconciliation in `scripts/verify_dedupe_reconciliation.py`.
- Confirmed Python modules compile cleanly:
  - `python -m py_compile scripts/sync_to_supabase.py scripts/supabase_db.py scripts/transform_toggl.py scripts/verify_dedupe_reconciliation.py`
- Confirmed the canonical dedupe key matches for equivalent CSV and enriched fixtures:
  - `537b604d08e9f6335743d504ce307f0d`
- Did not run live Postgres verification yet:
  - `scripts/verify_dedupe_reconciliation.py` still requires a reachable database via `SUPABASE_DB_URL`.
  - Full migration apply/reset remains blocked without a working local Supabase runtime or target Postgres environment.

## Verification Completed

- Python syntax check passed:
  - `python -m py_compile scripts/sync_to_supabase.py scripts/supabase_db.py`
- Frontend build passed after dependency install:
  - `npm install && npm run build` in `web/`
- Demo mode verified working:
  - Homepage shows mock weekly highlights
  - Dashboard shows mock metrics and breakdowns
  - Retrospect shows mock "on this day" history
  - Chat responds to demo queries ("top projects in 2024", "today", etc.)
- Dedupe hardening verification completed:
  - Canonical-key generation is stable across equivalent CSV and JSON fixtures.
  - Updated Python sync/database modules pass syntax compilation.

## Outstanding Items

- No migration applied yet for the new canonical-key schema changes or prior SQL function changes; DB still needs migration execution in target environments.
- Dedupe is stronger now, but still not fully canonical at the database level for all rows:
  - `canonical_key` is indexed and unique only for CSV-style rows (`toggl_id IS NULL`).
  - There is still no global uniqueness constraint that can guarantee one-row-only semantics across all historical import edge cases.
- Edge function auth now depends on environment vars (`SUPABASE_URL`, `SUPABASE_ANON_KEY`) being correctly set in Supabase Functions runtime.
- No end-to-end sync dry-run against live Toggl + Supabase has been executed since the canonical dedupe hardening landed.
- `scripts/verify_dedupe_reconciliation.py` has not been executed against a live/local Postgres database yet because `SUPABASE_DB_URL` was not available in this session.
- Working tree contains many untracked paths from migration work (`scripts/`, `supabase/`, `web/`, etc.); no commit created.

## Recommended Next Steps (Next Session)

1. Apply and validate DB migration changes:
    - `supabase db reset` (local) or equivalent migration apply command in target env.
    - Ensure `supabase/migrations/20260322_000004_time_entry_canonical_key.sql` runs successfully and backfills existing rows.
    - Verify RPC custom-range returns correct bounded results.
2. Run sync smoke tests against real credentials:
    - `python scripts/sync_to_supabase.py --mode quick --dry-run`
    - `python scripts/sync_to_supabase.py --mode enriched --earliest-year <year> --dry-run`
3. Validate duplicate reconciliation behavior with a controlled fixture:
    - Run `python scripts/verify_dedupe_reconciliation.py` against a real/local Postgres DB.
    - Confirm one reconciled row remains and enriched fields (`toggl_id`, `project_id`, `task_id`, `client_name`) are retained.
4. Decide on hardening plan for dedupe:
    - Decide whether current `canonical_key` + reconciliation behavior is sufficient.
    - If not, add a stronger migration-backed strategy (for example a reconciliation cleanup job and/or a stricter unique constraint after data cleanup).
5. Validate chat auth from frontend session:
    - Confirm unauthenticated call returns `401` and authenticated call succeeds.
6. If all checks pass, stage and commit with a focused message grouping sync/sql/auth/frontend fixes.

## Notes for Handoff

- Main risk reduced: sync modes should no longer fail immediately due missing client methods/signature mismatch.
- Main correctness fix: custom-range RPCs now reference function params rather than tautological column comparisons.
- Main security fix: `chat-query` is now gated by JWT validation.
- Demo mode now allows immediate UI preview without requiring Supabase CLI/Docker setup.
- New dedupe direction: CSV and enriched entries now share a normalized `canonical_key`, which should make mixed-history reconciliation much more reliable once the migration is applied.
- Remaining blocker: meaningful DB validation still depends on having either Docker-backed local Supabase or a reachable Postgres target with `SUPABASE_DB_URL` configured.
