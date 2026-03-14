"""Vercel endpoint for chat answers."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from _shared import bootstrap, configure_cors, get_firestore_client
from _shared import require_firebase_auth

bootstrap()

from chat_engine import answer_question


app = FastAPI()
configure_cors(app)


class ChatRequest(BaseModel):
    question: str


@app.post("/")
async def chat(payload: ChatRequest):
    return _chat_impl(payload)


def _chat_impl(payload: ChatRequest) -> dict[str, str]:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Missing required field: question")

    db = get_firestore_client()
    answer = answer_question(db, question)
    return {"answer": answer}


@app.middleware("http")
async def auth_middleware(request, call_next):
    if request.method != "OPTIONS":
        await require_firebase_auth(request)
    return await call_next(request)
