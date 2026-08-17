import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, Eye, EyeOff, KeyRound, Loader2, ShieldCheck } from 'lucide-react'
import toast from 'react-hot-toast'
import { version } from '../../package.json'
import { authApi } from '../services/api'

/**
 * Neues Passwort setzen — Ziel des Links aus der E-Mail.
 *
 * Der Token steht im Query-String, weil er anders nicht aus einer E-Mail in
 * die Anwendung kommt. Er ist deshalb bewusst kurzlebig (30 Minuten), genau
 * einmal verwendbar und wird serverseitig nur als Hash gespeichert.
 */
export default function ResetPasswordPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const token = params.get('token') || ''

  const [passwort, setPasswort] = useState('')
  const [wiederholung, setWiederholung] = useState('')
  const [zeigen, setZeigen] = useState(false)
  const [laeuft, setLaeuft] = useState(false)
  const [fertig, setFertig] = useState(false)

  // Reine Anzeigehilfe. Verbindlich prüft der Server (core/passwort.py) —
  // eine Prüfung, die nur im Browser läuft, ist keine Prüfung.
  const zuKurz = passwort.length > 0 && passwort.length < 10
  const ungleich = wiederholung.length > 0 && passwort !== wiederholung
  const absendbar = passwort.length >= 10 && passwort === wiederholung && !laeuft

  const absenden = async (e) => {
    e.preventDefault()
    if (!absendbar) return
    setLaeuft(true)
    try {
      const r = await authApi.resetPassword(token, passwort)
      setFertig(true)
      toast.success(r.data?.message || 'Passwort geändert.')
    } catch (err) {
      toast.error(err.response?.data?.detail
        || 'Zurücksetzen fehlgeschlagen. Bitte den Link erneut anfordern.')
    } finally {
      setLaeuft(false)
    }
  }

  return (
    <div className="min-h-screen bg-neutral-50 flex">
      {/* Linke Seite — Branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-primary-500 flex-col justify-between p-12">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-surface rounded-xl flex items-center justify-center">
            <span className="text-primary-600 font-bold text-lg">DZ</span>
          </div>
          <span className="text-white font-semibold text-xl">DeineZeit</span>
        </div>
        <div>
          <h2 className="text-white text-3xl font-bold leading-snug mb-4">
            Neues Passwort,<br />neue Ruhe.
          </h2>
          <p className="text-primary-100 text-base leading-relaxed">
            Nach dem Ändern werden alle bisherigen Anmeldungen beendet — auf
            allen Geräten. Wer sich unberechtigt Zugang verschafft hatte, ist
            damit ausgesperrt.
          </p>
        </div>
        <p className="text-primary-200 text-sm">© 2026 DeineZeit · v{version}</p>
      </div>

      {/* Rechte Seite */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <div className="flex items-center gap-3 mb-10 lg:hidden">
            <div className="w-9 h-9 bg-primary-500 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold">DZ</span>
            </div>
            <span className="text-neutral-900 font-semibold text-lg">DeineZeit</span>
          </div>

          {!token ? (
            <>
              <div className="flex items-center justify-center w-14 h-14 bg-red-50 rounded-2xl mb-6">
                <KeyRound size={28} className="text-red-500" />
              </div>
              <h1 className="text-2xl font-bold text-neutral-900 mb-2">
                Link unvollständig
              </h1>
              <p className="text-neutral-500 text-sm mb-8 leading-relaxed">
                In der Adresse fehlt der Bestätigungscode. Bitte den Link aus
                der E-Mail vollständig öffnen — manche Programme brechen lange
                Links um. Alternativ das Zurücksetzen erneut anfordern.
              </p>
              <button onClick={() => navigate('/forgot-password')}
                      className="btn-primary w-full justify-center py-2.5 mb-3">
                Erneut anfordern
              </button>
            </>
          ) : fertig ? (
            <>
              <div className="flex items-center justify-center w-14 h-14 bg-green-50 rounded-2xl mb-6">
                <ShieldCheck size={28} className="text-green-600" />
              </div>
              <h1 className="text-2xl font-bold text-neutral-900 mb-2">
                Passwort geändert
              </h1>
              <p className="text-neutral-500 text-sm mb-8 leading-relaxed">
                Sie können sich jetzt mit dem neuen Passwort anmelden. Alle
                bisherigen Anmeldungen — auch auf anderen Geräten — wurden
                beendet.
              </p>
              <button onClick={() => navigate('/login')}
                      className="btn-primary w-full justify-center py-2.5">
                Zur Anmeldung
              </button>
            </>
          ) : (
            <>
              <div className="flex items-center justify-center w-14 h-14 bg-primary-50 rounded-2xl mb-6">
                <KeyRound size={28} className="text-primary-500" />
              </div>
              <h1 className="text-2xl font-bold text-neutral-900 mb-2">
                Neues Passwort setzen
              </h1>
              <p className="text-neutral-500 text-sm mb-6 leading-relaxed">
                Mindestens 10 Zeichen. Am einfachsten ist eine Wortfolge, die
                Sie sich merken können — die ist sicherer als ein kurzes
                Passwort mit Sonderzeichen.
              </p>

              <form onSubmit={absenden} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                    Neues Passwort
                  </label>
                  <div className="relative">
                    <input
                      type={zeigen ? 'text' : 'password'}
                      value={passwort}
                      onChange={(e) => setPasswort(e.target.value)}
                      autoComplete="new-password"
                      autoFocus
                      required
                      className="input w-full pr-10"
                    />
                    <button type="button" onClick={() => setZeigen(!zeigen)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600"
                            aria-label={zeigen ? 'Passwort verbergen' : 'Passwort anzeigen'}>
                      {zeigen ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {zuKurz && (
                    <p className="text-xs text-amber-600 mt-1.5">
                      Noch {10 - passwort.length} Zeichen bis zur Mindestlänge.
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                    Passwort wiederholen
                  </label>
                  <input
                    type={zeigen ? 'text' : 'password'}
                    value={wiederholung}
                    onChange={(e) => setWiederholung(e.target.value)}
                    autoComplete="new-password"
                    required
                    className="input w-full"
                  />
                  {ungleich && (
                    <p className="text-xs text-red-600 mt-1.5">
                      Die beiden Eingaben stimmen nicht überein.
                    </p>
                  )}
                </div>

                <button type="submit" disabled={!absendbar}
                        className="btn-primary w-full justify-center py-2.5">
                  {laeuft
                    ? <><Loader2 size={16} className="animate-spin" /> Wird gespeichert…</>
                    : 'Passwort speichern'}
                </button>
              </form>
            </>
          )}

          <button onClick={() => navigate('/login')}
                  className="btn-secondary w-full justify-center py-2.5 mt-3">
            <ArrowLeft size={16} />
            Zurück zur Anmeldung
          </button>
        </div>
      </div>
    </div>
  )
}
