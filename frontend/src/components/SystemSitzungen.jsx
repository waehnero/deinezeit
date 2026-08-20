import { useState, useEffect, useCallback } from 'react'
import { systemApi } from '../services/api'
import toast from 'react-hot-toast'
import { Users, LogOut, RefreshCw, Loader2, Monitor, Clock } from 'lucide-react'

/**
 * Wer ist gerade angemeldet — und wer hat vergessen, sich abzumelden?
 *
 * Gezeigt werden ALLE offenen Sitzungen, nicht nur die der letzten Minuten.
 * Das ist Absicht: Die Vergessenen sind ja gerade die Stillen, eine
 * Fünf-Minuten-Ansicht würde genau den Fall ausblenden, den man aufräumen will.
 *
 * Grundlage ist `user_sessions` in der Datenbank und nicht die alte Zählung im
 * Arbeitsspeicher — die stimmt nur, solange das Backend mit einem einzigen
 * Arbeitsprozess läuft.
 */

const NACHLADEN_MS = 30000

function untaetigText(minuten) {
  if (minuten === null || minuten === undefined) return 'unbekannt'
  if (minuten < 2) return 'gerade aktiv'
  if (minuten < 60) return `vor ${minuten} Min.`
  const stunden = Math.floor(minuten / 60)
  if (stunden < 24) return `vor ${stunden} Std.`
  const tage = Math.floor(stunden / 24)
  return `vor ${tage} ${tage === 1 ? 'Tag' : 'Tagen'}`
}

/** Farbe nach Untätigkeit — auf einen Blick erkennbar, wer nur „hängt". */
function untaetigFarbe(minuten) {
  if (minuten === null || minuten === undefined) return 'text-gray-400'
  if (minuten < 5) return 'text-green-600'
  if (minuten < 60) return 'text-gray-500'
  if (minuten < 480) return 'text-amber-600'
  return 'text-red-500'
}

function geraet(bezeichnung) {
  if (!bezeichnung) return 'Unbekanntes Gerät'
  return bezeichnung.length > 40 ? bezeichnung.slice(0, 40) + '…' : bezeichnung
}

export default function SystemSitzungen() {
  const [sitzungen, setSitzungen] = useState([])
  const [laden, setLaden] = useState(true)
  const [arbeitet, setArbeitet] = useState(null)   // ID, die gerade beendet wird

  const holen = useCallback(async (stillschweigend = false) => {
    if (!stillschweigend) setLaden(true)
    try {
      const res = await systemApi.listSitzungen()
      setSitzungen(res.data)
    } catch (err) {
      if (!stillschweigend) {
        toast.error(err.response?.data?.detail || 'Sitzungen konnten nicht geladen werden')
      }
    } finally {
      setLaden(false)
    }
  }, [])

  useEffect(() => {
    holen()
    // Laufend nachladen, aber ohne Fehlermeldungen im Hintergrund — sonst
    // hagelt es Meldungen, sobald das Netz kurz weg ist.
    const t = setInterval(() => holen(true), NACHLADEN_MS)
    return () => clearInterval(t)
  }, [holen])

  const beenden = async (sitzung) => {
    if (sitzung.is_current) {
      toast.error('Das ist deine eigene Sitzung — damit würdest du dich selbst abmelden.')
      return
    }
    if (!window.confirm(
      `Sitzung von ${sitzung.user_name} beenden?\n\n` +
      `Die Person wird beim nächsten Klick auf die Anmeldeseite geschickt. ` +
      `Nicht gespeicherte Eingaben gehen verloren.`)) return

    setArbeitet(sitzung.id)
    try {
      await systemApi.beendeSitzung(sitzung.id)
      toast.success(`${sitzung.user_name} wurde abgemeldet`)
      holen(true)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Beenden fehlgeschlagen')
    } finally {
      setArbeitet(null)
    }
  }

  const benutzerAbmelden = async (userId, name, anzahl) => {
    if (!window.confirm(
      `Alle ${anzahl} Geräte von ${name} abmelden?\n\n` +
      `Nicht gespeicherte Eingaben gehen verloren.`)) return

    setArbeitet(userId)
    try {
      const res = await systemApi.beendeBenutzer(userId)
      toast.success(res.data.message)
      holen(true)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Abmelden fehlgeschlagen')
    } finally {
      setArbeitet(null)
    }
  }

  // Je Benutzer zählen, damit der Sammelknopf weiß, worum es geht
  const anzahlJeBenutzer = sitzungen.reduce((acc, s) => {
    acc[s.user_id] = (acc[s.user_id] || 0) + 1
    return acc
  }, {})

  const geradeAktiv = sitzungen.filter(s => (s.untaetig_minuten ?? 999) < 5).length

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-base font-semibold text-gray-900 flex items-center gap-2">
          <Users size={16} className="text-primary-500" />
          Angemeldete Benutzer
        </h3>
        <span className="text-sm text-gray-400">
          {sitzungen.length} {sitzungen.length === 1 ? 'Sitzung' : 'Sitzungen'}
          {geradeAktiv > 0 && ` · ${geradeAktiv} gerade aktiv`}
        </span>
        <button onClick={() => holen()} disabled={laden}
          className="ml-auto p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition"
          title="Neu laden">
          <RefreshCw size={15} className={laden ? 'animate-spin' : ''} />
        </button>
      </div>

      <p className="text-xs text-gray-500 mb-3">
        Zeigt jedes angemeldete Gerät, auch wenn seit Stunden nichts mehr kam —
        so fallen vergessene Anmeldungen auf. Die Liste aktualisiert sich alle
        30 Sekunden.
      </p>

      {laden && sitzungen.length === 0 ? (
        <div className="flex items-center justify-center py-10 text-gray-400">
          <Loader2 size={22} className="animate-spin" />
        </div>
      ) : sitzungen.length === 0 ? (
        <div className="text-center py-10 text-gray-400 text-sm">
          Niemand angemeldet.
        </div>
      ) : (
        <div className="border border-gray-200 rounded-xl divide-y divide-gray-100 overflow-hidden">
          {sitzungen.map(s => (
            <div key={s.id} className="flex items-center gap-3 px-4 py-3 hover:bg-gray-50">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-gray-900">{s.user_name}</span>
                  {s.is_current && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-primary-50 text-primary-700">
                      dieses Gerät
                    </span>
                  )}
                  {anzahlJeBenutzer[s.user_id] > 1 && (
                    <span className="text-[10px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                      {anzahlJeBenutzer[s.user_id]} Geräte
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-400 flex-wrap">
                  <span className="flex items-center gap-1">
                    <Monitor size={11} /> {geraet(s.device_label)}
                  </span>
                  {s.ip_address && <span>{s.ip_address}</span>}
                  <span className={`flex items-center gap-1 ${untaetigFarbe(s.untaetig_minuten)}`}>
                    <Clock size={11} /> {untaetigText(s.untaetig_minuten)}
                  </span>
                </div>
              </div>

              {anzahlJeBenutzer[s.user_id] > 1 && (
                <button
                  onClick={() => benutzerAbmelden(s.user_id, s.user_name,
                                                  anzahlJeBenutzer[s.user_id])}
                  disabled={arbeitet === s.user_id}
                  className="text-xs px-2 py-1 rounded-lg border border-gray-200 text-gray-500 hover:text-red-600 hover:border-red-200 transition whitespace-nowrap"
                  title="Alle Geräte dieses Benutzers abmelden">
                  alle
                </button>
              )}
              {!s.is_current && (
                <button onClick={() => beenden(s)} disabled={arbeitet === s.id}
                  className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition"
                  title="Diese Sitzung beenden">
                  {arbeitet === s.id
                    ? <Loader2 size={15} className="animate-spin" />
                    : <LogOut size={15} />}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
