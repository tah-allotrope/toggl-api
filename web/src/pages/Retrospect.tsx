import { useEffect, useState } from 'react'
import { fetchOnThisDay } from '../lib/api'

export default function Retrospect() {
  const [history, setHistory] = useState<any[]>([])
  const today = new Date()

  useEffect(() => {
    async function load() {
      const data = await fetchOnThisDay(today.getMonth() + 1, today.getDate())
      setHistory(data)
    }
    load()
  }, [])

  return (
    <div className="container">
      <h1>Retrospect</h1>
      <h2>On This Day ({today.getMonth() + 1}/{today.getDate()})</h2>
      {history.length === 0 ? (
        <p>No history for this date.</p>
      ) : (
        <ul>
          {history.map(h => (
            <li key={h.year}>
              {h.year}: {h.hours.toFixed(2)} hours across {h.entries} entries
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
