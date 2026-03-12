"""Sync orchestrator for Firebase Cloud Functions using Firestore storage."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from firebase_admin import firestore

from data_store import (
    get_available_years,
    get_enrichment_stats,
    get_sync_meta,
    set_sync_meta,
    upsert_clients_firestore,
    upsert_projects_firestore,
    upsert_tags_firestore,
    upsert_tasks_firestore,
    upsert_time_entries_firestore,
)
from toggl_client import TogglClient


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_full(
    client: TogglClient, db: firestore.Client, earliest_year: int = 2017
) -> dict[str, Any]:
    """Sync all years from earliest_year to current year into Firestore."""
    current_year = date.today().year
    years = list(range(earliest_year, current_year + 1))

    projects = client.get_projects()
    tags = client.get_tags()
    clients = client.get_clients()

    upsert_projects_firestore(db, projects)
    upsert_tags_firestore(db, tags)
    upsert_clients_firestore(db, clients)

    task_rows = client.get_all_tasks(projects)
    upsert_tasks_firestore(db, task_rows)

    tag_map = {int(t["id"]): t.get("name", "") for t in tags if t.get("id") is not None}
    task_map = {
        int(t["id"]): t.get("name", "") for t in task_rows if t.get("id") is not None
    }
    client_map = {
        int(c["id"]): c.get("name", "") for c in clients if c.get("id") is not None
    }

    total_entries = 0
    years_synced: list[int] = []
    errors: list[str] = []

    for year in years:
        try:
            entries = client.fetch_year_entries(
                year,
                tag_map=tag_map,
                task_map=task_map,
                client_map=client_map,
            )
            count = upsert_time_entries_firestore(db, entries)
            total_entries += count
            years_synced.append(year)
            set_sync_meta(db, f"last_sync_{year}", _iso_now())
        except Exception as exc:
            errors.append(f"{year}: {exc}")

    set_sync_meta(db, "last_full_sync", _iso_now())
    set_sync_meta(db, "earliest_year", str(earliest_year))

    return {
        "years_synced": len(years_synced),
        "years": years_synced,
        "total_entries": total_entries,
        "projects": len(projects),
        "tags": len(tags),
        "clients": len(clients),
        "tasks": len(task_rows),
        "errors": errors,
    }


def sync_current_year(client: TogglClient, db: firestore.Client) -> dict[str, Any]:
    """Sync only the current year into Firestore."""
    year = date.today().year

    projects = client.get_projects()
    tags = client.get_tags()
    clients = client.get_clients()

    upsert_projects_firestore(db, projects)
    upsert_tags_firestore(db, tags)
    upsert_clients_firestore(db, clients)

    task_rows = client.get_all_tasks(projects)
    upsert_tasks_firestore(db, task_rows)

    tag_map = {int(t["id"]): t.get("name", "") for t in tags if t.get("id") is not None}
    task_map = {
        int(t["id"]): t.get("name", "") for t in task_rows if t.get("id") is not None
    }
    client_map = {
        int(c["id"]): c.get("name", "") for c in clients if c.get("id") is not None
    }

    entries = client.fetch_year_entries(
        year,
        tag_map=tag_map,
        task_map=task_map,
        client_map=client_map,
    )
    count = upsert_time_entries_firestore(db, entries)

    now = _iso_now()
    set_sync_meta(db, "last_incremental_sync", now)
    set_sync_meta(db, f"last_sync_{year}", now)

    return {
        "year": year,
        "entries": count,
        "projects": len(projects),
        "tags": len(tags),
        "clients": len(clients),
        "tasks": len(task_rows),
    }


def sync_enriched_year(
    client: TogglClient, db: firestore.Client, year: int
) -> dict[str, Any]:
    """Sync exactly one year with enriched JSON fields into Firestore."""
    projects = client.get_projects()
    tags = client.get_tags()
    clients = client.get_clients()

    upsert_projects_firestore(db, projects)
    upsert_tags_firestore(db, tags)
    upsert_clients_firestore(db, clients)

    task_rows = client.get_all_tasks(projects)
    upsert_tasks_firestore(db, task_rows)

    tag_map = {int(t["id"]): t.get("name", "") for t in tags if t.get("id") is not None}
    task_map = {
        int(t["id"]): t.get("name", "") for t in task_rows if t.get("id") is not None
    }
    client_map = {
        int(c["id"]): c.get("name", "") for c in clients if c.get("id") is not None
    }

    entries = client.fetch_year_entries(
        year,
        tag_map=tag_map,
        task_map=task_map,
        client_map=client_map,
    )
    count = upsert_time_entries_firestore(db, entries)

    set_sync_meta(db, "last_enriched_sync", _iso_now())
    return {
        "year": year,
        "entries": count,
        "projects": len(projects),
        "tags": len(tags),
        "clients": len(clients),
        "tasks": len(task_rows),
    }


def get_sync_status(db: firestore.Client) -> dict[str, Any]:
    """Return sync metadata and whether any years currently exist in storage."""
    years = get_available_years(db)
    return {
        "last_full_sync": get_sync_meta(db, "last_full_sync"),
        "last_incremental_sync": get_sync_meta(db, "last_incremental_sync"),
        "last_enriched_sync": get_sync_meta(db, "last_enriched_sync"),
        "earliest_year": get_sync_meta(db, "earliest_year"),
        "years_with_data": years,
        "has_data": len(years) > 0,
    }


def get_stats(db: firestore.Client) -> dict[str, Any]:
    """Return enrichment and availability summary for frontend status rendering."""
    enrichment = get_enrichment_stats(db)
    total = enrichment["total_entries"]
    enriched = enrichment["enriched_entries"]
    pct = (100.0 * enriched / total) if total > 0 else 0.0

    return {
        "total_entries": total,
        "enriched_count": enriched,
        "enriched_pct": pct,
        "entries_with_project_id": enrichment["entries_with_project_id"],
        "entries_with_tag_ids": enrichment["entries_with_tag_ids"],
        "entries_with_tasks": enrichment["entries_with_tasks"],
        "entries_with_at": enrichment["entries_with_at"],
        "total_tasks": enrichment["total_tasks"],
        "total_clients": enrichment["total_clients"],
    }
