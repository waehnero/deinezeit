import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, X } from 'lucide-react'
import { systemApi } from '../services/api'

/**
 * Globales Update-Banner: polling /api/system/update-status alle 15 Sekunden.
 * Zeigt Countdown wenn ein Update ansteht, meldet Benutzer automatisch ab.
 */
export default function UpdateBanner() {
  const navigate = useNavigate()
  const [status, setStatus]       = useState(null)
  const [countdown, setCountdown] = useState(0)

  // Polling: Update-Status vom Backend abfragen
  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) return

    const poll = async () => {
      try {
        const res = await systemApi.getUpdateStatus()
        const data = res.data
        setStatus(data)
        if (data.status === 'notifying') {
          setCountdown(data.countdown_seconds || 0)
        } else if (data.status === 'updating') {
          // Backend startet neu — abmelden und warten
          handleLogout('Das System wird aktualisiert. Bitte in einigen Minuten erneut anmelden.')
        }
      } catch {
        // Backend nicht erreichbar — kein Banner
      }
    }

    poll()
    const interval = setInterval(poll, 15_000)
    return () => clearInterval(interval)
  }, [])

  // Lokaler Countdown-Timer (sekündlich herunterzählen)
  useEffect(() => {
    if (status?.status !== 'notifying' || countdown <= 0) return

    const timer = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(timer)
          return 0
        }
        return prev - 1
      })
    }, 1_000)

    return () => clearInterval(timer)
  }, [status?.status, countdown > 0])

  // Automatisch abmelden wenn Countdown abgelaufen
  useEffect(() => {
    if (status?.status === 'notifying' && countdown === 0) {
      handleLogout('Das System wird jetzt aktualisiert. Bitte in einigen Minuten erneut anmelden.')
    }
  }, [countdown])

  const handleLogout = useCallback((message) => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    sessionStorage.setItem('update_message', message)
    navigate('/login')
  }, [navigate])

  if (!status || status.status !== 'notifying') return null

  const minutes = Math.floor(countdown / 60)
  const seconds = countdown % 60
  const countdownStr = `${minutes}:${String(seconds).padStart(2, '0')}`

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500 text-white px-4 py-2.5 flex items-center gap-3 shadow-lg">
      <AlertTriangle size={16} className="flex-shrink-0" />
      <span className="text-sm font-medium flex-1">
        <strong>System-Update:</strong> {status.message}
        {countdown > 0 && (
          <span className="ml-2 font-mono bg-amber-600 px-2 py-0.5 rounded text-xs">
            {countdownStr}
          </span>
        )}
      </span>
      <span className="text-xs text-amber-100 flex-shrink-0">
        Sie werden automatisch abgemeldet.
      </span>
    </div>
  )
}
