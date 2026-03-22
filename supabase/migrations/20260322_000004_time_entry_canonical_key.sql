-- 20260322_000004_time_entry_canonical_key.sql

ALTER TABLE public.time_entries
    ADD COLUMN IF NOT EXISTS canonical_key TEXT;

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
WHERE canonical_key IS NULL;

CREATE INDEX IF NOT EXISTS idx_entries_canonical_key
    ON public.time_entries(canonical_key);

CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_csv_canonical_key
    ON public.time_entries(canonical_key)
    WHERE toggl_id IS NULL AND canonical_key IS NOT NULL;
