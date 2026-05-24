import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, Link } from 'react-router-dom'
import { authApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import { LogIn, Fingerprint, Eye, EyeOff } from 'lucide-react'

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
    try {
      const { startAuthentication } = await import('@simplewebauthn/browser')
      const optionsRes = await authApi.webauthnLoginBegin(email)
      const assertion = await startAuthentication(optionsRes.data)
      toast.success('Passkey-Login erfolgreich')
    } catch (err) {
      toast.error('Passkey-Login fehlgeschlagen')
    }
  }

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

      {/* Rechte Seite — Login-Formular */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          {/* Mobile Logo */}
          <div className="flex items-center gap-3 mb-10 lg:hidden">
            <div className="w-9 h-9 bg-primary-500 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold">DZ</span>
            </div>
            <span className="text-neutral-900 font-semibold text-lg">DeineZeit</span>
          </div>

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
