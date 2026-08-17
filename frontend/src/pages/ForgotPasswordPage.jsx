import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ShieldAlert, Loader2, MailCheck } from 'lucide-react'
import toast from 'react-hot-toast'
import { version } from '../../package.json'
import { authApi } from '../services/api'

/**
 * „Passwort vergessen" — jetzt mit Funktion.
 *
 * Diese Seite existierte bereits, war aber eine reine Auskunftsseite („bitte
 * wende dich an einen Administrator"). Der zugehörige Endpunkt fehlte im
 * Backend vollständig. Für eine selbst-gehostete Installation ist das ein
 * echtes Problem: Wenn der Administrator selbst sein Passwort vergisst, gibt
 * es niemanden, der zurücksetzen kann.
 */
export default function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [laeuft, setLaeuft] = useState(false)
  const [gesendet, setGesendet] = useState(false)

  const absenden = async (e) => {
    e.preventDefault()
    if (!email.trim()) return
    setLaeuft(true)
    try {
      const r = await authApi.forgotPassword(email.trim())
      // Die Antwort ist absichtlich immer dieselbe — auch für unbekannte
      // Adressen. Sonst ließe sich über diese Seite herausfinden, welche
      // E-Mail-Adressen im System hinterlegt sind.
      setGesendet(true)
      toast.success(r.data?.message || 'Nachricht verschickt, falls ein Konto besteht.')
    } catch (err) {
      const status = err.response?.status
      if (status === 429) {
        toast.error('Zu viele Anfragen. Bitte versuchen Sie es später erneut.')
      } else {
        toast.error(err.response?.data?.detail
          || 'Anfrage fehlgeschlagen. Bitte später erneut versuchen.')
      }
    } finally {
      setLaeuft(false)
    }
  }

  return (
    <div className="min-h-screen bg-neutral-50 flex">
      {/* Linke Seite — Branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-primary-500 flex-col justify-between p-12">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-surface rounded-xl flex items-center justify-center">
              <span className="text-primary-600 font-bold text-lg">DZ</span>
            </div>
            <span className="text-white font-semibold text-xl">DeineZeit</span>
          </div>
        </div>
        <div>
          <h2 className="text-white text-3xl font-bold leading-snug mb-4">
            Deine Stammdaten.<br />Deine Regeln.
          </h2>
          <p className="text-primary-100 text-base leading-relaxed">
            Flexible Datenverwaltung für Kunden, Lieferanten und Projekte —
            angepasst an dein Unternehmen, nicht umgekehrt.
          </p>
        </div>
        <p className="text-primary-200 text-sm">© 2026 DeineZeit · v{version}</p>
      </div>

      {/* Rechte Seite — Info */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          {/* Mobile Logo */}
          <div className="flex items-center gap-3 mb-10 lg:hidden">
            <div className="w-9 h-9 bg-primary-500 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold">DZ</span>
            </div>
            <span className="text-neutral-900 font-semibold text-lg">DeineZeit</span>
          </div>

          <div className="flex items-center justify-center w-14 h-14 bg-primary-50 rounded-2xl mb-6">
            <ShieldAlert size={28} className="text-primary-500" />
          </div>

          {gesendet ? (
            <>
              <h1 className="text-2xl font-bold text-neutral-900 mb-2">
                E-Mail unterwegs
              </h1>
              <div className="bg-primary-50 border border-primary-200 rounded-xl p-5 mb-8">
                <div className="flex items-start gap-3">
                  <MailCheck size={20} className="text-primary-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-neutral-700 space-y-2">
                    <p>
                      Falls ein Konto mit <strong>{email}</strong> besteht, ist eine
                      Nachricht mit einem Link zum Zurücksetzen unterwegs.
                    </p>
                    <p>
                      Der Link ist 30 Minuten gültig und funktioniert einmal.
                      Bitte auch den Spam-Ordner prüfen.
                    </p>
                  </div>
                </div>
              </div>
              <p className="text-xs text-neutral-500 mb-6 leading-relaxed">
                Keine E-Mail erhalten? Dann ist für diese Adresse kein Konto
                hinterlegt, oder der E-Mail-Versand ist auf dem Server noch
                nicht eingerichtet. In diesem Fall hilft ein Administrator
                weiter — er kann das Passwort in der Benutzerverwaltung direkt
                neu setzen.
              </p>
            </>
          ) : (
            <>
              <h1 className="text-2xl font-bold text-neutral-900 mb-2">Passwort vergessen?</h1>
              <p className="text-neutral-500 text-sm mb-6 leading-relaxed">
                E-Mail-Adresse eingeben — wir schicken einen Link, mit dem ein
                neues Passwort gesetzt werden kann.
              </p>

              <form onSubmit={absenden} className="space-y-4 mb-6">
                <div>
                  <label className="block text-sm font-medium text-neutral-700 mb-1.5">
                    E-Mail-Adresse
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="username"
                    autoFocus
                    required
                    className="input w-full"
                    placeholder="name@firma.at"
                  />
                </div>
                <button
                  type="submit"
                  disabled={laeuft}
                  className="btn-primary w-full justify-center py-2.5"
                >
                  {laeuft
                    ? <><Loader2 size={16} className="animate-spin" /> Wird gesendet…</>
                    : 'Link zum Zurücksetzen senden'}
                </button>
              </form>

              <p className="text-xs text-neutral-500 mb-6 leading-relaxed">
                Kein Zugriff auf das E-Mail-Postfach? Dann kann ein
                Administrator das Passwort in der Benutzerverwaltung direkt neu
                setzen und bei Bedarf die 2-Faktor-Authentifizierung
                zurücksetzen.
              </p>
            </>
          )}

          <button
            onClick={() => navigate('/login')}
            className="btn-secondary w-full justify-center py-2.5"
          >
            <ArrowLeft size={16} />
            Zurück zur Anmeldung
          </button>
        </div>
      </div>
    </div>
  )
}
