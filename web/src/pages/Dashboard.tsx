import { useEffect, useState } from 'react'
import { fetchOverview, fetchProjectBreakdown, fetchTagBreakdown, OverviewMetrics, ViewMode } from '../lib/api'

export default function Dashboard() {
  const [metrics, setMetrics] = useState<OverviewMetrics | null>(null)
  const [projects, setProjects] = useState<any[]>([])
  const [tags, setTags] = useState<any[]>([])
  const [mode, setMode] = useState<ViewMode>('all_time')

  useEffect(() => {
    async function load() {
      const year = new Date().getFullYear()
      const m = await fetchOverview(mode, mode === 'single_year' ? year : null, null)
      setMetrics(m)
      
      const p = await fetchProjectBreakdown(mode, mode === 'single_year' ? year : null, null)
      setProjects(p.slice(0, 10))
      
      const t = await fetchTagBreakdown(mode, mode === 'single_year' ? year : null, null)
      setTags(t.slice(0, 10))
    }
    load()
  }, [mode])

  return (
    <div className="container">
      <h1>Dashboard</h1>
      <div>
        <button onClick={() => setMode('all_time')}>All Time</button>
        <button onClick={() => setMode('single_year')}>This Year</button>
      </div>
      
      {metrics && (
        <div className="metrics">
          <p>Total Hours: {metrics.totalHours.toFixed(2)}</p>
          <p>Total Entries: {metrics.totalEntries}</p>
          <p>Unique Projects: {metrics.uniqueProjects}</p>
        </div>
      )}

      <div className="charts">
        <div>
          <h2>Top Projects</h2>
          <ul>
            {projects.map(p => (
              <li key={p.projectName}>{p.projectName}: {p.hours.toFixed(2)}h</li>
            ))}
          </ul>
        </div>
        <div>
          <h2>Top Tags</h2>
          <ul>
            {tags.map(t => (
              <li key={t.tagName}>{t.tagName}: {t.hours.toFixed(2)}h</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
