# Active Context

## Date
- 2026-03-13

## Current Branch
- `firebase-migration`

## Objective In Progress
- Migrate app from Streamlit architecture to Firebase architecture on a dedicated branch.

## Completed Work
- Created implementation plan file: `plans/ISSUE-1-streamlit-to-firebase.md`.
- Created Firebase config/rules/index files:
  - `firebase.json`
  - `.firebaserc` (now set to `toggl-journal`)
  - `firestore.rules`
  - `firestore.indexes.json`
- Implemented Cloud Functions backend scaffold under `functions/`:
  - `functions/main.py` (with lazy imports for emulator compatibility)
  - `functions/toggl_client.py`
  - `functions/data_store.py`
  - `functions/sync_engine.py`
  - `functions/chat_engine.py`
  - `functions/requirements.txt`
  - `functions/venv/` (created for emulator)
- Implemented frontend SPA scaffold under `frontend/`:
  - `frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html`
  - `frontend/src/main.js`, `frontend/src/auth.js`
  - `frontend/src/pages/homepage.js`
  - `frontend/src/pages/dashboard.js`
  - `frontend/src/pages/retrospect.js`
  - `frontend/src/pages/chat.js`
  - `frontend/src/theme.js`, `frontend/src/styles.css`, `frontend/src/utils.js`
  - `frontend/.env.example`, `frontend/.env` (with real Firebase SDK config)
- Added one-time migration script:
  - `scripts/migrate_sqlite_to_firestore.py`
- Updated project metadata/config docs:
  - `AGENTS.md` (Firebase stack/commands/architecture setup)
  - `requirements.txt` (added `firebase-admin`)
  - `.env.example` (Firebase variables)
  - `.gitignore` (frontend/functions/firebase/key ignores, added `frontend/.env`)
- Added deprecation headers to legacy Streamlit files:
  - `app.py`
  - `pages/0_Homepage.py`, `pages/1_Dashboard.py`, `pages/2_Retrospect.py`, `pages/3_Chat.py`
  - `src/data_store.py`, `src/sync.py`, `src/toggl_client.py`, `src/queries.py`, `src/theme.py`

## Validation Completed
- Python syntax compile check passed for new backend/migration files.
- Frontend dependency install completed.
- Frontend production build completed (`vite build` successful).
- Java installed globally (`openjdk 21.0.10`).
- Firebase emulator smoke tests passed:
  - Firestore only: passed
  - Functions + Firestore: passed; all 6 callables loaded
- Firestore rules and indexes deployed to `toggl-journal`.
- Hosting deployed: `https://toggl-journal.web.app`

## Project Resources Created
- Firebase Project ID: `toggl-journal`
- Firebase Web App: `toggl-journal-web` (App ID: `1:998696710377:web:6a87f559f71dbe8c854078`)
- Hosting URL: `https://toggl-journal.web.app`

## Blockers / Outstanding
- Firebase Authentication not yet configured (Email/Password provider needs enabling).
- No user created yet for app login.
- Firestore contains no data yet (migration script not run).
- Vercel project not yet linked/secrets set.
- GitHub repository secrets not yet set.

## Next Actions
1. Enable Firebase Authentication (Email/Password) in Console.
2. Create first user account for app login.
3. (Optional) Run migration script to seed Firestore: `python scripts/migrate_sqlite_to_firestore.py --service-account <path> --project-id toggl-journal`
4. Create a Firebase service account JSON with Firestore write access and add as secret in:
   - GitHub repo secrets: `FIREBASE_SERVICE_ACCOUNT_JSON`
   - Vercel env vars: `FIREBASE_SERVICE_ACCOUNT_JSON`
5. Add GitHub repo secret `TOGGL_API_TOKEN` (your Toggl API token).
6. Add Vercel env vars:
   - `TOGGL_API_TOKEN` (same as above)
   - `ALLOWED_ORIGINS` (e.g., `https://toggl-journal.web.app`)
   - `GITHUB_OWNER` (your GitHub username or org)
   - `GITHUB_REPO` (repo name, e.g., `toggl-api`)
   - `GITHUB_TOKEN` (personal access token with `workflow` scope)
   - Optional: `GITHUB_REF` (default `main`), `GITHUB_QUICK_WORKFLOW` (default `sync_quick.yml`), `GITHUB_SYNC_WORKFLOW` (default `sync_dispatch.yml`)
7. Set frontend env var `VITE_API_BASE_URL` to your Vercel API base (e.g., `https://<your-project>.vercel.app/api`).
8. Deploy frontend: `firebase deploy --only hosting`
9. Deploy Vercel project (via Vercel dashboard or `vercel --prod`).
10. Test login and sync flow.
11. (Optional) Remove `functions/` from `firebase.json` after verifying Vercel endpoints work.

(End of file - total 96 lines)
