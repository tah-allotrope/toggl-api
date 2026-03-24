"""Validate Supabase migration state and custom-range RPC behavior."""

import json
import os
import sys
from typing import Any, LiteralString

import psycopg

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.env_utils import get_postgres_url
from scripts.supabase_db import upsert_time_entries_pg
from scripts.transform_toggl import (
    build_canonical_entry_key,
    derive_time_parts,
    transform_json_entry,
)


FIXTURE_PREFIX = "VERIFY_SUPABASE_DB_STATE_DO_NOT_KEEP"
TEST_WORKSPACE_ID = 999001
TEST_RANGE_START = "2099-04-15"
TEST_RANGE_END = "2099-04-15"


def get_pg_connection() -> psycopg.Connection:
    """Return a Postgres connection using the configured local env vars."""
    return psycopg.connect(get_postgres_url())


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _fetch_one_value(
    cur: psycopg.Cursor, query: LiteralString, params: tuple[Any, ...]
) -> Any:
    cur.execute(query, params)
    row = cur.fetchone()
    return row[0] if row else None


def _verify_canonical_key_schema(cur: psycopg.Cursor) -> None:
    canonical_key_column = _fetch_one_value(
        cur,
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'time_entries'
          AND column_name = 'canonical_key';
        """,
        (),
    )
    _assert(
        canonical_key_column == 1, "Missing public.time_entries.canonical_key column"
    )

    null_canonical_rows = _fetch_one_value(
        cur,
        "SELECT COUNT(*) FROM public.time_entries WHERE canonical_key IS NULL;",
        (),
    )
    _assert(
        int(null_canonical_rows or 0) == 0,
        "Found rows with NULL canonical_key; migration backfill appears incomplete",
    )

    for index_name in ("idx_entries_canonical_key", "idx_entries_csv_canonical_key"):
        index_exists = _fetch_one_value(
            cur,
            "SELECT to_regclass(%s);",
            (f"public.{index_name}",),
        )
        _assert(index_exists == index_name, f"Missing expected index {index_name}")


def _verify_rpc_signatures(cur: psycopg.Cursor) -> None:
    expected_functions = (
        "get_overview_metrics",
        "get_project_breakdown",
        "get_tag_breakdown",
        "get_client_breakdown",
        "get_task_breakdown",
    )

    for function_name in expected_functions:
        arg_names = _fetch_one_value(
            cur,
            """
            SELECT proargnames
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND p.proname = %s
            ORDER BY p.oid DESC
            LIMIT 1;
            """,
            (function_name,),
        )
        _assert(arg_names is not None, f"Missing function public.{function_name}")
        _assert(
            list(arg_names)[:4]
            == ["view_mode", "filter_year", "p_start_date", "p_end_date"],
            f"Unexpected argument names for public.{function_name}: {arg_names}",
        )


def _verify_backfill_expression(cur: psycopg.Cursor, row_id: int) -> str:
    description = f"{FIXTURE_PREFIX}_canonical"
    project_name = "Verification Canonical Project"
    start_iso = "2099-04-01T09:00:00Z"
    stop_iso = "2099-04-01T10:00:00Z"
    duration = 3600
    start_date, start_year, start_month, start_day, start_week = derive_time_parts(
        start_iso
    )

    cur.execute(
        """
        INSERT INTO public.time_entries (
            id, description, start, stop, duration, project_id, project_name,
            workspace_id, tags, tag_ids, billable, at,
            start_date, start_year, start_month, start_day, start_week, duration_hours,
            canonical_key, toggl_id, task_id, task_name, client_name, user_id
        ) VALUES (
            %(id)s, %(description)s, %(start)s, %(stop)s, %(duration)s, NULL, %(project_name)s,
            %(workspace_id)s, %(tags)s::jsonb, %(tag_ids)s::jsonb, 0, NULL,
            %(start_date)s, %(start_year)s, %(start_month)s, %(start_day)s, %(start_week)s, %(duration_hours)s,
            NULL, NULL, NULL, NULL, NULL, NULL
        );
        """,
        {
            "id": row_id,
            "description": description,
            "start": start_iso,
            "stop": stop_iso,
            "duration": duration,
            "project_name": project_name,
            "workspace_id": TEST_WORKSPACE_ID,
            "tags": json.dumps(["verification", "canonical"]),
            "tag_ids": json.dumps([]),
            "start_date": start_date,
            "start_year": start_year,
            "start_month": start_month,
            "start_day": start_day,
            "start_week": start_week,
            "duration_hours": duration / 3600.0,
        },
    )

    cur.execute(
        """
        UPDATE public.time_entries
        SET canonical_key = md5(
            concat_ws(
                '|',
                COALESCE(
                    to_char(
                        date_trunc('second', (NULLIF(start, '')::timestamptz AT TIME ZONE 'UTC')),
                        'YYYY-MM-DD"T"HH24:MI:SS"Z"'
                    ),
                    COALESCE(start, '')
                ),
                COALESCE(
                    to_char(
                        date_trunc('second', (NULLIF(stop, '')::timestamptz AT TIME ZONE 'UTC')),
                        'YYYY-MM-DD"T"HH24:MI:SS"Z"'
                    ),
                    COALESCE(stop, '')
                ),
                COALESCE(duration::TEXT, '0'),
                COALESCE(description, ''),
                COALESCE(project_name, '')
            )
        )
        WHERE id = %s AND canonical_key IS NULL;
        """,
        (row_id,),
    )

    expected_key = build_canonical_entry_key(
        start_iso, stop_iso, description, project_name, duration
    )
    actual_key = _fetch_one_value(
        cur,
        "SELECT canonical_key FROM public.time_entries WHERE id = %s;",
        (row_id,),
    )
    _assert(
        actual_key == expected_key,
        "Canonical backfill key does not match Python normalization",
    )
    return actual_key


def _build_range_fixture_entry(
    row_id: int,
    start_iso: str,
    stop_iso: str,
    description: str,
    project_name: str,
    task_name: str,
    client_name: str,
    tags: list[str],
) -> dict[str, Any]:
    return transform_json_entry(
        {
            "id": row_id,
            "description": description,
            "start": start_iso,
            "stop": stop_iso,
            "duration": 3600,
            "project_id": row_id + 1000,
            "project_name": project_name,
            "workspace_id": TEST_WORKSPACE_ID,
            "tags": tags,
            "tag_ids": [row_id + 2000],
            "billable": False,
            "at": f"{start_iso[:10]}T12:00:00Z",
            "task_id": row_id + 3000,
            "task_name": task_name,
            "client_name": client_name,
            "user_id": 42,
        },
        workspace_id=TEST_WORKSPACE_ID,
    )


def _verify_custom_range_functions(conn: psycopg.Connection, base_id: int) -> None:
    inside_project = f"{FIXTURE_PREFIX}_project"
    inside_task = f"{FIXTURE_PREFIX}_task"
    inside_client = f"{FIXTURE_PREFIX}_client"
    inside_tag = f"{FIXTURE_PREFIX}_tag"

    entries = [
        _build_range_fixture_entry(
            base_id + 1,
            "2099-04-10T09:00:00Z",
            "2099-04-10T10:00:00Z",
            f"{FIXTURE_PREFIX}_before",
            f"{FIXTURE_PREFIX}_project_before",
            f"{FIXTURE_PREFIX}_task_before",
            f"{FIXTURE_PREFIX}_client_before",
            [f"{FIXTURE_PREFIX}_tag_before"],
        ),
        _build_range_fixture_entry(
            base_id + 2,
            "2099-04-15T09:00:00Z",
            "2099-04-15T10:00:00Z",
            f"{FIXTURE_PREFIX}_inside",
            inside_project,
            inside_task,
            inside_client,
            [inside_tag],
        ),
        _build_range_fixture_entry(
            base_id + 3,
            "2099-04-20T09:00:00Z",
            "2099-04-20T10:00:00Z",
            f"{FIXTURE_PREFIX}_after",
            f"{FIXTURE_PREFIX}_project_after",
            f"{FIXTURE_PREFIX}_task_after",
            f"{FIXTURE_PREFIX}_client_after",
            [f"{FIXTURE_PREFIX}_tag_after"],
        ),
    ]

    upsert_time_entries_pg(conn, entries)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT * FROM public.get_overview_metrics(%s, %s, %s, %s);",
            ("custom_range", None, TEST_RANGE_START, TEST_RANGE_END),
        )
        overview = cur.fetchone()
        if overview is None:
            raise AssertionError("get_overview_metrics returned no row")
        total_hours, total_entries, unique_projects, active_days, avg_hours_per_day = (
            overview
        )
        _assert(
            float(total_hours) == 1.0, f"Expected 1.0 total_hours, found {total_hours}"
        )
        _assert(
            int(total_entries) == 1, f"Expected 1 total_entry, found {total_entries}"
        )
        _assert(
            int(unique_projects) == 1,
            f"Expected 1 unique_project, found {unique_projects}",
        )
        _assert(int(active_days) == 1, f"Expected 1 active_day, found {active_days}")
        _assert(
            float(avg_hours_per_day) == 1.0,
            f"Expected 1.0 avg_hours_per_day, found {avg_hours_per_day}",
        )

        cur.execute(
            "SELECT project_name, hours, entries FROM public.get_project_breakdown(%s, %s, %s, %s);",
            ("custom_range", None, TEST_RANGE_START, TEST_RANGE_END),
        )
        project_rows = cur.fetchall()
        _assert(
            any(
                row[0] == inside_project and float(row[1]) == 1.0 and int(row[2]) == 1
                for row in project_rows
            ),
            "Custom-range project breakdown did not isolate the in-range project",
        )

        cur.execute(
            "SELECT tag_name, hours, entries FROM public.get_tag_breakdown(%s, %s, %s, %s);",
            ("custom_range", None, TEST_RANGE_START, TEST_RANGE_END),
        )
        tag_rows = cur.fetchall()
        _assert(
            any(
                row[0] == inside_tag and float(row[1]) == 1.0 and int(row[2]) == 1
                for row in tag_rows
            ),
            "Custom-range tag breakdown did not isolate the in-range tag",
        )

        cur.execute(
            "SELECT client_name, hours, entries FROM public.get_client_breakdown(%s, %s, %s, %s);",
            ("custom_range", None, TEST_RANGE_START, TEST_RANGE_END),
        )
        client_rows = cur.fetchall()
        _assert(
            any(
                row[0] == inside_client and float(row[1]) == 1.0 and int(row[2]) == 1
                for row in client_rows
            ),
            "Custom-range client breakdown did not isolate the in-range client",
        )

        cur.execute(
            "SELECT task_name, hours, entries FROM public.get_task_breakdown(%s, %s, %s, %s);",
            ("custom_range", None, TEST_RANGE_START, TEST_RANGE_END),
        )
        task_rows = cur.fetchall()
        _assert(
            any(
                row[0] == inside_task and float(row[1]) == 1.0 and int(row[2]) == 1
                for row in task_rows
            ),
            "Custom-range task breakdown did not isolate the in-range task",
        )


def main() -> int:
    base_id = 990000000000
    with get_pg_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.time_entries WHERE id BETWEEN %s AND %s;",
                    (base_id, base_id + 10),
                )
                _verify_canonical_key_schema(cur)
                _verify_rpc_signatures(cur)
                canonical_key = _verify_backfill_expression(cur, base_id)
            conn.commit()

            _verify_custom_range_functions(conn, base_id)

            print("Supabase database state verification passed")
            print(f"canonical_key_backfill={canonical_key}")
            print(f"custom_range={TEST_RANGE_START}..{TEST_RANGE_END}")
            return 0
        finally:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM public.time_entries WHERE id BETWEEN %s AND %s;",
                    (base_id, base_id + 10),
                )
            conn.commit()


if __name__ == "__main__":
    raise SystemExit(main())
