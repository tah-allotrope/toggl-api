"""Vercel endpoint for enrichment statistics."""

from __future__ import annotations

from fastapi import FastAPI

from _shared import bootstrap, configure_cors, get_firestore_client
from _shared import require_firebase_auth

bootstrap()

from sync_engine import get_stats


app = FastAPI()
configure_cors(app)


@app.post("/")
async def stats() -> dict:
    db = get_firestore_client()
    return get_stats(db)


@app.middleware("http")
async def auth_middleware(request, call_next):
    if request.method != "OPTIONS":
        await require_firebase_auth(request)
    return await call_next(request)
