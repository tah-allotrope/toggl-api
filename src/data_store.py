"""
SQLite-backed local data store for Toggl time entries, projects, and tags.

All dashboard and retrospect queries run against this local database,
so the Toggl API is only called during sync operations.
"""

import sqlite3
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "toggl.db"


def get_connection() -> sqlite3.Connection:
    """Get a SQLite connection, creating the database and tables if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrent read performance
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection):
    """Create tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS time_entries (
            id              INTEGER PRIMARY KEY,
            description     TEXT,
            start           TEXT NOT NULL,
            stop            TEXT,
            duration        INTEGER NOT NULL,
            project_id      INTEGER,
            project_name    TEXT,
            workspace_id    INTEGER,
            tags            TEXT,           -- JSON array of tag names
            tag_ids         TEXT,           -- JSON array of tag IDs
            billable        INTEGER DEFAULT 0,
            at              TEXT,           -- last updated timestamp
            -- Derived columns for fast querying
            start_date      TEXT,           -- YYYY-MM-DD extracted from start
            start_year      INTEGER,
            start_month     INTEGER,
            start_day       INTEGER,
            start_week      INTEGER,        -- ISO week number
            duration_hours  REAL            -- duration in hours
        );

        CREATE TABLE IF NOT EXISTS projects (
            id              INTEGER PRIMARY KEY,
            name            TEXT NOT NULL,
            workspace_id    INTEGER,
            color           TEXT,
            active          INTEGER DEFAULT 1,
            at              TEXT
        );

        CREATE TABLE IF NOT EXISTS tags (
            id              INTEGER PRIMARY KEY,
            name            TEXT NOT NULL,
            workspace_id    INTEGER
        );

        CREATE TABLE IF NOT EXISTS sync_meta (
            key             TEXT PRIMARY KEY,
            value           TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_entries_start_date ON time_entries(start_date);
        CREATE INDEX IF NOT EXISTS idx_entries_year ON time_entries(start_year);
        CREATE INDEX IF NOT EXISTS idx_entries_month_day ON time_entries(start_month, start_day);
        CREATE INDEX IF NOT EXISTS idx_entries_project ON time_entries(project_id);
        CREATE INDEX IF NOT EXISTS idx_entries_week ON time_entries(start_year, start_week);
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Insert / Upsert
# ---------------------------------------------------------------------------

def upsert_time_entries(conn: sqlite3.Connection, entries: list[dict]):
    """Insert or replace time entries. Computes derived date columns automatically."""
    rows = []
    for e in entries:
        start_str = e.get("start", "")
        try:
            dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            start_date = dt.strftime("%Y-%m-%d")
            start_year = dt.year
            start_month = dt.month
            start_day = dt.day
            start_week = dt.isocalendar()[1]
        except (ValueError, AttributeError):
            start_date = start_str[:10] if len(start_str) >= 10 else None
            start_year = int(start_str[:4]) if len(start_str) >= 4 else None
            start_month = int(start_str[5:7]) if len(start_str) >= 7 else None
            start_day = int(start_str[8:10]) if len(start_str) >= 10 else None
            start_week = None

        duration_sec = e.get("duration", 0)
        # Running entries have negative duration; skip those for stored data
        duration_hours = max(duration_sec, 0) / 3600.0

        tags = e.get("tags") or []
        tag_ids = e.get("tag_ids") or []

        rows.append((
            e.get("id"),
            e.get("description"),
            start_str,
            e.get("stop"),
            duration_sec,
            e.get("project_id"),
            e.get("project_name", ""),
            e.get("workspace_id") or e.get("wid"),
            json.dumps(tags),
            json.dumps(tag_ids),
            1 if e.get("billable") else 0,
            e.get("at", ""),
            start_date,
            start_year,
            start_month,
            start_day,
            start_week,
            duration_hours,
        ))

    conn.executemany("""
        INSERT OR REPLACE INTO time_entries
            (id, description, start, stop, duration, project_id, project_name,
             workspace_id, tags, tag_ids, billable, at,
             start_date, start_year, start_month, start_day, start_week, duration_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


def upsert_projects(conn: sqlite3.Connection, projects: list[dict]):
    """Insert or replace projects."""
    rows = [
        (p["id"], p.get("name", ""), p.get("workspace_id") or p.get("wid"),
         p.get("color", ""), 1 if p.get("active", True) else 0, p.get("at", ""))
        for p in projects
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO projects (id, name, workspace_id, color, active, at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


def upsert_tags(conn: sqlite3.Connection, tags: list[dict]):
    """Insert or replace tags."""
    rows = [(t["id"], t.get("name", ""), t.get("workspace_id") or t.get("wid")) for t in tags]
    conn.executemany("""
        INSERT OR REPLACE INTO tags (id, name, workspace_id)
        VALUES (?, ?, ?)
    """, rows)
    conn.commit()


# ---------------------------------------------------------------------------
# Sync metadata
# ---------------------------------------------------------------------------

def set_sync_meta(conn: sqlite3.Connection, key: str, value: str):
    conn.execute("INSERT OR REPLACE INTO sync_meta (key, value) VALUES (?, ?)", (key, value))
    conn.commit()


def get_sync_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


# ---------------------------------------------------------------------------
# Query helpers -- these power the dashboard and retrospect pages
# ---------------------------------------------------------------------------

def get_entries_df(conn: sqlite3.Connection, year: int | None = None,
                   start_date: str | None = None, end_date: str | None = None) -> pd.DataFrame:
    """
    Return time entries as a Pandas DataFrame, optionally filtered.
    This is the main query method used by all UI pages.
    """
    query = "SELECT * FROM time_entries WHERE duration > 0"
    params: list = []

    if year:
        query += " AND start_year = ?"
        params.append(year)
    if start_date:
        query += " AND start_date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND start_date <= ?"
        params.append(end_date)

    query += " ORDER BY start ASC"
    df = pd.read_sql_query(query, conn, params=params)

    # Parse the JSON tags column into actual lists
    if not df.empty and "tags" in df.columns:
        df["tags_list"] = df["tags"].apply(lambda x: json.loads(x) if x else [])

    return df


def get_available_years(conn: sqlite3.Connection) -> list[int]:
    """Return sorted list of years that have data."""
    rows = conn.execute(
        "SELECT DISTINCT start_year FROM time_entries WHERE start_year IS NOT NULL ORDER BY start_year"
    ).fetchall()
    return [r["start_year"] for r in rows]


def get_projects_df(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM projects ORDER BY name", conn)


def get_tags_list(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT name FROM tags ORDER BY name").fetchall()
    return [r["name"] for r in rows]


def get_entries_for_date_across_years(conn: sqlite3.Connection, month: int, day: int) -> pd.DataFrame:
    """Get all entries that occurred on a specific month/day across all years (for retrospect)."""
    query = """
        SELECT * FROM time_entries
        WHERE start_month = ? AND start_day = ? AND duration > 0
        ORDER BY start_year ASC, start ASC
    """
    df = pd.read_sql_query(query, conn, params=[month, day])
    if not df.empty and "tags" in df.columns:
        df["tags_list"] = df["tags"].apply(lambda x: json.loads(x) if x else [])
    return df


def get_entries_for_week_across_years(conn: sqlite3.Connection, week: int) -> pd.DataFrame:
    """Get all entries for a specific ISO week number across all years."""
    query = """
        SELECT * FROM time_entries
        WHERE start_week = ? AND duration > 0
        ORDER BY start_year ASC, start ASC
    """
    df = pd.read_sql_query(query, conn, params=[week])
    if not df.empty and "tags" in df.columns:
        df["tags_list"] = df["tags"].apply(lambda x: json.loads(x) if x else [])
    return df


def get_total_stats(conn: sqlite3.Connection) -> dict:
    """Quick aggregate stats across all data."""
    row = conn.execute("""
        SELECT
            COUNT(*) as total_entries,
            SUM(duration_hours) as total_hours,
            MIN(start_date) as earliest_date,
            MAX(start_date) as latest_date,
            COUNT(DISTINCT CASE WHEN project_name != '' THEN project_name END) as unique_projects,
            COUNT(DISTINCT start_year) as years_tracked
        FROM time_entries
        WHERE duration > 0
    """).fetchone()
    return dict(row)


def search_entries(conn: sqlite3.Connection, keyword: str, limit: int = 200) -> pd.DataFrame:
    """Search entries by description, project name, or tags."""
    query = """
        SELECT * FROM time_entries
        WHERE (description LIKE ? OR project_name LIKE ? OR tags LIKE ?)
          AND duration > 0
        ORDER BY start DESC
        LIMIT ?
    """
    pattern = f"%{keyword}%"
    df = pd.read_sql_query(query, conn, params=[pattern, pattern, pattern, limit])
    if not df.empty and "tags" in df.columns:
        df["tags_list"] = df["tags"].apply(lambda x: json.loads(x) if x else [])
    return df


def get_entries_by_tag(conn: sqlite3.Connection, tag_name: str,
                       year: int | None = None) -> pd.DataFrame:
    """Get all entries containing a specific tag (case-insensitive JSON search)."""
    # Tags are stored as JSON arrays, e.g. '["Highlight", "Deep"]'.
    # We use LIKE to match the tag name inside the JSON string.
    query = "SELECT * FROM time_entries WHERE tags LIKE ? AND duration > 0"
    params: list = [f'%"{tag_name}"%']
    if year:
        query += " AND start_year = ?"
        params.append(year)
    query += " ORDER BY start DESC"
    df = pd.read_sql_query(query, conn, params=params)
    if not df.empty and "tags" in df.columns:
        df["tags_list"] = df["tags"].apply(lambda x: json.loads(x) if x else [])
    return df


def get_all_project_names(conn: sqlite3.Connection) -> list[str]:
    """Return sorted list of distinct non-empty project names from time entries."""
    rows = conn.execute(
        "SELECT DISTINCT project_name FROM time_entries "
        "WHERE project_name != '' AND project_name IS NOT NULL "
        "ORDER BY project_name"
    ).fetchall()
    return [r["project_name"] for r in rows]


def get_all_tag_names(conn: sqlite3.Connection) -> list[str]:
    """Return sorted list of distinct tag names used in time entries."""
    rows = conn.execute("SELECT DISTINCT name FROM tags ORDER BY name").fetchall()
    return [r["name"] for r in rows]
