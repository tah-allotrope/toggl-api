-- 20260318_000003_views_and_rpc.sql

-- View: Overview metrics (total hours, entries, unique projects, active days)
-- We'll create a function instead of a view to allow parameterized filtering (view mode, year, date range)
CREATE OR REPLACE FUNCTION public.get_overview_metrics(
    view_mode TEXT,
    filter_year INT DEFAULT NULL,
    p_start_date TEXT DEFAULT NULL,
    p_end_date TEXT DEFAULT NULL
) RETURNS TABLE (
    total_hours REAL,
    total_entries BIGINT,
    unique_projects BIGINT,
    active_days BIGINT,
    avg_hours_per_day REAL
) LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY
    WITH filtered AS (
        SELECT duration_hours, project_name, start_date AS s_date
        FROM public.time_entries
        WHERE duration > 0
          AND (view_mode = 'all_time'
               OR (view_mode = 'single_year' AND start_year = filter_year)
               OR (view_mode = 'custom_range' AND start_date >= p_start_date AND start_date <= p_end_date))
    )
    SELECT
        COALESCE(SUM(f.duration_hours), 0)::REAL AS total_hours,
        COUNT(f.*)::BIGINT AS total_entries,
        COUNT(DISTINCT NULLIF(f.project_name, ''))::BIGINT AS unique_projects,
        COUNT(DISTINCT f.s_date)::BIGINT AS active_days,
        CASE WHEN COUNT(DISTINCT f.s_date) > 0
             THEN COALESCE(SUM(f.duration_hours), 0) / COUNT(DISTINCT f.s_date)
             ELSE 0
        END::REAL AS avg_hours_per_day
    FROM filtered f;
END;
$$;
GRANT EXECUTE ON FUNCTION public.get_overview_metrics TO authenticated;

-- Function: Project breakdown
CREATE OR REPLACE FUNCTION public.get_project_breakdown(
    view_mode TEXT,
    filter_year INT DEFAULT NULL,
    p_start_date TEXT DEFAULT NULL,
    p_end_date TEXT DEFAULT NULL
) RETURNS TABLE (
    project_name TEXT,
    hours REAL,
    entries BIGINT
) LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY
    SELECT
        COALESCE(NULLIF(te.project_name, ''), 'No Project') AS project_name,
        SUM(te.duration_hours)::REAL AS hours,
        COUNT(*)::BIGINT AS entries
    FROM public.time_entries te
    WHERE te.duration > 0
      AND (view_mode = 'all_time'
           OR (view_mode = 'single_year' AND te.start_year = filter_year)
           OR (view_mode = 'custom_range' AND te.start_date >= p_start_date AND te.start_date <= p_end_date))
    GROUP BY COALESCE(NULLIF(te.project_name, ''), 'No Project')
    ORDER BY hours DESC;
END;
$$;
GRANT EXECUTE ON FUNCTION public.get_project_breakdown TO authenticated;

-- Function: Tag breakdown (needs unnesting JSONB)
CREATE OR REPLACE FUNCTION public.get_tag_breakdown(
    view_mode TEXT,
    filter_year INT DEFAULT NULL,
    p_start_date TEXT DEFAULT NULL,
    p_end_date TEXT DEFAULT NULL
) RETURNS TABLE (
    tag_name TEXT,
    hours REAL,
    entries BIGINT
) LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY
    SELECT
        tag_val#>>'{}' AS tag_name,
        SUM(te.duration_hours)::REAL AS hours,
        COUNT(*)::BIGINT AS entries
    FROM public.time_entries te
    CROSS JOIN jsonb_array_elements(CASE WHEN jsonb_typeof(te.tags) = 'array' THEN te.tags ELSE '[]'::jsonb END) AS tag_val
    WHERE te.duration > 0
      AND (view_mode = 'all_time'
           OR (view_mode = 'single_year' AND te.start_year = filter_year)
           OR (view_mode = 'custom_range' AND te.start_date >= p_start_date AND te.start_date <= p_end_date))
    GROUP BY tag_val#>>'{}'
    ORDER BY hours DESC;
END;
$$;
GRANT EXECUTE ON FUNCTION public.get_tag_breakdown TO authenticated;

-- Function: Client breakdown
CREATE OR REPLACE FUNCTION public.get_client_breakdown(
    view_mode TEXT,
    filter_year INT DEFAULT NULL,
    p_start_date TEXT DEFAULT NULL,
    p_end_date TEXT DEFAULT NULL
) RETURNS TABLE (
    client_name TEXT,
    hours REAL,
    entries BIGINT
) LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY
    SELECT
        COALESCE(NULLIF(te.client_name, ''), 'No Client') AS client_name,
        SUM(te.duration_hours)::REAL AS hours,
        COUNT(*)::BIGINT AS entries
    FROM public.time_entries te
    WHERE te.duration > 0
      AND (view_mode = 'all_time'
           OR (view_mode = 'single_year' AND te.start_year = filter_year)
           OR (view_mode = 'custom_range' AND te.start_date >= p_start_date AND te.start_date <= p_end_date))
    GROUP BY COALESCE(NULLIF(te.client_name, ''), 'No Client')
    ORDER BY hours DESC;
END;
$$;
GRANT EXECUTE ON FUNCTION public.get_client_breakdown TO authenticated;

-- Function: Task breakdown
CREATE OR REPLACE FUNCTION public.get_task_breakdown(
    view_mode TEXT,
    filter_year INT DEFAULT NULL,
    p_start_date TEXT DEFAULT NULL,
    p_end_date TEXT DEFAULT NULL
) RETURNS TABLE (
    task_name TEXT,
    hours REAL,
    entries BIGINT
) LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY
    SELECT
        COALESCE(NULLIF(te.task_name, ''), 'No Task') AS task_name,
        SUM(te.duration_hours)::REAL AS hours,
        COUNT(*)::BIGINT AS entries
    FROM public.time_entries te
    WHERE te.duration > 0
      AND (view_mode = 'all_time'
           OR (view_mode = 'single_year' AND te.start_year = filter_year)
           OR (view_mode = 'custom_range' AND te.start_date >= p_start_date AND te.start_date <= p_end_date))
    GROUP BY COALESCE(NULLIF(te.task_name, ''), 'No Task')
    ORDER BY hours DESC;
END;
$$;
GRANT EXECUTE ON FUNCTION public.get_task_breakdown TO authenticated;

-- Function: On this day (cross years)
CREATE OR REPLACE FUNCTION public.get_on_this_day(
    target_month INT,
    target_day INT
) RETURNS TABLE (
    year INT,
    hours REAL,
    entries BIGINT
) LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY
    SELECT
        te.start_year::INT AS year,
        SUM(te.duration_hours)::REAL AS hours,
        COUNT(*)::BIGINT AS entries
    FROM public.time_entries te
    WHERE te.duration > 0
      AND te.start_month = target_month
      AND te.start_day = target_day
    GROUP BY te.start_year
    ORDER BY te.start_year ASC;
END;
$$;
GRANT EXECUTE ON FUNCTION public.get_on_this_day TO authenticated;

-- Function: Week across years
CREATE OR REPLACE FUNCTION public.get_week_across_years(
    target_week INT
) RETURNS TABLE (
    year INT,
    hours REAL,
    entries BIGINT
) LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    RETURN QUERY
    SELECT
        te.start_year::INT AS year,
        SUM(te.duration_hours)::REAL AS hours,
        COUNT(*)::BIGINT AS entries
    FROM public.time_entries te
    WHERE te.duration > 0
      AND te.start_week = target_week
    GROUP BY te.start_year
    ORDER BY te.start_year ASC;
END;
$$;
GRANT EXECUTE ON FUNCTION public.get_week_across_years TO authenticated;
