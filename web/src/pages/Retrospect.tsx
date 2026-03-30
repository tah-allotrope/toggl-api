import { useEffect, useState } from 'react'
import DatePicker from 'react-datepicker'
import 'react-datepicker/dist/react-datepicker.css'
import { 
  fetchOnThisDay, 
  fetchWeekAcrossYears, 
  fetchYearComparison, 
  fetchAvailableYears 
} from '../lib/api'
import LoadingSpinner from '../components/LoadingSpinner'
import NeonBarChart from '../components/Charts/NeonBarChart'
import NeonLineChart from '../components/Charts/NeonLineChart'

type TabType = 'on-this-day' | 'week-view' | 'year-comparison'

export default function Retrospect() {
  const [loading, setLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')
  const [activeTab, setActiveTab] = useState<TabType>('on-this-day')
  
  const [selectedDate, setSelectedDate] = useState<Date>(new Date())
  const [history, setHistory] = useState<any[]>([])
  
  const [isoWeek, setIsoWeek] = useState<number>(getCurrentIsoWeek())
  const [weekData, setWeekData] = useState<any[]>([])
  
  const [availableYears, setAvailableYears] = useState<number[]>([])
  const [yearA, setYearA] = useState<number>(new Date().getFullYear())
  const [yearB, setYearB] = useState<number>(new Date().getFullYear() - 1)
  const [comparisonData, setComparisonData] = useState<any[]>([])

  function getCurrentIsoWeek(): number {
    const now = new Date()
    const thursday = new Date(now)
    thursday.setDate(now.getDate() + (4 - (now.getDay() === 0 ? 7 : now.getDay())))
    const yearStart = new Date(thursday.getFullYear(), 0, 1)
    return Math.ceil((((thursday.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  }

  useEffect(() => {
    async function loadYears() {
      try {
        const years = await fetchAvailableYears()
        setAvailableYears(years)
        if (years.length >= 2) {
          setYearA(years[0])
          setYearB(years[1])
        } else {
          setYearA(new Date().getFullYear())
          setYearB(new Date().getFullYear() - 1)
        }
      } catch {
        setAvailableYears([2026, 2025, 2024, 2023, 2022])
        setYearA(2026)
        setYearB(2025)
      }
    }
    void loadYears()
  }, [])

  useEffect(() => {
    async function loadOnThisDay() {
      setLoading(true)
      try {
        setErrorMessage('')
        const data = await fetchOnThisDay(selectedDate.getMonth() + 1, selectedDate.getDate())
        setHistory(data)
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load data.')
      } finally {
        setLoading(false)
      }
    }
    if (activeTab === 'on-this-day') {
      void loadOnThisDay()
    }
  }, [activeTab, selectedDate])

  useEffect(() => {
    async function loadWeekView() {
      setLoading(true)
      try {
        setErrorMessage('')
        const data = await fetchWeekAcrossYears(isoWeek)
        setWeekData(data)
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load data.')
      } finally {
        setLoading(false)
      }
    }
    if (activeTab === 'week-view') {
      void loadWeekView()
    }
  }, [activeTab, isoWeek])

  useEffect(() => {
    async function loadYearComparison() {
      setLoading(true)
      try {
        setErrorMessage('')
        const data = await fetchYearComparison(yearA, yearB)
        setComparisonData(data)
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : 'Unable to load data.')
      } finally {
        setLoading(false)
      }
    }
    if (activeTab === 'year-comparison') {
      void loadYearComparison()
    }
  }, [activeTab, yearA, yearB])

  const formatDate = (date: Date): string => {
    return date.toLocaleDateString('en-US', { 
      weekday: 'short', 
      month: 'short', 
      day: 'numeric' 
    })
  }

  const weekChartData = weekData.length > 0 ? {
    x: weekData.map(d => d.year),
    y: weekData.map(d => d.hours)
  } : null

  const comparisonChartData = comparisonData.length > 0 ? [
    { x: comparisonData.map(d => d.month), y: comparisonData.map(d => d.hoursA), name: String(yearA) },
    { x: comparisonData.map(d => d.month), y: comparisonData.map(d => d.hoursB), name: String(yearB) }
  ] : null

  const getYearDiff = () => {
    if (comparisonData.length === 0) return 0
    const totalA = comparisonData.reduce((sum, d) => sum + d.hoursA, 0)
    const totalB = comparisonData.reduce((sum, d) => sum + d.hoursB, 0)
    return totalA - totalB
  }

  return (
    <div className="container">
      <h1>Retrospect</h1>
      
      <div className="tabs">
        <button 
          className={`tab ${activeTab === 'on-this-day' ? 'active' : ''}`}
          onClick={() => setActiveTab('on-this-day')}
        >
          On This Day
        </button>
        <button 
          className={`tab ${activeTab === 'week-view' ? 'active' : ''}`}
          onClick={() => setActiveTab('week-view')}
        >
          Week View
        </button>
        <button 
          className={`tab ${activeTab === 'year-comparison' ? 'active' : ''}`}
          onClick={() => setActiveTab('year-comparison')}
        >
          Year Comparison
        </button>
      </div>

      {errorMessage && <p className="error-text">{errorMessage}</p>}
      
      {loading ? (
        <LoadingSpinner />
      ) : activeTab === 'on-this-day' ? (
        <>
          <div className="filter-bar">
            <label>Select Date:</label>
            <DatePicker
              selected={selectedDate}
              onChange={(date: Date | null) => date && setSelectedDate(date)}
              dateFormat="yyyy-MM-dd"
              className="date-input"
            />
          </div>
          
          <h2>On This Day ({formatDate(selectedDate)})</h2>
          
          {history.length === 0 ? (
            <p className="empty-state">No history for this date.</p>
          ) : (
            <>
              <div className="chart-card" style={{ marginBottom: '1.5rem' }}>
                <NeonLineChart 
                  data={{
                    x: history.map(h => String(h.year)),
                    y: history.map(h => h.hours)
                  }}
                  title="Hours by Year"
                  height={250}
                />
              </div>
              
              <div className="table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Year</th>
                      <th>Hours</th>
                      <th>Entries</th>
                      <th>Avg/Day</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map(h => (
                      <tr key={h.year}>
                        <td>{h.year}</td>
                        <td>{h.hours.toFixed(1)}</td>
                        <td>{h.entries}</td>
                        <td>{(h.hours / h.entries).toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      ) : activeTab === 'week-view' ? (
        <>
          <div className="filter-bar">
            <label>ISO Week:</label>
            <select 
              value={isoWeek} 
              onChange={(e) => setIsoWeek(Number(e.target.value))}
            >
              {Array.from({ length: 53 }, (_, i) => i + 1).map(week => (
                <option key={week} value={week}>Week {week}</option>
              ))}
            </select>
          </div>
          
          <h2>Week {isoWeek} Across Years</h2>
          
          {weekData.length === 0 ? (
            <p className="empty-state">No data for this week.</p>
          ) : (
            <>
              <div className="metric-grid" style={{ marginBottom: '1.5rem' }}>
                {weekData.map(w => (
                  <div key={w.year} className="metric-card">
                    <div className="value">{w.hours.toFixed(1)}h</div>
                    <div className="label">{w.year}</div>
                  </div>
                ))}
              </div>
              
              {weekChartData && (
                <div className="chart-card">
                  <NeonBarChart 
                    data={weekChartData}
                    title="Hours by Year"
                    height={280}
                  />
                </div>
              )}
            </>
          )}
        </>
      ) : (
        <>
          <div className="filter-bar">
            <label>Compare:</label>
            <select 
              value={yearA} 
              onChange={(e) => setYearA(Number(e.target.value))}
            >
              {availableYears.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
            <span>vs</span>
            <select 
              value={yearB} 
              onChange={(e) => setYearB(Number(e.target.value))}
            >
              {availableYears.map(year => (
                <option key={year} value={year}>{year}</option>
              ))}
            </select>
          </div>
          
          <h2>{yearA} vs {yearB}</h2>
          
          {comparisonData.length === 0 ? (
            <p className="empty-state">No data for comparison.</p>
          ) : (
            <>
              <div className="metric-grid" style={{ marginBottom: '1.5rem' }}>
                <div className="metric-card">
                  <div className="value">{comparisonData.reduce((s, d) => s + d.hoursA, 0).toFixed(1)}</div>
                  <div className="label">{yearA} Hours</div>
                </div>
                <div className="metric-card">
                  <div className="value">{comparisonData.reduce((s, d) => s + d.hoursB, 0).toFixed(1)}</div>
                  <div className="label">{yearB} Hours</div>
                </div>
                <div className="metric-card">
                  <div className="value" style={{ color: getYearDiff() >= 0 ? '#00ffcc' : '#ff8fa3' }}>
                    {getYearDiff() >= 0 ? '+' : ''}{getYearDiff().toFixed(1)}
                  </div>
                  <div className="label">Difference</div>
                </div>
              </div>
              
              {comparisonChartData && (
                <div className="chart-card">
                  <NeonLineChart 
                    data={comparisonChartData}
                    title="Monthly Comparison"
                    height={300}
                  />
                </div>
              )}
              
              <div className="table-container" style={{ marginTop: '1.5rem' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>{yearA}</th>
                      <th>{yearB}</th>
                      <th>Diff</th>
                    </tr>
                  </thead>
                  <tbody>
                    {comparisonData.map((d, idx) => (
                      <tr key={idx}>
                        <td>{d.month}</td>
                        <td>{d.hoursA.toFixed(1)}</td>
                        <td>{d.hoursB.toFixed(1)}</td>
                        <td style={{ color: d.hoursA - d.hoursB >= 0 ? '#00ffcc' : '#ff8fa3' }}>
                          {d.hoursA - d.hoursB >= 0 ? '+' : ''}{(d.hoursA - d.hoursB).toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}
