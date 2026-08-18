import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  authApi, groupsApi, getAccessToken, setAbmeldeHandler,
  sitzungWiederherstellen, tokenVerwerfen, warAngemeldet,
} from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null)
  const [loadingAuth, setLoadingAuth] = useState(true)
  const navigate = useNavigate()

  /**
   * Anmeldezustand ermitteln.
   *
   * Neu gegenüber vorher: Es wird nicht mehr geprüft, ob ein Token in
   * localStorage liegt — dort liegt keiner mehr. Der Access-Token lebt im
   * Arbeitsspeicher und ist nach jedem Neuladen der Seite weg. Ist keiner da,
   * wird zuerst über den httpOnly-Cookie ein frischer geholt. Genau das lässt
   * eine Anmeldung ein Neuladen, einen Neustart des Browsers oder das
   * Schließen der installierten PWA überleben, ohne dass ein langlebiges Token
   * für JavaScript lesbar herumliegt.
   */
  const reload = useCallback(async () => {
    setLoadingAuth(true)
    try {
      if (!getAccessToken()) {
        // Nur versuchen, wenn hier schon einmal jemand angemeldet war. Sonst
        // erzeugt jeder erste Seitenaufruf einen 401 im Serverlog und einen
        // unnötigen Rundlauf, bevor die Anmeldemaske erscheint.
        if (!warAngemeldet()) {
          setCurrentUser(null)
          return
        }
        const token = await sitzungWiederherstellen()
        if (!token) { setCurrentUser(null); return }
      }
      const r = await authApi.me()
      setCurrentUser(r.data)
    } catch {
      tokenVerwerfen()
      setCurrentUser(null)
    } finally {
      setLoadingAuth(false)
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  /** Abmelden — beendet die Sitzung auch serverseitig.
   *
   *  Wichtig: Ohne den Server-Aufruf bliebe der Refresh-Token gültig. Vorher
   *  hat das Abmelden nur den Browser-Speicher geleert; wer den Token bereits
   *  kopiert hatte, konnte damit weiterarbeiten. */
  const logout = useCallback(async ({ alleGeraete = false } = {}) => {
    try {
      if (alleGeraete) await authApi.logoutAll()
      else await authApi.logout()
    } catch {
      // Auch wenn der Server nicht erreichbar ist, soll das Abmelden in der
      // Oberfläche funktionieren.
    } finally {
      tokenVerwerfen()
      setCurrentUser(null)
      navigate('/login', { replace: true })
    }
  }, [navigate])

  /** Vom axios-Interceptor aufgerufen, wenn die Sitzung endgültig abgelaufen
   *  ist. Ersetzt das frühere window.location.href = '/login', das einen
   *  vollständigen Seiten-Neuaufbau erzwang. */
  useEffect(() => {
    setAbmeldeHandler(() => {
      tokenVerwerfen()
      setCurrentUser(null)
      navigate('/login', { replace: true })
    })
    return () => setAbmeldeHandler(null)
  }, [navigate])

  const isAdmin = currentUser?.role === 'admin'

  /**
   * Effektive Rechte des angemeldeten Benutzers.
   *
   * Damit lassen sich Knöpfe und Dialoge sperren, statt den Benutzer erst ein
   * Formular ausfüllen zu lassen und ihn beim Speichern abzuweisen. Das ist
   * ausdrücklich **kein** Sicherheitsmerkmal — verbindlich prüft der Server
   * (deps.require_modul_rechte). Was hier passiert, ist reine Benutzerführung:
   * Eine gesperrte Funktion muss vorher erkennbar sein, sonst hält man die
   * Regel für einen Defekt.
   */
  const [rechte, setRechte] = useState(null)

  useEffect(() => {
    if (!currentUser) { setRechte(null); return }
    let abgebrochen = false
    groupsApi.meineRechte()
      .then((r) => { if (!abgebrochen) setRechte(r.data.rechte) })
      .catch(() => { /* Ohne Antwort bleibt die Oberfläche großzügig — der
                        Server weist notfalls ab. Lieber ein Knopf zu viel als
                        eine Anwendung, die nach einem Netzfehler leer wirkt. */ })
    return () => { abgebrochen = true }
  }, [currentUser])

  /** Darf der angemeldete Benutzer das? `recht` = lesen | schreiben | loeschen */
  const hasRecht = useCallback((modul, recht = 'lesen') => {
    if (isAdmin) return true
    if (!rechte) return true          // noch nicht geladen: nicht vorschnell sperren
    return !!rechte[modul]?.[recht]
  }, [isAdmin, rechte])

  /** True, wenn der Benutzer in diesem Modul nur eigene Datensätze sieht. */
  const nurEigene = useCallback((modul) => {
    if (isAdmin || !rechte) return false
    return rechte[modul]?.umfang === 'eigene'
  }, [isAdmin, rechte])

  // Modulrechte: /auth/me liefert die effektive Modul-Liste (Admin: alle;
  // null/undefined z.B. vor dem Laden = großzügig alles erlauben, das
  // Backend prüft ohnehin verbindlich).
  const modules = currentUser?.modules ?? null
  const hasModule = useCallback(
    (key) => modules === null || modules.includes(key),
    [modules]
  )

  const istAngemeldet = !!currentUser

  return (
    <AuthContext.Provider value={{
      currentUser, isAdmin, loadingAuth, reload, modules, hasModule,
      logout, istAngemeldet, setCurrentUser,
      // Rechte für die Oberfläche (siehe hasRecht) — nicht sicherheitsrelevant
      rechte, hasRecht, nurEigene,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
