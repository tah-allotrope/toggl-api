import os
import sys

import psycopg

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.env_utils import get_postgres_url
from scripts.supabase_db import upsert_time_entries_pg
from scripts.transform_toggl import transform_csv_entry, transform_json_entry


TEST_DESCRIPTION = "VERIFY_DEDUPE_RECONCILIATION_DO_NOT_KEEP"
TEST_PROJECT = "Verification Project"


def get_pg_connection() -> psycopg.Connection:
    return psycopg.connect(get_postgres_url())


def canonical_key_column_exists(conn: psycopg.Connection) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'time_entries'
              AND column_name = 'canonical_key';
            """
        )
        return cur.fetchone() is not None


def build_fixture_entries() -> tuple[dict, dict]:
    csv_entry = transform_csv_entry(
        {
            "Start date": "2024-06-01",
            "Start time": "09:00:00",
            "End date": "2024-06-01",
            "End time": "10:30:00",
            "Duration": "01:30:00",
            "Description": TEST_DESCRIPTION,
            "Project": TEST_PROJECT,
            "Client": "Verification Client",
            "Task": "Verification Task",
            "Tags": "Verification|Fixture",
            "Billable": "No",
        }
    )
    enriched_entry = transform_json_entry(
        {
            "id": 9090909090,
            "description": TEST_DESCRIPTION,
            "start": "2024-06-01T09:00:00+00:00",
            "stop": "2024-06-01T10:30:00+00:00",
            "duration": 5400,
            "project_id": 777,
            "project_name": TEST_PROJECT,
            "workspace_id": 10,
            "tags": ["Verification", "Fixture"],
            "tag_ids": [1, 2],
            "billable": False,
            "at": "2024-06-01T11:00:00+00:00",
            "task_id": 888,
            "task_name": "Verification Task",
            "client_name": "Verification Client",
            "user_id": 42,
        },
        workspace_id=10,
    )
    return csv_entry, enriched_entry


def main() -> int:
    csv_entry, enriched_entry = build_fixture_entries()

    if csv_entry["canonical_key"] != enriched_entry["canonical_key"]:
        print("Canonical key mismatch between CSV and enriched fixtures")
        return 1

    canonical_key = csv_entry["canonical_key"]

    with get_pg_connection() as conn:
        try:
            if not canonical_key_column_exists(conn):
                print(
                    "Verification requires public.time_entries.canonical_key; apply the canonical-key migration first"
                )
                return 1

            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.time_entries WHERE canonical_key = %s;",
                    (canonical_key,),
                )
            conn.commit()

            upsert_time_entries_pg(conn, [csv_entry])
            upsert_time_entries_pg(conn, [enriched_entry])

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*), MIN(toggl_id), MIN(project_id), MIN(task_id), MIN(client_name)
                    FROM public.time_entries
                    WHERE canonical_key = %s;
                    """,
                    (canonical_key,),
                )
                row = cur.fetchone()

            row_count = int(row[0]) if row else 0
            toggl_id = row[1] if row else None
            project_id = row[2] if row else None
            task_id = row[3] if row else None
            client_name = row[4] if row else None

            if row_count != 1:
                print(f"Expected 1 reconciled row, found {row_count}")
                return 1
            if toggl_id != enriched_entry["toggl_id"]:
                print(
                    f"Expected toggl_id {enriched_entry['toggl_id']}, found {toggl_id}"
                )
                return 1
            if project_id != enriched_entry["project_id"]:
                print(
                    f"Expected project_id {enriched_entry['project_id']}, found {project_id}"
                )
                return 1
            if task_id != enriched_entry["task_id"]:
                print(f"Expected task_id {enriched_entry['task_id']}, found {task_id}")
                return 1
            if client_name != enriched_entry["client_name"]:
                print(
                    f"Expected client_name {enriched_entry['client_name']!r}, found {client_name!r}"
                )
                return 1

            print("Dedupe reconciliation verification passed")
            print(f"canonical_key={canonical_key}")
            return 0
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.time_entries WHERE canonical_key = %s;",
                    (canonical_key,),
                )
            conn.commit()


if __name__ == "__main__":
    raise SystemExit(main())
