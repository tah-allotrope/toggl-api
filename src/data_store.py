"""
SQLite-backed local data store for Toggl time entries, projects, tags, tasks, and clients.

All dashboard and retrospect queries run against this local database,
so the Toggl API is only called during sync operations.

Schema versioning is handled via _apply_migrations(), which runs ALTER TABLE
statements idempotently so existing databases are upgraded in-place without
data loss on first run after this change.
"""

import sqlite3
import json
import os
from contextlib import contextmanager
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
    conn.execute("PRAGMA journal_mode=WAL")
    _create_tables(conn)
    _apply_migrations(conn)
    return conn


@contextmanager
def managed_connection():
    """Context manager that auto-closes the connection on exit."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def _create_tables(conn: sqlite3.Connection):
    """
    Create all tables if they don't exist.
    Includes both the original schema and all enrichment columns added during
    the data enrichment phase.
    """
    conn.executescript("""
        -- Core time entries table. The 'id' column stores the synthetic
        -- SHA-256 ID for entries from CSV sync, or the native Toggl integer
        -- ID for entries from the JSON enrichment sync. toggl_id is always
        -- the native Toggl integer once populated by the enrichment sync.
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
            duration_hours  REAL,           -- duration in hours
            -- Enrichment columns (populated by JSON sync, NULL from CSV sync)
            toggl_id        INTEGER UNIQUE, -- native Toggl entry ID (NULL until enriched)
            task_id         INTEGER,        -- Premium: task assignment
            task_name       TEXT,           -- Premium: denormalized task name
            client_name     TEXT,           -- denormalized client name via project
            user_id         INTEGER         -- Toggl user who created the entry
        );

        CREATE TABLE IF NOT EXISTS projects (
            id              INTEGER PRIMARY KEY,
            name            TEXT NOT NULL,
            workspace_id    INTEGER,
            color           TEXT,
            active          INTEGER DEFAULT 1,
            at              TEXT,
            -- Enrichment columns (Premium fields, NULL on Free plan)
            client_id       INTEGER,        -- FK to clients table
            billable        INTEGER,        -- Premium: project-level billable flag
            rate            REAL,           -- Premium: hourly rate
            currency        TEXT,           -- Premium: currency code (e.g. "USD")
            fixed_fee       REAL,           -- Premium: fixed project fee
            estimated_hours REAL,           -- Premium: time estimate in hours
            estimated_seconds INTEGER,      -- Premium: estimate in seconds (higher precision)
            auto_estimates  INTEGER,        -- Premium: auto-estimate from task estimates
            recurring       INTEGER,        -- Premium: is a recurring project
            recurring_parameters TEXT,      -- Premium: JSON blob of recurrence config
            template        INTEGER         -- Premium: is a project template
        );

        CREATE TABLE IF NOT EXISTS tags (
            id              INTEGER PRIMARY KEY,
            name            TEXT NOT NULL,
            workspace_id    INTEGER,
            -- Enrichment columns (from API v9 richer tag response)
            creator_id      INTEGER,        -- user who created the tag
            at              TEXT,           -- last modified timestamp
            deleted_at      TEXT            -- soft-delete timestamp (NULL = active)
        );

        -- New table: clients (populated by enrichment sync)
        CREATE TABLE IF NOT EXISTS clients (
            id              INTEGER PRIMARY KEY,
            name            TEXT NOT NULL,
            workspace_id    INTEGER,
            archived        INTEGER DEFAULT 0,
            at              TEXT
        );

        -- New table: tasks (Premium feature; populated by enrichment sync)
        CREATE TABLE IF NOT EXISTS tasks (
            id                  INTEGER PRIMARY KEY,
            name                TEXT NOT NULL,
            project_id          INTEGER,
            workspace_id        INTEGER,
            active              INTEGER DEFAULT 1,
            estimated_seconds   INTEGER,
            tracked_seconds     INTEGER,
            at                  TEXT
        );

        CREATE TABLE IF NOT EXISTS sync_meta (
            key             TEXT PRIMARY KEY,
            value           TEXT
        );

        -- Original indexes
        CREATE INDEX IF NOT EXISTS idx_entries_start_date ON time_entries(start_date);
        CREATE INDEX IF NOT EXISTS idx_entries_year ON time_entries(start_year);
        CREATE INDEX IF NOT EXISTS idx_entries_month_day ON time_entries(start_month, start_day);
        CREATE INDEX IF NOT EXISTS idx_entries_project ON time_entries(project_id);
        CREATE INDEX IF NOT EXISTS idx_entries_week ON time_entries(start_year, start_week);
    """)
    conn.commit()


def _apply_migrations(conn: sqlite3.Connection):
    """
    Idempotently add enrichment columns to pre-existing databases.

    This handles the case where the database was created before this version
    of the code. Each ALTER TABLE is wrapped in a try/except so re-running is
    safe — SQLite raises OperationalError if the column already exists.

    New databases created via _create_tables() above already have all columns,
    so these are no-ops for them.
    """
    migrations = [
        # time_entries enrichment columns
        "ALTER TABLE time_entries ADD COLUMN toggl_id INTEGER",
        "ALTER TABLE time_entries ADD COLUMN task_id INTEGER",
        "ALTER TABLE time_entries ADD COLUMN task_name TEXT",
        "ALTER TABLE time_entries ADD COLUMN client_name TEXT",
        "ALTER TABLE time_entries ADD COLUMN user_id INTEGER",
        # projects enrichment columns
        "ALTER TABLE projects ADD COLUMN client_id INTEGER",
        "ALTER TABLE projects ADD COLUMN billable INTEGER",
        "ALTER TABLE projects ADD COLUMN rate REAL",
        "ALTER TABLE projects ADD COLUMN currency TEXT",
        "ALTER TABLE projects ADD COLUMN fixed_fee REAL",
        "ALTER TABLE projects ADD COLUMN estimated_hours REAL",
        "ALTER TABLE projects ADD COLUMN estimated_seconds INTEGER",
        "ALTER TABLE projects ADD COLUMN auto_estimates INTEGER",
        "ALTER TABLE projects ADD COLUMN recurring INTEGER",
        "ALTER TABLE projects ADD COLUMN recurring_parameters TEXT",
        "ALTER TABLE projects ADD COLUMN template INTEGER",
        # tags enrichment columns
        "ALTER TABLE tags ADD COLUMN creator_id INTEGER",
        "ALTER TABLE tags ADD COLUMN at TEXT",
        "ALTER TABLE tags ADD COLUMN deleted_at TEXT",
        # unique index on toggl_id — must be created separately (not IF NOT EXISTS on UNIQUE)
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_toggl_id_unique ON time_entries(toggl_id) WHERE toggl_id IS NOT NULL",
        # Additional indexes for enrichment columns (safe to create after ALTER TABLE)
        "CREATE INDEX IF NOT EXISTS idx_entries_task ON time_entries(task_id)",
        "CREATE INDEX IF NOT EXISTS idx_entries_client_name ON time_entries(client_name)",
        "CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)",
        "CREATE INDEX IF NOT EXISTS idx_projects_client ON projects(client_id)",
    ]

    for stmt in migrations:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            # Column already exists or index already exists — safe to ignore
            pass

    conn.commit()


# ---------------------------------------------------------------------------
# Insert / Upsert
# ---------------------------------------------------------------------------

def upsert_time_entries(conn: sqlite3.Connection, entries: list[dict]):
    """
    Insert or replace time entries. Computes derived date columns automatically.
    Handles both CSV-sourced entries (synthetic id, toggl_id=None) and
    JSON-sourced entries (id = toggl_id = native Toggl integer).

    Deduplication guard: CSV-sourced entries (toggl_id=None) are checked against
    existing enriched rows before insertion. If an enriched row already exists with
    the same (start[:19], duration, description) the CSV entry is skipped — this
    prevents re-duplication when sync_current_year() runs after an enrichment sync.
    Enriched entries (toggl_id IS NOT NULL) always go through INSERT OR REPLACE and
    will update any stale CSV row that snuck in via the synthetic id collision path.
    """
    # Build a lookup of enriched entries already in the DB so CSV entries can be
    # skipped when they duplicate an enriched row. We only need start[:19] + duration
    # + description — the same triple used during the deduplication cleanup.
    csv_entries = [e for e in entries if not e.get("toggl_id")]
    enriched_entries = [e for e in entries if e.get("toggl_id")]

    existing_enriched_keys: set[tuple] = set()
    if csv_entries:
        # Load just the three columns needed for matching — fast indexed scan.
        rows_db = conn.execute(
            "SELECT substr(start,1,19) as s19, duration, description "
            "FROM time_entries WHERE toggl_id IS NOT NULL AND duration > 0"
        ).fetchall()
        existing_enriched_keys = {(r[0], r[1], r[2]) for r in rows_db}

    # Filter out CSV entries that already have an enriched counterpart.
    filtered_csv: list[dict] = []
    for e in csv_entries:
        start_str = e.get("start", "")
        key = (start_str[:19], e.get("duration", 0), e.get("description"))
        if key not in existing_enriched_keys:
            filtered_csv.append(e)

    entries_to_write = enriched_entries + filtered_csv

    rows = []
    for e in entries_to_write:
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
            e.get("toggl_id"),
            e.get("task_id"),
            e.get("task_name", "") or "",
            e.get("client_name", "") or "",
            e.get("user_id"),
        ))

    conn.executemany("""
        INSERT OR REPLACE INTO time_entries
            (id, description, start, stop, duration, project_id, project_name,
             workspace_id, tags, tag_ids, billable, at,
             start_date, start_year, start_month, start_day, start_week, duration_hours,
             toggl_id, task_id, task_name, client_name, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


def upsert_projects(conn: sqlite3.Connection, projects: list[dict]):
    """
    Insert or replace projects. Captures Premium fields (rate, fixed_fee, etc.)
    when present; they remain NULL in the DB if the API returns nothing for them.
    """
    rows = []
    for p in projects:
        recurring_params = p.get("recurring_parameters")
        recurring_params_json = (
            json.dumps(recurring_params) if recurring_params is not None else None
        )
        rows.append((
            p["id"],
            p.get("name", ""),
            p.get("workspace_id") or p.get("wid"),
            p.get("color", ""),
            1 if p.get("active", True) else 0,
            p.get("at", ""),
            # Enrichment fields
            p.get("client_id"),
            1 if p.get("billable") else None,
            p.get("rate"),
            p.get("currency"),
            p.get("fixed_fee"),
            p.get("estimated_hours"),
            p.get("estimated_seconds"),
            1 if p.get("auto_estimates") else None,
            1 if p.get("recurring") else None,
            recurring_params_json,
            1 if p.get("template") else None,
        ))

    conn.executemany("""
        INSERT OR REPLACE INTO projects
            (id, name, workspace_id, color, active, at,
             client_id, billable, rate, currency, fixed_fee,
             estimated_hours, estimated_seconds, auto_estimates,
             recurring, recurring_parameters, template)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


def upsert_tags(conn: sqlite3.Connection, tags: list[dict]):
    """
    Insert or replace tags. Captures enrichment fields (creator_id, at,
    deleted_at) when present from the API v9 response.
    """
    rows = [
        (
            t["id"],
            t.get("name", ""),
            t.get("workspace_id") or t.get("wid"),
            t.get("creator_id"),
            t.get("at"),
            t.get("deleted_at"),
        )
        for t in tags
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO tags (id, name, workspace_id, creator_id, at, deleted_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


def upsert_clients(conn: sqlite3.Connection, clients: list[dict]):
    """Insert or replace clients."""
    rows = [
        (
            c["id"],
            c.get("name", ""),
            c.get("workspace_id") or c.get("wid"),
            1 if c.get("archived") else 0,
            c.get("at", ""),
        )
        for c in clients
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO clients (id, name, workspace_id, archived, at)
        VALUES (?, ?, ?, ?, ?)
    """, rows)
    conn.commit()


def upsert_tasks(conn: sqlite3.Connection, tasks: list[dict]):
    """Insert or replace tasks (Premium feature)."""
    rows = [
        (
            t["id"],
            t.get("name", ""),
            t.get("project_id"),
            t.get("workspace_id") or t.get("wid"),
            1 if t.get("active", True) else 0,
            t.get("estimated_seconds"),
            t.get("tracked_seconds"),
            t.get("at", ""),
        )
        for t in tasks
    ]
    conn.executemany("""
        INSERT OR REPLACE INTO tasks
            (id, name, project_id, workspace_id, active, estimated_seconds, tracked_seconds, at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
# Query helpers — these power the dashboard and retrospect pages
# ---------------------------------------------------------------------------

def get_entries_df(conn: sqlite3.Connection, year: int | None = None,
                   start_date: str | None = None, end_date: str | None = None,
                   columns: list[str] | None = None) -> pd.DataFrame:
    """
    Return time entries as a Pandas DataFrame, optionally filtered.
    This is the main query method used by all UI pages.
    Pass `columns` to select specific columns instead of `*`.
    """
    col_expr = ", ".join(columns) if columns else "*"
    query = f"SELECT {col_expr} FROM time_entries WHERE duration > 0"
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


def get_clients_df(conn: sqlite3.Connection) -> pd.DataFrame:
    """Return all clients as a DataFrame."""
    return pd.read_sql_query("SELECT * FROM clients ORDER BY name", conn)


def get_tasks_df(conn: sqlite3.Connection, project_id: int | None = None) -> pd.DataFrame:
    """Return tasks, optionally filtered by project."""
    if project_id:
        return pd.read_sql_query(
            "SELECT * FROM tasks WHERE project_id = ? ORDER BY name",
            conn, params=[project_id],
        )
    return pd.read_sql_query("SELECT * FROM tasks ORDER BY name", conn)


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


def get_enrichment_stats(conn: sqlite3.Connection) -> dict:
    """
    Return statistics about enrichment coverage — how many entries have
    native Toggl IDs, tag_ids populated, project_ids, etc.
    Useful for showing enrichment progress in the UI.
    """
    row = conn.execute("""
        SELECT
            COUNT(*) as total_entries,
            COUNT(toggl_id) as enriched_entries,
            COUNT(CASE WHEN project_id IS NOT NULL THEN 1 END) as entries_with_project_id,
            COUNT(CASE WHEN tag_ids != '[]' AND tag_ids IS NOT NULL THEN 1 END) as entries_with_tag_ids,
            COUNT(CASE WHEN task_id IS NOT NULL THEN 1 END) as entries_with_tasks,
            COUNT(CASE WHEN at != '' AND at IS NOT NULL THEN 1 END) as entries_with_at
        FROM time_entries
        WHERE duration > 0
    """).fetchone()

    tasks_count = conn.execute("SELECT COUNT(*) as n FROM tasks").fetchone()
    clients_count = conn.execute("SELECT COUNT(*) as n FROM clients").fetchone()

    result = dict(row)
    result["total_tasks"] = tasks_count["n"]
    result["total_clients"] = clients_count["n"]
    return result


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
    """
    Get all entries containing a specific tag.
    Primary: JSON name search on the tags column.
    Fallback: look up the tag's integer ID and search tag_ids for entries
    that the name search would miss (e.g. renamed tags).
    """
    # Resolve tag ID for fallback search
    tag_row = conn.execute(
        "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (tag_name,)
    ).fetchone()
    tag_id_pattern = ""
    if tag_row:
        tag_id_pattern = f"%{tag_row['id']}%"

    if tag_id_pattern:
        query = (
            "SELECT * FROM time_entries "
            "WHERE (tags LIKE ? OR tag_ids LIKE ?) AND duration > 0"
        )
        params: list = [f'%"{tag_name}"%', tag_id_pattern]
    else:
        query = "SELECT * FROM time_entries WHERE tags LIKE ? AND duration > 0"
        params = [f'%"{tag_name}"%']

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


def get_all_client_names(conn: sqlite3.Connection) -> list[str]:
    """Return sorted list of distinct non-empty client names from time entries."""
    rows = conn.execute(
        "SELECT DISTINCT client_name FROM time_entries "
        "WHERE client_name != '' AND client_name IS NOT NULL "
        "ORDER BY client_name"
    ).fetchall()
    return [r["client_name"] for r in rows]
