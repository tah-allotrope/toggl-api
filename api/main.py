from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- SETUP PATHS ---
api_dir = Path(__file__).resolve().parent
if str(api_dir) not in sys.path:
    sys.path.insert(0, str(api_dir))

# --- APP SETUP ---
app = FastAPI()

allowed_origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins if o.strip()] or ["*"],
    allow_credentials=False,
    allow_methods=["POST", "OPTIONS", "GET"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    question: str

class SyncRequest(BaseModel):
    sync_type: str
    year: int | None = None
    earliest_year: int | None = None

# --- DATABASE HELPERS ---
def get_db_connection():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required")
    return psycopg2.connect(db_url, cursor_factory=RealDictCursor)

async def require_auth(request: Request) -> dict[str, Any]:
    from supabase import create_client
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth_header[7:].strip()
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    supabase = create_client(url, key)
    try:
        res = supabase.auth.get_user(token)
        if not res.user:
            raise HTTPException(status_code=401, detail="Invalid auth token")
        return {"uid": res.user.id, "email": res.user.email}
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid auth token") from exc

# --- ROUTES ---
@app.get("/api/health")
async def health():
    return {"status": "ok", "python_version": sys.version}

@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    await require_auth(request)
    import chat_engine
    db = get_db_connection()
    try:
        answer = chat_engine.answer_question(db, payload.question.strip())
        return {"answer": answer}
    finally:
        db.close()

@app.post("/api/stats")
async def stats(request: Request):
    await require_auth(request)
    import sync_engine
    db = get_db_connection()
    try:
        return sync_engine.get_stats(db)
    finally:
        db.close()

@app.post("/api/status")
async def status(request: Request):
    await require_auth(request)
    import sync_engine
    db = get_db_connection()
    try:
        return sync_engine.get_sync_status(db)
    finally:
        db.close()

@app.post("/api/sync")
async def sync(payload: SyncRequest, request: Request):
    await require_auth(request)
    import sync_engine
    import toggl_client
    sync_type = payload.sync_type.strip().lower()
    db = get_db_connection()
    client = toggl_client.TogglClient()
    try:
        if sync_type == "quick":
            return sync_engine.sync_current_year(client, db)
        elif sync_type == "full":
            return sync_full(client, db, payload.earliest_year or 2017)
        elif sync_type == "enriched":
            if not payload.year:
                raise HTTPException(status_code=400, detail="year is required")
            return sync_engine.sync_enriched_year(client, db, payload.year)
        else:
            raise HTTPException(status_code=400, detail="Invalid sync_type")
    finally:
        db.close()
