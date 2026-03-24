import { StrictMode } from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/AppShell'
import ProtectedRoute from './components/ProtectedRoute'
import { AuthProvider } from './lib/auth'
import Homepage from './pages/Homepage'
import Dashboard from './pages/Dashboard'
import Retrospect from './pages/Retrospect'
import Chat from './pages/Chat'
import LoginPage from './pages/LoginPage'
import './styles/theme.css'
import { isRunningInDemoMode } from './lib/supabase'

function DemoBanner() {
  const isDemo = isRunningInDemoMode()
  
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
    <AuthProvider>
      <DemoBanner />
      <HashRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/" element={<Homepage />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/retrospect" element={<Retrospect />} />
              <Route path="/chat" element={<Chat />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate replace to="/" />} />
        </Routes>
      </HashRouter>
    </AuthProvider>
  </StrictMode>,
)
