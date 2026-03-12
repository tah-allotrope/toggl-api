# Active Context

## Date
- 2026-03-12

## Current Branch
- `firebase-migration`

## Objective In Progress
- Migrate app from Streamlit architecture to Firebase architecture on a dedicated branch.

## Completed Work
- Created implementation plan file: `plans/ISSUE-1-streamlit-to-firebase.md`.
- Created Firebase config/rules/index files:
  - `firebase.json`
  - `.firebaserc` (placeholder project ID)
  - `firestore.rules`
  - `firestore.indexes.json`
- Implemented Cloud Functions backend scaffold under `functions/`:
  - `functions/main.py`
  - `functions/toggl_client.py`
  - `functions/data_store.py`
  - `functions/sync_engine.py`
  - `functions/chat_engine.py`
  - `functions/requirements.txt`
- Implemented frontend SPA scaffold under `frontend/`:
  - `frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html`
  - `frontend/src/main.js`, `frontend/src/auth.js`
  - `frontend/src/pages/homepage.js`
  - `frontend/src/pages/dashboard.js`
  - `frontend/src/pages/retrospect.js`
  - `frontend/src/pages/chat.js`
  - `frontend/src/theme.js`, `frontend/src/styles.css`, `frontend/src/utils.js`
  - `frontend/.env.example`
- Added one-time migration script:
  - `scripts/migrate_sqlite_to_firestore.py`
- Updated project metadata/config docs:
  - `AGENTS.md` (Firebase stack/commands/architecture setup)
  - `requirements.txt` (added `firebase-admin`)
  - `.env.example` (Firebase variables)
  - `.gitignore` (frontend/functions/firebase/key ignores)
- Added deprecation headers to legacy Streamlit files:
  - `app.py`
  - `pages/0_Homepage.py`, `pages/1_Dashboard.py`, `pages/2_Retrospect.py`, `pages/3_Chat.py`
  - `src/data_store.py`, `src/sync.py`, `src/toggl_client.py`, `src/queries.py`, `src/theme.py`

## Validation Completed
- Python syntax compile check passed for new backend/migration files.
- Frontend dependency install completed.
- Frontend production build completed (`vite build` successful).

## Blockers / Outstanding
- Java not installed globally (`java -version` currently not found).
- Firebase emulator smoke test blocked until Java is available on PATH.
- `.firebaserc` still contains placeholder `<FIREBASE_PROJECT_ID>`.
- Frontend runtime env (`VITE_FIREBASE_*`) still needs real project values.

## Reverted During Session
- Local portable Java install attempt was reverted by removing `tools/` after user request.

## Next Actions After Java Install
1. Re-run emulator smoke check for Firestore.
2. Validate callable functions via Firebase emulator or deployed functions.
3. Final pass on migration wiring and optional commit if requested.
