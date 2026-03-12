"""One-time migration script to copy SQLite data into Firestore collections."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import firebase_admin
from firebase_admin import credentials, firestore


def _row_dicts(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    cursor = conn.execute(f"SELECT * FROM {table_name}")
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def transform_time_entry(row: dict) -> dict:
    """Normalize a SQLite time_entries row for Firestore storage."""
    tags = []
    if row.get("tags"):
        try:
            tags = json.loads(row["tags"])
        except json.JSONDecodeError:
            tags = []

    tag_ids = []
    if row.get("tag_ids"):
        try:
            tag_ids = json.loads(row["tag_ids"])
        except json.JSONDecodeError:
            tag_ids = []

    start_raw = row.get("start")
    stop_raw = row.get("stop")
    start_dt = _parse_iso(start_raw)
    stop_dt = _parse_iso(stop_raw)

    local_month = row.get("start_month")
    local_day = row.get("start_day")
    if (local_month is None or local_day is None) and start_raw:
        try:
            local_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            local_month = local_dt.month
            local_day = local_dt.day
        except ValueError:
            pass

    return {
        "toggl_id": row.get("toggl_id"),
        "description": row.get("description") or "",
        "start": start_dt,
        "end": stop_dt,
        "duration_seconds": int(row.get("duration") or 0),
        "duration_hours": float(row.get("duration_hours") or 0.0),
        "project": row.get("project_name") or "",
        "project_name": row.get("project_name") or "",
        "project_id": row.get("project_id"),
        "workspace_id": row.get("workspace_id"),
        "tags_json": tags,
        "tag_ids": tag_ids,
        "billable": bool(row.get("billable", 0)),
        "enriched": row.get("toggl_id") is not None,
        "at": row.get("at") or "",
        "task_id": row.get("task_id"),
        "task_name": row.get("task_name") or "",
        "client_name": row.get("client_name") or "",
        "user_id": row.get("user_id"),
        "start_date": row.get("start_date"),
        "start_year": row.get("start_year"),
        "start_month": local_month,
        "start_day": local_day,
        "start_week": row.get("start_week"),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def migrate_collection(
    db: firestore.Client,
    conn: sqlite3.Connection,
    table_name: str,
    collection_name: str,
    id_field: str,
    transform_fn: Callable[[dict], dict] | None = None,
) -> int:
    """Migrate all rows from one SQLite table into one Firestore collection."""
    rows = _row_dicts(conn, table_name)
    total = len(rows)
    migrated = 0

    batch = db.batch()
    batch_count = 0

    for index, row in enumerate(rows, start=1):
        doc_id_value = row.get(id_field)
        if table_name == "time_entries" and row.get("toggl_id") is not None:
            doc_id_value = row.get("toggl_id")
        if doc_id_value is None:
            doc_id_value = row.get("id")
        if doc_id_value is None:
            continue

        payload = transform_fn(row) if transform_fn else row
        doc_ref = db.collection(collection_name).document(str(doc_id_value))
        batch.set(doc_ref, payload, merge=True)
        batch_count += 1
        migrated += 1

        if batch_count == 500:
            batch.commit()
            batch = db.batch()
            batch_count = 0
            print(f"Migrated {index}/{total} {table_name}")

    if batch_count:
        batch.commit()

    print(f"Migrated {migrated}/{total} {table_name}")
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate SQLite toggl.db into Firestore."
    )
    parser.add_argument(
        "--db-path", default="data/toggl.db", help="Path to SQLite database file"
    )
    parser.add_argument(
        "--service-account", required=True, help="Path to Firebase service account JSON"
    )
    parser.add_argument("--project-id", required=True, help="Firebase project ID")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite DB not found: {db_path}")

    cred = credentials.Certificate(args.service_account)
    firebase_admin.initialize_app(cred, {"projectId": args.project_id})
    db = firestore.client()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        migrate_collection(
            db,
            conn,
            "time_entries",
            "time_entries",
            "id",
            transform_fn=transform_time_entry,
        )
        migrate_collection(db, conn, "projects", "projects", "id")
        migrate_collection(db, conn, "tags", "tags", "id")
        migrate_collection(db, conn, "clients", "clients", "id")
        migrate_collection(db, conn, "tasks", "tasks", "id")
        migrate_collection(db, conn, "sync_meta", "sync_meta", "key")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
