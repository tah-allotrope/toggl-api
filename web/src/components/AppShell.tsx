import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../lib/auth'

const navItems = [
  { to: '/', label: 'Home', end: true },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/retrospect', label: 'Retrospect' },
  { to: '/chat', label: 'Chat' }
]

export default function AppShell() {
  const { isDemoMode, signOut, user } = useAuth()

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Toggl Time Journal</p>
          <h1 className="topbar-title">Cyberpunk analytics cockpit</h1>
        </div>
        <div className="topbar-actions">
          <span className="status-pill">
            {isDemoMode ? 'Demo access' : `Signed in as ${user?.email ?? 'authenticated user'}`}
          </span>
          {!isDemoMode && (
            <button type="button" onClick={() => void signOut()}>
              Sign out
            </button>
          )}
        </div>
      </header>

      <nav className="nav-grid" aria-label="Primary">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            className={({ isActive }) => `nav-card${isActive ? ' active' : ''}`}
            end={item.end}
            to={item.to}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  )
}
