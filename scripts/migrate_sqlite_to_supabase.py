import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS time_entries (
    id BIGINT PRIMARY KEY,
    description TEXT,
    start TEXT NOT NULL,
    stop TEXT,
    duration BIGINT NOT NULL,
    project_id BIGINT,
    project_name TEXT,
    workspace_id BIGINT,
    tags TEXT,
    tag_ids TEXT,
    billable INTEGER DEFAULT 0,
    at TEXT,
    start_date TEXT,
    start_year INTEGER,
    start_month INTEGER,
    start_day INTEGER,
    start_week INTEGER,
    duration_hours REAL,
    toggl_id BIGINT,
    task_id BIGINT,
    task_name TEXT,
    client_name TEXT,
    user_id BIGINT
);

CREATE TABLE IF NOT EXISTS projects (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_id BIGINT,
    color TEXT,
    active INTEGER DEFAULT 1,
    at TEXT,
    client_id BIGINT,
    billable INTEGER,
    rate REAL,
    currency TEXT,
    fixed_fee REAL,
    estimated_hours REAL,
    estimated_seconds BIGINT,
    auto_estimates INTEGER,
    recurring INTEGER,
    recurring_parameters TEXT,
    template INTEGER
);

CREATE TABLE IF NOT EXISTS tags (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_id BIGINT,
    creator_id BIGINT,
    at TEXT,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS clients (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_id BIGINT,
    archived INTEGER DEFAULT 0,
    at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    project_id BIGINT,
    workspace_id BIGINT,
    active INTEGER DEFAULT 1,
    estimated_seconds BIGINT,
    tracked_seconds BIGINT,
    at TEXT
);
"""

def migrate_table(sqlite_conn, pg_conn, table_name, id_col="id"):
    print(f"Migrating {table_name}...")
    sqlite_conn.row_factory = sqlite3.Row
    rows = sqlite_conn.execute(f"SELECT * FROM {table_name}").fetchall()
    if not rows:
        print(f"No rows in {table_name}.")
        return

    cols = list(rows[0].keys())
    col_names = ", ".join(cols)
    placeholders = ", ".join([f"%({col})s" for col in cols])
    
    insert_query = f"""
        INSERT INTO {table_name} ({col_names}) 
        VALUES %s
        ON CONFLICT ({id_col}) DO UPDATE SET 
        {", ".join([f"{col} = EXCLUDED.{col}" for col in cols if col != id_col])}
    """
    if table_name == "sync_meta":
        insert_query = f"""
            INSERT INTO {table_name} ({col_names}) 
            VALUES %s
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """

    data = [dict(row) for row in rows]
    
    with pg_conn.cursor() as cur:
        # Use execute_values for fast batch insert
        execute_values(
            cur,
            insert_query,
            data,
            template=f"({placeholders})",
            page_size=1000
        )
    pg_conn.commit()
    print(f"Successfully migrated {len(data)} rows to {table_name}.")

def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        return
        
    print("Connecting to PostgreSQL...")
    pg_conn = psycopg2.connect(db_url)
    
    with pg_conn.cursor() as cur:
        print("Initializing schema...")
        cur.execute(PG_SCHEMA)
    pg_conn.commit()
    
    print("Connecting to SQLite...")
    sqlite_conn = sqlite3.connect("data/toggl.db")
    
    tables = [
        ("time_entries", "id"),
        ("projects", "id"),
        ("tags", "id"),
        ("sync_meta", "key"),
        ("clients", "id"),
        ("tasks", "id")
    ]
    
    for table, id_col in tables:
        migrate_table(sqlite_conn, pg_conn, table, id_col)
        
    sqlite_conn.close()
    pg_conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    main()
