import argparse
import csv
import io
import os
import sys
import psycopg
from datetime import datetime
from dataclasses import dataclass
from typing import Literal

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.toggl_client import TogglClient
from scripts.transform_toggl import transform_csv_entry, transform_json_entry
from scripts.supabase_db import (
    upsert_time_entries_pg,
    upsert_projects_pg,
    upsert_tags_pg,
    upsert_clients_pg,
    upsert_tasks_pg,
)


@dataclass
class SyncSummary:
    mode: Literal["quick", "full", "enriched"]
    years_processed: int
    entries_written: int
    projects_written: int
    tags_written: int
    clients_written: int
    tasks_written: int
    errors: list[str]


def get_pg_connection():
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        raise ValueError("SUPABASE_DB_URL environment variable is required")
    return psycopg.connect(db_url)


def run_sync(
    mode: Literal["quick", "full", "enriched"],
    earliest_year: int,
    dry_run: bool = False,
    max_requests_per_hour: int = 30,
) -> SyncSummary:
    client = TogglClient()
    # Keep CLI argument for compatibility; limiter tuning can be added later.
    _ = max_requests_per_hour
    projects: list[dict] = []
    tags: list[dict] = []
    clients: list[dict] = []
    tasks: list[dict] = []

    summary = SyncSummary(
        mode=mode,
        years_processed=0,
        entries_written=0,
        projects_written=0,
        tags_written=0,
        clients_written=0,
        tasks_written=0,
        errors=[],
    )

    try:
        me = client.get_me()
        workspace_id = me["default_workspace_id"]
    except Exception as e:
        summary.errors.append(f"Failed to get workspace: {e}")
        return summary

    try:
        projects = client.get_projects(workspace_id)
        if projects and not dry_run:
            with get_pg_connection() as conn:
                summary.projects_written += upsert_projects_pg(conn, projects)
        elif projects:
            summary.projects_written += len(projects)

        tags = client.get_tags(workspace_id)
        if tags and not dry_run:
            with get_pg_connection() as conn:
                summary.tags_written += upsert_tags_pg(conn, tags)
        elif tags:
            summary.tags_written += len(tags)

        clients = client.get_clients(workspace_id)
        if clients and not dry_run:
            with get_pg_connection() as conn:
                summary.clients_written += upsert_clients_pg(conn, clients)
        elif clients:
            summary.clients_written += len(clients)

        tasks = client.get_all_tasks(projects, workspace_id)
        if tasks and not dry_run:
            with get_pg_connection() as conn:
                summary.tasks_written += upsert_tasks_pg(conn, tasks)
        elif tasks:
            summary.tasks_written += len(tasks)

    except Exception as e:
        summary.errors.append(f"Failed to sync metadata: {e}")

    current_year = datetime.now().year
    years_to_sync = (
        [current_year]
        if mode == "quick"
        else list(range(earliest_year, current_year + 1))
    )
    summary.years_processed = len(years_to_sync)

    tag_map = {int(t["id"]): t.get("name", "") for t in tags if t.get("id") is not None}
    task_map = {
        int(t["id"]): t.get("name", "") for t in tasks if t.get("id") is not None
    }
    client_map = {
        int(c["id"]): c.get("name", "") for c in clients if c.get("id") is not None
    }

    if mode in ("quick", "full"):
        for year in years_to_sync:
            try:
                csv_bytes = client.fetch_year_csv(year)
                csv_text = csv_bytes.decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(csv_text))
                entries = [transform_csv_entry(row) for row in reader]
                if not dry_run and entries:
                    with get_pg_connection() as conn:
                        summary.entries_written += upsert_time_entries_pg(conn, entries)
                elif entries:
                    summary.entries_written += len(entries)
            except Exception as e:
                summary.errors.append(f"Failed to sync CSV for year {year}: {e}")
    elif mode == "enriched":
        for year in years_to_sync:
            try:
                entries = client.fetch_year_entries_json(
                    year,
                    tag_map=tag_map,
                    task_map=task_map,
                    client_map=client_map,
                    workspace_id=workspace_id,
                )
                normalized_entries = [
                    transform_json_entry(row, workspace_id) for row in entries
                ]
                for idx, row in enumerate(entries):
                    normalized_entries[idx]["project_name"] = row.get("project_name")
                    normalized_entries[idx]["task_name"] = row.get("task_name")
                    normalized_entries[idx]["client_name"] = row.get("client_name")
                if not dry_run and entries:
                    with get_pg_connection() as conn:
                        summary.entries_written += upsert_time_entries_pg(
                            conn, normalized_entries
                        )
                elif normalized_entries:
                    summary.entries_written += len(normalized_entries)
            except Exception as e:
                summary.errors.append(
                    f"Failed to sync enriched entries for year {year}: {e}"
                )

    if not dry_run and not summary.errors:
        try:
            with get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO public.sync_meta (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                        ("last_incremental_sync", datetime.utcnow().isoformat() + "Z"),
                    )
                conn.commit()
        except Exception as e:
            summary.errors.append(f"Failed to update sync_meta: {e}")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["quick", "full", "enriched"], required=True)
    parser.add_argument("--earliest-year", type=int, default=datetime.now().year)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-requests-per-hour", type=int, default=30)
    args = parser.parse_args()

    summary = run_sync(
        args.mode, args.earliest_year, args.dry_run, args.max_requests_per_hour
    )
    print(f"Sync Summary: {summary}")
    if summary.errors:
        sys.exit(1)
