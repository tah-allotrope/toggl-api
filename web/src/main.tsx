import { StrictMode } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Homepage from './pages/Homepage'
import Dashboard from './pages/Dashboard'
import Retrospect from './pages/Retrospect'
import Chat from './pages/Chat'
import './styles/theme.css'

function DemoBanner() {
  const isDemo = !import.meta.env.VITE_SUPABASE_URL || 
                 !import.meta.env.VITE_SUPABASE_ANON_KEY ||
                 import.meta.env.VITE_SUPABASE_URL.includes('localhost')
  
  if (!isDemo) return null
  
  return (
    <div style={{
      background: 'linear-gradient(90deg, #ff00ff, #00ffcc)',
      color: '#000',
      padding: '8px 16px',
      textAlign: 'center',
      fontWeight: 'bold',
      fontSize: '14px'
    }}>
      🔥 DEMO MODE — Running with mock data. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY to connect to real backend.
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <DemoBanner />
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Homepage />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/retrospect" element={<Retrospect />} />
        <Route path="/chat" element={<Chat />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)