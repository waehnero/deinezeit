import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ShieldAlert, Mail, Phone } from 'lucide-react'

export default function ForgotPasswordPage() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-neutral-50 flex">
      {/* Linke Seite — Branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-primary-500 flex-col justify-between p-12">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-white rounded-xl flex items-center justify-center">
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
        <p className="text-primary-200 text-sm">© 2026 DeineZeit · v0.3.0</p>
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

          <h1 className="text-2xl font-bold text-neutral-900 mb-2">Passwort vergessen?</h1>
          <p className="text-neutral-500 text-sm mb-8 leading-relaxed">
            Passwörter können in DeineZeit nur von einem Administrator zurückgesetzt werden.
            Bitte wende dich direkt an deine zuständige Ansprechperson.
          </p>

          <div className="bg-neutral-50 border border-neutral-200 rounded-xl p-5 space-y-4 mb-8">
            <p className="text-xs font-semibold text-neutral-500 uppercase tracking-wide">Was der Administrator für dich erledigt</p>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-primary-700 text-xs font-bold">1</span>
                </div>
                <p className="text-sm text-neutral-700">Ein neues Passwort für deinen Account vergeben</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-primary-700 text-xs font-bold">2</span>
                </div>
                <p className="text-sm text-neutral-700">Bei Bedarf die 2-Faktor-Authentifizierung zurücksetzen</p>
              </div>
              <div className="flex items-start gap-3">
                <div className="w-6 h-6 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <span className="text-primary-700 text-xs font-bold">3</span>
                </div>
                <p className="text-sm text-neutral-700">Du kannst dich danach sofort wieder anmelden</p>
              </div>
            </div>
          </div>

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
