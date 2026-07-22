import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import toast from 'react-hot-toast'
import { Loader2, Rocket, Eye, EyeOff, ArrowRight, ArrowLeft, Check, Building2, ImagePlus } from 'lucide-react'
import { setupApi, settingsApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import { useSettings } from '../contexts/SettingsContext'
import { version } from '../../package.json'

// ── Willkommens-Panel (linke Seite) ──────────────────────────────────────────
function WelcomePanel({ step }) {
  const steps = [
    { nr: 1, titel: 'Administrator anlegen', text: 'Dein persönliches Konto mit vollen Rechten.' },
    { nr: 2, titel: 'Firma erfassen', text: 'Stammdaten für Briefkopf und Rechnungen (optional).' },
  ]
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-3 mb-8 flex-shrink-0">
        <div className="w-10 h-10 bg-white/20 rounded-xl flex items-center justify-center">
          <span className="text-white font-bold text-lg">DZ</span>
        </div>
        <span className="text-white font-semibold text-xl">DeineZeit</span>
      </div>

      <h2 className="text-white text-2xl font-bold mb-2">Willkommen bei DeineZeit</h2>
      <p className="text-white/70 text-sm mb-8">
        Nur noch wenige Schritte bis zu deiner einsatzbereiten Installation.
      </p>

      <div className="space-y-4">
        {steps.map((s) => {
          const done = step > s.nr
          const active = step === s.nr
          return (
            <div key={s.nr} className={`flex items-start gap-3 rounded-xl p-3 transition ${active ? 'bg-white/15' : 'bg-white/5'}`}>
              <div className={`w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 text-sm font-semibold ${done ? 'bg-white text-primary-700' : active ? 'bg-white/90 text-primary-700' : 'bg-white/20 text-white/80'}`}>
                {done ? <Check size={16} /> : s.nr}
              </div>
              <div>
                <div className="text-white font-medium text-sm">{s.titel}</div>
                <div className="text-white/60 text-xs">{s.text}</div>
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-white/40 text-xs pt-8 mt-auto flex-shrink-0">© 2026 DeineZeit · v{version}</p>
    </div>
  )
}

export default function SetupPage() {
  const navigate = useNavigate()
  const { reload } = useAuth()
  const { loadSettings } = useSettings()

  const [checking, setChecking] = useState(true)
  const [step, setStep] = useState(1)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  // Schritt 1 – Admin
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [password2, setPassword2] = useState('')

  // Schritt 2 – Firma (optional)
  const [company, setCompany] = useState({
    firmenname: '', ansprechperson: '', email: '', telefon: '',
    adresse: '', plz: '', ort: '', land: '', uid: '', iban: '', bic: '', bankname: '',
  })
  const [logoFile, setLogoFile] = useState(null)
  const [logoPreview, setLogoPreview] = useState(null)

  // Vorschau-URL fuer das gewaehlte Logo erzeugen und wieder freigeben
  useEffect(() => {
    if (!logoFile) { setLogoPreview(null); return }
    const url = URL.createObjectURL(logoFile)
    setLogoPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [logoFile])

  // Assistent nur zeigen, solange noch kein Benutzer existiert
  useEffect(() => {
    setupApi.status()
      .then((r) => {
        if (!r.data.needs_setup) { navigate('/login', { replace: true }) }
        else setChecking(false)
      })
      .catch(() => setChecking(false))
  }, [navigate])

  const updateCompany = (key) => (e) =>
    setCompany((c) => ({ ...c, [key]: e.target.value }))

  const goToStep2 = (e) => {
    e.preventDefault()
    if (!fullName.trim()) return toast.error('Bitte deinen Namen angeben.')
    if (!email.trim() || !email.includes('@')) return toast.error('Bitte eine gültige E-Mail-Adresse angeben.')
    if (password.length < 8) return toast.error('Das Passwort muss mindestens 8 Zeichen lang sein.')
    if (password !== password2) return toast.error('Die Passwörter stimmen nicht überein.')
    setStep(2)
  }

  const finish = async (withCompany) => {
    setLoading(true)
    try {
      const payload = {
        admin_email: email.trim(),
        admin_full_name: fullName.trim(),
        admin_password: password,
        language: 'de',
        company: withCompany && company.firmenname.trim() ? company : null,
      }
      const res = await setupApi.init(payload)
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)

      // Logo optional hochladen (benötigt das eben erhaltene Token)
      if (withCompany && logoFile) {
        try { await settingsApi.uploadLogo(logoFile) }
        catch { toast('Logo konnte nicht hochgeladen werden — später in den Einstellungen möglich.', { icon: '⚠️' }) }
      }

      await reload()
      // Einstellungen (Firmenname, Logo, Briefkopf) sofort neu laden, damit
      // sie direkt im Dashboard/den Einstellungen sichtbar sind — ohne Re-Login.
      try { await loadSettings() } catch { /* Standardwerte behalten */ }
      toast.success('Einrichtung abgeschlossen. Willkommen!')
      navigate('/dashboard', { replace: true })
    } catch (err) {
      const detail = err.response?.data?.detail
      const msg = Array.isArray(detail) ? detail.map((d) => d.msg).join(', ')
        : (typeof detail === 'string' ? detail : 'Einrichtung fehlgeschlagen.')
      toast.error(msg)
      setLoading(false)
    }
  }

  if (checking) {
    return (
      <div className="h-screen flex items-center justify-center bg-neutral-50">
        <Loader2 size={28} className="animate-spin text-primary-500" />
      </div>
    )
  }

  return (
    <div className="h-screen overflow-hidden bg-neutral-50 flex">
      {/* Linke Seite */}
      <div className="hidden lg:flex lg:w-5/12 bg-primary-500 flex-col p-10 h-full">
        <WelcomePanel step={step} />
      </div>

      {/* Rechte Seite */}
      <div className="w-full lg:w-7/12 flex items-center justify-center p-8 overflow-y-auto">
        <div className="w-full max-w-md">
          {step === 1 && (
            <>
              <div className="flex items-center gap-2 mb-1">
                <Rocket size={22} className="text-primary-500" />
                <h1 className="text-2xl font-bold text-neutral-900">Ersteinrichtung</h1>
              </div>
              <p className="text-neutral-500 text-sm mb-8">Lege deinen Administrator-Zugang an. Er hat volle Rechte.</p>

              <form onSubmit={goToStep2} className="space-y-4">
                <div>
                  <label className="label">Name</label>
                  <input className="input" value={fullName} onChange={(e) => setFullName(e.target.value)}
                    required placeholder="Vor- und Nachname" autoComplete="name" autoFocus />
                </div>
                <div>
                  <label className="label">E-Mail</label>
                  <input type="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)}
                    required placeholder="name@firma.at" autoComplete="username" />
                </div>
                <div>
                  <label className="label">Passwort</label>
                  <div className="relative">
                    <input type={showPassword ? 'text' : 'password'} className="input pr-10"
                      value={password} onChange={(e) => setPassword(e.target.value)}
                      required placeholder="mindestens 8 Zeichen" autoComplete="new-password" />
                    <button type="button" onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-400 hover:text-neutral-600">
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="label">Passwort bestätigen</label>
                  <input type={showPassword ? 'text' : 'password'} className="input"
                    value={password2} onChange={(e) => setPassword2(e.target.value)}
                    required placeholder="••••••••" autoComplete="new-password" />
                </div>

                <button type="submit" className="btn-primary w-full justify-center py-2.5 mt-2">
                  Weiter <ArrowRight size={16} />
                </button>
              </form>
            </>
          )}

          {step === 2 && (
            <>
              <div className="flex items-center gap-2 mb-1">
                <Building2 size={22} className="text-primary-500" />
                <h1 className="text-2xl font-bold text-neutral-900">Firma erfassen</h1>
              </div>
              <p className="text-neutral-500 text-sm mb-6">
                Diese Daten werden als Firmen-Kontakt angelegt und als Briefkopf verknüpft. Alles optional — du kannst es später in den Einstellungen ergänzen.
              </p>

              <div className="space-y-4 max-h-[55vh] overflow-y-auto pr-1">
                <div>
                  <label className="label">Firmenname</label>
                  <input className="input" value={company.firmenname} onChange={updateCompany('firmenname')}
                    placeholder="z.B. Muster GmbH" autoFocus />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="label">Ansprechperson</label>
                    <input className="input" value={company.ansprechperson} onChange={updateCompany('ansprechperson')} placeholder="Vor- und Nachname" />
                  </div>
                  <div>
                    <label className="label">UID-Nummer</label>
                    <input className="input" value={company.uid} onChange={updateCompany('uid')} placeholder="ATU12345678" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="label">E-Mail</label>
                    <input type="email" className="input" value={company.email} onChange={updateCompany('email')} placeholder="info@firma.at" />
                  </div>
                  <div>
                    <label className="label">Telefon</label>
                    <input className="input" value={company.telefon} onChange={updateCompany('telefon')} placeholder="+43 1 234 567" />
                  </div>
                </div>
                <div>
                  <label className="label">Adresse</label>
                  <input className="input" value={company.adresse} onChange={updateCompany('adresse')} placeholder="Straße und Hausnummer" />
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="label">PLZ</label>
                    <input className="input" value={company.plz} onChange={updateCompany('plz')} placeholder="1010" />
                  </div>
                  <div>
                    <label className="label">Ort</label>
                    <input className="input" value={company.ort} onChange={updateCompany('ort')} placeholder="Wien" />
                  </div>
                  <div>
                    <label className="label">Land</label>
                    <input className="input" value={company.land} onChange={updateCompany('land')} placeholder="Österreich" />
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                  <div className="col-span-2">
                    <label className="label">IBAN</label>
                    <input className="input" value={company.iban} onChange={updateCompany('iban')} placeholder="AT12 3456 …" />
                  </div>
                  <div>
                    <label className="label">BIC</label>
                    <input className="input" value={company.bic} onChange={updateCompany('bic')} placeholder="BKAUATWW" />
                  </div>
                </div>
                <div>
                  <label className="label">Bankname</label>
                  <input className="input" value={company.bankname} onChange={updateCompany('bankname')} placeholder="z.B. Bank Austria" />
                </div>
                <div>
                  <label className="label flex items-center gap-1"><ImagePlus size={14} /> Logo (optional)</label>
                  <input type="file" accept=".png,.jpg,.jpeg,.svg,.webp"
                    onChange={(e) => setLogoFile(e.target.files?.[0] || null)}
                    className="block w-full text-sm text-neutral-600 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-primary-50 file:text-primary-700 hover:file:bg-primary-100" />
                  {logoPreview && (
                    <div className="mt-3 flex items-center gap-3 rounded-xl border border-neutral-200 bg-neutral-50 p-3">
                      <img src={logoPreview} alt="Logo-Vorschau"
                        className="h-14 w-auto max-w-[160px] object-contain" />
                      <div className="min-w-0">
                        <p className="text-xs text-neutral-600 truncate">{logoFile?.name}</p>
                        <button type="button" onClick={() => setLogoFile(null)}
                          className="text-xs text-primary-600 hover:text-primary-700 mt-0.5">
                          Entfernen
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3 mt-6">
                <button type="button" disabled={loading} onClick={() => setStep(1)}
                  className="btn-secondary justify-center py-2.5 px-4">
                  <ArrowLeft size={16} /> Zurück
                </button>
                <button type="button" disabled={loading} onClick={() => finish(false)}
                  className="btn-secondary justify-center py-2.5 flex-1">
                  Überspringen
                </button>
                <button type="button" disabled={loading} onClick={() => finish(true)}
                  className="btn-primary justify-center py-2.5 flex-1">
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
                  Fertig
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
