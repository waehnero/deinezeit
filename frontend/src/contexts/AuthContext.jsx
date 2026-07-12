import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authApi } from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null)
  const [loadingAuth, setLoadingAuth]  = useState(true)

  const reload = useCallback(async () => {
    const token = localStorage.getItem('access_token')
    if (!token) { setCurrentUser(null); setLoadingAuth(false); return }
    try {
      const r = await authApi.me()
      setCurrentUser(r.data)
    } catch {
      setCurrentUser(null)
    } finally {
      setLoadingAuth(false)
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  const isAdmin = currentUser?.role === 'admin'

  // Modulrechte: /auth/me liefert die effektive Modul-Liste (Admin: alle;
  // null/undefined z.B. vor dem Laden = großzügig alles erlauben, das
  // Backend prüft ohnehin verbindlich).
  const modules = currentUser?.modules ?? null
  const hasModule = useCallback(
    (key) => modules === null || modules.includes(key),
    [modules]
  )

  return (
    <AuthContext.Provider value={{ currentUser, isAdmin, loadingAuth, reload, modules, hasModule }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
