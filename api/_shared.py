"""Shared helpers for Vercel Python endpoints."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import firebase_admin
from fastapi import HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, firestore


def _load_functions_path() -> None:
    root = Path(__file__).resolve().parents[1]
    functions_dir = root / "functions"
    if str(functions_dir) not in sys.path:
        sys.path.insert(0, str(functions_dir))


def _initialize_firebase() -> None:
    if firebase_admin._apps:
        return

    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not service_account_json:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is required")

    try:
        service_account_info = json.loads(service_account_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_JSON is not valid JSON") from exc

    cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(cred)


def bootstrap() -> None:
    _load_functions_path()
    _initialize_firebase()


def get_firestore_client() -> firestore.Client:
    return firestore.client()


async def require_firebase_auth(request: Request) -> dict[str, Any]:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth_header[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    try:
        decoded = firebase_auth.verify_id_token(token)
    except Exception as exc:  # pragma: no cover - depends on runtime token validity
        raise HTTPException(status_code=401, detail="Invalid auth token") from exc

    return decoded


def configure_cors(app: Any) -> None:
    allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
    origins = [
        origin.strip() for origin in allowed_origins.split(",") if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=False,
        allow_methods=["POST", "OPTIONS"],
        allow_headers=["*"],
    )
