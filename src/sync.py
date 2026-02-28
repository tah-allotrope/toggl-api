"""
Sync orchestrator: coordinates fetching data from Toggl and storing it locally.

Handles:
- Initial full sync (all years from earliest_year to now)
- Incremental sync (current year only, since last sync)
- Progress callbacks for UI display
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from src.toggl_client import TogglClient
from src.data_store import (
    get_connection, upsert_time_entries, upsert_projects, upsert_tags,
    set_sync_meta, get_sync_meta, get_available_years,
)

DATA_RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


def sync_all(
    client: TogglClient,
    earliest_year: int = 2017,
    progress_callback: Callable[[str, float], None] | None = None,
) -> dict:
    """
    Full sync: fetch all years from earliest_year to current year.
    Saves raw JSON per year and populates SQLite.

    progress_callback(message, fraction) is called to report progress.
    Returns a summary dict.
    """
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    current_year = date.today().year
    years = list(range(earliest_year, current_year + 1))
    total_entries = 0

    def report(msg: str, frac: float):
        if progress_callback:
            progress_callback(msg, frac)
        print(msg)

    # Step 1: Fetch projects and tags (2 API calls)
    report("Fetching projects...", 0.0)
    projects = client.get_projects()
    upsert_projects(conn, projects)
    report(f"  Stored {len(projects)} projects", 0.02)

    report("Fetching tags...", 0.04)
    tags = client.get_tags()
    upsert_tags(conn, tags)
    report(f"  Stored {len(tags)} tags", 0.06)

    # Build project name lookup for enriching entries if project_name is missing
    project_map = {p["id"]: p.get("name", "") for p in projects}

    # Step 2: Fetch time entries year by year (CSV export = 1 API call per year)
    errors: list[str] = []
    for i, year in enumerate(years):
        frac = 0.06 + (0.90 * (i / len(years)))
        report(f"Fetching {year}...", frac)

        try:
            entries = client.fetch_year_entries(year)
        except Exception as exc:
            msg = f"  {year}: FAILED ({exc})"
            report(msg, frac + 0.04)
            errors.append(msg)
            continue

        # Enrich entries with project names if missing
        for e in entries:
            if not e.get("project_name") and e.get("project_id"):
                e["project_name"] = project_map.get(e["project_id"], "")

        # Save raw JSON for archival
        raw_path = DATA_RAW_DIR / f"{year}.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        # Store in SQLite
        upsert_time_entries(conn, entries)
        total_entries += len(entries)
        report(f"  {year}: {len(entries)} entries", frac + 0.04)

    # Step 3: Record sync timestamp
    now = datetime.now(tz=None).isoformat()
    set_sync_meta(conn, "last_full_sync", now)
    set_sync_meta(conn, "earliest_year", str(earliest_year))

    conn.close()
    report("Sync complete!", 1.0)

    conn.close()
    report("Sync complete!", 1.0)

    return {
        "years_synced": len(years),
        "total_entries": total_entries,
        "projects": len(projects),
        "tags": len(tags),
        "errors": errors,
    }


def sync_current_year(
    client: TogglClient,
    progress_callback: Callable[[str, float], None] | None = None,
) -> dict:
    """
    Incremental sync: only fetch the current year's entries.
    Much faster and uses fewer API calls than a full sync.
    """
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    year = date.today().year

    def report(msg: str, frac: float):
        if progress_callback:
            progress_callback(msg, frac)
        print(msg)

    # Refresh projects and tags in case new ones were created
    report("Refreshing projects & tags...", 0.0)
    projects = client.get_projects()
    upsert_projects(conn, projects)
    tags = client.get_tags()
    upsert_tags(conn, tags)

    project_map = {p["id"]: p.get("name", "") for p in projects}

    report(f"Fetching {year} entries...", 0.3)
    entries = client.fetch_year_entries(year)

    for e in entries:
        if not e.get("project_name") and e.get("project_id"):
            e["project_name"] = project_map.get(e["project_id"], "")

    # Save raw JSON
    raw_path = DATA_RAW_DIR / f"{year}.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    upsert_time_entries(conn, entries)

    now = datetime.now(tz=None).isoformat()
    set_sync_meta(conn, "last_incremental_sync", now)
    set_sync_meta(conn, f"last_sync_{year}", now)

    conn.close()
    report("Sync complete!", 1.0)

    return {
        "year": year,
        "entries": len(entries),
    }


def get_sync_status() -> dict:
    """Return information about when the last sync happened."""
    conn = get_connection()
    last_full = get_sync_meta(conn, "last_full_sync")
    last_incr = get_sync_meta(conn, "last_incremental_sync")
    earliest = get_sync_meta(conn, "earliest_year")
    years = get_available_years(conn)
    conn.close()
    return {
        "last_full_sync": last_full,
        "last_incremental_sync": last_incr,
        "earliest_year": int(earliest) if earliest else None,
        "years_with_data": years,
        "has_data": len(years) > 0,
    }
