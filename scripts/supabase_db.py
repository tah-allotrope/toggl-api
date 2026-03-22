import json
from typing import Any, List
import psycopg


def _resolve_existing_time_entry_id(
    cur: psycopg.Cursor, entry: dict[str, Any]
) -> int | None:
    """Return existing row id to update when enriched data matches a legacy CSV row."""
    toggl_id = entry.get("toggl_id")
    if toggl_id is None:
        return None

    cur.execute(
        "SELECT id FROM public.time_entries WHERE toggl_id = %(toggl_id)s LIMIT 1;",
        {"toggl_id": toggl_id},
    )
    existing = cur.fetchone()
    if existing:
        return int(existing[0])

    canonical_key = entry.get("canonical_key")
    if canonical_key:
        cur.execute(
            """
            SELECT id
            FROM public.time_entries
            WHERE canonical_key = %(canonical_key)s
            ORDER BY CASE WHEN toggl_id IS NULL THEN 0 ELSE 1 END, id
            LIMIT 1;
            """,
            {"canonical_key": canonical_key},
        )
        canonical_match = cur.fetchone()
        if canonical_match:
            return int(canonical_match[0])

    cur.execute(
        """
        SELECT id
        FROM public.time_entries
        WHERE toggl_id IS NULL
          AND start = %(start)s
          AND stop IS NOT DISTINCT FROM %(stop)s
          AND duration = %(duration)s
          AND COALESCE(description, '') = COALESCE(%(description)s, '')
          AND COALESCE(project_name, '') = COALESCE(%(project_name)s, '')
        ORDER BY id
        LIMIT 1;
        """,
        {
            "start": entry.get("start"),
            "stop": entry.get("stop"),
            "duration": entry.get("duration"),
            "description": entry.get("description"),
            "project_name": entry.get("project_name"),
        },
    )
    legacy_match = cur.fetchone()
    if legacy_match:
        return int(legacy_match[0])

    return None


def upsert_time_entries_pg(
    conn: psycopg.Connection, entries: List[dict[str, Any]]
) -> int:
    """Return count of time-entry rows upserted into Postgres."""
    if not entries:
        return 0

    query = """
        INSERT INTO public.time_entries (
            id, description, start, stop, duration, project_id, project_name,
            workspace_id, tags, tag_ids, billable, at,
            start_date, start_year, start_month, start_day, start_week, duration_hours, canonical_key,
            toggl_id, task_id, task_name, client_name, user_id
        ) VALUES (
            %(id)s, %(description)s, %(start)s, %(stop)s, %(duration)s, %(project_id)s, %(project_name)s,
            %(workspace_id)s, %(tags)s, %(tag_ids)s, %(billable)s, %(at)s,
            %(start_date)s, %(start_year)s, %(start_month)s, %(start_day)s, %(start_week)s, %(duration_hours)s, %(canonical_key)s,
            %(toggl_id)s, %(task_id)s, %(task_name)s, %(client_name)s, %(user_id)s
        )
        ON CONFLICT (id) DO UPDATE SET
            description = EXCLUDED.description,
            start = EXCLUDED.start,
            stop = EXCLUDED.stop,
            duration = EXCLUDED.duration,
            project_id = EXCLUDED.project_id,
            project_name = EXCLUDED.project_name,
            workspace_id = EXCLUDED.workspace_id,
            tags = EXCLUDED.tags,
            tag_ids = EXCLUDED.tag_ids,
            billable = EXCLUDED.billable,
            at = EXCLUDED.at,
            start_date = EXCLUDED.start_date,
            start_year = EXCLUDED.start_year,
            start_month = EXCLUDED.start_month,
            start_day = EXCLUDED.start_day,
            start_week = EXCLUDED.start_week,
            duration_hours = EXCLUDED.duration_hours,
            canonical_key = EXCLUDED.canonical_key,
            toggl_id = EXCLUDED.toggl_id,
            task_id = EXCLUDED.task_id,
            task_name = EXCLUDED.task_name,
            client_name = EXCLUDED.client_name,
            user_id = EXCLUDED.user_id;
    """

    with conn.cursor() as cur:
        for entry in entries:
            # Ensure JSON serialization for JSONB columns
            params = dict(entry)
            params["tags"] = json.dumps(params.get("tags", []))
            params["tag_ids"] = json.dumps(params.get("tag_ids", []))
            existing_id = _resolve_existing_time_entry_id(cur, params)
            if existing_id is not None:
                params["id"] = existing_id
            cur.execute(query, params)

    conn.commit()
    return len(entries)


def upsert_projects_pg(conn: psycopg.Connection, projects: List[dict[str, Any]]) -> int:
    """Return count of project rows upserted into Postgres."""
    if not projects:
        return 0

    query = """
        INSERT INTO public.projects (
            id, name, workspace_id, color, active, at,
            client_id, billable, rate, currency, fixed_fee,
            estimated_hours, estimated_seconds, auto_estimates,
            recurring, recurring_parameters, template
        ) VALUES (
            %(id)s, %(name)s, %(workspace_id)s, %(color)s, %(active)s, %(at)s,
            %(client_id)s, %(billable)s, %(rate)s, %(currency)s, %(fixed_fee)s,
            %(estimated_hours)s, %(estimated_seconds)s, %(auto_estimates)s,
            %(recurring)s, %(recurring_parameters)s, %(template)s
        )
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            workspace_id = EXCLUDED.workspace_id,
            color = EXCLUDED.color,
            active = EXCLUDED.active,
            at = EXCLUDED.at,
            client_id = EXCLUDED.client_id,
            billable = EXCLUDED.billable,
            rate = EXCLUDED.rate,
            currency = EXCLUDED.currency,
            fixed_fee = EXCLUDED.fixed_fee,
            estimated_hours = EXCLUDED.estimated_hours,
            estimated_seconds = EXCLUDED.estimated_seconds,
            auto_estimates = EXCLUDED.auto_estimates,
            recurring = EXCLUDED.recurring,
            recurring_parameters = EXCLUDED.recurring_parameters,
            template = EXCLUDED.template;
    """

    with conn.cursor() as cur:
        for p in projects:
            params = dict(p)
            params["recurring_parameters"] = (
                json.dumps(params.get("recurring_parameters"))
                if params.get("recurring_parameters") is not None
                else None
            )
            cur.execute(query, params)

    conn.commit()
    return len(projects)


def upsert_tags_pg(conn: psycopg.Connection, tags: List[dict[str, Any]]) -> int:
    """Return count of tag rows upserted into Postgres."""
    if not tags:
        return 0

    query = """
        INSERT INTO public.tags (id, name, workspace_id, creator_id, at, deleted_at)
        VALUES (%(id)s, %(name)s, %(workspace_id)s, %(creator_id)s, %(at)s, %(deleted_at)s)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            workspace_id = EXCLUDED.workspace_id,
            creator_id = EXCLUDED.creator_id,
            at = EXCLUDED.at,
            deleted_at = EXCLUDED.deleted_at;
    """

    with conn.cursor() as cur:
        for t in tags:
            cur.execute(query, t)

    conn.commit()
    return len(tags)


def upsert_clients_pg(conn: psycopg.Connection, clients: List[dict[str, Any]]) -> int:
    """Return count of client rows upserted into Postgres."""
    if not clients:
        return 0

    query = """
        INSERT INTO public.clients (id, name, workspace_id, archived, at)
        VALUES (%(id)s, %(name)s, %(workspace_id)s, %(archived)s, %(at)s)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            workspace_id = EXCLUDED.workspace_id,
            archived = EXCLUDED.archived,
            at = EXCLUDED.at;
    """

    with conn.cursor() as cur:
        for c in clients:
            cur.execute(query, c)

    conn.commit()
    return len(clients)


def upsert_tasks_pg(conn: psycopg.Connection, tasks: List[dict[str, Any]]) -> int:
    """Return count of task rows upserted into Postgres."""
    if not tasks:
        return 0

    query = """
        INSERT INTO public.tasks (id, name, project_id, workspace_id, active, estimated_seconds, tracked_seconds, at)
        VALUES (%(id)s, %(name)s, %(project_id)s, %(workspace_id)s, %(active)s, %(estimated_seconds)s, %(tracked_seconds)s, %(at)s)
        ON CONFLICT (id) DO UPDATE SET
            name = EXCLUDED.name,
            project_id = EXCLUDED.project_id,
            workspace_id = EXCLUDED.workspace_id,
            active = EXCLUDED.active,
            estimated_seconds = EXCLUDED.estimated_seconds,
            tracked_seconds = EXCLUDED.tracked_seconds,
            at = EXCLUDED.at;
    """

    with conn.cursor() as cur:
        for t in tasks:
            cur.execute(query, t)

    conn.commit()
    return len(tasks)
