import { createClient, SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

const isDemoMode = !supabaseUrl || !supabaseAnonKey || supabaseUrl.includes('localhost')

if (isDemoMode) {
  console.log('Running in demo mode - using mock data')
}

// Mock data for demo mode
const mockEntries = [
  { id: 1, description: 'Design review', project_name: 'Project Alpha', start_date: '2024-01-15', start: '2024-01-15T09:00:00Z', duration_hours: 2.5, tags: ['Deep Work'] },
  { id: 2, description: 'Team standup', project_name: 'Project Beta', start_date: '2024-01-15', start: '2024-01-15T14:00:00Z', duration_hours: 1.0, tags: ['Meeting'] },
  { id: 3, description: 'Code review', project_name: 'Project Alpha', start_date: '2024-01-16', start: '2024-01-16T10:00:00Z', duration_hours: 3.0, tags: ['Deep Work'] },
  { id: 4, description: 'Planning session', project_name: 'Project Gamma', start_date: '2024-01-17', start: '2024-01-17T11:00:00Z', duration_hours: 1.5, tags: ['Meeting'] },
  { id: 5, description: 'Feature development', project_name: 'Project Alpha', start_date: '2024-01-18', start: '2024-01-18T09:00:00Z', duration_hours: 4.0, tags: ['Deep Work'] },
]

function filterByYear(entries: typeof mockEntries, year: number) {
  return entries.filter(e => e.start.startsWith(String(year)))
}

let client: SupabaseClient | null = null

if (!isDemoMode) {
  client = createClient(supabaseUrl, supabaseAnonKey)
}

// Mock query builder
function createMockQueryBuilder(table: string) {
  return {
    select: (_columns?: string) => {
      return {
        then: (resolve: (value: { data: typeof mockEntries; error: null }) => void) => {
          setTimeout(() => resolve({ data: mockEntries, error: null }), 100)
          return { catch: () => {} }
        },
        gte: () => createMockFilter(),
        contains: () => createMockFilter(),
        order: () => createMockQueryBuilder(table)
      }
    }
  }
}

function createMockFilter() {
  return {
    lte: () => createMockFilter(),
    order: () => ({
      then: (resolve: (value: { data: typeof mockEntries; error: null }) => void) => {
        setTimeout(() => resolve({ data: mockEntries, error: null }), 100)
        return { catch: () => {} }
      }
    })
  }
}

export const supabase = {
  from: (table: string) => {
    if (isDemoMode) {
      return createMockQueryBuilder(table)
    }
    return client!.from(table)
  },
  rpc: (fn: string, params: any) => {
    if (isDemoMode) {
      return {
        then: (resolve: (value: { data: any[]; error: null }) => void) => {
          let data: any[] = []
          
          if (fn === 'get_overview_metrics') {
            const entries = params.filter_year 
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const uniqueDates = [...new Set(entries.map(e => e.start_date))]
            data = [{
              total_hours: entries.reduce((sum, e) => sum + e.duration_hours, 0),
              total_entries: entries.length,
              unique_projects: [...new Set(entries.map(e => e.project_name))].length,
              active_days: uniqueDates.length,
              avg_hours_per_day: entries.length / Math.max(uniqueDates.length, 1)
            }]
          } else if (fn === 'get_project_breakdown') {
            const entries = params.filter_year 
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const grouped: Record<string, { hours: number, entriesCount: number }> = {}
            for (const e of entries) {
              const key = e.project_name || 'No Project'
              if (!grouped[key]) grouped[key] = { hours: 0, entriesCount: 0 }
              grouped[key].hours += e.duration_hours
              grouped[key].entriesCount++
            }
            data = Object.entries(grouped)
              .map(([project_name, v]) => ({ project_name, hours: v.hours, entries: v.entriesCount }))
              .sort((a, b) => b.hours - a.hours)
          } else if (fn === 'get_tag_breakdown') {
            const entries = params.filter_year 
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const grouped: Record<string, { hours: number, entriesCount: number }> = {}
            for (const e of entries) {
              for (const tag of e.tags || []) {
                if (!grouped[tag]) grouped[tag] = { hours: 0, entriesCount: 0 }
                grouped[tag].hours += e.duration_hours
                grouped[tag].entriesCount++
              }
            }
            data = Object.entries(grouped)
              .map(([tag_name, v]) => ({ tag_name, hours: v.hours, entries: v.entriesCount }))
              .sort((a, b) => b.hours - a.hours)
          } else if (fn === 'get_on_this_day') {
            data = [
              { year: 2024, hours: 5.5, entries: 3 },
              { year: 2023, hours: 4.0, entries: 2 },
              { year: 2022, hours: 3.5, entries: 2 },
            ]
          }
          
          setTimeout(() => resolve({ data, error: null }), 100)
          return { catch: () => {} }
        }
      }
    }
    return client!.rpc(fn, params)
  },
  functions: {
    invoke: (_fn: string, options: any) => {
      if (isDemoMode) {
        return {
          then: (resolve: (value: { data: { answer: string }; error: null }) => void) => {
            const question = options.body?.question?.toLowerCase() || ''
            let answer = ''
            
            if (question.includes('top projects')) {
              answer = 'Top 10 Projects (2024):\n1. Project Alpha - 156.5h\n2. Project Beta - 98.2h\n3. Project Gamma - 45.0h'
            } else if (question.includes('today')) {
              answer = 'Across all years, you\'ve tracked 12.5 hours on this day (Jan 15), averaging 4.2h per occurrence.'
            } else if (question.includes('task')) {
              answer = 'No entries found for task matching that name.'
            } else {
              answer = `You asked: "${options.body?.question}". In demo mode, I can show mock responses for common queries like "top projects in 2024", "today", or queries about specific tasks.`
            }
            
            setTimeout(() => resolve({ data: { answer }, error: null }), 150)
            return { catch: () => {} }
          }
        }
      }
      return client!.functions.invoke(_fn, options)
    }
  },
  auth: {
    getSession: () => ({ data: { session: null }, error: null }),
    getUser: () => ({ data: { user: null }, error: null }),
    signInWithPassword: () => ({ data: { user: null, session: null }, error: null }),
    signOut: () => ({ error: null }),
  }
} as any