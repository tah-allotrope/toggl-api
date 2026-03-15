# Active Context

## Date
- 2026-03-15

## Current Branch
- `firebase-migration` (Note: Strategy pivoted to Supabase/Vercel)

## Objective In Progress
- Migrate app from Streamlit architecture to a free Supabase (Postgres/Auth) + Vercel (FastAPI/Hosting) architecture.

## Completed Work
### 1. Pivot to Supabase & Vercel
- Abandoned Firebase due to credit card requirements for Cloud Functions and free-tier write quotas (20k/day).
- Provisioned Supabase project (`itxfaxlnlbzbddyvqvwd`).
- Created `scripts/migrate_sqlite_to_supabase.py` and successfully migrated all **56,727 time entries** to Postgres.
- Created primary user account in Supabase Auth.

### 2. Backend Migration (FastAPI on Vercel)
- Implemented `api/index.py` as a consolidated FastAPI entry point.
- Adapted `api/data_store.py`, `api/sync_engine.py`, and `api/chat_engine.py` to use PostgreSQL (psycopg2) instead of Firestore.
- Configured Vercel environment variables (`SUPABASE_URL`, `SUPABASE_KEY`, `DATABASE_URL`).
- Pruned `requirements.txt` to exclude heavy local analysis libraries (`scipy`, `scikit-learn`) to stay under the 500MB Lambda limit.

### 3. Frontend Migration (Vite on Vercel)
- Swapped Firebase SDK for `@supabase/supabase-js`.
- Updated `frontend/src/auth.js` and `frontend/src/main.js` for Supabase Authentication.
- Rewrote `homepage.js`, `dashboard.js`, and `retrospect.js` to query Supabase Postgres via the JS client.
- Integrated frontend build (`npm run build`) into the Vercel deployment pipeline.

### 4. Repository Cleanup & Reorganization
- Deleted all Firebase config files (`firebase.json`, `.firebaserc`, rules, indexes).
- Moved legacy Streamlit code (`app.py`, `pages/`, `src/`) to `legacy/`.
- Removed root-level `node_modules`, `package.json`, and temporary test scripts.
- Updated `.gitignore` to silence build artifacts and Vercel caches.

## Validation Completed
- **Data Integrity:** 100% of SQLite data migrated to Supabase Postgres.
- **Backend Health:** Deployed FastAPI backend is live and reachable at `/api/health`.
- **Backend Security:** API endpoints are guarded; return `401 Unauthorized` without a valid token.
- **Frontend Build:** Local and remote Vite builds succeed.

## Project Resources
- Supabase Project ID: `itxfaxlnlbzbddyvqvwd`
- Vercel URL: `https://toggl-api.vercel.app`

## Blockers / Outstanding
- **Vercel Routing Conflict:** The FastAPI backend is currently intercepting the root `/` path, resulting in a JSON "Not Found" error instead of serving the static `index.html`. 
- **SPA Rewrites:** Need to ensure Vercel correctly serves `index.html` for all non-API paths while keeping `/api/*` routed to the Python backend.

## Next Actions
1. Fix Vercel routing to allow the static frontend to load at the root URL.
2. Verify frontend-to-backend communication (Sync buttons, Chat).
3. Confirm Dashboard charts render correctly with Supabase data.
4. (Optional) Final cleanup of `api/` directory (remove any unused `.pyc` or redundant files).
