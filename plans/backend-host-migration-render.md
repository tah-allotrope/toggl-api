# Backend Host Migration (Render)

## Goal
Run FastAPI backend on Render (IPv4-friendly) while keeping frontend on Vercel.

## Why
- Current Vercel serverless runtime cannot connect to Supabase direct Postgres host for this project.
- App login works, but authenticated backend routes (`/api/status`, `/api/sync`, `/api/chat`) fail due to DB socket connectivity.

## Added in repo
- `render.yaml` (Render blueprint)
- `api/render_entrypoint.py` (alternate ASGI entrypoint)
- `api/requirements.txt` now includes `uvicorn`

## Render setup
1. In Render dashboard, create a new **Web Service** from this repo.
2. If Render detects blueprint, keep defaults from `render.yaml`.
3. Set environment variables in Render service:
   - `DATABASE_URL` = your working Supabase Postgres URI for Render runtime
   - `SUPABASE_URL` = `https://itxfaxlnlbzbddyvqvwd.supabase.co`
   - `SUPABASE_KEY` = Supabase server key (service role or secret key used for token verification)
   - `TOGGL_API_TOKEN` = your Toggl token
   - `ALLOWED_ORIGINS` = `https://toggl-api.vercel.app`
4. Deploy service and note the Render URL, for example:
   - `https://toggl-time-journal-api.onrender.com`

## Wire frontend to new backend
1. In Vercel project settings, update Production env var:
   - `VITE_API_BASE_URL=https://<your-render-service>.onrender.com/api`
2. Redeploy Vercel frontend.

## Verify
1. `GET https://<render-host>/api/health` returns 200.
2. In browser, login succeeds (already working password-only).
3. `Dashboard` loads.
4. `Chat` returns answer (not 500).
5. `Quick Sync` returns success message (or valid Toggl error if token invalid).

## Security follow-up
- Rotate the previously exposed secret key and update Render `SUPABASE_KEY`.
