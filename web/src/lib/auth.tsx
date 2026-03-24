import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from 'react'
import type { Session, User } from '@supabase/supabase-js'
import { isRunningInDemoMode, supabase } from './supabase'

type AuthContextValue = {
  isDemoMode: boolean
  isLoading: boolean
  isAuthenticated: boolean
  user: User | null
  signInWithPassword: (email: string, password: string) => Promise<{ error: Error | null }>
  signOut: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

type AuthProviderProps = {
  children: ReactNode
}

function createDemoUser(): User {
  return {
    id: 'demo-user',
    app_metadata: { provider: 'demo' },
    user_metadata: { name: 'Demo User' },
    aud: 'authenticated',
    created_at: '2026-03-24T00:00:00Z'
  } as User
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [session, setSession] = useState<Session | null>(null)
  const [user, setUser] = useState<User | null>(null)
  const demoMode = isRunningInDemoMode()

  useEffect(() => {
    if (demoMode) {
      setUser(createDemoUser())
      setIsLoading(false)
      return
    }

    let isMounted = true

    async function bootstrapSession() {
      const { data, error } = await supabase.auth.getSession()

      if (!isMounted) {
        return
      }

      if (error) {
        setSession(null)
        setUser(null)
      } else {
        setSession(data.session)
        setUser(data.session?.user ?? null)
      }

      setIsLoading(false)
    }

    bootstrapSession()

    const { data: listener } = supabase.auth.onAuthStateChange((_event: string, nextSession: Session | null) => {
      if (!isMounted) {
        return
      }

      setSession(nextSession)
      setUser(nextSession?.user ?? null)
      setIsLoading(false)
    })

    return () => {
      isMounted = false
      listener.subscription.unsubscribe()
    }
  }, [demoMode])

  const value = useMemo<AuthContextValue>(() => {
    return {
      isDemoMode: demoMode,
      isLoading,
      isAuthenticated: demoMode || Boolean(session?.user),
      user,
      signInWithPassword: async (email: string, password: string) => {
        if (demoMode) {
          return { error: null }
        }

        const { error } = await supabase.auth.signInWithPassword({ email, password })
        return { error: error ? new Error(error.message) : null }
      },
      signOut: async () => {
        if (demoMode) {
          return
        }

        await supabase.auth.signOut()
      }
    }
  }, [demoMode, isLoading, session, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)

  if (!value) {
    throw new Error('useAuth must be used within an AuthProvider')
  }

  return value
}
