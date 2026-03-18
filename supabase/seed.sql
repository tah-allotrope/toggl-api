-- supabase/seed.sql
-- Tiny fixture dataset (3-6 rows) for local verification.

INSERT INTO public.clients (id, name, workspace_id, archived, at)
VALUES
(100, 'Test Client A', 10, 0, '2024-01-01T00:00:00Z');

INSERT INTO public.projects (id, name, workspace_id, client_id, color, active, at)
VALUES
(200, 'Project Alpha', 10, 100, '#ff0000', 1, '2024-01-01T00:00:00Z'),
(201, 'Project Beta', 10, NULL, '#00ff00', 1, '2024-01-01T00:00:00Z');

INSERT INTO public.tags (id, name, workspace_id, creator_id, at)
VALUES
(300, 'Deep Work', 10, 1, '2024-01-01T00:00:00Z'),
(301, 'Meeting', 10, 1, '2024-01-01T00:00:00Z');

INSERT INTO public.tasks (id, name, project_id, workspace_id, active)
VALUES
(400, 'Design UI', 200, 10, 1);

INSERT INTO public.time_entries (
    id, description, start, stop, duration, project_id, project_name, workspace_id,
    tags, tag_ids, start_date, start_year, start_month, start_day, start_week,
    duration_hours, toggl_id, task_id, task_name, client_name, user_id
) VALUES
(1000, 'Mockups', '2024-01-02T09:00:00Z', '2024-01-02T11:00:00Z', 7200, 200, 'Project Alpha', 10,
 '["Deep Work"]', '[300]', '2024-01-02', 2024, 1, 2, 1, 2.0, 1000, 400, 'Design UI', 'Test Client A', 1),

(1001, 'Review', '2024-01-02T13:00:00Z', '2024-01-02T14:00:00Z', 3600, 200, 'Project Alpha', 10,
 '["Meeting"]', '[301]', '2024-01-02', 2024, 1, 2, 1, 1.0, 1001, NULL, NULL, 'Test Client A', 1),

(1002, 'Planning', '2024-01-03T10:00:00Z', '2024-01-03T10:30:00Z', 1800, 201, 'Project Beta', 10,
 '[]', '[]', '2024-01-03', 2024, 1, 3, 1, 0.5, 1002, NULL, NULL, NULL, 1);
