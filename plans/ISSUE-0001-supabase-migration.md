# ISSUE-0001: Supabase Migration Plan

1. **Objective**

Migrate the current Streamlit + local SQLite app to a production-style web platform centered on Supabase Free so data, auth, API, and scheduled sync are cloud-managed with strict no-billing constraints and near-zero manual setup after one-time CLI authentication.

2. **Mathematical Formulation / Logic**

Current repository baseline (must be assumed by implementer):
- UI is Streamlit (`app.py`, `pages/*.py`) and requires `DASHBOARD_PASSWORD`.
- Data persistence is local SQLite in `data/toggl.db` via `src/data_store.py`.
- Toggl ingestion is Python (`src/toggl_client.py`, `src/sync.py`) with known rate limits: 30 requests/hour (free) and 600 requests/hour (premium) auto-detected by headers.
- There is no test framework currently configured.
- `frontend/` contains deploy artifacts only (`dist/`, `node_modules/`) and no editable source, so a new source frontend must be created.

Decision logic for platform selection (deterministic, no pseudocode):

Definitions:
- Let \( P = \{\text{firebase\_spark}, \text{supabase\_free}\} \).
- Let \( g_1(p) \in \{0,1\} \) be whether platform \(p\) supports a secret server-side execution path on free tier (required for `TOGGL_API_TOKEN` safety).
- Let \( g_2(p) \in \{0,1\} \) be whether platform \(p\) can be provisioned and deployed primarily from CLI (required for agent takeover).
- Let \( g_3(p) \in \{0,1\} \) be whether SQL-first schema migration from existing SQLite can be done without a full data-model rewrite.
- Let \( s_{sql}(p) \in [0,1] \) be SQL compatibility score.
- Let \( s_{cli}(p) \in [0,1] \) be CLI automation coverage score.
- Let \( s_{ux}(p) \in [0,1] \) be setup simplicity score (fewer human steps = higher score).

Hard gate formula:
- \( G(p) = g_1(p) \times g_2(p) \times g_3(p) \).
- Reject any platform where \( G(p)=0 \).

Weighted score formula for surviving options:
- \( S(p) = 0.50\cdot s_{sql}(p) + 0.30\cdot s_{cli}(p) + 0.20\cdot s_{ux}(p) \).
- Select \( p^* = \arg\max_{p \in P,\; G(p)=1} S(p) \).

Concrete evaluation used by this plan:
- `supabase_free`: \(g_1=1, g_2=1, g_3=1\), \(s_{sql}=1.00\), \(s_{cli}=0.95\), \(s_{ux}=0.90\), so \(S=0.965\).
- `firebase_spark`: \(g_3=0\) for this codebase because moving SQL-heavy query logic to Firestore requires major model/query redesign (violates minimal-confusion condition), so rejected by gate.

Therefore this plan selects **Supabase Free** as the primary target.

Operational logic for sync cadence and quota safety:

Definitions:
- \(Y\) = number of years synced (integer years, e.g., 2017..current).
- \(R_{full}\) = Toggl requests for full CSV sync.
- \(R_{quick}\) = Toggl requests for quick sync.
- \(L\) = Toggl hourly request cap (30 req/hour on free tier).
- \(\Delta t\) = minimum interval between requests in seconds (already 1.1s in existing client).

Formulas:
- \(R_{full} = 2 + Y\) (projects + tags + one CSV export per year).
- \(R_{quick} = 3\) (projects + tags + current-year CSV export).
- Safety condition for any one-hour window: \(R_{window} \leq L\).

Execution policy:
1. Default production schedule is one `quick` sync per day at `02:15 UTC`.
2. `full` sync is manual-only (operator-triggered) and not scheduled.
3. `enriched` sync (JSON) is manual-only and disabled by default in cloud mode due high call volume.
4. All persisted timestamps are UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SS+00:00`).

Authentication and access logic:
1. Replace `DASHBOARD_PASSWORD` UI gate with Supabase Auth email/password.
2. Enable RLS on all public tables.
3. Allow authenticated read-only dashboard access.
4. Deny all direct client writes; writes are only via service-role sync path.

3. **File Changes**

Create/modify exactly the following files.

If any listed file already exists from an earlier attempt, modify it in place and keep migration ordering stable.

Create (Supabase project and schema):
- `supabase/config.toml`
  - **Create** with project config and local dev defaults.
  - Add function directory settings and environment variable passthrough names only.
  - **Leave alone:** no hardcoded secrets; no environment-specific production keys.

- `supabase/migrations/20260318_000001_init_schema.sql`
  - **Create** Postgres schema mirroring existing SQLite logical model: `time_entries`, `projects`, `tags`, `clients`, `tasks`, `sync_meta`.
  - Include equivalent indexes for date/year/week/project/task/client fields.
  - Use JSONB for `tags` and `tag_ids` arrays (instead of TEXT JSON strings).
  - **Leave alone:** do not drop or rename columns from the existing logical model; preserve semantic column names used by current query logic.

- `supabase/migrations/20260318_000002_rls_policies.sql`
  - **Create** RLS enablement and policies.
  - Add `SELECT` policies for authenticated users.
  - **Critical:** every read policy must explicitly specify `FOR SELECT` (never rely on default policy scope).
  - Add `INSERT/UPDATE/DELETE` denial for anon/authenticated roles.
  - Add service-role-only write policy for sync path.
  - **Leave alone:** do not expose service-role-only tables/views to anon role.

- `supabase/seed.sql`
  - **Create** optional tiny fixture dataset (3-6 rows) for local verification.
  - Include at least one row with tag IDs and one with task/client data.
  - **Leave alone:** no personal or real production Toggl data.

Create (backend sync and transform scripts in Python, reusing existing Toggl client):
- `scripts/sync_to_supabase.py`
  - **Create** CLI script that imports `src.toggl_client` and `src.sync`-compatible transformation logic, then upserts to Supabase Postgres.
  - Support modes: `quick`, `full`, `enriched`.
  - Support `--earliest-year`, `--dry-run`, `--max-requests-per-hour` override for testing.
  - **Critical:** use existing `TogglClient` API names only (`get_projects`, `get_tags`, `get_clients`, `get_all_tasks`, `fetch_year_entries`, `fetch_year_entries_json`, `get_time_entries`).
  - **Critical:** any call to `get_time_entries` must include both required args: `start_date` and `end_date`.
  - **Leave alone:** do not alter existing `src/sync.py` behavior for local Streamlit until cutover is complete.

- `scripts/transform_toggl.py`
  - **Create** pure transformation helpers (no network I/O).
  - Parse CSV durations to integer seconds, derive `start_date/year/month/day/week`, normalize JSON arrays, and compute deterministic synthetic IDs for CSV-only entries.
  - **Leave alone:** do not embed DB connection code here.

- `scripts/supabase_db.py`
  - **Create** Postgres connection + upsert helpers (idempotent writes).
  - Use parameterized SQL only.
  - **Leave alone:** no ORM introduction; keep SQL explicit for predictable behavior.

Create (new web frontend source; current `frontend/` is artifacts only):
- `web/package.json`
  - **Create** new app package manifest with React + TypeScript + Vite + Supabase JS.
  - Add scripts: `dev`, `build`, `preview`, `test`.
  - **Leave alone:** do not modify `frontend/dist/*` artifacts.

- `web/tsconfig.json`, `web/vite.config.ts`, `web/index.html`
  - **Create** baseline frontend build config.
  - If `noUnusedLocals=true`, remove unused imports from TSX files (especially default `React` imports with `jsx: react-jsx`).
  - **Leave alone:** no SSR requirement in phase 1.

- `web/src/main.tsx`
  - **Create** app bootstrap with router and auth context.
  - **Leave alone:** no business logic in bootstrap file.

- `web/src/lib/supabase.ts`
  - **Create** Supabase client initializer using `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
  - **Leave alone:** never import service role key in frontend.

- `web/src/lib/api.ts`
  - **Create** typed query wrappers for dashboard/retrospect/chat data reads.
  - **Leave alone:** no direct SQL strings in components.

- `web/src/pages/Homepage.tsx`
  - **Create** weekly highlights page matching current behavior from `pages/0_Homepage.py`.
  - **Leave alone:** keep filter semantics: current ISO week, tag name `Highlight` exact match.
  - **Critical:** do not use latest-record shortcut queries that can leak prior-week highlights.

- `web/src/pages/Dashboard.tsx`
  - **Create** year/all-time/custom range dashboard with metrics + project/tag/client/task charts.
  - **Leave alone:** preserve metric definitions and units from Streamlit version.

- `web/src/pages/Retrospect.tsx`
  - **Create** on-this-day, week view, year-vs-year pages using SQL-backed data APIs.
  - **Leave alone:** preserve ISO week logic and Monday-first weekday ordering.

- `web/src/pages/Chat.tsx`
  - **Create** chat UI shell and wire to server endpoint for answer generation.
  - **Leave alone:** no direct prompt parsing in browser (keep logic server-side).

- `web/src/styles/theme.css`
  - **Create** cyberpunk palette equivalent to existing visual identity.
  - **Leave alone:** do not introduce dark/light mode toggle in phase 1.

Create (edge/server logic for chat + lightweight aggregations when SQL view is insufficient):
- `supabase/functions/chat-query/index.ts`
  - **Create** Edge Function that ports regex routing from `src/queries.py`.
  - Accept JSON `{ question: string }` and return `{ answer: string }`.
  - **Critical:** enforce auth and return `401` for missing/invalid bearer token.
  - **Leave alone:** no third-party LLM integration in phase 1.

- `supabase/functions/chat-query/deno.json`
  - **Create** function-specific config.
  - **Leave alone:** no unrestricted external network domains.

Create (database views and RPC helpers to simplify frontend queries):
- `supabase/migrations/20260318_000003_views_and_rpc.sql`
  - **Create** read-only views/RPCs for:
    - overview metrics,
    - project/tag/client/task aggregates,
    - date-across-years and week-across-years,
    - monthly trend and heatmap data.
  - **Critical:** use parameter names that cannot collide with column names (example: `_start_date`, `_end_date`) to avoid tautological filters.
  - **Leave alone:** no write-capable RPC in anon/auth role.

Create (CI/CD and scheduler with minimal user steps):
- `.github/workflows/sync-quick.yml`
  - **Create** daily cron workflow at `15 2 * * *` UTC + manual dispatch.
  - Run `python scripts/sync_to_supabase.py --mode quick`.
  - **Leave alone:** do not store secrets directly in workflow YAML.

- `.github/workflows/sync-full.yml`
  - **Create** manual-only workflow with inputs `earliest_year` and `mode` (`full` or `enriched`).
  - **Leave alone:** no automatic schedule for full/enriched.

- `.github/workflows/web-deploy.yml`
  - **Create** web build + deploy workflow (target chosen in implementation step; prefer GitHub Pages to avoid extra account signup).
  - **Leave alone:** no paid hosting dependencies.

Modify (existing repo metadata/config):
- `.env.example`
  - **Modify** to add:
    - `SUPABASE_URL`,
    - `SUPABASE_ANON_KEY`,
    - `SUPABASE_SERVICE_ROLE_KEY`,
    - `SUPABASE_DB_URL` (direct Postgres URL),
    - keep `TOGGL_API_TOKEN`.
  - Keep `DASHBOARD_PASSWORD` but mark as legacy for local Streamlit only.

- `.gitignore`
  - **Modify** to add `web/node_modules/`, `web/dist/`, `.supabase/`, and any generated local env files.
  - Keep existing `data/` ignore rules.

- `requirements.txt`
  - **Modify** to add Postgres dependency (`psycopg[binary]` or equivalent) for sync writer.
  - Keep existing analysis dependencies unchanged.

- `AGENTS.md`
  - **Modify** project architecture section to document dual mode during migration:
    - legacy Streamlit path,
    - new Supabase + web path.
  - Add canonical run/deploy commands for the new stack.

Do not modify in this migration phase:
- `analysis/**` (already standalone and should continue reading local SQLite unless separate migration is explicitly requested later).
- `src/theme.py` visual constants should be treated as reference values only; frontend copies values into CSS variables.
- `frontend/dist/**` and `frontend/node_modules/**` should be treated as legacy artifacts, not source of truth.

4. **Function Signatures**

Define these interfaces exactly (or stricter), then implement:

Python (sync + DB writer):

```python
from dataclasses import dataclass
from typing import Literal, Any

@dataclass
class SyncSummary:
    mode: Literal["quick", "full", "enriched"]
    years_processed: int
    entries_written: int
    projects_written: int
    tags_written: int
    clients_written: int
    tasks_written: int
    errors: list[str]

def parse_duration_hms(duration_hms: str) -> int:
    """Return duration in whole seconds parsed from HH:MM:SS."""

def derive_time_parts(start_iso: str) -> tuple[str, int, int, int, int]:
    """Return (start_date, start_year, start_month, start_day, start_week_iso)."""

def build_synthetic_id(start_iso: str, stop_iso: str, description: str, project_name: str, duration_sec: int) -> int:
    """Return deterministic positive integer ID from SHA-256 seed fields."""

def transform_csv_entry(row: dict[str, str]) -> dict[str, Any]:
    """Return normalized time-entry dict from one Toggl CSV row."""

def transform_json_entry(row: dict[str, Any], workspace_id: int) -> dict[str, Any]:
    """Return normalized time-entry dict from one Toggl JSON entry."""

def upsert_time_entries_pg(conn, entries: list[dict[str, Any]]) -> int:
    """Return count of time-entry rows upserted into Postgres."""

def upsert_projects_pg(conn, projects: list[dict[str, Any]]) -> int:
    """Return count of project rows upserted into Postgres."""

def upsert_tags_pg(conn, tags: list[dict[str, Any]]) -> int:
    """Return count of tag rows upserted into Postgres."""

def upsert_clients_pg(conn, clients: list[dict[str, Any]]) -> int:
    """Return count of client rows upserted into Postgres."""

def upsert_tasks_pg(conn, tasks: list[dict[str, Any]]) -> int:
    """Return count of task rows upserted into Postgres."""

def run_sync(mode: Literal["quick", "full", "enriched"], earliest_year: int, dry_run: bool = False) -> SyncSummary:
    """Return full sync summary for one sync run."""
```

TypeScript (web data access and chat):

```ts
export type DateRange = { startDate: string; endDate: string };
export type ViewMode = "single_year" | "all_time" | "custom_range";

export interface OverviewMetrics {
  totalHours: number;
  totalEntries: number;
  uniqueProjects: number;
  activeDays: number;
  avgHoursPerDay: number;
}

export async function fetchOverview(mode: ViewMode, year: number | null, range: DateRange | null): Promise<OverviewMetrics>;
// Returns top-line dashboard metrics for the selected scope.

export async function fetchProjectBreakdown(mode: ViewMode, year: number | null, range: DateRange | null): Promise<Array<{ projectName: string; hours: number; entries: number }>>;
// Returns project aggregate rows sorted by descending hours.

export async function fetchTagBreakdown(mode: ViewMode, year: number | null, range: DateRange | null): Promise<Array<{ tagName: string; hours: number; entries: number }>>;
// Returns tag aggregate rows sorted by descending hours.

export async function fetchClientBreakdown(mode: ViewMode, year: number | null, range: DateRange | null): Promise<Array<{ clientName: string; hours: number; entries: number }>>;
// Returns client aggregate rows sorted by descending hours.

export async function fetchTaskBreakdown(mode: ViewMode, year: number | null, range: DateRange | null): Promise<Array<{ taskName: string; hours: number; entries: number }>>;
// Returns task aggregate rows sorted by descending hours.

export async function fetchOnThisDay(month: number, day: number): Promise<Array<{ year: number; hours: number; entries: number }>>;
// Returns cross-year aggregates for a specific month/day.

export async function fetchWeekAcrossYears(isoWeek: number): Promise<Array<{ year: number; hours: number; entries: number }>>;
// Returns cross-year aggregates for one ISO week number.

export async function askChat(question: string): Promise<{ answer: string }>;
// Returns chat answer text generated by server-side regex query engine.
```

Supabase Edge Function (chat):

```ts
export interface ChatQueryRequest { question: string }
export interface ChatQueryResponse { answer: string }

export default async function handler(req: Request): Promise<Response>;
// Returns JSON ChatQueryResponse with HTTP 200 on success, 400 for invalid input, 401 for unauthenticated access.
```

5. **Test Specifications**

Use both unit tests and integration checks with explicit fixtures.

Python transformation tests:
- `parse_duration_hms("01:30:15")` returns `5415` (seconds).
- `parse_duration_hms("0:00:00")` returns `0`.
- `parse_duration_hms("invalid")` returns `0` (graceful parse fail).

- `derive_time_parts("2024-12-31T23:30:00+00:00")` returns:
  - `start_date="2024-12-31"`,
  - `start_year=2024`,
  - `start_month=12`,
  - `start_day=31`,
  - `start_week_iso=1` (ISO week can roll to week 1 at year boundary).

- `build_synthetic_id(...)` deterministic fixture:
  - input tuple:
    - `start_iso="2024-01-02T09:00:00"`
    - `stop_iso="2024-01-02T10:30:00"`
    - `description="Deep Work"`
    - `project_name="Project Alpha"`
    - `duration_sec=5400`
  - expected SHA-256 hex digest:
    - `c05022c756acccbeefc54d59a25fc139dc9d21dc9fc56848702c3a6c7b95cc0a`
  - expected stability assertion:
    - calling function twice in same process returns identical integer ID value.

Database upsert tests (local Supabase/Postgres test DB):
- Seed one `time_entries` row with `toggl_id=12345`, then upsert same `toggl_id` with changed `description="Updated"`.
  - expected row count stays `1`.
  - expected final `description` is `"Updated"`.

- Seed one CSV-style row with `toggl_id=NULL` and one enriched row with same `(start, duration, description)` triple.
  - expected dedupe behavior: exactly one logical row retained for analytics.

RLS and auth tests:
- Unauthenticated request to protected read endpoint returns HTTP `401`.
- Authenticated non-service user attempts insert into `time_entries` and gets HTTP `403` or Postgres permission error.
- Service-role sync path inserts one row successfully and returns affected count `1`.
- Policy-scope test: inspect generated policy definitions and assert reader policies are `FOR SELECT` (not `FOR ALL`).

Frontend query contract tests:
- With fixture dataset of 3 entries:
  - `2h` + `1h` on `Project A`, `0.5h` on `Project B` over two active days,
  - expected `fetchOverview` response:
    - `totalHours=3.5`,
    - `totalEntries=3`,
    - `uniqueProjects=2`,
    - `activeDays=2`,
    - `avgHoursPerDay=1.75`.

Chat parity tests (ported from current regex behavior):
- input: `"top projects in 2024"`
  - expected response contains heading text `"Top 10 Projects (2024):"`.
- input: `"today"`
  - expected response contains phrase `"across all years"`.
- input: `"task xyz_nonexistent_123"`
  - expected response starts with `"No entries found for task matching"`.
- input: unauthenticated request (no `Authorization` header) to `chat-query`
  - expected HTTP status `401`.

Sync compatibility tests:
- `python scripts/sync_to_supabase.py --mode quick --dry-run`
  - expected: no `AttributeError` for non-existent `TogglClient` method names.
- `python scripts/sync_to_supabase.py --mode enriched --dry-run`
  - expected: no `TypeError` from missing `end_date` argument to `get_time_entries`.

RPC date-filter correctness tests:
- Seed rows dated `2024-01-01`, `2024-06-01`, and `2025-01-01`; query with `_start_date='2024-06-01'` and `_end_date='2024-12-31'`.
  - expected: only `2024-06-01` contributes to metrics.

Scheduler tests:
- Manual workflow dispatch `mode=quick` with empty DB:
  - expected exit code `0`.
  - expected `sync_meta.last_incremental_sync` set to non-empty UTC timestamp.
- Manual workflow dispatch `mode=full`, `earliest_year=current_year`:
  - expected requests made `<= 3` and completion under one run.

Non-regression checks against existing Streamlit logic:
- For identical fixture rows, month/day and ISO week aggregates in new SQL/RPC endpoints must match existing `src.data_store` query outputs exactly.
- Units must remain `hours` as decimal floating-point (not minutes) in dashboard metrics and chart datasets.

6. **Implementation Order**

1. Create Supabase project scaffold (`supabase/config.toml`) and initial SQL migration files; run local `supabase start` and `supabase db reset` to verify schema compiles.
2. Implement RLS policies and validate auth/write separation with direct SQL tests before any app code is written; explicitly verify every reader policy is `FOR SELECT`.
3. Build Python Postgres writer (`scripts/supabase_db.py`) and pure transform module (`scripts/transform_toggl.py`); write unit tests for transforms first.
4. Implement sync CLI (`scripts/sync_to_supabase.py`) in `quick` mode only using actual `TogglClient` method names; verify one successful end-to-end run into Supabase.
5. Add `full` and `enriched` modes with explicit manual-only flags; verify summary counts and confirm no missing-argument failures for `get_time_entries(start_date, end_date)`.
6. Create SQL views/RPCs for dashboard/retrospect read patterns; validate output against SQLite-based expected fixtures and confirm date-range filters with non-overlapping fixture dates.
7. Implement `chat-query` Edge Function and port regex routing behavior from `src/queries.py`; enforce auth and run both parity tests and unauthenticated (401) tests.
8. Scaffold new `web/` React + TypeScript app and wire Supabase auth/login flow.
9. Build pages in order: `Homepage` -> `Dashboard` -> `Retrospect` -> `Chat`; after each page, verify with fixed fixture dataset and confirm Homepage uses current ISO week boundary.
10. Resolve TypeScript strict-build blockers (including unused imports with `noUnusedLocals=true`) and verify `npm run build` passes.
11. Add GitHub Actions workflows: `sync-quick` daily and `sync-full` manual; test manual dispatch first, then enable schedule.
12. Configure web deployment workflow (free target; prefer GitHub Pages to avoid additional signup), deploy preview, and confirm production URL serves authenticated app.
13. Update `.env.example`, `.gitignore`, and `AGENTS.md` documentation; include clear "user does only auth" setup instructions.
14. Run final verification checklist: auth, RLS, sync, metrics parity, chat parity, TypeScript build, and timezone/ISO week edge cases.
15. Only after parity is confirmed, mark Streamlit path as legacy in docs; do not delete legacy files in first migration PR.

7. **Gotchas**

- `frontend/` is not real source code in this repo; it only has build artifacts, so editing `frontend/dist/*` is a dead end.
- Supabase service role key must never be shipped to browser code; only `anon` key belongs in `web/` env.
- Timezone handling is the biggest correctness risk: store and compare in UTC, and only localize in UI rendering.
- ISO week numbering is not calendar-week numbering; dates near Jan 1 can belong to ISO week 52/53/1 of adjacent ISO year.
- Keep duration units explicit: source duration is **seconds** (`INTEGER`), analytics duration is **hours** (`REAL`) where `hours = seconds / 3600.0`.
- Currency fields (`projects.currency`) are ISO 4217 codes like `USD`; never treat missing currency as numeric zero.
- Tag arrays should be JSONB arrays in Postgres; string-contains matching can produce false positives if not normalized.
- RLS defaults can silently deny reads/writes; verify each policy with authenticated and unauthenticated tokens before frontend debugging.
- Postgres policy scope footgun: omitting `FOR SELECT` creates `FOR ALL` policy scope, which can accidentally allow writes.
- SQL argument naming footgun: function parameters named like columns (`start_date`, `end_date`) can create tautological predicates.
- Toggl API integration footgun: invented method names or wrong argument counts against `src/toggl_client.py` fail at runtime.
- Daily scheduled sync should remain `quick` only; auto-running `full` or `enriched` can exceed Toggl free-tier hourly limits and confuse operations.
- Supabase free projects can pause when idle; first request after idle may have cold-start delay, so frontend should show explicit loading state.
- TypeScript strict mode footgun: `jsx: react-jsx` plus `noUnusedLocals=true` fails builds when unused default `React` imports remain.
- Do not remove Streamlit files during first cutover; keep them as rollback path until web parity is validated in production.
- Naming conventions must remain stable with existing project:
  - snake_case for Python files/functions,
  - kebab-case for workflow and issue-plan filenames,
  - UTC ISO-8601 timestamps for all persisted datetime text values.
