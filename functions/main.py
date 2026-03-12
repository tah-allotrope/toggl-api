"""Firebase callable function entrypoints for sync, chat, and status APIs."""

from __future__ import annotations

import os
from typing import Any

from firebase_admin import firestore, initialize_app
from firebase_functions import https_fn, options

initialize_app()


def _require_auth(req: https_fn.CallableRequest) -> None:
    if req.auth is None:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Authentication required.",
        )


def _client():
    from toggl_client import TogglClient

    token = os.getenv("TOGGL_API_TOKEN", "")
    if not token:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message="TOGGL_API_TOKEN is not configured in function environment.",
        )
    return TogglClient(api_token=token)


@https_fn.on_call(timeout_sec=300, memory=options.MemoryOption.MB_512)
def sync_quick(req: https_fn.CallableRequest) -> dict[str, Any]:
    """Run current-year sync and return summary payload."""
    from sync_engine import sync_current_year

    _require_auth(req)
    db = firestore.client()
    result = sync_current_year(_client(), db)
    return {
        "success": True,
        "entries_synced": result.get("entries", 0),
        "year": result.get("year"),
        "message": "Quick sync completed.",
        "details": result,
    }


@https_fn.on_call(timeout_sec=300, memory=options.MemoryOption.GB_1)
def sync_full(req: https_fn.CallableRequest) -> dict[str, Any]:
    """Run full multi-year sync and return summary payload."""
    from sync_engine import sync_full as sync_full_impl

    _require_auth(req)
    earliest_year = 2017
    if isinstance(req.data, dict) and req.data.get("earliest_year") is not None:
        earliest_year = int(req.data["earliest_year"])

    db = firestore.client()
    result = sync_full_impl(_client(), db, earliest_year=earliest_year)
    return {
        "success": True,
        "entries_synced": result.get("total_entries", 0),
        "years_synced": result.get("years", []),
        "message": "Full sync completed.",
        "details": result,
    }


@https_fn.on_call(timeout_sec=540, memory=options.MemoryOption.GB_1)
def sync_enriched_year(req: https_fn.CallableRequest) -> dict[str, Any]:
    """Run single-year enriched sync and return summary payload."""
    from sync_engine import sync_enriched_year as sync_enriched_year_impl

    _require_auth(req)
    if not isinstance(req.data, dict) or req.data.get("year") is None:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Missing required field: year (int).",
        )

    year = int(req.data["year"])
    db = firestore.client()
    result = sync_enriched_year_impl(_client(), db, year)
    return {
        "success": True,
        "entries_synced": result.get("entries", 0),
        "year": result.get("year", year),
        "message": "Enriched year sync completed.",
        "details": result,
    }


@https_fn.on_call(timeout_sec=120, memory=options.MemoryOption.MB_512)
def chat_answer(req: https_fn.CallableRequest) -> dict[str, Any]:
    """Answer a natural-language time-tracking question."""
    from chat_engine import answer_question

    _require_auth(req)
    if not isinstance(req.data, dict) or not req.data.get("question"):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Missing required field: question (string).",
        )

    db = firestore.client()
    answer = answer_question(db, str(req.data["question"]))
    return {"answer": answer}


@https_fn.on_call(timeout_sec=60, memory=options.MemoryOption.MB_256)
def get_sync_status(req: https_fn.CallableRequest) -> dict[str, Any]:
    """Return sync metadata and data-availability status."""
    from sync_engine import get_sync_status as get_sync_status_impl

    _require_auth(req)
    db = firestore.client()
    return get_sync_status_impl(db)


@https_fn.on_call(timeout_sec=60, memory=options.MemoryOption.MB_256)
def get_stats(req: https_fn.CallableRequest) -> dict[str, Any]:
    """Return high-level data and enrichment statistics."""
    from sync_engine import get_stats as get_stats_impl

    _require_auth(req)
    db = firestore.client()
    return get_stats_impl(db)
