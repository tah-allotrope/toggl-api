# Active Context

## Date
- 2026-03-16

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
- Implemented `api/main.py` as a consolidated FastAPI entry point.
- Adapted `api/data_store.py`, `api/sync_engine.py`, and `api/chat_engine.py` to use PostgreSQL (psycopg2) instead of Firestore.
- Configured Vercel environment variables (`SUPABASE_URL`, `SUPABASE_KEY`, `DATABASE_URL`).
- Pruned `requirements.txt` to exclude heavy local analysis libraries (`scipy`, `scikit-learn`) to stay under the 500MB Lambda limit.
- Fixed `sync_type=full` runtime bug in `api/main.py` by calling `sync_engine.sync_full(...)` correctly.
- Added FastAPI static-serving fallback (`/`, `/assets/*`, and SPA fallback route) so the frontend still loads when Vercel root traffic is handled by Python.

### 3. Frontend Migration (Vite on Vercel)
- Swapped Firebase SDK for `@supabase/supabase-js`.
- Updated `frontend/src/auth.js` and `frontend/src/main.js` for Supabase Authentication.
- Rewrote `homepage.js`, `dashboard.js`, and `retrospect.js` to query Supabase Postgres via the JS client.
- Integrated frontend build (`npm run build`) into the Vercel deployment pipeline.
- Fixed chat auth wiring in `frontend/src/pages/chat.js` to use the active Supabase session bearer token.
- Set `frontend/src/api.js` default API base URL to `/api` for same-origin production calls.
- Upgraded login UX/accessibility in `frontend/src/auth.js` to use a semantic `<form>` and mapped user-friendly auth errors.
- Added frontend boot-time configuration guards in `frontend/src/main.js` to block secret key usage (`sb_secret_*`) in the browser and show actionable error text.

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
- **Routing Fix Verification:** Production root `/` now serves SPA HTML (200), and non-API route `/dashboard` resolves via SPA fallback (200).
- **Live Deploy Verification:** Multiple production redeploys succeeded and are aliased to `https://toggl-api.vercel.app`.
- **Playwright QA:** Console/network checks and failed-login tests executed on desktop + mobile.

## Project Resources
- Supabase Project ID: `itxfaxlnlbzbddyvqvwd`
- Vercel URL: `https://toggl-api.vercel.app`

## Blockers / Outstanding
- **Critical Auth Config Blocker:** `VITE_SUPABASE_ANON_KEY` in Vercel Production is set to a secret-style key (`sb_secret_*`) instead of Supabase anon/publishable key, causing login failure and a configuration error screen.
- **Security Follow-up:** Rotate exposed/incorrect Supabase secret key if it was ever used in frontend runtime configuration.
- **Functional Validation Pending:** After key correction, re-run end-to-end checks for Login, Sync buttons, Chat, and Dashboard charts.
- **Vercel Framework Preset (Optional):** Project may remain on `python`; app is currently resilient due to FastAPI SPA fallback, but setting framework to `Other` can reduce routing surprises.

## Next Actions
1. In Vercel Production, replace `VITE_SUPABASE_ANON_KEY` with the Supabase anon/publishable key (not `sb_secret_*`).
2. Redeploy and confirm login works without the configuration error screen.
3. Re-run Playwright validation for Login, Sync (quick/full/enriched), Chat, and Dashboard rendering.
4. Rotate the previously exposed/incorrect secret key and verify server-side env vars (`SUPABASE_KEY`) still work for backend auth verification.
5. (Optional) Set Vercel Framework Preset to `Other` for cleaner static+API routing behavior.
6. (Optional) Final cleanup of `api/` directory (remove any unused `.pyc` or redundant files).
