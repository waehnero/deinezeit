import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { authApi, usersApi } from '../services/api'
import MailKonten from '../components/MailImportVerwaltung'
import toast from 'react-hot-toast'
import {
  User, Globe, Shield, Fingerprint, Key,
  Check, Loader2, Eye, EyeOff, Smartphone, Trash2
} from 'lucide-react'
import AnzeigeEinstellungen from '../components/AnzeigeEinstellungen'

export default function ProfilePage() {
  const { t, i18n } = useTranslation()
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // Profilfelder
  const [fullName, setFullName] = useState('')
  const [language, setLanguage] = useState('de')
  const [savingProfile, setSavingProfile] = useState(false)

  // Passwort
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [showPw, setShowPw] = useState(false)
  const [savingPw, setSavingPw] = useState(false)

  // TOTP
  const [totpStep, setTotpStep] = useState('idle')  // idle | setup | verify
  const [totpData, setTotpData] = useState(null)
  const [totpCode, setTotpCode] = useState('')
  const [totpLoading, setTotpLoading] = useState(false)

  useEffect(() => {
    authApi.me().then(r => {
      setUser(r.data)
      setFullName(r.data.full_name)
      setLanguage(r.data.language)
    }).finally(() => setLoading(false))
  }, [])

  const handleSaveProfile = async (e) => {
    e.preventDefault()
    setSavingProfile(true)
    try {
      const res = await usersApi.updateMe({ full_name: fullName, language })
      setUser(res.data)
      i18n.changeLanguage(language)
      localStorage.setItem('i18nextLng', language)
      toast.success(t('common.success'))
    } catch {
      toast.error(t('common.error'))
    } finally {
      setSavingProfile(false)
    }
  }

  const handleSavePassword = async (e) => {
    e.preventDefault()
    if (newPassword.length < 8) {
      toast.error('Passwort muss mindestens 8 Zeichen lang sein')
      return
    }
    setSavingPw(true)
    try {
      await usersApi.updateMe({ password: newPassword })
      toast.success('Passwort erfolgreich geändert')
      setCurrentPassword(''); setNewPassword('')
    } catch {
      toast.error('Passwort konnte nicht geändert werden')
    } finally {
      setSavingPw(false)
    }
  }

  const handleSetupTotp = async () => {
    setTotpLoading(true)
    try {
      const res = await authApi.setupTotp()
      setTotpData(res.data)
      setTotpStep('setup')
    } catch {
      toast.error('2FA-Setup fehlgeschlagen')
    } finally {
      setTotpLoading(false)
    }
  }

  const handleEnableTotp = async () => {
    setTotpLoading(true)
    try {
      await authApi.enableTotp(totpData.secret, totpCode)
      toast.success('2FA erfolgreich aktiviert!')
      setUser({ ...user, totp_enabled: true })
      setTotpStep('idle'); setTotpCode('')
    } catch {
      toast.error('Code ungültig. Bitte erneut versuchen.')
    } finally {
      setTotpLoading(false)
    }
  }

  const handleDisableTotp = async () => {
    if (!totpCode) { setTotpStep('verify'); return }
    setTotpLoading(true)
    try {
      await authApi.disableTotp(totpCode)
      toast.success('2FA deaktiviert')
      setUser({ ...user, totp_enabled: false })
      setTotpStep('idle'); setTotpCode('')
    } catch {
      toast.error('Code ungültig')
    } finally {
      setTotpLoading(false)
    }
  }

  const handleAddPasskey = async () => {
    try {
      const { startRegistration } = await import('@simplewebauthn/browser')
      const optRes = await authApi.webauthnRegisterBegin()
      const credential = await startRegistration(optRes.data)
      await authApi.webauthnRegisterComplete(credential, 'Mein Gerät')
      toast.success('Passkey erfolgreich hinzugefügt')
    } catch (err) {
      if (err.name !== 'NotAllowedError') {
        toast.error('Passkey konnte nicht registriert werden')
      }
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 size={32} className="animate-spin text-primary-500" />
    </div>
  )

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{t('profile.title')}</h1>

      <div className="space-y-4">

        {/* ── Profil ── */}
        <div className="bg-surface rounded-2xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <User size={18} className="text-gray-400" /> Persönliche Daten
          </h2>
          <form onSubmit={handleSaveProfile} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
              <input type="text" value={fullName} onChange={e => setFullName(e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">E-Mail</label>
              <input type="email" value={user?.email} disabled
                className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm bg-gray-50 text-gray-500" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-2">
                <Globe size={14} /> {t('profile.language')}
              </label>
              <div className="flex gap-2">
                {[{ code: 'de', label: 'Deutsch' }, { code: 'en', label: 'English' }].map(lang => (
                  <button key={lang.code} type="button"
                    onClick={() => setLanguage(lang.code)}
                    className={`px-4 py-2 rounded-xl text-sm font-medium border-2 transition ${
                      language === lang.code
                        ? 'border-primary-500 bg-primary-50 text-primary-700'
                        : 'border-gray-200 text-gray-600 hover:border-gray-300'
                    }`}>
                    {lang.label}
                  </button>
                ))}
              </div>
            </div>
            <button type="submit" disabled={savingProfile}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white text-sm font-medium rounded-xl transition">
              {savingProfile ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              {t('common.save')}
            </button>
          </form>
        </div>

        {/* ── Anzeige & Barrierefreiheit (pro Benutzer/Gerät) ── */}
        <AnzeigeEinstellungen />

        {/* ── Passwort ── */}
        <div className="bg-surface rounded-2xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <Key size={18} className="text-gray-400" /> Passwort ändern
          </h2>
          <form onSubmit={handleSavePassword} className="space-y-3">
            <div className="relative">
              <input type={showPw ? 'text' : 'password'}
                value={newPassword} onChange={e => setNewPassword(e.target.value)}
                placeholder="Neues Passwort (min. 8 Zeichen)"
                className="w-full px-4 py-2.5 pr-10 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
              <button type="button" onClick={() => setShowPw(!showPw)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400">
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <button type="submit" disabled={savingPw || newPassword.length < 8}
              className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white text-sm font-medium rounded-xl transition">
              {savingPw ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
              Passwort speichern
            </button>
          </form>
        </div>

        {/* ── 2FA (TOTP) ── */}
        <div className="bg-surface rounded-2xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-1 flex items-center gap-2">
            <Shield size={18} className="text-gray-400" /> {t('profile.twoFactor')}
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            {user?.totp_enabled ? t('profile.twoFactorEnabled') : t('profile.twoFactorDisabled')}
          </p>

          {!user?.totp_enabled && totpStep === 'idle' && (
            <button onClick={handleSetupTotp} disabled={totpLoading}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-sm text-gray-700 hover:bg-gray-50 rounded-xl transition">
              {totpLoading ? <Loader2 size={14} className="animate-spin" /> : <Smartphone size={14} />}
              {t('profile.enableTotp')}
            </button>
          )}

          {totpStep === 'setup' && totpData && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">
                Scannen Sie diesen QR-Code mit <strong>Google Authenticator</strong>, <strong>Authy</strong> oder einer anderen Authenticator-App:
              </p>
              <img src={totpData.qr_code_url} alt="QR-Code für 2FA"
                className="w-48 h-48 border border-gray-200 rounded-xl p-2" />
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  6-stelligen Code aus der App eingeben:
                </label>
                <input type="text" value={totpCode}
                  onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                  className="w-40 px-4 py-2 border border-gray-300 rounded-xl text-center font-mono text-xl tracking-widest focus:outline-none focus:ring-2 focus:ring-primary-500"
                  placeholder="000000" maxLength={6} autoFocus />
              </div>
              <div className="flex gap-2">
                <button onClick={handleEnableTotp} disabled={totpCode.length !== 6 || totpLoading}
                  className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white text-sm font-medium rounded-xl transition">
                  {totpLoading ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
                  2FA aktivieren
                </button>
                <button onClick={() => { setTotpStep('idle'); setTotpCode('') }}
                  className="px-4 py-2 border border-gray-300 text-gray-600 text-sm rounded-xl hover:bg-gray-50 transition">
                  Abbrechen
                </button>
              </div>
            </div>
          )}

          {user?.totp_enabled && (
            <div>
              {totpStep !== 'verify' ? (
                <button onClick={() => setTotpStep('verify')}
                  className="flex items-center gap-2 px-4 py-2 border border-red-200 text-red-600 text-sm hover:bg-red-50 rounded-xl transition">
                  <Trash2 size={14} /> {t('profile.disableTotp')}
                </button>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-gray-600">Code aus der Authenticator-App eingeben um 2FA zu deaktivieren:</p>
                  <input type="text" value={totpCode}
                    onChange={e => setTotpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    className="w-40 px-4 py-2 border border-gray-300 rounded-xl text-center font-mono text-xl tracking-widest focus:outline-none focus:ring-2 focus:ring-red-400"
                    placeholder="000000" maxLength={6} autoFocus />
                  <div className="flex gap-2">
                    <button onClick={handleDisableTotp} disabled={totpCode.length !== 6 || totpLoading}
                      className="flex items-center gap-2 px-4 py-2 bg-red-500 hover:bg-red-600 disabled:bg-red-300 text-white text-sm font-medium rounded-xl transition">
                      {totpLoading ? <Loader2 size={14} className="animate-spin" /> : null}
                      2FA deaktivieren
                    </button>
                    <button onClick={() => { setTotpStep('idle'); setTotpCode('') }}
                      className="px-4 py-2 border border-gray-300 text-gray-600 text-sm rounded-xl hover:bg-gray-50 transition">
                      Abbrechen
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Passkeys / Face ID ── */}
        <div className="bg-surface rounded-2xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-1 flex items-center gap-2">
            <Fingerprint size={18} className="text-gray-400" /> {t('profile.passkeys')}
          </h2>
          <p className="text-sm text-gray-500 mb-4">
            Mit Face ID oder Fingerabdruck anmelden — kein Passwort nötig.
          </p>
          <button onClick={handleAddPasskey}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-sm text-gray-700 hover:bg-gray-50 rounded-xl transition">
            <Fingerprint size={14} />
            {t('profile.addPasskey')}
          </button>
          <p className="text-xs text-gray-400 mt-2">
            Unterstützt Face ID (iPhone), Touch ID (Mac), Windows Hello und Android-Fingerabdruck.
          </p>
        </div>

        {/* ── Mail-Import (persönliche Konten, Aufgabenmodul) ── */}
        <div className="bg-surface rounded-2xl border border-gray-200 p-6">
          <MailKonten />
        </div>

      </div>
    </div>
  )
}
