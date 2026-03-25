# Active Context

Date: 2026-03-25
Project: Toggl Time Journal
Task: Retarget GitHub Pages deployment to `master` and prepare branch for merge

## Plan

- [x] Retarget the web deployment workflow from `main` to `master`.
- [x] Ignore local frontend temp and TypeScript build-info artifacts so they do not pollute the merge.
- [x] Verify the frontend readiness scripts and production build still pass.
- [x] Capture deployment notes and merge readiness results.

## Review / Results

- GitHub Pages deploy now triggers on pushes to `master`, which matches the repository's current default branch.
- Added ignore coverage for `web/tmp/` and `web/*.tsbuildinfo` so local dev output does not reappear in future merges.
- Removed tracked generated frontend artifacts from git index while leaving local copies intact.
- Verification passed with `node scripts/verify-pages-demo-readiness.mjs`, `node scripts/verify-auth-readiness.mjs`, and `npm run build` in `web/`.
- Remaining deploy dependency: GitHub repo `vars` or `secrets` must contain `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` for live Supabase mode; otherwise Pages still ships demo mode successfully.
