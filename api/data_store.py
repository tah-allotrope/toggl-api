"""Postgres-backed data access helpers for sync and chat functions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def upsert_time_entries_pg(conn, entries: list[dict[str, Any]]) -> int:
    if not entries:
        return 0
    
    written = 0
    data_to_upsert = []
    
    for entry in entries:
        toggl_id = entry.get("toggl_id")
        doc_id = toggl_id if toggl_id is not None else entry.get("id")
        if doc_id is None:
            continue

        start_raw = entry.get("start")
        stop_raw = entry.get("stop")
        start_dt = _parse_iso_datetime(start_raw)
        stop_dt = _parse_iso_datetime(stop_raw)

        if start_dt:
            start_year = start_dt.year
            start_month = start_dt.month
            start_day = start_dt.day
            start_week = int(start_dt.isocalendar()[1])
            start_date = start_dt.strftime("%Y-%m-%d")
        else:
            start_year = start_month = start_day = start_week = start_date = None

        payload = {
            "id": doc_id,
            "toggl_id": toggl_id,
            "description": entry.get("description", ""),
            "start": start_raw,
            "stop": stop_raw,
            "duration": int(entry.get("duration", 0) or 0),
            "duration_hours": max(int(entry.get("duration", 0) or 0), 0) / 3600.0,
            "project_name": entry.get("project_name", "") or "",
            "project_id": entry.get("project_id"),
            "workspace_id": entry.get("workspace_id"),
            "tags": json.dumps(entry.get("tags") or []),
            "tag_ids": json.dumps(entry.get("tag_ids") or []),
            "billable": int(bool(entry.get("billable", False))),
            "at": entry.get("at") or "",
            "task_id": entry.get("task_id"),
            "task_name": entry.get("task_name") or "",
            "client_name": entry.get("client_name") or "",
            "user_id": entry.get("user_id"),
            "start_date": start_date,
            "start_year": start_year,
            "start_month": start_month,
            "start_day": start_day,
            "start_week": start_week,
        }
        data_to_upsert.append(payload)

    if not data_to_upsert:
        return 0

    cols = list(data_to_upsert[0].keys())
    col_names = ", ".join(cols)
    placeholders = ", ".join([f"%({col})s" for col in cols])
    upsert_query = f"""
        INSERT INTO time_entries ({col_names})
        VALUES %s
        ON CONFLICT (id) DO UPDATE SET
        {", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c != "id"])}
    """
    
    with conn.cursor() as cur:
        execute_values(cur, upsert_query, data_to_upsert, template=f"({placeholders})", page_size=500)
        written = len(data_to_upsert)
    conn.commit()
    return written


def upsert_projects_pg(conn, projects: list[dict[str, Any]]) -> int:
    if not projects:
        return 0
    data = []
    for p in projects:
        if p.get("id") is None: continue
        data.append({
            "id": p["id"],
            "name": p.get("name", ""),
            "workspace_id": p.get("workspace_id") or p.get("wid"),
            "color": p.get("color", ""),
            "active": int(bool(p.get("active", True))),
            "billable": int(bool(p.get("billable", False))),
            "client_id": p.get("client_id"),
            "at": p.get("at")
        })
    if not data: return 0
    cols = list(data[0].keys())
    query = f"INSERT INTO projects ({', '.join(cols)}) VALUES %s ON CONFLICT (id) DO UPDATE SET {', '.join([f'{c}=EXCLUDED.{c}' for c in cols if c!='id'])}"
    with conn.cursor() as cur:
        execute_values(cur, query, data, template=f"({', '.join([f'%({c})s' for c in cols])})")
    conn.commit()
    return len(data)


def upsert_tags_pg(conn, tags: list[dict[str, Any]]) -> int:
    if not tags: return 0
    data = [{"id": t["id"], "name": t.get("name", ""), "workspace_id": t.get("workspace_id") or t.get("wid")} for t in tags if t.get("id")]
    if not data: return 0
    cols = list(data[0].keys())
    query = f"INSERT INTO tags ({', '.join(cols)}) VALUES %s ON CONFLICT (id) DO UPDATE SET {', '.join([f'{c}=EXCLUDED.{c}' for c in cols if c!='id'])}"
    with conn.cursor() as cur:
        execute_values(cur, query, data, template=f"({', '.join([f'%({c})s' for c in cols])})")
    conn.commit()
    return len(data)


def set_sync_meta(conn, key: str, value: str) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO sync_meta (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
    conn.commit()


def get_sync_meta(conn, key: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM sync_meta WHERE key = %s", (key,))
        row = cur.fetchone()
        return row["value"] if row else None


def get_entries(conn, start_date=None, end_date=None, project=None, tag=None) -> list[dict]:
    query = "SELECT * FROM time_entries WHERE 1=1"
    params = []
    if start_date:
        query += " AND start_date >= %s"
        params.append(start_date)
    if end_date:
        query += " AND start_date <= %s"
        params.append(end_date)
    if project:
        query += " AND project_name = %s"
        params.append(project)
    if tag:
        query += " AND tags LIKE %s"
        params.append(f'%"{tag}"%')
    query += " ORDER BY start ASC"
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def get_entries_for_date_across_years(conn, month: int, day: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM time_entries WHERE start_month = %s AND start_day = %s ORDER BY start_year ASC, start ASC", (month, day))
        return cur.fetchall()


def get_entries_for_week_across_years(conn, week: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM time_entries WHERE start_week = %s ORDER BY start_year ASC, start ASC", (week,))
        return cur.fetchall()


def search_entries(conn, keyword: str) -> list[dict]:
    needle = f"%{keyword.lower()}%"
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM time_entries WHERE LOWER(description) LIKE %s OR LOWER(project_name) LIKE %s OR LOWER(client_name) LIKE %s OR LOWER(tags) LIKE %s ORDER BY start DESC", (needle, needle, needle, needle))
        return cur.fetchall()


def get_total_stats(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) as total_entries, SUM(duration_hours) as total_hours, MIN(start_date) as earliest_date, MAX(start_date) as latest_date, COUNT(DISTINCT project_name) as unique_projects, COUNT(DISTINCT start_year) as years_tracked FROM time_entries WHERE duration_hours > 0")
        return dict(cur.fetchone())


def get_stats(conn) -> dict:
    return get_total_stats(conn)


def get_sync_status(conn) -> dict:
    return {
        "last_csv_sync": get_sync_meta(conn, "last_csv_sync"),
        "last_enriched_sync": get_sync_meta(conn, "last_enriched_sync"),
        "enrichment_earliest_year": get_sync_meta(conn, "enrichment_earliest_year")
    }


def get_all_project_names(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT project_name FROM time_entries WHERE project_name IS NOT NULL AND project_name != '' ORDER BY project_name")
        return [row["project_name"] for row in cur.fetchall()]


def get_all_tag_names(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT name FROM tags ORDER BY name")
        return [row["name"] for row in cur.fetchall()]


def get_all_client_names(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT client_name FROM time_entries WHERE client_name IS NOT NULL AND client_name != '' ORDER BY client_name")
        return [row["client_name"] for row in cur.fetchall()]
