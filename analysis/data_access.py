"""
Data access layer for the analysis module.

Reads directly from data/toggl.db using only stdlib + pandas.
Zero coupling to src/ or Streamlit — works in any Python environment.

All public functions return DataFrames or Series ready for analysis.
The DB path is resolved relative to the repo root (two levels up from this file).
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional

import pandas as pd

# ---------------------------------------------------------------------------
# DB path resolution — works regardless of CWD when running python -m analysis
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
DB_PATH = _REPO_ROOT / "data" / "toggl.db"

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _get_connection() -> sqlite3.Connection:
    """Open a read-only connection to the SQLite database."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. "
            "Run the Streamlit app and sync data first."
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_tags(val: Optional[str]) -> list[str]:
    """Parse a JSON tag array string into a Python list."""
    if not val:
        return []
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Core entry loader
# ---------------------------------------------------------------------------

def load_entries(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load all time entries from the database with derived columns.

    Parameters
    ----------
    start_date : YYYY-MM-DD string, optional
    end_date   : YYYY-MM-DD string, optional

    Returns
    -------
    DataFrame with columns:
        id, description, start, stop, duration, project_id, project_name,
        workspace_id, tags, tag_ids, billable, at, start_date, start_year,
        start_month, start_day, start_week, duration_hours, toggl_id,
        task_id, task_name, client_name, user_id,
        tags_list       -- parsed Python list of tag name strings
        start_dt        -- parsed datetime (UTC)
        hour_of_day     -- 0-23 int
        day_of_week     -- 0=Monday … 6=Sunday int
        day_name        -- "Monday" … "Sunday"
        is_weekend      -- bool
        quarter         -- "2024Q1" string
        year_month      -- "2024-03" string
    """
    conn = _get_connection()
    try:
        conditions = ["duration > 0"]
        params: list = []
        if start_date:
            conditions.append("start_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("start_date <= ?")
            params.append(end_date)

        where = " AND ".join(conditions)
        query = f"SELECT * FROM time_entries WHERE {where} ORDER BY start"
        df = pd.read_sql_query(query, conn, params=params)
    finally:
        conn.close()

    if df.empty:
        return df

    # Parsed tag list
    df["tags_list"] = df["tags"].apply(_parse_tags)

    # Datetime parsing (Toggl stores ISO 8601 with Z suffix)
    df["start_dt"] = pd.to_datetime(df["start"], utc=True, errors="coerce")

    # Time-of-day / day-of-week derived columns
    df["hour_of_day"] = df["start_dt"].dt.hour
    df["day_of_week"] = df["start_dt"].dt.dayofweek  # 0=Mon, 6=Sun
    df["day_name"] = df["day_of_week"].map(lambda i: DAY_NAMES[i])
    df["is_weekend"] = df["day_of_week"] >= 5

    # Period labels
    df["year_month"] = df["start_date"].str[:7]
    df["quarter"] = df["start_dt"].dt.to_period("Q").astype(str)

    # Fill missing project names
    df["project_name"] = df["project_name"].fillna("(no project)")
    df["client_name"] = df["client_name"].fillna("(no client)")

    return df


# ---------------------------------------------------------------------------
# Daily aggregation
# ---------------------------------------------------------------------------

def load_daily_series() -> pd.DataFrame:
    """
    Return one row per calendar date that has any tracked time.

    Columns:
        date                -- YYYY-MM-DD
        hours               -- total tracked hours
        entry_count         -- number of entries
        unique_projects     -- distinct project names
        unique_tags         -- distinct tag names (exploded)
        first_entry_hour    -- hour of first entry that day (0-23)
        last_entry_hour     -- hour of last entry that day (0-23)
        is_weekend          -- bool
        year, month, week   -- int
    """
    df = load_entries()
    if df.empty:
        return pd.DataFrame()

    # Unique tag count per day requires exploding
    tag_daily = (
        df.explode("tags_list")
        .groupby("start_date")["tags_list"]
        .nunique()
        .rename("unique_tags")
    )

    daily = (
        df.groupby("start_date")
        .agg(
            hours=("duration_hours", "sum"),
            entry_count=("id", "count"),
            unique_projects=("project_name", "nunique"),
            first_entry_hour=("hour_of_day", "min"),
            last_entry_hour=("hour_of_day", "max"),
        )
        .join(tag_daily, how="left")
        .reset_index()
        .rename(columns={"start_date": "date"})
    )

    daily["unique_tags"] = daily["unique_tags"].fillna(0).astype(int)
    daily["date_dt"] = pd.to_datetime(daily["date"])
    daily["is_weekend"] = daily["date_dt"].dt.dayofweek >= 5
    daily["year"] = daily["date_dt"].dt.year
    daily["month"] = daily["date_dt"].dt.month
    daily["week"] = daily["date_dt"].dt.isocalendar().week.astype(int)
    daily["year_week"] = (
        daily["date_dt"].dt.isocalendar().year.astype(str)
        + "-W"
        + daily["week"].astype(str).str.zfill(2)
    )

    return daily.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Weekly pivot matrix (for correlations and life phases)
# ---------------------------------------------------------------------------

def load_weekly_matrix(top_n_projects: int = 25) -> pd.DataFrame:
    """
    Return a (weeks × projects) pivot of tracked hours.

    Only the top-N projects by total hours are included. Missing
    week-project combinations are filled with 0.

    Index: year_week strings ("2024-W03")
    Columns: project name strings
    """
    df = load_entries()
    if df.empty:
        return pd.DataFrame()

    # Identify top-N projects
    top_projects = (
        df.groupby("project_name")["duration_hours"]
        .sum()
        .nlargest(top_n_projects)
        .index.tolist()
    )

    filtered = df[df["project_name"].isin(top_projects)].copy()

    # Build week label: ISO year + week
    filtered["year_week"] = (
        filtered["start_dt"].dt.isocalendar().year.astype(str)
        + "-W"
        + filtered["start_dt"].dt.isocalendar().week.astype(int).astype(str).str.zfill(2)
    )

    pivot = (
        filtered.groupby(["year_week", "project_name"])["duration_hours"]
        .sum()
        .unstack(fill_value=0.0)
        .sort_index()
    )

    return pivot


# ---------------------------------------------------------------------------
# Description corpus for text mining
# ---------------------------------------------------------------------------

def load_description_corpus() -> pd.DataFrame:
    """
    Return a DataFrame with entry descriptions alongside metadata.

    Columns: id, description, start_date, start_year, project_name,
             duration_hours, tags_list
    Only includes entries with non-empty descriptions.
    """
    df = load_entries()
    if df.empty:
        return pd.DataFrame()

    cols = ["id", "description", "start_date", "start_year", "project_name",
            "duration_hours", "tags_list", "quarter", "year_month"]
    corpus = df[cols].copy()
    corpus = corpus[corpus["description"].notna() & (corpus["description"].str.strip() != "")]
    corpus["description"] = corpus["description"].str.strip()
    return corpus.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Projects reference table
# ---------------------------------------------------------------------------

def load_projects() -> pd.DataFrame:
    """Return all projects from the projects table."""
    conn = _get_connection()
    try:
        return pd.read_sql_query("SELECT * FROM projects", conn)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Database metadata / health check
# ---------------------------------------------------------------------------

def get_db_meta() -> dict:
    """
    Return summary statistics about the database.

    Used by the CLI to print a data summary before running analyzers.
    """
    conn = _get_connection()
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*)                        AS total_entries,
                SUM(duration_hours)             AS total_hours,
                MIN(start_date)                 AS earliest_date,
                MAX(start_date)                 AS latest_date,
                COUNT(DISTINCT start_year)      AS years_tracked,
                COUNT(DISTINCT project_name)    AS unique_projects,
                SUM(CASE WHEN toggl_id IS NOT NULL THEN 1 ELSE 0 END) AS enriched_entries
            FROM time_entries
            WHERE duration > 0
            """
        ).fetchone()
        meta = dict(row)

        # Sync meta
        sync_rows = conn.execute("SELECT key, value FROM sync_meta").fetchall()
        meta["sync"] = {r["key"]: r["value"] for r in sync_rows}

        return meta
    finally:
        conn.close()
