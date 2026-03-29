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
- Added `scripts/verify_supabase_db_state.py` to validate migration state on a real Postgres target:
  - Confirms `time_entries.canonical_key` exists, is backfilled, and required indexes are present.
  - Confirms RPC functions use `p_start_date` / `p_end_date` argument names.
  - Seeds bounded fixtures and verifies custom-range RPCs only return in-range rows.

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

## This Session (2026-03-24)

- Added `scripts/verify_supabase_db_state.py` to turn the remaining SQL verification work into a repeatable Postgres-backed check instead of a manual checklist.
- The new verification script covers both outstanding SQL risks in one run:
  - migration/backfill state for `canonical_key`
  - custom-range RPC parameter/signature and bounded-result behavior
- Updated Postgres-backed scripts to load `.env` automatically and accept `DATABASE_URL` as a fallback to `SUPABASE_DB_URL`:
  - `scripts/sync_to_supabase.py`
  - `scripts/verify_dedupe_reconciliation.py`
  - `scripts/verify_supabase_db_state.py`
- Added shared environment helpers in `scripts/env_utils.py` so sync and verification scripts resolve credentials consistently.
- Added `scripts/doctor_supabase_env.py` as a one-command readiness check for the next session:
  - checks `TOGGL_API_TOKEN` presence
  - checks `SUPABASE_URL` / key presence
  - checks `DATABASE_URL` parsing, DNS resolution, and TCP reachability
- Confirmed the new script compiles cleanly:
  - `python -m py_compile scripts/verify_supabase_db_state.py`
- Confirmed all updated Python scripts compile cleanly:
  - `python -m py_compile scripts/env_utils.py scripts/doctor_supabase_env.py scripts/sync_to_supabase.py scripts/verify_dedupe_reconciliation.py scripts/verify_supabase_db_state.py`
- Ran the new environment doctor:
  - `python scripts/doctor_supabase_env.py`
  - Result: `TOGGL_API_TOKEN` missing, `SUPABASE_URL` and key present, `DATABASE_URL` present, but DB host DNS lookup still fails.
- Added `scripts/apply_hosted_supabase_migrations.py` to apply the pending SQL migrations directly to the reachable hosted Supabase database when local CLI access is unavailable.
- Updated local runtime env files so the active app paths use real credentials:
  - `.env` now includes `TOGGL_API_TOKEN`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_DB_URL`
  - `web/.env` now provides the active Vite app with real Supabase URL + anon key
- Applied the missing hosted SQL changes successfully:
  - `python scripts/apply_hosted_supabase_migrations.py`
  - Applied `supabase/migrations/20260318_000003_views_and_rpc.sql`
  - Applied `supabase/migrations/20260322_000004_time_entry_canonical_key.sql`
- Found and fixed one live-schema compatibility bug after applying migrations:
  - `public.time_entries.tags` is `TEXT` on the hosted DB, so `get_tag_breakdown` now casts `te.tags::jsonb` before using JSONB functions.
- Reran hosted verification successfully after the live migration fix:
  - `python scripts/verify_supabase_db_state.py`
  - `python scripts/verify_dedupe_reconciliation.py`
- Confirmed sync smoke test now succeeds with real credentials:
  - `python scripts/sync_to_supabase.py --mode quick --dry-run`
  - Result: `entries_written=1874`, `projects_written=29`, `tags_written=3`, `clients_written=0`, `tasks_written=0`, `errors=[]`
- Built and started the real web frontend against hosted Supabase:
  - `npm run build` in `web/` passed
  - `npm run dev -- --host 0.0.0.0` in `web/` started successfully
  - Preview URL: `http://localhost:5173/toggl-api/`
- Attempted live Postgres verification using `.env` `DATABASE_URL`, but execution is still blocked by environment, not code:
  - `python scripts/verify_supabase_db_state.py`
  - `python scripts/verify_dedupe_reconciliation.py`
  - Both failed with DNS resolution errors for `db.itxfaxlnlbzbddyvqvwd.supabase.co`.
- Confirmed the configured Supabase project host itself does not currently resolve from this environment:
  - `nslookup db.itxfaxlnlbzbddyvqvwd.supabase.co`
  - `nslookup itxfaxlnlbzbddyvqvwd.supabase.co`
- Attempted the next sync smoke test:
  - `python scripts/sync_to_supabase.py --mode quick --dry-run`
  - This failed immediately because `TOGGL_API_TOKEN` is not present in `.env`.

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
- DB verification automation added and syntax-checked:
  - `python -m py_compile scripts/env_utils.py scripts/doctor_supabase_env.py scripts/sync_to_supabase.py scripts/verify_dedupe_reconciliation.py scripts/verify_supabase_db_state.py`
  - `python scripts/doctor_supabase_env.py`
- Hosted migration and verification completed:
  - `python scripts/apply_hosted_supabase_migrations.py`
  - `python scripts/verify_supabase_db_state.py`
  - `python scripts/verify_dedupe_reconciliation.py`
- Real sync dry-run completed:
  - `python scripts/sync_to_supabase.py --mode quick --dry-run`
- Real frontend build and preview completed:
  - `npm run build` in `web/`
  - `http://localhost:5173/toggl-api/`

## Outstanding Items

- No migration applied yet for the new canonical-key schema changes or prior SQL function changes; DB still needs migration execution in target environments.
- Dedupe is stronger now, but still not fully canonical at the database level for all rows:
  - `canonical_key` is indexed and unique only for CSV-style rows (`toggl_id IS NULL`).
  - There is still no global uniqueness constraint that can guarantee one-row-only semantics across all historical import edge cases.
- Edge function auth now depends on environment vars (`SUPABASE_URL`, `SUPABASE_ANON_KEY`) being correctly set in Supabase Functions runtime.
- No end-to-end sync dry-run against live Toggl + Supabase has been executed since the canonical dedupe hardening landed.
- Frontend chat auth from a real signed-in session is still not explicitly verified end-to-end.
- Working tree contains many untracked paths from migration work (`scripts/`, `supabase/`, `web/`, etc.); no commit created.

## Recommended Next Steps (Next Session)

1. Apply and validate DB migration changes:
    - Done on hosted Supabase for the current environment.
 2. Run the enriched sync smoke test against real credentials:
    - `python scripts/sync_to_supabase.py --mode enriched --earliest-year <year> --dry-run`
 3. Validate chat auth from frontend session:
    - Confirm unauthenticated call returns `401` and authenticated call succeeds.
 4. Decide on hardening plan for dedupe:
    - Decide whether current `canonical_key` + reconciliation behavior is sufficient.
    - If not, add a stronger migration-backed strategy (for example a reconciliation cleanup job and/or a stricter unique constraint after data cleanup).
 5. If all checks pass, stage and commit with a focused message grouping sync/sql/auth/frontend fixes.

## Notes for Handoff

- Main risk reduced: sync modes should no longer fail immediately due missing client methods/signature mismatch.
- Main correctness fix: custom-range RPCs now reference function params rather than tautological column comparisons.
- Main security fix: `chat-query` is now gated by JWT validation.
- Demo mode now allows immediate UI preview without requiring Supabase CLI/Docker setup.
- New dedupe direction: CSV and enriched entries now share a normalized `canonical_key`, which should make mixed-history reconciliation much more reliable once the migration is applied.
- Remaining blocker: meaningful DB validation still depends on having either Docker-backed local Supabase or a reachable Postgres target with `SUPABASE_DB_URL` configured.
