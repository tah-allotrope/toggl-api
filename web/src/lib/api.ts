import { supabase } from './supabase'

const isDemoMode = !import.meta.env.VITE_SUPABASE_URL || 
                   !import.meta.env.VITE_SUPABASE_ANON_KEY ||
                   import.meta.env.VITE_SUPABASE_URL.includes('localhost:54321')

export function isRunningInDemoMode(): boolean {
  return isDemoMode
}

export type DateRange = { startDate: string; endDate: string };
export type ViewMode = "single_year" | "all_time" | "custom_range";

export interface OverviewMetrics {
  totalHours: number;
  totalEntries: number;
  uniqueProjects: number;
  activeDays: number;
  avgHoursPerDay: number;
}

export async function fetchOverview(mode: ViewMode, year: number | null, range: DateRange | null): Promise<OverviewMetrics> {
  const { data, error } = await supabase.rpc('get_overview_metrics', {
    view_mode: mode,
    filter_year: year,
    p_start_date: range?.startDate,
    p_end_date: range?.endDate
  })
  if (error) throw error
  if (!data || data.length === 0) return { totalHours: 0, totalEntries: 0, uniqueProjects: 0, activeDays: 0, avgHoursPerDay: 0 }
  const row = data[0]
  return {
    totalHours: row.total_hours,
    totalEntries: row.total_entries,
    uniqueProjects: row.unique_projects,
    activeDays: row.active_days,
    avgHoursPerDay: row.avg_hours_per_day
  }
}

export async function fetchProjectBreakdown(mode: ViewMode, year: number | null, range: DateRange | null): Promise<Array<{ projectName: string; hours: number; entries: number }>> {
  const { data, error } = await supabase.rpc('get_project_breakdown', {
    view_mode: mode,
    filter_year: year,
    p_start_date: range?.startDate,
    p_end_date: range?.endDate
  })
  if (error) throw error
  return data.map((d: any) => ({ projectName: d.project_name, hours: d.hours, entries: d.entries }))
}

export async function fetchTagBreakdown(mode: ViewMode, year: number | null, range: DateRange | null): Promise<Array<{ tagName: string; hours: number; entries: number }>> {
  const { data, error } = await supabase.rpc('get_tag_breakdown', {
    view_mode: mode,
    filter_year: year,
    p_start_date: range?.startDate,
    p_end_date: range?.endDate
  })
  if (error) throw error
  return data.map((d: any) => ({ tagName: d.tag_name, hours: d.hours, entries: d.entries }))
}

export async function fetchClientBreakdown(mode: ViewMode, year: number | null, range: DateRange | null): Promise<Array<{ clientName: string; hours: number; entries: number }>> {
  const { data, error } = await supabase.rpc('get_client_breakdown', {
    view_mode: mode,
    filter_year: year,
    p_start_date: range?.startDate,
    p_end_date: range?.endDate
  })
  if (error) throw error
  return data.map((d: any) => ({ clientName: d.client_name, hours: d.hours, entries: d.entries }))
}

export async function fetchTaskBreakdown(mode: ViewMode, year: number | null, range: DateRange | null): Promise<Array<{ taskName: string; hours: number; entries: number }>> {
  const { data, error } = await supabase.rpc('get_task_breakdown', {
    view_mode: mode,
    filter_year: year,
    p_start_date: range?.startDate,
    p_end_date: range?.endDate
  })
  if (error) throw error
  return data.map((d: any) => ({ taskName: d.task_name, hours: d.hours, entries: d.entries }))
}

export async function fetchOnThisDay(month: number, day: number): Promise<Array<{ year: number; hours: number; entries: number }>> {
  const { data, error } = await supabase.rpc('get_on_this_day', {
    target_month: month,
    target_day: day
  })
  if (error) throw error
  return data.map((d: any) => ({ year: d.year, hours: d.hours, entries: d.entries }))
}

export async function fetchWeekAcrossYears(isoWeek: number): Promise<Array<{ year: number; hours: number; entries: number }>> {
  const { data, error } = await supabase.rpc('get_week_across_years', {
    target_week: isoWeek
  })
  if (error) throw error
  return data.map((d: any) => ({ year: d.year, hours: d.hours, entries: d.entries }))
}

export async function askChat(question: string): Promise<{ answer: string }> {
  const { data, error } = await supabase.functions.invoke('chat-query', {
    body: { question }
  })
  if (error) throw error
  return data as { answer: string }
}
