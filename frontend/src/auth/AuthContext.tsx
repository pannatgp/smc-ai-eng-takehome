import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'
import { login as apiLogin, register as apiRegister } from '../api/client'

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)
const STORAGE_KEY = 'smc_chat_token'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(STORAGE_KEY))

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      isAuthenticated: token !== null,
      async login(email, password) {
        const accessToken = await apiLogin(email, password)
        localStorage.setItem(STORAGE_KEY, accessToken)
        setToken(accessToken)
      },
      async register(email, password) {
        await apiRegister(email, password)
      },
      logout() {
        localStorage.removeItem(STORAGE_KEY)
        setToken(null)
      },
    }),
    [token],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
