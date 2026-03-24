import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'

type LocationState = {
  from?: {
    pathname?: string
  }
}

export default function LoginPage() {
  const { isAuthenticated, isDemoMode, signInWithPassword } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const state = location.state as LocationState | null
  const destination = state?.from?.pathname ?? '/'

  if (isAuthenticated) {
    return <Navigate replace to={destination} />
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')

    const result = await signInWithPassword(email, password)

    if (result.error) {
      setError(result.error.message)
      setSubmitting(false)
      return
    }

    navigate(destination, { replace: true })
  }

  return (
    <div className="container auth-card">
      <p className="eyebrow">Private Beta Access</p>
      <h1>Sign in to the live dashboard</h1>
      <p>
        Demo mode stays public for previews. Real Supabase-backed access uses your authenticated session.
      </p>
      {isDemoMode && (
        <p className="helper-copy">
          Demo mode is active, so this screen will be skipped once real frontend env vars are configured.
        </p>
      )}
      <form className="auth-form" onSubmit={(event) => void handleSubmit(event)}>
        <label>
          Email
          <input
            autoComplete="email"
            onChange={(event) => setEmail(event.target.value)}
            type="email"
            value={email}
          />
        </label>
        <label>
          Password
          <input
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            value={password}
          />
        </label>
        <button disabled={submitting} type="submit">
          {submitting ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
      {error && <p className="error-text">{error}</p>}
    </div>
  )
}
