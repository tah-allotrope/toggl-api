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
- Cloud Functions deploy blocked: project needs Blaze (pay-as-you-go) plan for `cloudbuild.googleapis.com`.
- Firebase Authentication not yet configured (Email/Password provider needs enabling).
- Toggl API token not yet set as function environment secret.
- No user created yet for app login.
- Firestore contains no data yet (migration script not run).

## Next Actions
1. Upgrade `toggl-journal` to Blaze plan: https://console.firebase.google.com/project/toggl-journal/usage/details
2. Enable Firebase Authentication (Email/Password) in Console.
3. Create first user account for app login.
4. Set Toggl API token as function secret: `firebase functions:secrets:set TOGGL_API_TOKEN`
5. Deploy Cloud Functions: `firebase deploy --only functions --project toggl-journal`
6. (Optional) Run migration script to seed Firestore: `python scripts/migrate_sqlite_to_firestore.py --service-account <path> --project-id toggl-journal`

(End of file - total 96 lines)
