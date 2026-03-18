-- 20260318_000002_rls_policies.sql

-- Enable RLS on all tables
ALTER TABLE public.time_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sync_meta ENABLE ROW LEVEL SECURITY;

-- Deny all by default for anon/authenticated (implicit if no policies exist, but let's be explicit on access)

-- 1. SELECT policies for authenticated users
CREATE POLICY select_time_entries ON public.time_entries FOR SELECT TO authenticated USING (true);
CREATE POLICY select_projects ON public.projects FOR SELECT TO authenticated USING (true);
CREATE POLICY select_tags ON public.tags FOR SELECT TO authenticated USING (true);
CREATE POLICY select_clients ON public.clients FOR SELECT TO authenticated USING (true);
CREATE POLICY select_tasks ON public.tasks FOR SELECT TO authenticated USING (true);
CREATE POLICY select_sync_meta ON public.sync_meta FOR SELECT TO authenticated USING (true);

-- 2. ALL policies for service role (used for sync path)
CREATE POLICY all_time_entries_service ON public.time_entries TO service_role USING (true) WITH CHECK (true);
CREATE POLICY all_projects_service ON public.projects TO service_role USING (true) WITH CHECK (true);
CREATE POLICY all_tags_service ON public.tags TO service_role USING (true) WITH CHECK (true);
CREATE POLICY all_clients_service ON public.clients TO service_role USING (true) WITH CHECK (true);
CREATE POLICY all_tasks_service ON public.tasks TO service_role USING (true) WITH CHECK (true);
CREATE POLICY all_sync_meta_service ON public.sync_meta TO service_role USING (true) WITH CHECK (true);
