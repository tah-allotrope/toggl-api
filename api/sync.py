"""Vercel endpoint to trigger sync workflows on GitHub Actions."""

from __future__ import annotations

import os

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from _shared import configure_cors, require_firebase_auth


app = FastAPI()
configure_cors(app)


class SyncRequest(BaseModel):
    sync_type: str
    year: int | None = None
    earliest_year: int | None = None


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _dispatch_workflow(workflow_file: str, inputs: dict[str, str]) -> None:
    owner = _required_env("GITHUB_OWNER")
    repo = _required_env("GITHUB_REPO")
    token = _required_env("GITHUB_TOKEN")
    ref = os.getenv("GITHUB_REF", "main").strip() or "main"

    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches"
    response = requests.post(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        json={"ref": ref, "inputs": inputs},
        timeout=30,
    )
    if response.status_code >= 300:
        raise HTTPException(
            status_code=502,
            detail=f"GitHub dispatch failed: {response.status_code} {response.text}",
        )


@app.post("/")
async def sync(payload: SyncRequest) -> dict[str, str]:
    sync_type = payload.sync_type.strip().lower()
    if sync_type not in {"quick", "full", "enriched"}:
        raise HTTPException(
            status_code=400, detail="sync_type must be quick, full, or enriched"
        )

    if sync_type == "quick":
        workflow_file = os.getenv("GITHUB_QUICK_WORKFLOW", "sync_quick.yml")
        _dispatch_workflow(workflow_file, {})
        return {
            "message": "Quick sync job dispatched. Check GitHub Actions for progress."
        }

    workflow_file = os.getenv("GITHUB_SYNC_WORKFLOW", "sync_dispatch.yml")
    if sync_type == "full":
        earliest_year = (
            payload.earliest_year if payload.earliest_year is not None else 2017
        )
        _dispatch_workflow(
            workflow_file,
            {
                "sync_type": "full",
                "earliest_year": str(earliest_year),
            },
        )
        return {
            "message": "Full sync job dispatched. Check GitHub Actions for progress."
        }

    if payload.year is None:
        raise HTTPException(
            status_code=400, detail="year is required for enriched sync"
        )
    _dispatch_workflow(
        workflow_file,
        {
            "sync_type": "enriched",
            "year": str(payload.year),
        },
    )
    return {
        "message": "Enriched sync job dispatched. Check GitHub Actions for progress."
    }


@app.middleware("http")
async def auth_middleware(request, call_next):
    if request.method != "OPTIONS":
        await require_firebase_auth(request)
    return await call_next(request)
