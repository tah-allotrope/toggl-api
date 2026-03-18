import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'

function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function getCurrentIsoWeekRange(): { monday: string; sunday: string; isoWeek: number } {
  const now = new Date()
  const weekday = now.getDay() === 0 ? 7 : now.getDay()
  const mondayDate = new Date(now)
  mondayDate.setDate(now.getDate() - (weekday - 1))
  const sundayDate = new Date(mondayDate)
  sundayDate.setDate(mondayDate.getDate() + 6)

  const thursday = new Date(now)
  thursday.setDate(now.getDate() + (4 - weekday))
  const yearStart = new Date(thursday.getFullYear(), 0, 1)
  const isoWeek = Math.ceil((((thursday.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)

  return {
    monday: formatLocalDate(mondayDate),
    sunday: formatLocalDate(sundayDate),
    isoWeek,
  }
}

export default function Homepage() {
  const [highlights, setHighlights] = useState<any[]>([])
  const [isoWeekLabel, setIsoWeekLabel] = useState<number | null>(null)

  useEffect(() => {
    async function load() {
      const { monday, sunday, isoWeek } = getCurrentIsoWeekRange()
      setIsoWeekLabel(isoWeek)

      const { data, error } = await supabase
        .from('time_entries')
        .select('*')
        .contains('tags', ['Highlight'])
        .gte('start_date', monday)
        .lte('start_date', sunday)
        .order('start', { ascending: true })

      if (!error && data) {
        setHighlights(data)
      }
    }
    load()
  }, [])

  return (
    <div className="container">
      <h1>Weekly Highlights</h1>
      {isoWeekLabel !== null && <p>Week {isoWeekLabel}</p>}
      {highlights.length === 0 ? (
        <p>No highlights found.</p>
      ) : (
        <ul>
          {highlights.map(h => (
            <li key={h.id}>
              <strong>{h.project_name}</strong>: {h.description} ({h.duration_hours.toFixed(2)}h)
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
