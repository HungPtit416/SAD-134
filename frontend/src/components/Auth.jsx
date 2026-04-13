import { createContext, useContext, useMemo, useState } from 'react'

const AuthCtx = createContext(null)

const STORAGE_KEY = 'sad_auth_v1'

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => loadStored())

  const api = useMemo(() => {
    return {
      auth,
      setAuth: (next) => {
        setAuth(next)
        if (next) localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
        else localStorage.removeItem(STORAGE_KEY)
      },
      logout: () => {
        setAuth(null)
        localStorage.removeItem(STORAGE_KEY)
      },
    }
  }, [auth])

  return <AuthCtx.Provider value={api}>{children}</AuthCtx.Provider>
}

export function useAuth() {
  const v = useContext(AuthCtx)
  if (!v) throw new Error('useAuth must be used within AuthProvider')
  return v
}

