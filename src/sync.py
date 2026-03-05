"""
Sync orchestrator: coordinates fetching data from Toggl and storing it locally.

Handles:
- Initial full sync (all years from earliest_year to now) — CSV-based, fast
- Incremental sync (current year only) — CSV-based, fast
- Enrichment sync (all years, JSON-based) — pulls full field set while on Premium
- Progress callbacks for UI display
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from src.toggl_client import TogglClient
from src.data_store import (
    get_connection, upsert_time_entries, upsert_projects, upsert_tags,
    upsert_clients, upsert_tasks,
    set_sync_meta, get_sync_meta, get_available_years,
)

DATA_RAW_DIR = Path(__file__).parent.parent / "data" / "raw"


def sync_all(
    client: TogglClient,
    earliest_year: int = 2017,
    progress_callback: Callable[[str, float], None] | None = None,
) -> dict:
    """
    Full sync: fetch all years from earliest_year to current year via CSV export.
    Saves raw JSON per year and populates SQLite.
    1 API call per year — very efficient on the Free tier (30 req/hr).

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

        upsert_time_entries(conn, entries)
        total_entries += len(entries)
        report(f"  {year}: {len(entries)} entries", frac + 0.04)

    # Step 3: Record sync timestamp
    now = datetime.now(tz=None).isoformat()
    set_sync_meta(conn, "last_full_sync", now)
    set_sync_meta(conn, "earliest_year", str(earliest_year))

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
    Incremental sync: only fetch the current year's entries via CSV export.
    Much faster and uses fewer API calls than a full sync (3 total API calls).
    """
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    year = date.today().year

    def report(msg: str, frac: float):
        if progress_callback:
            progress_callback(msg, frac)
        print(msg)

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


def sync_enriched_all(
    client: TogglClient,
    earliest_year: int = 2017,
    progress_callback: Callable[[str, float], None] | None = None,
) -> dict:
    """
    Enrichment sync: re-fetch all years via the Reports API v3 JSON endpoint
    with enrich_response=True to pull the full field set unavailable in CSV:

      - Native Toggl entry IDs (toggl_id) — replacing synthetic SHA-256 IDs
      - Real project_id integers — enabling FK joins to the projects table
      - Real tag_ids integer arrays — enabling FK joins to the tags table
      - task_id / task_name — Premium task assignments
      - client_name — denormalized from the project→client chain
      - at timestamp — last-modified time for each entry
      - Premium project metadata — rates, fees, estimated hours, recurring params
      - Tasks table — all tasks across all projects (Premium)
      - Clients table — all clients in the workspace

    IMPORTANT: This function makes many more API calls than sync_all().
    With Premium (600 req/hr) a full 10-year backfill takes approximately 2 hours.
    The function is designed to be idempotent — upserts are safe to re-run if
    interrupted (each completed year persists to SQLite before moving on).

    progress_callback(message, fraction) is called to report progress.
    Returns a summary dict with enrichment coverage statistics.
    """
    DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection()
    wid = client.get_workspace_id()
    current_year = date.today().year
    years = list(range(earliest_year, current_year + 1))
    total_entries = 0
    errors: list[str] = []

    # Progress budget allocation:
    #   0%–3%   : clients (1 API call)
    #   3%–6%   : projects + Premium fields (1 API call)
    #   6%–9%   : tags with enrichment (1 API call)
    #   9%–15%  : tasks per project (~N calls)
    #   15%–99% : time entries year by year (~1132 calls for 10 years)
    #   99%–100%: finalize

    def report(msg: str, frac: float):
        if progress_callback:
            progress_callback(msg, frac)
        print(msg)

    # ---- Step 1: Clients (1 API call) ----------------------------------------
    report("Fetching clients...", 0.00)
    clients = client.get_clients(wid)
    upsert_clients(conn, clients)
    client_map: dict[int, str] = {c["id"]: c.get("name", "") for c in clients}
    report(f"  Stored {len(clients)} clients", 0.03)

    # ---- Step 2: Projects — with Premium fields (1 API call) -----------------
    report("Fetching projects (with Premium fields)...", 0.03)
    projects = client.get_projects(wid)
    upsert_projects(conn, projects)
    project_map: dict[int, str] = {p["id"]: p.get("name", "") for p in projects}
    report(f"  Stored {len(projects)} projects", 0.06)

    # ---- Step 3: Tags — with enriched metadata (1 API call) ------------------
    report("Fetching tags (with enriched metadata)...", 0.06)
    tags = client.get_tags(wid)
    upsert_tags(conn, tags)
    tag_map: dict[int, str] = {t["id"]: t.get("name", "") for t in tags}
    report(f"  Stored {len(tags)} tags", 0.09)

    # ---- Step 4: Tasks per project — Premium (1 call per active project) ------
    report("Fetching tasks (Premium)...", 0.09)
    all_tasks = client.get_all_tasks(projects, workspace_id=wid)
    upsert_tasks(conn, all_tasks)
    task_map: dict[int, str] = {t["id"]: t.get("name", "") for t in all_tasks}
    report(f"  Stored {len(all_tasks)} tasks across {len(projects)} projects", 0.15)

    # ---- Step 5: Time entries year by year via JSON ---------------------------
    entry_frac_start = 0.15
    entry_frac_span = 0.84  # 15% to 99%

    for i, year in enumerate(years):
        year_frac = entry_frac_start + (entry_frac_span * (i / len(years)))
        report(f"Enriching {year} entries (JSON)...", year_frac)

        try:
            entries = client.fetch_year_entries_json(
                year,
                tag_map=tag_map,
                task_map=task_map,
                client_map=client_map,
                workspace_id=wid,
            )
        except Exception as exc:
            msg = f"  {year}: FAILED ({exc})"
            report(msg, year_frac)
            errors.append(msg)
            continue

        # Backfill project_name if missing (shouldn't be needed with enrich_response
        # but defensive in case the API omits it on older entries)
        for e in entries:
            if not e.get("project_name") and e.get("project_id"):
                e["project_name"] = project_map.get(e["project_id"], "")

        # Save enriched JSON archive alongside the CSV-derived archive
        raw_path = DATA_RAW_DIR / f"{year}_enriched.json"
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        upsert_time_entries(conn, entries)
        total_entries += len(entries)

        done_frac = entry_frac_start + (entry_frac_span * ((i + 1) / len(years)))
        report(f"  {year}: {len(entries)} entries enriched", done_frac)

    # ---- Step 6: Record enrichment metadata ----------------------------------
    now = datetime.now(tz=None).isoformat()
    set_sync_meta(conn, "last_enriched_sync", now)
    set_sync_meta(conn, "enriched_earliest_year", str(earliest_year))

    conn.close()
    report("Enrichment sync complete!", 1.0)

    return {
        "years_enriched": len(years) - len(errors),
        "total_entries": total_entries,
        "projects": len(projects),
        "tags": len(tags),
        "clients": len(clients),
        "tasks": len(all_tasks),
        "errors": errors,
    }


def get_sync_status() -> dict:
    """Return information about when the last sync happened."""
    conn = get_connection()
    last_full = get_sync_meta(conn, "last_full_sync")
    last_incr = get_sync_meta(conn, "last_incremental_sync")
    last_enriched = get_sync_meta(conn, "last_enriched_sync")
    earliest = get_sync_meta(conn, "earliest_year")
    years = get_available_years(conn)
    conn.close()
    return {
        "last_full_sync": last_full,
        "last_incremental_sync": last_incr,
        "last_enriched_sync": last_enriched,
        "earliest_year": int(earliest) if earliest else None,
        "years_with_data": years,
        "has_data": len(years) > 0,
    }
