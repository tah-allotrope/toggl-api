import type { Session, SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

const hasValidSupabaseConfig = supabaseUrl && supabaseAnonKey && 
  supabaseUrl.trim().length > 0 && 
  supabaseAnonKey.trim().length > 0 &&
  !supabaseUrl.includes('localhost') &&
  !supabaseUrl.includes('example')

const isDemoMode = !hasValidSupabaseConfig

let createClient: ((url: string, key: string) => SupabaseClient) | null = null

if (!isDemoMode) {
  import('@supabase/supabase-js').then(module => {
    createClient = module.createClient
  })
}

if (isDemoMode) {
  console.log('Running in demo mode - using mock data')
}

type MockEntry = {
  id: number
  description: string
  project_name: string
  start_date: string
  start: string
  duration_hours: number
  tags: string[]
}

type MockResult<T> = { data: T; error: null }

type MockQueryResult<T> = Promise<MockResult<T>>

type FilterOperator = 'contains' | 'gte' | 'lte'

type Filter = {
  field: keyof MockEntry
  operator: FilterOperator
  value: string | string[]
}

type OrderSpec = {
  field: keyof MockEntry
  ascending: boolean
} | null

const mockEntries: MockEntry[] = [
  {
    id: 1,
    description: 'Weekly wins roundup',
    project_name: 'Project Alpha',
    start_date: '2026-03-23',
    start: '2026-03-23T09:00:00Z',
    duration_hours: 2.5,
    tags: ['Highlight', 'Deep Work']
  },
  {
    id: 2,
    description: 'Ship review notes',
    project_name: 'Project Beta',
    start_date: '2026-03-24',
    start: '2026-03-24T14:00:00Z',
    duration_hours: 1,
    tags: ['Highlight', 'Meeting']
  },
  {
    id: 3,
    description: 'Code review',
    project_name: 'Project Alpha',
    start_date: '2024-01-16',
    start: '2024-01-16T10:00:00Z',
    duration_hours: 3,
    tags: ['Deep Work']
  },
  {
    id: 4,
    description: 'Planning session',
    project_name: 'Project Gamma',
    start_date: '2024-01-17',
    start: '2024-01-17T11:00:00Z',
    duration_hours: 1.5,
    tags: ['Meeting']
  },
  {
    id: 5,
    description: 'Feature development',
    project_name: 'Project Alpha',
    start_date: '2024-01-18',
    start: '2024-01-18T09:00:00Z',
    duration_hours: 4,
    tags: ['Deep Work']
  },
  {
    id: 6,
    description: 'Client meeting',
    project_name: 'Project Beta',
    start_date: '2024-01-18',
    start: '2024-01-18T14:00:00Z',
    duration_hours: 2,
    tags: ['Meeting']
  },
  {
    id: 7,
    description: 'Bug fixes',
    project_name: 'Project Alpha',
    start_date: '2024-01-19',
    start: '2024-01-19T09:00:00Z',
    duration_hours: 3.5,
    tags: ['Deep Work']
  },
  {
    id: 8,
    description: 'Documentation',
    project_name: 'Project Gamma',
    start_date: '2024-01-19',
    start: '2024-01-19T13:00:00Z',
    duration_hours: 1,
    tags: ['Admin']
  },
  {
    id: 9,
    description: 'Sprint planning',
    project_name: 'Project Beta',
    start_date: '2024-01-20',
    start: '2024-01-20T10:00:00Z',
    duration_hours: 1.5,
    tags: ['Meeting']
  },
  {
    id: 10,
    description: 'API development',
    project_name: 'Project Alpha',
    start_date: '2024-01-20',
    start: '2024-01-20T11:30:00Z',
    duration_hours: 4,
    tags: ['Deep Work']
  }
]

function filterByYear(entries: MockEntry[], year: number) {
  return entries.filter((entry) => entry.start.startsWith(String(year)))
}

function applyFilters(entries: MockEntry[], filters: Filter[]) {
  return filters.reduce((result, filter) => {
    return result.filter((entry) => {
      const candidate = entry[filter.field]

      if (filter.operator === 'contains') {
        if (!Array.isArray(candidate) || !Array.isArray(filter.value)) {
          return false
        }

        return filter.value.every((value) => candidate.includes(value))
      }

      if (typeof candidate !== 'string' || Array.isArray(filter.value)) {
        return false
      }

      if (filter.operator === 'gte') {
        return candidate >= filter.value
      }

      return candidate <= filter.value
    })
  }, entries)
}

function applyOrder(entries: MockEntry[], orderSpec: OrderSpec) {
  if (!orderSpec) {
    return entries
  }

  const direction = orderSpec.ascending ? 1 : -1

  return [...entries].sort((left, right) => {
    const leftValue = left[orderSpec.field]
    const rightValue = right[orderSpec.field]

    if (leftValue < rightValue) {
      return -1 * direction
    }

    if (leftValue > rightValue) {
      return 1 * direction
    }

    return 0
  })
}

function resolveMockRows(filters: Filter[], orderSpec: OrderSpec) {
  return applyOrder(applyFilters(mockEntries, filters), orderSpec)
}

function createResolvedPromise<T>(data: T): MockQueryResult<T> {
  return Promise.resolve({ data, error: null })
}

function createMockQuery(filters: Filter[] = [], orderSpec: OrderSpec = null) {
  return {
    contains: (field: keyof MockEntry, value: string[]) => createMockQuery([...filters, { field, operator: 'contains', value }], orderSpec),
    gte: (field: keyof MockEntry, value: string) => createMockQuery([...filters, { field, operator: 'gte', value }], orderSpec),
    lte: (field: keyof MockEntry, value: string) => createMockQuery([...filters, { field, operator: 'lte', value }], orderSpec),
    order: (field: keyof MockEntry, options?: { ascending?: boolean }) => createResolvedPromise(resolveMockRows(filters, {
      field,
      ascending: options?.ascending ?? true
    })),
    then: (resolve: (value: { data: MockEntry[]; error: null }) => void) => Promise.resolve(resolve({
      data: resolveMockRows(filters, orderSpec),
      error: null
    }))
  }
}

let client: SupabaseClient | null = null

async function initClient() {
  if (!isDemoMode && createClient) {
    client = createClient(supabaseUrl, supabaseAnonKey)
  }
}

initClient()

export const supabase = {
  from: (table: string) => {
    if (isDemoMode) {
      return {
        select: (_columns?: string) => createMockQuery()
      }
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
            const uniqueDates = [...new Set(entries.map((entry) => entry.start_date))]
            data = [{
              total_hours: entries.reduce((sum, entry) => sum + entry.duration_hours, 0),
              total_entries: entries.length,
              unique_projects: [...new Set(entries.map((entry) => entry.project_name))].length,
              active_days: uniqueDates.length,
              avg_hours_per_day: entries.length / Math.max(uniqueDates.length, 1)
            }]
          } else if (fn === 'get_project_breakdown') {
            const entries = params.filter_year
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const grouped: Record<string, { hours: number; entriesCount: number }> = {}
            for (const entry of entries) {
              const key = entry.project_name || 'No Project'
              if (!grouped[key]) {
                grouped[key] = { hours: 0, entriesCount: 0 }
              }
              grouped[key].hours += entry.duration_hours
              grouped[key].entriesCount += 1
            }
            data = Object.entries(grouped)
              .map(([project_name, value]) => ({ project_name, hours: value.hours, entries: value.entriesCount }))
              .sort((left, right) => right.hours - left.hours)
          } else if (fn === 'get_tag_breakdown') {
            const entries = params.filter_year
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const grouped: Record<string, { hours: number; entriesCount: number }> = {}
            for (const entry of entries) {
              for (const tag of entry.tags || []) {
                if (!grouped[tag]) {
                  grouped[tag] = { hours: 0, entriesCount: 0 }
                }
                grouped[tag].hours += entry.duration_hours
                grouped[tag].entriesCount += 1
              }
            }
            data = Object.entries(grouped)
              .map(([tag_name, value]) => ({ tag_name, hours: value.hours, entries: value.entriesCount }))
              .sort((left, right) => right.hours - left.hours)
          } else if (fn === 'get_on_this_day') {
            data = [
              { year: 2024, hours: 5.5, entries: 3 },
              { year: 2023, hours: 4, entries: 2 },
              { year: 2022, hours: 3.5, entries: 2 }
            ]
          } else if (fn === 'get_available_years') {
            data = [
              { year: 2026 },
              { year: 2025 },
              { year: 2024 },
              { year: 2023 },
              { year: 2022 }
            ]
          } else if (fn === 'get_daily_hours') {
            const entries = params.filter_year
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const grouped: Record<string, { hours: number; entriesCount: number }> = {}
            for (const entry of entries) {
              const key = entry.start_date
              if (!grouped[key]) {
                grouped[key] = { hours: 0, entriesCount: 0 }
              }
              grouped[key].hours += entry.duration_hours
              grouped[key].entriesCount += 1
            }
            data = Object.entries(grouped)
              .map(([start_date, value]) => ({ start_date, hours: value.hours, entries: value.entriesCount }))
              .sort((a, b) => a.start_date.localeCompare(b.start_date))
          } else if (fn === 'get_monthly_hours') {
            const entries = params.filter_year
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const grouped: Record<string, number> = {}
            for (const entry of entries) {
              const month = entry.start_date.substring(0, 7)
              grouped[month] = (grouped[month] || 0) + entry.duration_hours
            }
            data = Object.entries(grouped)
              .map(([month, hours]) => ({ month, hours }))
              .sort((a, b) => a.month.localeCompare(b.month))
          } else if (fn === 'get_year_comparison') {
            const yearA = params.year_a
            const yearB = params.year_b
            const entriesA = filterByYear(mockEntries, yearA)
            const entriesB = filterByYear(mockEntries, yearB)
            const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            data = months.map((month, idx) => {
              const monthNum = String(idx + 1).padStart(2, '0')
              const hoursA = entriesA
                .filter(e => e.start_date.startsWith(`${yearA}-${monthNum}`))
                .reduce((sum, e) => sum + e.duration_hours, 0)
              const hoursB = entriesB
                .filter(e => e.start_date.startsWith(`${yearB}-${monthNum}`))
                .reduce((sum, e) => sum + e.duration_hours, 0)
              return { month, hours_a: hoursA, hours_b: hoursB }
            })
          } else if (fn === 'get_week_across_years') {
            data = [
              { year: 2026, hours: 12.5, entries: 5 },
              { year: 2025, hours: 15.2, entries: 6 },
              { year: 2024, hours: 18.0, entries: 7 },
              { year: 2023, hours: 10.5, entries: 4 }
            ]
          } else if (fn === 'get_top_descriptions') {
            const entries = params.filter_year
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const projectEntries = entries.filter(e => e.project_name === params.p_project_name)
            const grouped: Record<string, { hours: number; entriesCount: number }> = {}
            for (const entry of projectEntries) {
              const key = entry.description || 'No description'
              if (!grouped[key]) {
                grouped[key] = { hours: 0, entriesCount: 0 }
              }
              grouped[key].hours += entry.duration_hours
              grouped[key].entriesCount += 1
            }
            const limit = params.p_limit || 10
            data = Object.entries(grouped)
              .map(([description, value]) => ({ description, hours: value.hours, entries: value.entriesCount }))
              .sort((a, b) => b.hours - a.hours)
              .slice(0, limit)
          } else if (fn === 'get_client_breakdown') {
            const entries = params.filter_year
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            const grouped: Record<string, { hours: number; entriesCount: number }> = {}
            for (const entry of entries) {
              const key = 'Client A'
              if (!grouped[key]) {
                grouped[key] = { hours: 0, entriesCount: 0 }
              }
              grouped[key].hours += entry.duration_hours
              grouped[key].entriesCount += 1
            }
            data = Object.entries(grouped)
              .map(([client_name, value]) => ({ client_name, hours: value.hours, entries: value.entriesCount }))
              .sort((a, b) => b.hours - a.hours)
          } else if (fn === 'get_task_breakdown') {
            const entries = params.filter_year
              ? filterByYear(mockEntries, params.filter_year)
              : mockEntries
            data = entries
              .filter(e => e.description)
              .map(e => ({ task_name: e.description, hours: e.duration_hours, entries: 1 }))
              .slice(0, 10)
          }

          return Promise.resolve(resolve({ data, error: null }))
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
              answer = "Across all years, you've tracked 12.5 hours on this day (Jan 15), averaging 4.2h per occurrence."
            } else if (question.includes('task')) {
              answer = 'No entries found for task matching that name.'
            } else {
              answer = `You asked: "${options.body?.question}". In demo mode, I can show mock responses for common queries like "top projects in 2024", "today", or queries about specific tasks.`
            }

            return Promise.resolve(resolve({ data: { answer }, error: null }))
          }
        }
      }

      return client!.functions.invoke(_fn, options)
    }
  },
  auth: {
    getSession: () => ({ data: { session: null }, error: null }),
    getUser: () => ({ data: { user: null }, error: null }),
    signInWithPassword: (_credentials?: { email: string; password: string }) => ({ data: { user: null, session: null }, error: null }),
    signOut: () => ({ error: null }),
    onAuthStateChange: (_callback: (event: string, session: Session | null) => void) => ({
      data: {
        subscription: {
          unsubscribe: () => undefined
        }
      }
    })
  }
} as any

export function isRunningInDemoMode(): boolean {
  return isDemoMode
}
