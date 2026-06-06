import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import { version } from '../../package.json'
import toast from 'react-hot-toast'
import { LogIn, Fingerprint, Eye, EyeOff, Check, Wrench } from 'lucide-react'
import { changelog } from '../data/changelog'

// ── News-Panel (linke Seite der Anmeldeseite) ─────────────────────────────────
function NewsPanel() {
  const [activeTab, setActiveTab] = useState('features')

  // Nur Einträge anzeigen, die im aktiven Tab Inhalt haben
  const items = changelog.filter(entry =>
    activeTab === 'features'
      ? (entry.features?.length ?? 0) > 0
      : (entry.updates?.length ?? 0) > 0
  )

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Logo */}
      <div className="flex items-center gap-3 mb-6 flex-shrink-0">
        <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
          <span className="text-white font-bold text-lg">DZ</span>
        </div>
        <span className="text-white font-semibold text-xl">DeineZeit</span>
      </div>

      {/* Tab-Leiste */}
      <div className="flex gap-1 mb-5 flex-shrink-0 bg-white/10 rounded-xl p-1">
        <button
          onClick={() => setActiveTab('features')}
          className={`flex-1 py-1.5 text-sm font-medium rounded-lg transition ${
            activeTab === 'features'
              ? 'bg-white text-primary-700 shadow-sm'
              : 'text-white/80 hover:text-white hover:bg-white/10'
          }`}
        >
          Neue Features
        </button>
        <button
          onClick={() => setActiveTab('updates')}
          className={`flex-1 py-1.5 text-sm font-medium rounded-lg transition ${
            activeTab === 'updates'
              ? 'bg-white text-primary-700 shadow-sm'
              : 'text-white/80 hover:text-white hover:bg-white/10'
          }`}
        >
          Updates
        </button>
      </div>

      {/* Zeitleiste — scrollbar, schrumpft auf verfügbaren Platz */}
      <div className="flex-1 min-h-0 overflow-y-auto space-y-6"
           style={{ scrollbarWidth: 'thin', scrollbarColor: 'rgba(255,255,255,0.25) transparent' }}>
        {items.length === 0 ? (
          <p className="text-white/60 text-sm text-center pt-8">Keine Einträge</p>
        ) : (
          items.map((entry, idx) => {
            const list = activeTab === 'features' ? (entry.features ?? []) : (entry.updates ?? [])
            const Icon = activeTab === 'features' ? Check : Wrench
            return (
              <div key={entry.version} className="flex gap-3">
                {/* Datum + Linie */}
                <div className="flex flex-col items-center flex-shrink-0 w-10">
                  <div className="w-8 h-8 rounded-full bg-white/20 flex flex-col items-center justify-center flex-shrink-0">
                    <span className="text-white font-bold leading-none text-xs">{entry.day}</span>
                    <span className="text-white/70 leading-none text-[9px]">{entry.month}</span>
                  </div>
                  {idx < items.length - 1 && (
                    <div className="w-px flex-1 bg-white/20 mt-2" />
                  )}
                </div>

                {/* Inhalt */}
                <div className="pb-2 flex-1 min-w-0">
                  <p className="text-white font-semibold text-sm mb-2">
                    v{entry.version}
                  </p>
                  <ul className="space-y-1.5">
                    {list.map((item, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <Icon size={12} className="text-white/70 mt-0.5 flex-shrink-0" />
                        <span className="text-white/80 text-xs leading-relaxed">{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )
          })
        )}
      </div>

      {/* Footer */}
      <p className="text-white/40 text-xs pt-4 flex-shrink-0">© 2026 DeineZeit · v{version}</p>
    </div>
  )
}

export default function LoginPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { reload } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [showTotp, setShowTotp] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)

  // Update-Nachricht anzeigen wenn Benutzer durch Update abgemeldet wurde
  const updateMessage = sessionStorage.getItem('update_message')
  if (updateMessage) sessionStorage.removeItem('update_message')

  const handleLogin = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await authApi.login(email, password, showTotp ? totpCode : undefined)
      const data = res.data

      if (data.requires_totp) {
        setShowTotp(true)
        toast(t('auth.totpRequired'), { icon: '🔐' })
        setLoading(false)
        return
      }

      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      await reload()
      navigate('/dashboard')
    } catch (err) {
      const detail = err.response?.data?.detail
      const msg = Array.isArray(detail)
        ? detail.map(d => d.msg).join(', ')
        : (typeof detail === 'string' ? detail : t('auth.invalidCredentials'))
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  const handlePasskeyLogin = async () => {
    if (!email) {
      toast.error('Bitte zuerst E-Mail eingeben')
      return
    }
    setLoading(true)
    try {
      const { startAuthentication } = await import('@simplewebauthn/browser')
      const optionsRes = await authApi.webauthnLoginBegin(email)
      const assertion = await startAuthentication(optionsRes.data)
      const res = await authApi.webauthnLoginComplete(email, assertion)
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      await reload()
      navigate('/dashboard')
    } catch (err) {
      if (err.name !== 'NotAllowedError') {
        const detail = err.response?.data?.detail
        toast.error(typeof detail === 'string' ? detail : 'Passkey-Login fehlgeschlagen')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-screen overflow-hidden bg-neutral-50 flex">
      {/* Linke Seite — News-Panel: feste Höhe = Fensterhöhe, kein Überlauf nach außen */}
      <div className="hidden lg:flex lg:w-5/12 bg-primary-500 flex-col p-10 h-full">
        <NewsPanel />
      </div>

      {/* Rechte Seite — Login-Formular: eigener Scroll falls Fenster sehr klein */}
      <div className="w-full lg:w-7/12 flex items-center justify-center p-8 overflow-y-auto">
        <div className="w-full max-w-sm">
          {/* Mobile Logo */}
          <div className="flex items-center gap-3 mb-10 lg:hidden">
            <div className="w-9 h-9 bg-primary-500 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold">DZ</span>
            </div>
            <span className="text-neutral-900 font-semibold text-lg">DeineZeit</span>
          </div>

          {updateMessage && (
            <div className="mb-6 p-3 bg-green-50 border border-green-200 rounded-xl text-sm text-green-800 flex items-start gap-2">
              <span className="text-green-500 mt-0.5">✓</span>
              <span>{updateMessage}</span>
            </div>
          )}

          <h1 className="text-2xl font-bold text-neutral-900 mb-1">Willkommen zurück</h1>
          <p className="text-neutral-500 text-sm mb-8">Melde dich mit deinem Konto an</p>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="label">{t('auth.email')}</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="input"
                placeholder="name@firma.at"
                autoComplete="email"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="label mb-0">{t('auth.password')}</label>
                <Link to="/forgot-password" className="text-xs text-primary-500 hover:text-primary-600 transition-colors">
                  Passwort vergessen?
                </Link>
              </div>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="input pr-10"
                  placeholder="••••••••"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600 transition-colors"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {showTotp && (
              <div>
                <label className="label">{t('auth.totpCode')}</label>
                <input
                  type="text"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="input text-center text-xl tracking-[0.4em] font-mono"
                  placeholder="000000"
                  autoComplete="one-time-code"
                  maxLength={6}
                  autoFocus
                />
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full justify-center py-2.5 mt-2"
            >
              <LogIn size={16} />
              {loading ? 'Anmelden...' : t('auth.loginButton')}
            </button>
          </form>

          <div className="relative my-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-neutral-200" />
            </div>
            <div className="relative flex justify-center text-xs">
              <span className="px-3 bg-neutral-50 text-neutral-400">oder</span>
            </div>
          </div>

          <button
            type="button"
            onClick={handlePasskeyLogin}
            className="btn-secondary w-full justify-center py-2.5"
          >
            <Fingerprint size={16} className="text-primary-500" />
            {t('auth.loginWithPasskey')}
          </button>
        </div>
      </div>
    </div>
  )
}
