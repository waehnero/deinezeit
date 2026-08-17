import { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  AlertTriangle, Clock, Loader2, LogOut, Monitor, RefreshCw, ShieldCheck, X,
} from 'lucide-react'
import { authApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'

/**
 * „Hier bist du angemeldet" — offene Sitzungen und die letzten Anmeldungen.
 *
 * Bis zu dieser Etappe gab es diese Ansicht nicht, und es hätte sie auch nicht
 * geben können: Sitzungen wurden zwar gespeichert, aber nie geprüft und waren
 * nicht widerrufbar. Wer einen Token abgegriffen hatte, blieb bis zu sieben
 * Tage drin, ohne dass es jemand sehen oder beenden konnte.
 *
 * Der zweite Teil — die letzten Ereignisse — ist bewusst für normale Benutzer
 * sichtbar und nicht nur für Administratoren. Fehlversuche auf dem eigenen
 * Konto bemerkt der Betroffene selbst am ehesten.
 */

function zeitpunkt(wert) {
  if (!wert) return '—'
  const d = new Date(wert)
  const jetzt = new Date()
  const minuten = Math.round((jetzt - d) / 60000)
  if (minuten < 1) return 'gerade eben'
  if (minuten < 60) return `vor ${minuten} Min.`
  if (minuten < 60 * 24) return `vor ${Math.round(minuten / 60)} Std.`
  return d.toLocaleString('de-AT', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function SitzungsUebersicht() {
  const { logout } = useAuth()
  const [sitzungen, setSitzungen] = useState([])
  const [ereignisse, setEreignisse] = useState([])
  const [laden, setLaden] = useState(true)
  const [beendet, setBeendet] = useState(null)

  const laden_ = useCallback(async () => {
    setLaden(true)
    try {
      const [s, e] = await Promise.all([
        authApi.sessions(),
        authApi.events(15).catch(() => ({ data: [] })),
      ])
      setSitzungen(s.data || [])
      setEreignisse(e.data || [])
    } catch {
      toast.error('Sitzungen konnten nicht geladen werden')
    } finally {
      setLaden(false)
    }
  }, [])

  useEffect(() => { laden_() }, [laden_])

  const beenden = async (sitzung) => {
    setBeendet(sitzung.id)
    try {
      await authApi.revokeSession(sitzung.id)
      if (sitzung.is_current) {
        // Die eigene Sitzung zu beenden ist ein Abmelden.
        toast.success('Abgemeldet')
        logout()
        return
      }
      toast.success(`„${sitzung.device_label || 'Gerät'}" wurde abgemeldet`)
      laden_()
    } catch {
      toast.error('Sitzung konnte nicht beendet werden')
    } finally {
      setBeendet(null)
    }
  }

  const alleBeenden = async () => {
    if (!window.confirm(
      'Wirklich von allen Geräten abmelden? Sie müssen sich danach neu anmelden.'
    )) return
    await logout({ alleGeraete: true })
  }

  const auffaellige = ereignisse.filter((e) => e.suspicious)

  return (
    <div className="space-y-6">
      {/* ── Offene Sitzungen ───────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Monitor size={16} className="text-gray-500" />
            <h3 className="font-semibold text-gray-900">Angemeldete Geräte</h3>
          </div>
          <button onClick={laden_} disabled={laden}
                  className="text-gray-400 hover:text-gray-600 transition"
                  aria-label="Aktualisieren">
            <RefreshCw size={14} className={laden ? 'animate-spin' : ''} />
          </button>
        </div>

        <p className="text-sm text-gray-500 mb-4">
          Jede Anmeldung an einem Gerät erscheint hier. Kommt Ihnen ein Eintrag
          fremd vor, beenden Sie ihn und ändern Sie anschließend Ihr Passwort.
        </p>

        {laden && sitzungen.length === 0 ? (
          <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
            <Loader2 size={14} className="animate-spin" /> Wird geladen…
          </div>
        ) : sitzungen.length === 0 ? (
          <p className="text-sm text-gray-500 py-4">Keine offenen Sitzungen.</p>
        ) : (
          <div className="space-y-2">
            {sitzungen.map((s) => (
              <div key={s.id}
                   className={`flex items-center justify-between gap-3 p-3 rounded-xl border ${
                     s.is_current
                       ? 'border-primary-200 bg-primary-50'
                       : 'border-gray-200 bg-white'
                   }`}>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-gray-900 text-sm">
                      {s.device_label || 'Unbekanntes Gerät'}
                    </span>
                    {s.is_current && (
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 font-medium">
                        dieses Gerät
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5 flex items-center gap-3 flex-wrap">
                    {s.ip_address && <span>IP {s.ip_address}</span>}
                    <span className="flex items-center gap-1">
                      <Clock size={11} /> zuletzt {zeitpunkt(s.last_used_at || s.created_at)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={() => beenden(s)}
                  disabled={beendet === s.id}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs border border-gray-300 text-gray-700 hover:bg-gray-50 rounded-lg transition flex-shrink-0"
                >
                  {beendet === s.id
                    ? <Loader2 size={12} className="animate-spin" />
                    : <X size={12} />}
                  Beenden
                </button>
              </div>
            ))}
          </div>
        )}

        {sitzungen.length > 1 && (
          <button onClick={alleBeenden}
                  className="mt-3 flex items-center gap-2 px-4 py-2 text-sm border border-red-200 text-red-700 hover:bg-red-50 rounded-xl transition">
            <LogOut size={14} />
            Von allen Geräten abmelden
          </button>
        )}
      </div>

      {/* ── Letzte Ereignisse ──────────────────────────────────────────────── */}
      <div className="pt-4 border-t border-gray-200">
        <div className="flex items-center gap-2 mb-3">
          <ShieldCheck size={16} className="text-gray-500" />
          <h3 className="font-semibold text-gray-900">Letzte Anmeldungen</h3>
        </div>

        {auffaellige.length > 0 && (
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-xl p-3 mb-3">
            <AlertTriangle size={16} className="text-amber-600 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-amber-900">
              {auffaellige.length === 1
                ? 'Ein Eintrag unten ist auffällig'
                : `${auffaellige.length} Einträge unten sind auffällig`}
              {' '}(zum Beispiel fehlgeschlagene Anmeldungen). Waren Sie das
              nicht, ändern Sie bitte Ihr Passwort.
            </p>
          </div>
        )}

        {ereignisse.length === 0 ? (
          <p className="text-sm text-gray-500">Noch keine Einträge.</p>
        ) : (
          <div className="space-y-1">
            {ereignisse.map((e) => (
              <div key={e.id}
                   className="flex items-center justify-between gap-3 text-sm py-1.5">
                <span className={e.suspicious ? 'text-amber-700' : 'text-gray-700'}>
                  {e.label || e.event}
                  {e.detail && <span className="text-gray-400"> · {e.detail}</span>}
                </span>
                <span className="text-xs text-gray-400 flex-shrink-0">
                  {e.ip_address ? `${e.ip_address} · ` : ''}{zeitpunkt(e.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
