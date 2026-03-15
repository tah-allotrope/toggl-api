"""Sync orchestrator for Postgres storage."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from data_store import (
    get_sync_status as get_sync_status_pg,
    get_stats as get_stats_pg,
    get_sync_meta,
    set_sync_meta,
    upsert_projects_pg,
    upsert_tags_pg,
    upsert_time_entries_pg,
)
from toggl_client import TogglClient


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync_full(
    client: TogglClient, db, earliest_year: int = 2017
) -> dict[str, Any]:
    """Sync all years from earliest_year to current year into Postgres."""
    current_year = date.today().year
    years = list(range(earliest_year, current_year + 1))

    projects = client.get_projects()
    tags = client.get_tags()
    
    upsert_projects_pg(db, projects)
    upsert_tags_pg(db, tags)

    tag_map = {int(t["id"]): t.get("name", "") for t in tags if t.get("id") is not None}
    
    total_entries = 0
    years_synced: list[int] = []
    errors: list[str] = []

    for year in years:
        try:
            entries = client.fetch_year_entries(
                year,
                tag_map=tag_map,
            )
            count = upsert_time_entries_pg(db, entries)
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
        "errors": errors,
    }


def sync_current_year(client: TogglClient, db) -> dict[str, Any]:
    """Sync only the current year into Postgres."""
    year = date.today().year

    projects = client.get_projects()
    tags = client.get_tags()

    upsert_projects_pg(db, projects)
    upsert_tags_pg(db, tags)

    tag_map = {int(t["id"]): t.get("name", "") for t in tags if t.get("id") is not None}

    entries = client.fetch_year_entries(
        year,
        tag_map=tag_map,
    )
    count = upsert_time_entries_pg(db, entries)

    now = _iso_now()
    set_sync_meta(db, "last_incremental_sync", now)
    set_sync_meta(db, f"last_sync_{year}", now)

    return {
        "year": year,
        "entries": count,
        "projects": len(projects),
        "tags": len(tags),
    }


def sync_enriched_year(
    client: TogglClient, db, year: int
) -> dict[str, Any]:
    """Sync exactly one year with enriched JSON fields into Postgres."""
    projects = client.get_projects()
    tags = client.get_tags()

    upsert_projects_pg(db, projects)
    upsert_tags_pg(db, tags)

    tag_map = {int(t["id"]): t.get("name", "") for t in tags if t.get("id") is not None}

    entries = client.fetch_year_entries(
        year,
        tag_map=tag_map,
    )
    count = upsert_time_entries_pg(db, entries)

    set_sync_meta(db, "last_enriched_sync", _iso_now())
    return {
        "year": year,
        "entries": count,
        "projects": len(projects),
        "tags": len(tags),
    }


def get_sync_status(db) -> dict[str, Any]:
    return get_sync_status_pg(db)


def get_stats(db) -> dict[str, Any]:
    return get_stats_pg(db)
