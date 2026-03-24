# Active Context

Date: 2026-03-24
Project: Toggl Time Journal
Task: GitHub Pages deployment-readiness for minimal-input hosted demo and private auth beta bootstrap

## Plan

- [x] Update frontend routing for static GitHub Pages hosting.
- [x] Update Vite build config for repo-subpath deployment.
- [x] Fix demo-mode query chaining so all pages work without Supabase credentials.
- [x] Tighten GitHub Pages deployment workflow for low-touch publishing.
- [x] Document frontend env expectations for local and hosted builds.
- [x] Verify with a production build.
- [x] Add frontend auth/session bootstrap for real Supabase mode.
- [x] Add login/logout and protected routes for private beta behavior.
- [x] Update deployment docs/workflow to support optional real Supabase frontend envs.
- [x] Verify production build after auth changes.

## Review / Results

- Routing now uses `HashRouter` for GitHub Pages-safe deep links.
- Vite now builds for the repository subpath at `/toggl-api/`.
- Demo mode now supports chained homepage filters without a live Supabase backend.
- Pages workflow now builds a no-secret demo deploy by default.
- Frontend env expectations are documented in both root and `web/` examples.
- Verification passed with `node web/scripts/verify-pages-demo-readiness.mjs` and `npm run build` in `web/`.
- Added a real-mode auth provider, login page, protected routes, and signed-in shell for private beta behavior.
- GitHub Pages workflow now accepts optional frontend Supabase vars while still supporting demo-mode deploys.
- Auth verification passed with `node web/scripts/verify-auth-readiness.mjs` and a fresh `npm run build` in `web/`.
