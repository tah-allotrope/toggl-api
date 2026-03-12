# ISSUE-1: Migrate Streamlit App to Firebase

## 1. Objective

Migrate the Toggl Time Journal from a Streamlit single-process Python app (with ephemeral SQLite storage on Streamlit Community Cloud) to a Firebase-hosted architecture — using **Firebase Hosting** for a static frontend, **Cloud Firestore** for persistent data, and **Firebase Cloud Functions (Python)** for the Toggl API sync and chat engine — so that data persists across cold starts, the UI is faster and more customizable, and the app is no longer constrained by Streamlit's component model.

---

## 2. Decision Logic

### 2.1 Why Firebase (not just "a rewrite")

The current app loses all enriched data on every Streamlit Community Cloud cold start because the filesystem is ephemeral and SQLite is a local file. Firebase Firestore is a persistent, serverless NoSQL database that survives restarts. Firebase Hosting serves a static SPA with a global CDN. Cloud Functions run the Python sync/chat logic on demand without a long-running server.

### 2.2 Architecture Mapping

| Current (Streamlit)                     | Target (Firebase)                                  |
|-----------------------------------------|----------------------------------------------------|
| `app.py` — router + auth gate           | Firebase Hosting SPA + Firebase Auth (email/pass)  |
| `pages/*.py` — 4 Streamlit pages        | 4 SPA routes rendered by React (or vanilla JS)     |
| `src/data_store.py` — SQLite read/write | Firestore collections + Cloud Function writes      |
| `src/toggl_client.py` — API client      | Cloud Function (Python) — unchanged logic          |
| `src/sync.py` — sync orchestrator       | Cloud Function (Python) — triggered via HTTP       |
| `src/queries.py` — chat NLP             | Cloud Function (Python) — HTTP callable            |
| `src/theme.py` — CSS + Plotly template  | CSS file served by Hosting + Plotly.js in browser  |
| `st.session_state` — auth + chat history| Firebase Auth + Firestore `chat_sessions` collection|
| `data/toggl.db` — SQLite file           | Firestore (structured) + Storage (raw JSON backups)|
| `analysis/` module (CLI)                | **Unchanged** — stays as local CLI, reads Firestore export or local SQLite |

### 2.3 Data Model Mapping: SQLite → Firestore

Firestore is a document-oriented NoSQL database. Each SQLite table becomes a Firestore **collection**. Each row becomes a **document**. Firestore document IDs should be strings. The mapping:

**Collection: `time_entries`**
- Document ID: `{toggl_id}` (string of the integer Toggl ID). For CSV-only entries that have no toggl_id, use the existing SHA-256 synthetic ID stored in the `id` column.
- Fields map 1:1 from the SQLite `time_entries` columns:
  - `toggl_id`: number | null
  - `project`: string (project name)
  - `project_id`: number | null
  - `client_name`: string | null
  - `task_name`: string | null
  - `description`: string
  - `start`: Firestore Timestamp (convert from ISO 8601 string `YYYY-MM-DDTHH:MM:SS+ZZ:ZZ`)
  - `end`: Firestore Timestamp | null
  - `duration_seconds`: number (integer, total seconds — NOT milliseconds)
  - `tags_json`: array of strings (convert from JSON-encoded string `'["Tag1","Tag2"]'` to native Firestore array)
  - `user_id`: number | null
  - `billable`: boolean (convert from integer 0/1)
  - `enriched`: boolean (convert from integer 0/1)
  - `currency`: string | null
  - `rate`: number | null (hourly rate in the currency specified)
  - `at`: string (ISO 8601 last-modified timestamp from Toggl)
  - `synced_at`: string (ISO 8601 timestamp of when this record was synced)

**Collection: `projects`**
- Document ID: `{id}` (string of integer Toggl project ID)
- Fields: `name`, `workspace_id`, `client_id`, `color`, `active` (boolean), `billable` (boolean), `is_private` (boolean), `estimated_hours` (number|null), `rate` (number|null), `currency` (string|null), `fixed_fee` (number|null), `actual_hours` (number|null), `created_at`, `at`, `server_deleted_at`

**Collection: `tags`**
- Document ID: `{id}` (string of integer Toggl tag ID)
- Fields: `name`, `workspace_id`, `creator_id`, `at`, `deleted_at`

**Collection: `clients`**
- Document ID: `{id}` (string of integer Toggl client ID)
- Fields: `name`, `workspace_id`, `archived` (boolean)

**Collection: `tasks`**
- Document ID: `{id}` (string of integer Toggl task ID)
- Fields: `name`, `project_id`, `workspace_id`, `user_id`, `active` (boolean), `estimated_seconds` (number|null), `tracked_seconds` (number), `at`

**Collection: `sync_meta`**
- Document ID: the key string (e.g., `"last_csv_sync"`, `"last_enriched_sync"`, `"enrichment_earliest_year"`)
- Fields: `value` (string)

**Collection: `chat_sessions`** (new — replaces `st.session_state.messages`)
- Document ID: auto-generated
- Fields: `user_id` (string), `messages` (array of `{role: "user"|"assistant", content: string, timestamp: Timestamp}`), `created_at` (Timestamp)

### 2.4 Firestore Indexes Required

Firestore requires composite indexes for queries that filter/sort on multiple fields. Based on the existing SQL queries in `src/data_store.py` and `src/queries.py`:

1. `time_entries`: composite index on (`start`, ascending) — for date range queries
2. `time_entries`: composite index on (`project`, ascending) + (`start`, ascending) — for project-filtered date ranges
3. `time_entries`: composite index on (`tags_json`, array-contains) + (`start`, ascending) — for tag-filtered queries (e.g., "Highlight" tag on Homepage)
4. `time_entries`: composite index on (`client_name`, ascending) + (`start`, ascending)
5. `time_entries`: composite index on (`task_name`, ascending) + (`start`, ascending)

These will be defined in `firestore.indexes.json`.

### 2.5 Authentication Flow

Current: `st.session_state["authenticated"]` checked against `DASHBOARD_PASSWORD` env var (plaintext comparison, default "290391").

Target: Firebase Authentication with Email/Password provider.
- Create a single user account (this is a personal dashboard, not multi-tenant).
- Email: whatever the owner specifies during setup.
- Password: whatever they choose.
- The frontend checks `firebase.auth().onAuthStateChanged()` and shows a login form if not authenticated.
- Cloud Functions verify the Firebase ID token on every request using `firebase_admin.auth.verify_id_token()`.
- The Toggl API token is stored in Firebase **environment configuration** (`firebase functions:config:set toggl.api_token="..."`) — NOT in Firestore, NOT in client code.

### 2.6 Sync Trigger Logic

Current: Three sidebar buttons in `app.py` — Quick Sync, Full Sync, Enriched Sync — each calling functions from `src/sync.py` synchronously with `st.spinner`.

Target: Three HTTP-callable Cloud Functions. The frontend calls them via `firebase.functions().httpsCallable("syncQuick")`. Each function:
1. Verifies the Firebase Auth ID token.
2. Reads the Toggl API token from environment config.
3. Runs the same sync logic (adapted from `src/sync.py` + `src/toggl_client.py`).
4. Writes results to Firestore instead of SQLite.
5. Returns a status JSON `{success: bool, entries_synced: int, message: string}`.

Cloud Functions have a **540-second (9 minute) timeout** on the paid plan. The full enrichment sync currently takes ~2 hours for 10 years of data. This MUST be handled by:
- Breaking the enrichment sync into per-year chunks.
- Each chunk is a separate function invocation.
- The frontend chains them: call year 2017, wait for response, call year 2018, etc.
- OR: use a Cloud Task queue (more complex, skip for v1 — just do sequential HTTP calls from the client).

### 2.7 Chart Rendering

Current: `st.plotly_chart(fig)` passes a Plotly Figure object from Python to the Streamlit frontend, which renders it using Plotly.js.

Target: The frontend loads `plotly.js` directly. The Cloud Functions (or Firestore reads from the client SDK) return raw data as JSON. The frontend builds Plotly traces in JavaScript.

The cyberpunk Plotly template currently defined in `src/theme.py` as a Python dict must be translated to an equivalent JavaScript object and applied via `Plotly.newPlot(div, data, layout, config)`.

---

## 3. File Changes

### 3.0 New Branch

Create a new git branch named `firebase-migration` off of `main` (or the current default branch). All changes below happen on this branch.

```
git checkout -b firebase-migration
```

### 3.1 Firebase Configuration Files (CREATE)

**`firebase.json`** (CREATE at project root)
- Purpose: Firebase project configuration.
- Contents:
  - `hosting.public`: `"frontend/dist"` (the built SPA output directory)
  - `hosting.rewrites`: single rule `{"source": "**", "destination": "/index.html"}` (SPA catch-all)
  - `functions.source`: `"functions"` (Python Cloud Functions directory)
  - `functions.runtime`: `"python312"`
  - `firestore.rules`: `"firestore.rules"`
  - `firestore.indexes`: `"firestore.indexes.json"`

**`.firebaserc`** (CREATE at project root)
- Purpose: Links to the Firebase project ID.
- Contents: `{"projects": {"default": "<FIREBASE_PROJECT_ID>"}}` — the implementer must replace `<FIREBASE_PROJECT_ID>` with their actual project ID from the Firebase Console.

**`firestore.rules`** (CREATE at project root)
- Purpose: Firestore security rules.
- Logic:
  - All collections (`time_entries`, `projects`, `tags`, `clients`, `tasks`, `sync_meta`, `chat_sessions`): allow read/write only if `request.auth != null` (any authenticated user — this is a single-user app).
  - Default: deny all.

**`firestore.indexes.json`** (CREATE at project root)
- Purpose: Composite index definitions (see Section 2.4).
- Define all 5 composite indexes listed above.

### 3.2 Cloud Functions (CREATE)

Create directory: `functions/`

**`functions/requirements.txt`** (CREATE)
```
firebase-functions>=0.4.0
firebase-admin>=6.4.0
requests>=2.31.0
pandas>=2.1.0
python-dotenv>=1.0.0
```

**`functions/main.py`** (CREATE)
- Purpose: Entry point for all Cloud Functions. Contains 6 exported functions:
  1. `sync_quick` — HTTP callable, runs CSV sync for current year only
  2. `sync_full` — HTTP callable, runs CSV sync for all years (2017–current)
  3. `sync_enriched_year` — HTTP callable, accepts `{year: int}` param, runs JSON enrichment for one year
  4. `chat_answer` — HTTP callable, accepts `{question: string}` param, returns `{answer: string}`
  5. `get_sync_status` — HTTP callable, returns sync metadata from `sync_meta` collection
  6. `get_stats` — HTTP callable, returns total entry count, date range, enrichment coverage
- Each function: verifies auth token, delegates to internal modules, catches exceptions, returns JSON.

**`functions/toggl_client.py`** (CREATE — adapted copy of `src/toggl_client.py`)
- Copy the entire `src/toggl_client.py` file.
- Remove all Streamlit imports (`import streamlit as st`).
- Remove the `st.secrets` fallback in `_get_api_token()`. Instead, read the token from Firebase environment config: `os.environ.get("TOGGL_API_TOKEN")` (set via `firebase functions:config`).
- The `RateLimiter` class and `TogglClient` class remain identical in logic.
- Remove type hint `X | Y` syntax if targeting Python 3.10 and Cloud Functions runtime doesn't support it — but Python 3.12 runtime supports it, so this should be fine.

**`functions/sync_engine.py`** (CREATE — adapted from `src/sync.py`)
- Copy the sync logic from `src/sync.py`.
- Replace every `sqlite3` / `managed_connection()` call with Firestore writes using `firebase_admin.firestore`.
- Replace `upsert_time_entries(conn, entries)` with a function `upsert_time_entries_firestore(db, entries)` that:
  - For each entry, computes the document ID (use `toggl_id` as string if present, else the SHA-256 `id`).
  - Uses `db.collection("time_entries").document(doc_id).set(entry_dict, merge=True)` for upsert semantics.
  - Converts `start`/`end` from ISO 8601 strings to `datetime` objects (Firestore SDK auto-converts to Timestamps).
  - Converts `tags_json` from JSON string to Python list.
  - Converts `billable` and `enriched` from 0/1 to Python bool.
- Replace `save_sync_meta(conn, key, value)` with `db.collection("sync_meta").document(key).set({"value": value})`.
- Replace `get_sync_meta(conn, key)` with Firestore document read.
- Remove the `progress_callback` parameter (no Streamlit progress bar). Instead, return a summary dict.
- Remove raw JSON file saving to `data/raw/` — instead, optionally upload to Firebase Storage bucket `raw-json/` (skip for v1 if complexity is too high).

**`functions/data_store.py`** (CREATE — Firestore query helpers)
- Purpose: Replaces `src/data_store.py` with Firestore equivalents.
- Functions (all take `db` as first parameter, which is `firestore.client()`):
  - `get_entries(db, start_date: str | None, end_date: str | None, project: str | None, tag: str | None) -> list[dict]` — queries `time_entries` collection with optional filters. Returns list of dicts. Dates are ISO 8601 strings like `"2024-01-15"` which must be converted to `datetime` for Firestore comparison.
  - `get_entries_for_date_across_years(db, month: int, day: int) -> list[dict]` — queries entries where the month and day of `start` match. **GOTCHA**: Firestore cannot query on derived fields (month/day of a timestamp). Solution: add `start_month` (int 1–12) and `start_day` (int 1–31) fields to each document during sync. Then query with `.where("start_month", "==", month).where("start_day", "==", day)`.
  - `search_entries(db, keyword: str) -> list[dict]` — **GOTCHA**: Firestore has NO full-text search. Options: (a) fetch all descriptions client-side and filter (bad for 10 years of data), (b) use a `description_lower` field and do prefix matching with `>=` / `<` (limited), (c) integrate Algolia or Typesense. **For v1**: fetch all descriptions from Firestore in the Cloud Function and filter in Python (same as current SQLite `LIKE` query, just in memory).
  - `get_total_stats(db) -> dict` — count documents, find min/max `start`.
  - `get_enrichment_stats(db) -> dict` — count documents where `enriched == true` vs total.
  - `get_projects(db) -> list[dict]`, `get_tags(db) -> list[dict]`, `get_clients(db) -> list[dict]`, `get_tasks(db) -> list[dict]` — read full collections.

**`functions/chat_engine.py`** (CREATE — adapted from `src/queries.py`)
- Copy `src/queries.py`.
- Replace `managed_connection()` + raw SQL with calls to `functions/data_store.py` Firestore helpers.
- Replace `pd.read_sql_query(...)` with: fetch list of dicts from Firestore, then `pd.DataFrame(entries)`.
- The regex dispatch logic, fuzzy matching, and all 16 answer functions remain structurally identical — only the data source changes.
- Remove the `import sqlite3` and replace with `from firebase_admin import firestore`.

### 3.3 Frontend SPA (CREATE)

Create directory: `frontend/`

**Technology choice**: Use **vanilla JavaScript + Vite** (no React/Vue/Angular). Rationale: the current UI is simple (4 pages, no complex interactivity beyond Plotly charts), the owner knows Python not JS frameworks, and vanilla JS minimizes build complexity.

**`frontend/package.json`** (CREATE)
```json
{
  "name": "toggl-time-journal",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "firebase": "^10.14.0",
    "plotly.js-dist-min": "^2.35.0"
  },
  "devDependencies": {
    "vite": "^6.0.0"
  }
}
```

**`frontend/index.html`** (CREATE)
- Single HTML file, SPA shell.
- Includes `<div id="app"></div>` container.
- Loads `<script type="module" src="/src/main.js"></script>`.
- Loads Share Tech Mono font from Google Fonts (same as current Streamlit theme).
- Includes a `<link rel="stylesheet" href="/src/styles.css">`.

**`frontend/src/main.js`** (CREATE)
- Initializes Firebase app with config object (project ID, API key, auth domain — from Firebase Console).
- Sets up `firebase.auth().onAuthStateChanged()`:
  - If not authenticated → render login form.
  - If authenticated → render the app shell (sidebar + page router).
- Implements a simple hash-based router (`window.location.hash`):
  - `#/` or `#/homepage` → Homepage
  - `#/dashboard` → Dashboard
  - `#/retrospect` → Retrospect
  - `#/chat` → Chat
- Sidebar: navigation links + sync buttons (Quick Sync, Full Sync, Enriched Sync).
- Sync buttons call Cloud Functions via `firebase.functions().httpsCallable("sync_quick")` etc.

**`frontend/src/auth.js`** (CREATE)
- `renderLoginForm(container)` — renders email + password inputs + submit button into the given DOM element.
- On submit: calls `firebase.auth().signInWithEmailAndPassword(email, password)`.
- Error handling: display error message in a `<p class="error">` element.
- `signOut()` — calls `firebase.auth().signOut()`.

**`frontend/src/pages/homepage.js`** (CREATE)
- Replicates `pages/0_Homepage.py`.
- On load: query Firestore client-side for time entries in the current ISO week where `tags_json` array-contains `"Highlight"`.
- Render each entry as a styled card (project name, description, duration, date).
- Duration formatting: convert `duration_seconds` to `Xh Ym` format. Formula: `hours = Math.floor(seconds / 3600)`, `minutes = Math.floor((seconds % 3600) / 60)`.
- Current ISO week calculation: use `getISOWeek()` helper (see below).

**`frontend/src/pages/dashboard.js`** (CREATE)
- Replicates `pages/1_Dashboard.py` (the most complex page — 474 lines of Python).
- Sidebar filter: year selector dropdown (populated from min/max year in data) + "All Time" + "Custom Range" (two date pickers).
- On filter change: query Firestore for entries in range, aggregate in JavaScript.
- **5 summary metrics**: Total Hours, Unique Projects, Unique Tags, Entries, Daily Average.
  - Total Hours: `sum(duration_seconds) / 3600`, display with 1 decimal.
  - Daily Average: `totalHours / numberOfDaysInRange`.
- **Charts** (all using Plotly.js):
  - Project breakdown: horizontal bar chart (hours per project, sorted descending) + pie chart.
  - Tag breakdown: horizontal bar chart.
  - Client breakdown: horizontal bar chart.
  - Monthly trend: line chart (x = month label `"Jan 2024"`, y = total hours).
  - Daily heatmap: GitHub-style grid. Each cell = one day. Color intensity = hours tracked. Use `Plotly.newPlot()` with `type: "heatmap"`. X-axis = ISO week number (1–53), Y-axis = day of week (Mon–Sun), Z = hours.
  - Top descriptions: HTML `<table>` (not a chart).

**`frontend/src/pages/retrospect.js`** (CREATE)
- Replicates `pages/2_Retrospect.py`.
- 3 tabs (implement as `<div>` toggles with button bar):
  1. **On This Day**: Date picker input. Fetch entries for that month/day across all years. Render bar chart (x = year, y = hours) + expandable detail per year.
  2. **Week View**: ISO week slider (1–53). Fetch entries for that ISO week across years. Stacked bar chart (x = year, segments = projects).
  3. **Year vs Year**: Two year dropdowns. Fetch both years' entries. Side-by-side monthly grouped bar chart + project comparison table + summary stats.

**`frontend/src/pages/chat.js`** (CREATE)
- Replicates `pages/3_Chat.py`.
- Render a chat UI: scrollable message list + input box at bottom.
- On submit: append user message to DOM, call `firebase.functions().httpsCallable("chat_answer")({question: text})`, append assistant response.
- Quick query buttons: "What did I work on today?", "Top projects this year", "How much did I track this week?", etc.
- Chat history: store in local `messages` array (in-memory). Optionally persist to Firestore `chat_sessions` collection.

**`frontend/src/theme.js`** (CREATE)
- Export the cyberpunk color constants as a JS object:
  ```js
  export const COLORS = {
    bg: "#0a0a1a", bg2: "#12122a", bg3: "#1a1a3e",
    cyan: "#00fff9", magenta: "#ff00ff", green: "#39ff14",
    purple: "#bf00ff", pink: "#ff2a6d", gold: "#ffd700",
    amber: "#ffbf00", red: "#ff0040", text: "#e0e0ff",
    textMuted: "#8888aa", grid: "#2a2a4a", border: "#3a3a6a"
  };
  ```
- Export the Plotly layout template as a JS object (translate from the Python dict in `src/theme.py` lines ~380–440):
  ```js
  export const PLOTLY_LAYOUT = {
    paper_bgcolor: COLORS.bg2,
    plot_bgcolor: COLORS.bg,
    font: { family: "Share Tech Mono, monospace", color: COLORS.text, size: 12 },
    xaxis: { gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
    yaxis: { gridcolor: COLORS.grid, zerolinecolor: COLORS.grid },
    colorway: [COLORS.cyan, COLORS.magenta, COLORS.green, COLORS.purple, COLORS.pink, COLORS.gold, COLORS.amber, COLORS.red],
    margin: { l: 60, r: 30, t: 50, b: 50 }
  };
  ```
- Export `NEON_SEQUENCE` (16 colors) and all 5 color scales as JS arrays.

**`frontend/src/styles.css`** (CREATE)
- Translate the ~370 lines of CSS from `src/theme.py` (the string embedded in `inject_custom_css()`).
- Key elements: dark background (`#0a0a1a`), neon text glows, Share Tech Mono font, scanline overlay, styled scrollbars, card styling for metrics, chat bubble styling.
- Remove all Streamlit-specific selectors (`.stApp`, `.stSidebar`, `.stMetric`, `[data-testid="stHeader"]`, etc.) and replace with semantic class names.

**`frontend/src/utils.js`** (CREATE)
- `getISOWeek(date)` — returns ISO 8601 week number (1–53). Algorithm: Thursday-based, matching Python's `datetime.isocalendar()`.
- `formatDuration(seconds)` — returns string like `"2h 35m"`. If < 60 seconds, return `"< 1m"`.
- `formatDate(firestoreTimestamp)` — converts Firestore Timestamp to `"YYYY-MM-DD"` string.
- `groupBy(array, keyFn)` — generic group-by utility, returns `Map<string, array>`.
- `aggregateHours(entries)` — sums `duration_seconds` and returns hours (float). Formula: `entries.reduce((sum, e) => sum + e.duration_seconds, 0) / 3600`.

**`frontend/vite.config.js`** (CREATE)
```js
import { defineConfig } from "vite";
export default defineConfig({
  root: ".",
  build: { outDir: "dist" }
});
```

### 3.4 Data Migration Script (CREATE)

**`scripts/migrate_sqlite_to_firestore.py`** (CREATE)
- Purpose: One-time script to export all data from `data/toggl.db` into Firestore.
- Reads from SQLite using `sqlite3` (same connection pattern as `src/data_store.py`).
- Writes to Firestore using `firebase_admin` SDK (initialized with a service account JSON key file).
- Process:
  1. Read all rows from `time_entries` table.
  2. For each row, transform: parse `tags_json` string to list, convert `billable`/`enriched` from int to bool, parse `start`/`end` to `datetime`, extract `start_month` and `start_day` integers.
  3. Batch write to Firestore (max 500 docs per batch — Firestore batch limit).
  4. Repeat for `projects`, `tags`, `clients`, `tasks`, `sync_meta`.
  5. Print progress: `"Migrated {n}/{total} time_entries"` every 500 docs.
- Accepts CLI args: `--db-path` (default `data/toggl.db`), `--service-account` (path to Firebase service account JSON), `--project-id` (Firebase project ID).
- **IMPORTANT**: Must be idempotent — uses `set(merge=True)` so running it twice doesn't create duplicates.

### 3.5 Files to Leave Unchanged

- **`analysis/` entire directory** — This module is deliberately decoupled from the Streamlit app. It reads `data/toggl.db` directly and produces standalone HTML reports. It has zero imports from `src/`. Do NOT modify any file in `analysis/`. It will continue to work against the local SQLite database for offline analysis.
- **`data/`** — Keep the gitignore, keep the SQLite DB and raw JSON files for the analysis module.
- **`AGENTS.md`** — Update only the "Commands" and "Architecture" sections (see below).
- **`ANALYSIS_PLAN.md`** — Leave unchanged.

### 3.6 Files to Modify

**`AGENTS.md`** (MODIFY)
- Update the "Stack" section: add Firebase (Hosting, Firestore, Cloud Functions, Auth).
- Update the "Commands" section: add `cd frontend && npm run dev` (local frontend dev), `firebase deploy` (deploy all), `firebase deploy --only functions` (deploy functions only), `firebase deploy --only hosting` (deploy frontend only).
- Update the "Architecture" section to describe the new Firebase layout.
- Keep the "Analysis Module" section unchanged.
- Add a "Firebase Setup" section documenting: Firebase project creation, `firebase login`, `firebase init`, environment config for Toggl API token.

**`requirements.txt`** (MODIFY)
- Add `firebase-admin>=6.4.0` (for the migration script).
- Keep all existing dependencies (the analysis module and local tools still need them).

**`.gitignore`** (MODIFY)
- Add: `frontend/node_modules/`, `frontend/dist/`, `.firebase/`, `functions/__pycache__/`, `functions/venv/`, `*.pyc` in functions.

**`.env.example`** (MODIFY)
- Add: `FIREBASE_PROJECT_ID=your-project-id`, `FIREBASE_SERVICE_ACCOUNT_KEY_PATH=path/to/serviceAccountKey.json`.
- Keep existing: `TOGGL_API_TOKEN`, `DASHBOARD_PASSWORD` (still needed for local Streamlit if anyone runs it).

### 3.7 Files to Deprecate (Do NOT Delete Yet)

Mark these as deprecated with a comment at the top of each file but do NOT delete them on this branch. They remain functional for the analysis module and as reference:

- `app.py` — Add comment: `# DEPRECATED: Streamlit entrypoint. See frontend/ for the Firebase SPA.`
- `pages/0_Homepage.py`, `pages/1_Dashboard.py`, `pages/2_Retrospect.py`, `pages/3_Chat.py` — Add same deprecation comment.
- `src/data_store.py`, `src/sync.py`, `src/toggl_client.py`, `src/queries.py`, `src/theme.py` — Add deprecation comment.

---

## 4. Function Signatures

### 4.1 Cloud Functions (`functions/main.py`)

```python
@https_fn.on_call()
def sync_quick(req: https_fn.CallableRequest) -> dict:
    """Run CSV sync for the current year only. Returns {"success": bool, "entries_synced": int, "message": str}."""

@https_fn.on_call()
def sync_full(req: https_fn.CallableRequest) -> dict:
    """Run CSV sync for all years (2017 to current). Returns {"success": bool, "entries_synced": int, "years_synced": list[int], "message": str}."""

@https_fn.on_call()
def sync_enriched_year(req: https_fn.CallableRequest) -> dict:
    """Run JSON enrichment sync for a single year. req.data must contain {"year": int}. Returns {"success": bool, "entries_synced": int, "year": int, "message": str}."""

@https_fn.on_call()
def chat_answer(req: https_fn.CallableRequest) -> dict:
    """Answer a natural-language question about time entries. req.data must contain {"question": str}. Returns {"answer": str}."""

@https_fn.on_call()
def get_sync_status(req: https_fn.CallableRequest) -> dict:
    """Return sync metadata. Returns {"last_csv_sync": str|null, "last_enriched_sync": str|null, "enrichment_earliest_year": str|null}."""

@https_fn.on_call()
def get_stats(req: https_fn.CallableRequest) -> dict:
    """Return high-level stats. Returns {"total_entries": int, "earliest_date": str|null, "latest_date": str|null, "enriched_count": int, "enriched_pct": float}."""
```

### 4.2 Firestore Helpers (`functions/data_store.py`)

```python
def get_entries(
    db: firestore.Client,
    start_date: str | None = None,  # ISO 8601 "YYYY-MM-DD"
    end_date: str | None = None,    # ISO 8601 "YYYY-MM-DD"
    project: str | None = None,     # exact project name
    tag: str | None = None          # exact tag name (uses array-contains)
) -> list[dict]:
    """Fetch time_entries matching filters. Returns list of document dicts sorted by start ascending."""

def get_entries_for_date_across_years(
    db: firestore.Client,
    month: int,  # 1-12
    day: int     # 1-31
) -> list[dict]:
    """Fetch entries that occurred on this month/day in any year. Uses start_month + start_day fields."""

def search_entries(
    db: firestore.Client,
    keyword: str  # case-insensitive substring to match in description
) -> list[dict]:
    """Full-text search on descriptions. Fetches all, filters in-memory (Firestore has no LIKE). Returns matches sorted by start desc."""

def get_total_stats(db: firestore.Client) -> dict:
    """Returns {"total_entries": int, "earliest_date": str|None, "latest_date": str|None}."""

def get_enrichment_stats(db: firestore.Client) -> dict:
    """Returns {"total": int, "enriched": int, "percentage": float}."""

def get_projects(db: firestore.Client) -> list[dict]:
    """Fetch all documents from 'projects' collection."""

def get_tags(db: firestore.Client) -> list[dict]:
    """Fetch all documents from 'tags' collection."""

def get_clients(db: firestore.Client) -> list[dict]:
    """Fetch all documents from 'clients' collection."""

def get_tasks(db: firestore.Client) -> list[dict]:
    """Fetch all documents from 'tasks' collection."""

def upsert_time_entries_firestore(
    db: firestore.Client,
    entries: list[dict]  # raw entries from toggl_client
) -> int:
    """Write entries to Firestore with merge. Returns count of documents written."""

def get_sync_meta(db: firestore.Client, key: str) -> str | None:
    """Read a value from sync_meta collection. Returns None if not found."""

def set_sync_meta(db: firestore.Client, key: str, value: str) -> None:
    """Write a key-value pair to sync_meta collection."""
```

### 4.3 Frontend Utilities (`frontend/src/utils.js`)

```javascript
/**
 * @param {Date} date
 * @returns {number} ISO 8601 week number (1-53), Thursday-based
 */
export function getISOWeek(date) {}

/**
 * @param {number} seconds - duration in seconds (integer)
 * @returns {string} formatted as "Xh Ym", e.g., "2h 35m". Returns "< 1m" if under 60.
 */
export function formatDuration(seconds) {}

/**
 * @param {firebase.firestore.Timestamp} ts
 * @returns {string} "YYYY-MM-DD"
 */
export function formatDate(ts) {}

/**
 * @param {Array<Object>} array
 * @param {Function} keyFn - (item) => string
 * @returns {Map<string, Array<Object>>}
 */
export function groupBy(array, keyFn) {}

/**
 * @param {Array<Object>} entries - each must have `duration_seconds` (number)
 * @returns {number} total hours as float, e.g., 7.583333
 */
export function aggregateHours(entries) {}
```

### 4.4 Migration Script (`scripts/migrate_sqlite_to_firestore.py`)

```python
def migrate_collection(
    db: firestore.Client,
    conn: sqlite3.Connection,
    table_name: str,          # SQLite table name, e.g., "time_entries"
    collection_name: str,     # Firestore collection name (same as table name)
    id_field: str,            # column to use as document ID, e.g., "id" or "toggl_id"
    transform_fn: Callable[[dict], dict] | None = None  # optional row transformer
) -> int:
    """Migrate all rows from a SQLite table to a Firestore collection. Returns count migrated."""

def transform_time_entry(row: dict) -> dict:
    """Transform a time_entries row: parse tags_json to list, bools from int, add start_month/start_day."""

def main() -> None:
    """CLI entry point. Parses --db-path, --service-account, --project-id args. Migrates all 6 tables."""
```

---

## 5. Test Specifications

> **Note**: The project has no test framework configured. These are manual verification procedures the implementer should follow after each step.

### 5.1 Migration Script Tests

**Test M1: Empty database migration**
- Input: Create an empty `toggl.db` with schema only (run `init_db()` from `src/data_store.py` on a fresh file).
- Expected: Script completes without error. All 6 Firestore collections exist but contain 0 documents. Console output: `"Migrated 0/0 time_entries"`, etc.

**Test M2: Single entry migration**
- Input: SQLite `time_entries` with 1 row: `id="abc123"`, `toggl_id=NULL`, `project="TestProject"`, `description="Test entry"`, `start="2024-06-15T10:00:00+02:00"`, `end="2024-06-15T11:30:00+02:00"`, `duration_seconds=5400`, `tags_json='["Focus","Deep Work"]'`, `billable=0`, `enriched=0`.
- Expected Firestore document at `time_entries/abc123`:
  - `toggl_id`: null
  - `project`: "TestProject"
  - `description`: "Test entry"
  - `start`: Timestamp(2024-06-15T08:00:00Z) — note: stored as UTC
  - `end`: Timestamp(2024-06-15T09:30:00Z)
  - `duration_seconds`: 5400 (NOT 5400000 — seconds, not milliseconds)
  - `tags_json`: ["Focus", "Deep Work"] (native array, NOT a JSON string)
  - `billable`: false (NOT 0)
  - `enriched`: false (NOT 0)
  - `start_month`: 6
  - `start_day`: 15

**Test M3: Idempotency**
- Run the migration script twice on the same data.
- Expected: Second run completes without error. Document count is identical. No duplicates.

**Test M4: Tags JSON edge cases**
- Input rows with `tags_json` values: `NULL`, `"[]"`, `'["Single"]'`, `'["A","B","C"]'`.
- Expected Firestore `tags_json` values: `[]`, `[]`, `["Single"]`, `["A", "B", "C"]`.

**Test M5: Large batch (500+ entries)**
- Input: 1200 time_entries.
- Expected: Script processes 3 batches (500 + 500 + 200). All 1200 documents exist in Firestore.

### 5.2 Cloud Function Tests

**Test F1: sync_quick — unauthenticated call**
- Call `sync_quick` without a Firebase Auth token.
- Expected: HTTP 401 or `UNAUTHENTICATED` error. No Firestore writes.

**Test F2: sync_quick — authenticated, happy path**
- Call with valid auth. Toggl API token is configured.
- Expected: Returns `{"success": true, "entries_synced": <some positive int>, "message": "..."}`. Entries appear in Firestore `time_entries` collection. `sync_meta/last_csv_sync` document exists.

**Test F3: chat_answer — "What are my top projects this year?"**
- Input: `{"question": "What are my top projects this year?"}`
- Expected: Returns `{"answer": "<markdown string>"}` containing project names and hours. The answer must not be empty or an error.

**Test F4: chat_answer — unrecognized question**
- Input: `{"question": "What is the meaning of life?"}`
- Expected: Returns the help message (same as `_help_message()` in current `src/queries.py`).

**Test F5: get_sync_status — no syncs performed**
- Expected: Returns `{"last_csv_sync": null, "last_enriched_sync": null, "enrichment_earliest_year": null}`.

### 5.3 Frontend Tests

**Test U1: Login flow**
- Open the app URL. Expected: login form visible, no data visible.
- Enter wrong password. Expected: error message displayed.
- Enter correct credentials. Expected: login form disappears, sidebar + homepage render.

**Test U2: Navigation**
- Click each nav link. Expected: URL hash changes, correct page content renders, no full page reload.

**Test U3: Homepage — Highlight cards**
- Ensure Firestore has entries this ISO week with `tags_json` containing `"Highlight"`.
- Expected: Cards display with project name, description, formatted duration (e.g., "1h 30m"), date.

**Test U4: Dashboard — year filter**
- Select "2024" from year dropdown.
- Expected: All charts update to show only 2024 data. Summary metrics match manual Firestore query for 2024.

**Test U5: Dashboard — heatmap renders**
- Expected: A grid with 7 rows (Mon–Sun) × 53 columns (weeks). Cells colored by hour intensity. Mouse hover shows date + hours.

**Test U6: Chat — round trip**
- Type "How much did I track this week?" and press Enter.
- Expected: User message appears. After 1–3 seconds, assistant response appears with hours/project breakdown.

**Test U7: Sync button — progress feedback**
- Click "Quick Sync". Expected: Button shows loading state (spinner or "Syncing..."). On completion, shows success message with count.

### 5.4 Data Integrity Cross-Check

**Test D1: Total hours match**
- Query SQLite: `SELECT SUM(duration_seconds) / 3600.0 FROM time_entries;`
- Query Firestore: sum all `duration_seconds` fields in `time_entries` collection, divide by 3600.
- Expected: Values match within 0.01 hours (rounding tolerance from float precision).

**Test D2: Entry count match**
- `SELECT COUNT(*) FROM time_entries;` vs Firestore document count.
- Expected: Exact match.

---

## 6. Implementation Order

Each step should be verified before moving to the next.

1. **Create the `firebase-migration` branch.**
   - Verify: `git branch` shows the new branch, `git log` matches the parent.

2. **Set up the Firebase project.**
   - Create project in Firebase Console. Enable Firestore (start in test mode temporarily). Enable Authentication (Email/Password provider). Enable Cloud Functions (requires Blaze plan). Enable Hosting.
   - Create `firebase.json`, `.firebaserc`, `firestore.rules`, `firestore.indexes.json`.
   - Run `firebase init` to validate config.
   - Verify: `firebase projects:list` shows the project. `firebase deploy --only firestore:rules` succeeds.

3. **Write the data migration script (`scripts/migrate_sqlite_to_firestore.py`).**
   - Verify: Run tests M1–M5. Check Firestore Console to see documents.

4. **Run the migration script against the real `data/toggl.db`.**
   - Verify: Run test D1 and D2. All collections populated. Spot-check 5 random entries against SQLite.

5. **Create `functions/toggl_client.py`** (adapted copy).
   - Verify: `python -c "from toggl_client import TogglClient; print('OK')"` runs without import errors in the `functions/` directory.

6. **Create `functions/data_store.py`** (Firestore query helpers).
   - Verify: Write a small test script that calls `get_entries(db, "2024-01-01", "2024-01-31")` and prints results. Confirm non-empty results if data exists for that range.

7. **Create `functions/sync_engine.py`** (adapted from `src/sync.py`).
   - Verify: Import check passes. Unit test: mock the Toggl API response and verify Firestore writes.

8. **Create `functions/chat_engine.py`** (adapted from `src/queries.py`).
   - Verify: Import check. Call `answer_question("top projects this year")` against Firestore data.

9. **Create `functions/main.py`** (Cloud Function entry points).
   - Verify: `firebase deploy --only functions` succeeds. Test F1–F5 via `firebase functions:shell` or `curl`.

10. **Set up the frontend scaffold (`frontend/`).**
    - Create `package.json`, `vite.config.js`, `index.html`.
    - Run `npm install` and `npm run dev`.
    - Verify: Browser opens to `localhost:5173`, shows blank page without errors in console.

11. **Implement `frontend/src/theme.js` and `frontend/src/styles.css`.**
    - Verify: Add a test `<h1>` to `index.html`, confirm cyberpunk styling applies (dark bg, neon cyan text, Share Tech Mono font).

12. **Implement `frontend/src/auth.js` + login flow in `main.js`.**
    - Verify: Test U1 passes.

13. **Implement `frontend/src/utils.js`.**
    - Verify: Open browser console, test each function manually:
      - `getISOWeek(new Date("2024-12-30"))` → `1` (it's ISO week 1 of 2025).
      - `formatDuration(5400)` → `"1h 30m"`.
      - `formatDuration(45)` → `"< 1m"`.
      - `formatDuration(3600)` → `"1h 0m"`.
      - `aggregateHours([{duration_seconds: 3600}, {duration_seconds: 1800}])` → `1.5`.

14. **Implement `frontend/src/pages/homepage.js`.**
    - Verify: Test U3 passes.

15. **Implement `frontend/src/pages/dashboard.js`.**
    - Verify: Tests U4, U5 pass. Charts render with cyberpunk theme.

16. **Implement `frontend/src/pages/retrospect.js`.**
    - Verify: "On This Day" tab shows data for a known date. "Year vs Year" shows comparison.

17. **Implement `frontend/src/pages/chat.js`.**
    - Verify: Test U6 passes.

18. **Wire up sync buttons in sidebar.**
    - Verify: Test U7 passes.

19. **Deploy to Firebase Hosting.**
    - Run `cd frontend && npm run build && cd .. && firebase deploy`.
    - Verify: The live URL loads, login works, data displays.

20. **Update `AGENTS.md`, `.gitignore`, `.env.example`, `requirements.txt`.**
    - Verify: All changes listed in Section 3.6 are applied.

21. **Add deprecation comments to old Streamlit files.**
    - Verify: Each file in `app.py`, `pages/*.py`, `src/*.py` has the comment on line 1.

22. **Lock down Firestore rules** (replace test-mode rules with authenticated-only rules from `firestore.rules`).
    - Verify: `firebase deploy --only firestore:rules`. Unauthenticated reads fail.

---

## 7. Gotchas

### 7.1 Duration Units
The SQLite `duration_seconds` column stores integer **seconds**. The Toggl API sometimes returns duration in **seconds** (v9) but the CSV export also uses seconds. Never divide by 1000 (that's for milliseconds). Always divide by 3600 to get hours. Double-check that no intermediate conversion introduces millisecond confusion.

### 7.2 Timezone Handling
Toggl stores `start` and `end` as ISO 8601 strings with timezone offset (e.g., `"2024-06-15T10:00:00+02:00"`). Firestore Timestamps are stored in UTC internally. When writing to Firestore, parse the ISO string into a timezone-aware `datetime` object — the Firestore SDK will convert to UTC. When reading back, Firestore returns UTC. The frontend must convert UTC timestamps to the user's local timezone for display. Use `toLocaleString()` or explicitly apply the user's offset.

The `start_month` and `start_day` fields added for the "On This Day" query must be extracted from the **local time** in the original ISO string (not UTC). If the entry is `"2024-06-15T01:00:00+05:30"`, that's June 15 in IST but June 14 in UTC. Use the local date. Parse the ISO string directly to extract month=6, day=15 before converting to UTC.

### 7.3 Firestore Batch Write Limit
Firestore batches support a maximum of **500 operations** per batch. The migration script must chunk accordingly. If you try to commit a batch with 501 operations, it throws an error.

### 7.4 Firestore Query Limitations
- **No `LIKE` / substring search**: Firestore cannot do `WHERE description LIKE '%keyword%'`. The `search_entries()` function must fetch all documents and filter in Python. For 10 years of data (~50,000+ entries), this is slow. Consider adding a `description_lower` field and doing prefix queries for partial mitigation, but accept that full substring search requires fetching all docs.
- **No `OR` queries across different fields**: Each `where()` clause is an AND. To query "entries with tag X OR project Y", you need two separate queries and merge results client-side.
- **No inequality on multiple fields**: You cannot do `.where("start", ">=", date1).where("duration_seconds", ">", 3600)` on different fields. If you need this, restructure queries.
- **`array-contains` is limited to one per query**: You cannot filter by two tags simultaneously with `array-contains`. Use `array-contains-any` for OR logic (up to 30 values).

### 7.5 Cloud Function Timeout
Default timeout for Cloud Functions (2nd gen) is **60 seconds**. The full CSV sync for 10 years makes ~10 API calls (one per year), each waiting for rate limiting. This may exceed 60s. Increase the timeout to **300 seconds** in the function decorator:
```python
@https_fn.on_call(timeout_sec=300)
```
For enriched sync (which processes ~50,000 entries in batches of 50), a single year might take several minutes. The per-year chunking (one function call per year) mitigates this, but set timeout to **540 seconds** (maximum) for `sync_enriched_year`.

### 7.6 Cloud Function Memory
The enrichment sync loads all entries for a year into memory as a Pandas DataFrame. Default Cloud Function memory is 256MB. Increase to **512MB** or **1GB**:
```python
@https_fn.on_call(memory=options.MemoryOption.GB_1, timeout_sec=540)
```

### 7.7 Firebase Auth Token in Cloud Functions
When using `@https_fn.on_call()`, the Firebase SDK automatically verifies the auth token from the client. The authenticated user's UID is available at `req.auth.uid`. If `req.auth` is `None`, the user is not authenticated. Always check this at the top of every function.

### 7.8 Firestore Document ID Constraints
Document IDs must be strings, cannot be empty, cannot contain `/`, and cannot be `.` or `..`. Max 1500 bytes. The SHA-256 hex strings used as synthetic IDs in `time_entries.id` are 64 characters — this is fine. Toggl integer IDs converted to strings (e.g., `"123456789"`) are also fine.

### 7.9 Tags JSON Field Name
The SQLite column is called `tags_json` and stores a JSON-encoded string like `'["Tag1","Tag2"]'`. In Firestore, store this as a native array and keep the field name `tags_json` for consistency with the existing codebase (even though it's no longer JSON). Do NOT rename it to `tags` — the chat engine and query helpers reference `tags_json` by name, and renaming would introduce bugs in the adapted code.

### 7.10 The Analysis Module Must NOT Be Touched
The `analysis/` directory is a standalone CLI tool. It imports nothing from `src/`. It reads `data/toggl.db` directly using its own `analysis/data_access.py`. After migration to Firebase, the analysis module continues to work against the local SQLite file. If the implementer wants analysis to work against Firestore data, that's a separate future task — a Firestore-to-SQLite export script. Do NOT modify any file under `analysis/`.

### 7.11 CSS Scan-Line Overlay
The current theme includes a CSS pseudo-element scan-line overlay (`::before` on the body with a repeating gradient). This is purely decorative. When translating to `styles.css`, ensure the overlay has `pointer-events: none` so it doesn't block clicks on the page.

### 7.12 Plotly.js Bundle Size
`plotly.js-dist-min` is ~1MB minified. This is the full bundle. If bundle size is a concern, use `plotly.js-basic-dist-min` (~400KB) which includes bar, scatter, pie, and heatmap trace types — all that this app needs. Do NOT use `plotly.js-cartesian-dist-min` because it lacks the `pie` trace type used in the Dashboard.

### 7.13 Firebase Hosting SPA Rewrite
The `firebase.json` must include a rewrite rule `{"source": "**", "destination": "/index.html"}` so that all routes (e.g., `yourdomain.web.app/#/dashboard`) resolve to the SPA. Without this, direct navigation to a URL returns a 404.

### 7.14 `X | Y` Union Syntax in Cloud Functions
The codebase uses Python 3.10+ union syntax (`str | None` instead of `Optional[str]`). The Firebase Cloud Functions Python 3.12 runtime supports this. If for any reason the runtime is set to Python 3.9 or 3.10-early, these type hints will cause `TypeError` at import time. Always use Python 3.12 runtime.

### 7.15 Naming Convention: snake_case Everywhere in Python
The existing codebase uses `snake_case` for all Python function and variable names. The Firebase Functions SDK also uses `snake_case` for Python. Maintain this. Do NOT switch to `camelCase` in the Python Cloud Functions even though the JavaScript frontend uses `camelCase`. The boundary is the JSON API: Cloud Functions return `snake_case` JSON keys, and the frontend handles them as-is.

### 7.16 Firestore Read Costs
Firestore charges per document read. The Dashboard page currently loads ALL entries for a year (potentially 5,000–15,000 entries) to compute aggregations. This could get expensive at scale. For v1, accept this cost. For v2, consider pre-computing aggregations (monthly summaries, project totals) in Firestore during sync and reading those instead.

### 7.17 CORS for Cloud Functions
If the frontend is served from `yourproject.web.app` and Cloud Functions are at `us-central1-yourproject.cloudfunctions.net`, CORS headers are needed. Using `@https_fn.on_call()` handles CORS automatically when called via the Firebase JS SDK's `httpsCallable()`. Do NOT use `@https_fn.on_request()` unless you manually configure CORS headers.

### 7.18 Service Account Key Security
The `scripts/migrate_sqlite_to_firestore.py` requires a Firebase service account JSON key file. This file contains private keys. NEVER commit it to git. Add `*serviceAccountKey*` and `*.json.key` to `.gitignore`. The `.env.example` should document the path but the actual key file must be excluded.
