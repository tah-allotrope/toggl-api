import { useEffect, useState } from 'react'
import { supabase } from '../lib/supabase'
import LoadingSpinner from '../components/LoadingSpinner'

function formatLocalDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatDisplayDate(dateStr: string): { day: string; date: string } {
  const date = new Date(dateStr + 'T00:00:00')
  const day = date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
  const dateFull = date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
  return { day, date: dateFull }
}

function formatTime(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function formatDuration(hours: number): string {
  if (hours < 1) {
    return `${Math.round(hours * 60)}m`
  }
  return `${hours.toFixed(1)}h`
}

function getCurrentIsoWeekRange(): { monday: string; sunday: string; isoWeek: number; mondayDisplay: string; sundayDisplay: string } {
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

  const formatShort = (d: Date) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  const formatFull = (d: Date) => d.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })

  return {
    monday: formatLocalDate(mondayDate),
    sunday: formatLocalDate(sundayDate),
    isoWeek,
    mondayDisplay: `${formatShort(mondayDate)}`,
    sundayDisplay: `${formatFull(sundayDate)}`
  }
}

export default function Homepage() {
  const [highlights, setHighlights] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')
  const [isoWeekLabel, setIsoWeekLabel] = useState<number | null>(null)
  const [weekRange, setWeekRange] = useState<{ mondayDisplay: string; sundayDisplay: string } | null>(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const { monday, sunday, isoWeek, mondayDisplay, sundayDisplay } = getCurrentIsoWeekRange()
      setIsoWeekLabel(isoWeek)
      setWeekRange({ mondayDisplay, sundayDisplay })

      const { data, error } = await supabase
        .from('time_entries')
        .select('*')
        .contains('tags', ['Highlight'])
        .gte('start_date', monday)
        .lte('start_date', sunday)
        .order('start', { ascending: true })

      if (error) {
        setErrorMessage(error.message)
        setHighlights([])
      } else if (data) {
        setHighlights(data)
      }
      setLoading(false)
    }
    load()
  }, [])

  return (
    <div className="container">
      <h1>Weekly Highlights</h1>
      
      {weekRange && (
        <p className="week-range">
          Week <span>{isoWeekLabel}</span> — {weekRange.mondayDisplay} to {weekRange.sundayDisplay}
        </p>
      )}
      
      {loading ? (
        <LoadingSpinner />
      ) : errorMessage ? (
        <p className="error-text">{errorMessage}</p>
      ) : highlights.length === 0 ? (
        <p className="empty-state">No highlights found for this week.</p>
      ) : (
        <div>
          {highlights.map(h => {
            const { day } = formatDisplayDate(h.start_date)
            const time = formatTime(h.start)
            const duration = formatDuration(h.duration_hours)
            
            return (
              <div key={h.id} className="entry-card">
                <div className="header">
                  <div>
                    <span className="day-label">{day}</span>
                    <span className="time-label"> — {time}</span>
                  </div>
                  <span className="duration">{duration}</span>
                </div>
                <div className="project-name">{h.project_name || 'No Project'}</div>
                {h.description && (
                  <div className="description"><strong>{h.description}</strong></div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
