# Active Context

## Date
- 2026-03-17

## Current Branch
- `firebase-migration` (Note: Strategy now split-hosting: Vercel frontend + Render backend)

## Objective In Progress
- Complete migration to Supabase + split hosting: Vercel (frontend SPA) and Render (FastAPI backend) due to Vercel->Postgres connectivity limits.

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

### 5. Session Update (2026-03-17, late)
- Implemented password-only login UX: removed email input from login form and wired fixed login email via `VITE_LOGIN_EMAIL`.
- Updated frontend auth validation and boot-time config checks (`frontend/src/auth.js`, `frontend/src/main.js`, `frontend/.env.example`, `.env.example`).
- Replaced incorrect frontend key usage in production: `VITE_SUPABASE_ANON_KEY` now uses publishable key format (`sb_publishable_*`).
- Added backend stability fixes in `api/main.py` (trim env values, explicit auth user extraction, DB fallback attempt) and missing helper `get_entries_by_tag` in `api/data_store.py`.
- Added split-host migration artifacts for Render: `render.yaml`, `api/render_entrypoint.py`, `plans/backend-host-migration-render.md`, and `uvicorn` dependency in `api/requirements.txt`.

## Validation Completed
- **Data Integrity:** 100% of SQLite data migrated to Supabase Postgres.
- **Backend Health:** Deployed FastAPI backend is live and reachable at `/api/health`.
- **Backend Security:** API endpoints are guarded; return `401 Unauthorized` without a valid token.
- **Frontend Build:** Local and remote Vite builds succeed.
- **Routing Fix Verification:** Production root `/` now serves SPA HTML (200), and non-API route `/dashboard` resolves via SPA fallback (200).
- **Live Deploy Verification:** Multiple production redeploys succeeded and are aliased to `https://toggl-api.vercel.app`.
- **Playwright QA:** Console/network checks and failed-login tests executed on desktop + mobile.
- **Auth Config Fix Verification (2026-03-17):** Vercel Production `VITE_SUPABASE_ANON_KEY` replaced with `sb_publishable_*`; deployment `https://toggl-jp494snlb-tah-allotropes-projects.vercel.app` promoted and aliased to `https://toggl-api.vercel.app`.
- **Post-fix Smoke Check (2026-03-17):** `/api/health` returns 200 and cache-busted frontend load renders Login screen with no console errors.
- **Password-only Login Verification (2026-03-17):** Playwright confirms signed-out view shows only Password + Login, and sign-in succeeds.
- **Backend 500 Root-Cause Verification (2026-03-17):** Vercel production logs show authenticated API calls fail at Postgres connect with `Cannot assign requested address` to `db.itxfaxlnlbzbddyvqvwd.supabase.co:5432` (IPv6 path issue in current runtime).

## Project Resources
- Supabase Project ID: `itxfaxlnlbzbddyvqvwd`
- Vercel URL: `https://toggl-api.vercel.app`

## Blockers / Outstanding
- **Security Follow-up:** Rotate exposed/incorrect Supabase secret key (`sb_secret_*`) because it was previously used in frontend runtime configuration.
- **Backend Connectivity Blocker (Vercel -> Postgres):** Vercel serverless runtime cannot reliably reach Supabase direct Postgres host for this project, causing authenticated backend routes (`/api/status`, `/api/sync`, `/api/chat`) to return 500.
- **Supabase Free Plan Constraint:** IPv4 add-on is unavailable on Free Plan, so direct Vercel->Postgres path remains blocked.
- **Functional Validation Pending:** Execute authenticated end-to-end checks for Login, Sync buttons, Chat, and Dashboard charts after backend host migration.
- **Vercel Framework Preset (Optional):** Project may remain on `python`; app is currently resilient due to FastAPI SPA fallback, but setting framework to `Other` can reduce routing surprises.

## Next Actions
1. Move FastAPI backend to Render using `render.yaml` and set backend env vars there (`DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `TOGGL_API_TOKEN`, `ALLOWED_ORIGINS`).
2. Set Vercel `VITE_API_BASE_URL` to the Render backend URL (`https://<render-service>.onrender.com/api`) and redeploy frontend.
3. Re-run authenticated validation for Login, Sync (quick/full/enriched), Chat, and Dashboard rendering.
4. Rotate the previously exposed/incorrect secret key and update backend `SUPABASE_KEY` in Render.
5. (Optional) Keep using cache-busted URLs (`?v=<timestamp>`) for immediate post-deploy smoke checks to avoid stale asset hash caching.

## Immediate Handoff Tasks (Next Session)
1. Create Render Web Service from repo and deploy backend using `render.yaml`.
2. Confirm `GET https://<render-host>/api/health` returns 200.
3. Set Vercel Production `VITE_API_BASE_URL=https://<render-host>/api` and redeploy frontend.
4. Execute full smoke test: login (password-only), dashboard load, quick sync, full/enriched sync, and chat response.
5. Capture Render logs for any failed endpoint and patch backend if needed.
