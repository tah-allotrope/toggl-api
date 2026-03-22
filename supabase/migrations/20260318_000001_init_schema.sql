-- 20260318_000001_init_schema.sql
-- Create Postgres schema mirroring existing SQLite logical model:
-- time_entries, projects, tags, clients, tasks, sync_meta.

-- time_entries
CREATE TABLE IF NOT EXISTS public.time_entries (
    id BIGINT PRIMARY KEY,
    description TEXT,
    start TEXT NOT NULL,
    stop TEXT,
    duration BIGINT NOT NULL,
    project_id BIGINT,
    project_name TEXT,
    workspace_id BIGINT,
    tags JSONB,           -- JSON array of tag names
    tag_ids JSONB,        -- JSON array of tag IDs
    billable SMALLINT DEFAULT 0,
    at TEXT,              -- last updated timestamp
    -- Derived columns for fast querying
    start_date TEXT,      -- YYYY-MM-DD extracted from start
    start_year SMALLINT,
    start_month SMALLINT,
    start_day SMALLINT,
    start_week SMALLINT,  -- ISO week number
    duration_hours REAL,  -- duration in hours
    canonical_key TEXT,   -- stable key for reconciling CSV and enriched copies
    -- Enrichment columns (populated by JSON sync, NULL from CSV sync)
    toggl_id BIGINT UNIQUE, -- native Toggl entry ID (NULL until enriched)
    task_id BIGINT,        -- Premium: task assignment
    task_name TEXT,        -- Premium: denormalized task name
    client_name TEXT,      -- denormalized client name via project
    user_id BIGINT         -- Toggl user who created the entry
);

CREATE TABLE IF NOT EXISTS public.projects (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_id BIGINT,
    color TEXT,
    active SMALLINT DEFAULT 1,
    at TEXT,
    -- Enrichment columns
    client_id BIGINT,        -- FK to clients table
    billable SMALLINT,       -- Premium
    rate REAL,               -- Premium
    currency TEXT,           -- Premium
    fixed_fee REAL,          -- Premium
    estimated_hours REAL,    -- Premium
    estimated_seconds BIGINT,-- Premium
    auto_estimates SMALLINT, -- Premium
    recurring SMALLINT,      -- Premium
    recurring_parameters JSONB, -- Premium: JSON blob
    template SMALLINT        -- Premium
);

CREATE TABLE IF NOT EXISTS public.tags (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_id BIGINT,
    -- Enrichment columns
    creator_id BIGINT,       -- user who created the tag
    at TEXT,                 -- last modified timestamp
    deleted_at TEXT          -- soft-delete timestamp (NULL = active)
);

CREATE TABLE IF NOT EXISTS public.clients (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_id BIGINT,
    archived SMALLINT DEFAULT 0,
    at TEXT
);

CREATE TABLE IF NOT EXISTS public.tasks (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    project_id BIGINT,
    workspace_id BIGINT,
    active SMALLINT DEFAULT 1,
    estimated_seconds BIGINT,
    tracked_seconds BIGINT,
    at TEXT
);

CREATE TABLE IF NOT EXISTS public.sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_entries_start_date ON public.time_entries(start_date);
CREATE INDEX IF NOT EXISTS idx_entries_year ON public.time_entries(start_year);
CREATE INDEX IF NOT EXISTS idx_entries_month_day ON public.time_entries(start_month, start_day);
CREATE INDEX IF NOT EXISTS idx_entries_project ON public.time_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_entries_week ON public.time_entries(start_year, start_week);
CREATE INDEX IF NOT EXISTS idx_entries_task ON public.time_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_entries_client_name ON public.time_entries(client_name);
CREATE INDEX IF NOT EXISTS idx_entries_canonical_key ON public.time_entries(canonical_key);
CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_csv_canonical_key
    ON public.time_entries(canonical_key)
    WHERE toggl_id IS NULL AND canonical_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_project ON public.tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_projects_client ON public.projects(client_id);
