import { useState, useRef, useEffect } from 'react'
import { useSettings } from '../contexts/SettingsContext'
import { settingsApi, systemApi, invoiceApi, accountingApi } from '../services/api'
import toast from 'react-hot-toast'
import {
  Settings2, Building2, Palette, HardDrive, Mail,
  Save, Upload, Trash2, Download, Send, Loader2,
  CheckCircle, Eye, EyeOff, RefreshCw, Cloud,
  ImageIcon, Link2, Monitor, Cpu, ArrowUpCircle,
  Users, AlertTriangle, CheckCircle2, XCircle, ChevronDown, ChevronUp,
  Receipt, FileText, BookOpen, Plus, Star
} from 'lucide-react'

// ── Farbthemen ────────────────────────────────────────────────────────────────
const THEMES = [
  { id: 'orange', label: 'Orange',  color: '#f97316' },
  { id: 'blue',   label: 'Blau',    color: '#3b82f6' },
  { id: 'green',  label: 'Grün',    color: '#22c55e' },
  { id: 'purple', label: 'Lila',    color: '#a855f7' },
  { id: 'teal',   label: 'Teal',    color: '#14b8a6' },
  { id: 'red',    label: 'Rot',     color: '#f43f5e' },
]

// ── Tab-Komponente ────────────────────────────────────────────────────────────
function Tab({ id, label, icon: Icon, active, onClick }) {
  return (
    <button
      onClick={() => onClick(id)}
      className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-xl transition whitespace-nowrap
        ${active
          ? 'bg-primary-600 text-white shadow-sm'
          : 'text-gray-600 hover:bg-gray-100'}`}
    >
      <Icon size={15} />
      {label}
    </button>
  )
}

// ── Formularfeld ──────────────────────────────────────────────────────────────
function Field({ label, children, hint }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-gray-400">{hint}</p>}
    </div>
  )
}

function Input({ value, onChange, type = 'text', placeholder, disabled }) {
  return (
    <input
      type={type} value={value} onChange={e => onChange(e.target.value)}
      placeholder={placeholder} disabled={disabled}
      className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:bg-gray-50"
    />
  )
}

// ── Tab: Allgemein ────────────────────────────────────────────────────────────
function TabAllgemein({ settings, onSaved }) {
  const { updateSettings } = useSettings()
  const [companyName,    setCompanyName]    = useState(settings.company_name || '')
  const [appSubtitle,    setAppSubtitle]    = useState(settings.app_subtitle || '')
  const [saving,         setSaving]         = useState(false)
  const [logoUploading,  setLogoUploading]  = useState(false)
  const [favUploading,   setFavUploading]   = useState(false)
  const [contactGroups,  setContactGroups]  = useState([])
  const [selectedContact, setSelectedContact] = useState({
    id:   settings.company_contact_id   || '',
    type: settings.company_contact_type || '',
  })
  const [contactSaving,  setContactSaving]  = useState(false)

  const logoRef   = useRef(null)
  const favRef    = useRef(null)

  const logoUrl        = settings.logo_url        || null
  const logoHeaderUrl  = settings.logo_header_url  || null
  const logoFaviconUrl = settings.logo_favicon_url || null

  // Kontaktoptionen laden
  useEffect(() => {
    settingsApi.getContactOptions()
      .then(r => setContactGroups(r.data.groups || []))
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      await settingsApi.update({ company_name: companyName, app_subtitle: appSubtitle })
      toast.success('Einstellungen gespeichert')
      onSaved()
    } catch { toast.error('Fehler beim Speichern') }
    finally { setSaving(false) }
  }

  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setLogoUploading(true)
    try {
      const res = await settingsApi.uploadLogo(file)
      updateSettings({
        logo_url:        res.data.logo_url,
        logo_header_url: res.data.logo_header_url,
        logo_favicon_url: res.data.logo_favicon_url,
      })
      toast.success('Logo hochgeladen — 3 Varianten wurden automatisch generiert')
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Upload fehlgeschlagen')
    } finally {
      setLogoUploading(false)
      if (logoRef.current) logoRef.current.value = ''
    }
  }

  const handleDeleteLogo = async () => {
    try {
      await settingsApi.deleteLogo()
      updateSettings({ logo_url: '', logo_header_url: '', logo_favicon_url: '' })
      toast.success('Logo gelöscht')
      onSaved()
    } catch { toast.error('Fehler beim Löschen') }
  }

  const handleFaviconAutoGenerate = async () => {
    if (!logoUrl) return toast.error('Zuerst ein Logo hochladen')
    // Backend hat Favicon bereits beim Logo-Upload generiert — einfach Settings neu laden
    toast.success('Favicon wurde beim Logo-Upload automatisch generiert')
  }

  const handleFaviconUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setFavUploading(true)
    try {
      const res = await settingsApi.uploadFavicon(file)
      updateSettings({ logo_favicon_url: res.data.logo_favicon_url })
      toast.success('Favicon hochgeladen')
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Favicon-Upload fehlgeschlagen')
    } finally {
      setFavUploading(false)
      if (favRef.current) favRef.current.value = ''
    }
  }

  const handleContactSave = async () => {
    setContactSaving(true)
    try {
      await settingsApi.update({
        company_contact_id:   selectedContact.id,
        company_contact_type: selectedContact.type,
      })
      toast.success('Firmen-Kontakt gespeichert')
      onSaved()
    } catch { toast.error('Fehler beim Speichern') }
    finally { setContactSaving(false) }
  }

  // Alle Records aus allen Gruppen flach für Selektor
  const allContacts = contactGroups.flatMap(g =>
    g.records.map(r => ({ ...r, type_name: g.type_name, type_slug: g.type_slug }))
  )
  const selectedName = allContacts.find(c => c.id === selectedContact.id)?.display_name || ''

  return (
    <div className="space-y-8">

      {/* Firmendaten */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Firmendaten</h3>
        <div className="grid grid-cols-1 gap-4">
          <Field label="Firmenname" hint="Wird in der Sidebar und auf der Login-Seite angezeigt">
            <Input value={companyName} onChange={setCompanyName} placeholder="Meine Firma GmbH" />
          </Field>
          <Field label="Untertitel" hint="Kurze Beschreibung unter dem Firmennamen">
            <Input value={appSubtitle} onChange={setAppSubtitle} placeholder="Zeiterfassung & Stammdaten" />
          </Field>
        </div>
        <div className="flex justify-end">
          <button onClick={handleSave} disabled={saving}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition">
            {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
            Speichern
          </button>
        </div>
      </div>

      <hr className="border-gray-100" />

      {/* Logo */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Firmenlogo</h3>
          <div className="flex gap-2">
            <button onClick={() => logoRef.current?.click()} disabled={logoUploading}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition">
              {logoUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {logoUrl ? 'Neues Logo hochladen' : 'Logo hochladen'}
            </button>
            {logoUrl && (
              <button onClick={handleDeleteLogo}
                className="flex items-center gap-2 px-4 py-2 border border-red-200 rounded-xl text-sm font-medium text-red-600 hover:bg-red-50 transition">
                <Trash2 size={14} /> Entfernen
              </button>
            )}
          </div>
          <input ref={logoRef} type="file" accept=".png,.jpg,.jpeg,.svg,.webp" className="hidden" onChange={handleLogoUpload} />
        </div>

        <p className="text-xs text-gray-400">
          PNG, JPG oder WebP hochladen — das System generiert automatisch alle drei Varianten.
          Für beste Qualität empfiehlt sich ein transparentes PNG mit min. 800px Breite.
        </p>

        {/* 3 Varianten-Vorschau */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">

          {/* Sidebar-Logo */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500">
              <Monitor size={12} /> Sidebar
            </div>
            <div className="h-16 border border-gray-200 rounded-xl bg-gray-50 flex items-center justify-center p-2">
              {logoUrl
                ? <img src={logoUrl} alt="Sidebar" className="max-h-full max-w-full object-contain" />
                : <Building2 size={20} className="text-gray-300" />
              }
            </div>
            <p className="text-xs text-gray-400">Original · Sidebar & Login</p>
          </div>

          {/* Berichtskopf */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500">
              <ImageIcon size={12} /> Berichtskopf
            </div>
            <div className="h-16 border border-gray-200 rounded-xl bg-white flex items-center justify-center p-2">
              {logoHeaderUrl
                ? <img src={`${logoHeaderUrl}?v=${Date.now()}`} alt="Header" className="max-h-full max-w-full object-contain" />
                : <div className="text-xs text-gray-300 text-center">600 × 120 px<br/>für Berichte</div>
              }
            </div>
            <p className="text-xs text-gray-400">Querformat · Berichte & Dokumente</p>
          </div>

          {/* Favicon */}
          <div className="space-y-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-gray-500">
              <Monitor size={12} /> Browser-Tab
            </div>
            <div className="h-16 border border-gray-200 rounded-xl bg-gray-100 flex items-center gap-3 px-4">
              <div className="w-8 h-8 border border-gray-200 rounded bg-white flex items-center justify-center flex-shrink-0 overflow-hidden">
                {logoFaviconUrl
                  ? <img src={`${logoFaviconUrl}?v=${Date.now()}`} alt="Favicon" className="w-full h-full object-contain" />
                  : <Monitor size={14} className="text-gray-300" />
                }
              </div>
              <div className="text-xs text-gray-500 min-w-0">
                <div className="font-medium truncate">{companyName || 'DeineZeit'}</div>
                <div className="text-gray-400">Browser-Tab</div>
              </div>
            </div>
            <p className="text-xs text-gray-400">32 × 32 px · Automatisch generiert</p>
          </div>

        </div>
      </div>

      <hr className="border-gray-100" />

      {/* Favicon */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Favicon (Browser-Tab)</h3>
        <p className="text-xs text-gray-400">
          Beim Logo-Upload wird der Favicon automatisch als 32×32 Variante generiert.
          Du kannst auch ein eigenes Favicon hochladen — z.B. ein Icon ohne Text.
        </p>

        <div className="flex items-center gap-4">
          {/* Vorschau */}
          <div className="flex-shrink-0">
            {logoFaviconUrl ? (
              <div className="w-16 h-16 border border-gray-200 rounded-xl bg-gray-50 flex items-center justify-center p-2 overflow-hidden">
                <img
                  src={`${logoFaviconUrl}?v=${Date.now()}`}
                  alt="Favicon"
                  className="w-8 h-8 object-contain"
                />
              </div>
            ) : (
              <div className="w-16 h-16 border-2 border-dashed border-gray-300 rounded-xl flex items-center justify-center text-gray-300">
                <Monitor size={20} />
              </div>
            )}
          </div>

          {/* Buttons */}
          <div className="flex flex-col gap-2">
            <div className="flex gap-2">
              <button onClick={handleFaviconAutoGenerate} disabled={!logoUrl}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-40 transition">
                <RefreshCw size={14} />
                Aus Logo generieren
              </button>
              <button onClick={() => favRef.current?.click()} disabled={favUploading}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition">
                {favUploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                Eigenes hochladen
              </button>
            </div>
            <p className="text-xs text-gray-400">PNG, JPG oder ICO · wird auf 32×32 px skaliert</p>
          </div>
        </div>

        <input ref={favRef} type="file" accept=".png,.jpg,.jpeg,.ico" className="hidden" onChange={handleFaviconUpload} />
      </div>

      <hr className="border-gray-100" />

      {/* Firmen-Kontakt */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">Firmen-Kontakt (Briefkopf)</h3>
        <p className="text-xs text-gray-400">
          Verknüpfe einen Kontakt aus den Stammdaten als offizielle Firmenadresse —
          diese Daten werden als Briefkopf auf Rechnungen und Dokumenten verwendet.
        </p>

        {contactGroups.length === 0 ? (
          <div className="p-4 border border-dashed border-gray-200 rounded-xl text-sm text-gray-400 text-center">
            Keine Stammdaten-Einträge vorhanden. Zuerst einen Kontakt in den Stammdaten anlegen.
          </div>
        ) : (
          <div className="space-y-3">
            <Field label="Kontakt auswählen">
              <select
                value={selectedContact.id}
                onChange={e => {
                  const id = e.target.value
                  const found = allContacts.find(c => c.id === id)
                  setSelectedContact({ id, type: found?.type_slug || '' })
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">— Kein Kontakt ausgewählt —</option>
                {contactGroups.map(group => (
                  <optgroup key={group.type_slug} label={group.type_name}>
                    {group.records.map(r => (
                      <option key={r.id} value={r.id}>{r.display_name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </Field>

            {selectedContact.id && selectedName && (
              <div className="flex items-center gap-2 px-3 py-2 bg-primary-50 border border-primary-200 rounded-xl text-sm text-primary-700">
                <Link2 size={14} />
                <span>Verknüpft mit: <strong>{selectedName}</strong></span>
              </div>
            )}

            <div className="flex justify-end">
              <button onClick={handleContactSave} disabled={contactSaving}
                className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition">
                {contactSaving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
                Kontakt-Verknüpfung speichern
              </button>
            </div>
          </div>
        )}
      </div>

    </div>
  )
}

// ── Tab: Design ───────────────────────────────────────────────────────────────
function TabDesign({ settings, onSaved }) {
  const [theme, setTheme] = useState(settings.color_theme || 'orange')
  const [saving, setSaving] = useState(false)
  const { updateSettings } = useSettings()

  const handleSave = async () => {
    setSaving(true)
    try {
      await settingsApi.update({ color_theme: theme })
      updateSettings({ color_theme: theme })
      toast.success('Design gespeichert')
      onSaved()
    } catch { toast.error('Fehler beim Speichern') }
    finally { setSaving(false) }
  }

  return (
    <div className="space-y-6">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-3">Farbthema</label>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
          {THEMES.map(t => (
            <button key={t.id} onClick={() => setTheme(t.id)}
              className={`flex flex-col items-center gap-2 p-3 rounded-2xl border-2 transition
                ${theme === t.id ? 'border-gray-800 bg-gray-50' : 'border-gray-200 hover:border-gray-300'}`}
            >
              <div className="w-10 h-10 rounded-full shadow-inner" style={{ backgroundColor: t.color }} />
              <span className="text-xs font-medium text-gray-700">{t.label}</span>
              {theme === t.id && <CheckCircle size={14} className="text-gray-700" />}
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-gray-400">
          Das gewählte Farbthema wird sofort für alle Benutzer aktiv — ohne Neustart.
        </p>
      </div>

      {/* Vorschau */}
      <div className="p-4 border border-gray-200 rounded-2xl bg-gray-50">
        <p className="text-xs font-medium text-gray-500 mb-3">Vorschau</p>
        <div className="flex flex-wrap gap-2">
          <button className="px-4 py-2 rounded-lg text-sm font-medium text-white" style={{ backgroundColor: THEMES.find(t=>t.id===theme)?.color }}>
            Primär-Button
          </button>
          <button className="px-4 py-2 rounded-lg text-sm font-medium border" style={{ color: THEMES.find(t=>t.id===theme)?.color, borderColor: THEMES.find(t=>t.id===theme)?.color }}>
            Outline-Button
          </button>
          <span className="px-3 py-1 rounded-full text-xs font-medium" style={{ backgroundColor: THEMES.find(t=>t.id===theme)?.color + '20', color: THEMES.find(t=>t.id===theme)?.color }}>
            Badge
          </span>
        </div>
      </div>

      <div className="pt-2 flex justify-end">
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          Design übernehmen
        </button>
      </div>
    </div>
  )
}

// ── Cloud-Speicher Vorschläge ─────────────────────────────────────────────────
const CLOUD_PRESETS = [
  {
    id: 'onedrive',
    label: 'OneDrive',
    hint: 'Automatisch mit Microsoft Cloud synchronisiert',
    color: '#0078d4',
    bg: '#eff6ff',
    border: '#bfdbfe',
    path: (user) => `C:\\Users\\${user}\\OneDrive\\Backups\\DeineZeit`,
  },
  {
    id: 'googledrive',
    label: 'Google Drive',
    hint: 'Automatisch mit Google Drive synchronisiert',
    color: '#1a73e8',
    bg: '#f0fdf4',
    border: '#bbf7d0',
    path: (user) => `C:\\Users\\${user}\\Google Drive\\Backups\\DeineZeit`,
  },
  {
    id: 'dropbox',
    label: 'Dropbox',
    hint: 'Automatisch mit Dropbox synchronisiert',
    color: '#0061ff',
    bg: '#f5f3ff',
    border: '#ddd6fe',
    path: (user) => `C:\\Users\\${user}\\Dropbox\\DeineZeit-Backup`,
  },
]

// Versucht den Windows-Benutzernamen aus dem Backup-Pfad zu extrahieren
function guessUsername(currentDir) {
  if (!currentDir) return 'IhrName'
  const m = currentDir.match(/^[A-Za-z]:\\[Uu]sers\\([^\\]+)/)
  return m ? m[1] : 'IhrName'
}

// ── Tab: Backup ───────────────────────────────────────────────────────────────
function TabBackup({ settings, onSaved }) {
  const [backupDir,     setBackupDir]     = useState(settings.backup_dir            || '')
  const [scheduleTime,  setScheduleTime]  = useState(settings.backup_schedule_time  || '02:00')
  const [keepDays,      setKeepDays]      = useState(settings.backup_keep_days      || '30')
  const [saving,        setSaving]        = useState(false)
  const [downloading,   setDownloading]   = useState(false)

  // Letzte 3 Backups aus backup_history (JSON-Array von ISO-Strings)
  let history = []
  try { history = JSON.parse(settings.backup_history || '[]') } catch {}

  const username = guessUsername(backupDir || settings.backup_dir)

  const handleSave = async () => {
    setSaving(true)
    try {
      await settingsApi.update({
        backup_dir:           backupDir,
        backup_schedule_time: scheduleTime,
        backup_keep_days:     keepDays,
      })
      toast.success('Backup-Einstellungen gespeichert')
      onSaved()
    } catch { toast.error('Fehler beim Speichern') }
    finally { setSaving(false) }
  }

  const handleDownload = async () => {
    setDownloading(true)
    try {
      const res   = await settingsApi.downloadBackup()
      const url   = window.URL.createObjectURL(new Blob([res.data]))
      const a     = document.createElement('a')
      const cd    = res.headers['content-disposition'] || ''
      const match = cd.match(/filename="?([^"]+)"?/)
      a.href      = url
      a.download  = match ? match[1] : `deinezeit_backup_${new Date().toISOString().slice(0,10)}.sql`
      a.click()
      window.URL.revokeObjectURL(url)
      toast.success('Backup heruntergeladen')
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Backup fehlgeschlagen')
    } finally { setDownloading(false) }
  }

  const fmtBackupDate = (iso) => {
    try {
      return new Date(iso).toLocaleString('de-AT', {
        weekday: 'short', day: '2-digit', month: '2-digit',
        year: 'numeric', hour: '2-digit', minute: '2-digit'
      })
    } catch { return iso }
  }

  return (
    <div className="space-y-6">

      {/* Cloud-Speicher Schnellauswahl */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-2">
          <Cloud size={14} className="text-gray-400" />
          Cloud-Speicher (Schnellauswahl)
        </label>
        <p className="text-xs text-gray-400 mb-3">
          Backups werden im Cloud-Sync-Ordner gespeichert und automatisch hochgeladen.
          Benutzernamen ggf. anpassen.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {CLOUD_PRESETS.map(preset => {
            const suggestedPath = preset.path(username)
            const isActive = backupDir === suggestedPath
            return (
              <button
                key={preset.id}
                onClick={() => setBackupDir(suggestedPath)}
                className={`text-left p-3 rounded-xl border-2 transition ${
                  isActive
                    ? 'border-primary-400 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300 bg-white'
                }`}
              >
                <div className="font-medium text-sm text-gray-800 mb-0.5 flex items-center gap-1.5">
                  {isActive && <CheckCircle size={13} className="text-primary-500 flex-shrink-0" />}
                  {preset.label}
                </div>
                <div className="text-xs text-gray-400">{preset.hint}</div>
              </button>
            )
          })}
        </div>
      </div>

      <hr className="border-gray-100" />

      {/* Automatisches Backup – Einstellungen */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Backup-Ordner" hint="Lokaler oder Cloud-Sync-Pfad für die .sql-Dateien">
          <Input value={backupDir} onChange={setBackupDir} placeholder="C:\Backups\DeineZeit" />
        </Field>
        <Field label="Tägliche Backup-Zeit" hint="Uhrzeit für den automatischen Windows-Task">
          <Input value={scheduleTime} onChange={setScheduleTime} placeholder="02:00" />
        </Field>
        <Field label="Aufbewahrung">
          <select value={keepDays} onChange={e => setKeepDays(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500">
            <option value="7">7 Tage</option>
            <option value="14">14 Tage</option>
            <option value="30">30 Tage</option>
            <option value="60">60 Tage</option>
            <option value="90">90 Tage</option>
            <option value="365">1 Jahr</option>
          </select>
        </Field>
      </div>

      <div className="p-3 bg-green-50 border border-green-200 rounded-xl text-xs text-green-700">
        <strong>Automatische Synchronisation:</strong> Änderungen werden innerhalb von 30 Sekunden
        automatisch auf den Windows-Aufgabenplaner übertragen — kein manuelles Ausführen nötig.
      </div>

      <div className="flex justify-end">
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          Einstellungen speichern
        </button>
      </div>

      <hr className="border-gray-100" />

      {/* Manuelles Backup / Download */}
      <div className="p-4 border border-gray-200 rounded-2xl bg-gray-50 space-y-3">
        <div>
          <p className="text-sm font-medium text-gray-700">Backup jetzt erstellen</p>
          <p className="text-xs text-gray-400 mt-0.5">
            Erstellt sofort einen vollständigen Datenbank-Dump und lädt ihn in deinen Download-Ordner.
          </p>
        </div>
        <button onClick={handleDownload} disabled={downloading}
          className="flex items-center gap-2 px-5 py-2.5 bg-gray-800 hover:bg-gray-900 disabled:bg-gray-400 text-white text-sm font-medium rounded-xl transition">
          {downloading
            ? <><Loader2 size={15} className="animate-spin" /> Erstelle Backup…</>
            : <><Download size={15} /> Backup herunterladen</>
          }
        </button>
      </div>

      <hr className="border-gray-100" />

      {/* Letzte 3 Backups */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-3">Letzte Backups</label>
        {history.length === 0 ? (
          <p className="text-sm text-gray-400">Noch kein Backup aufgezeichnet.</p>
        ) : (
          <div className="divide-y divide-gray-100 border border-gray-200 rounded-xl overflow-hidden">
            {history.map((iso, i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3 bg-white">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${i === 0 ? 'bg-green-400' : 'bg-gray-300'}`} />
                <span className="text-sm text-gray-700">{fmtBackupDate(iso)}</span>
                {i === 0 && <span className="ml-auto text-xs text-green-600 font-medium">Letztes</span>}
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  )
}

// ── E-Mail-Anbieter Schnellauswahl ────────────────────────────────────────────
const EMAIL_PROVIDERS = [
  {
    id: 'office365',
    label: 'Office 365',
    emoji: '🏢',
    host: 'smtp.office365.com',
    port: '587',
    tls: true,
    steps: [
      { label: 'Schritt 1 – SMTP AUTH aktivieren', text: 'Im Microsoft 365 Admin Center (admin.microsoft.com) → Benutzer → Aktive Benutzer → Benutzer wählen → Tab „E-Mail" → „E-Mail-Apps verwalten" → Haken bei „Authentifiziertes SMTP" setzen → Speichern.' },
      { label: 'Schritt 2 – Warten', text: 'Wichtig: Die Änderung kann 30–60 Minuten dauern bis sie wirkt. Danach erneut testen.' },
      { label: 'MFA aktiv?', text: 'Falls Mehr-Faktor-Authentifizierung eingeschaltet ist: Unter myaccount.microsoft.com → Sicherheitsinfo ein App-Passwort erstellen und dieses statt des normalen Passworts verwenden.' },
      { label: 'Immer noch Fehler 535?', text: 'Unter admin.microsoft.com → Einstellungen → Organisationseinstellungen → Dienste → Moderne Authentifizierung prüfen ob SMTP AUTH auf Tenant-Ebene deaktiviert ist. Falls ja: dort aktivieren oder einen IT-Administrator kontaktieren.' },
    ],
  },
  {
    id: 'gmail',
    label: 'Gmail',
    emoji: '📧',
    host: 'smtp.gmail.com',
    port: '587',
    tls: true,
    hint: {
      type: 'info',
      text: 'Bei aktivierter 2-Faktor-Authentifizierung muss ein App-Passwort verwendet werden: Google-Konto → Sicherheit → App-Passwörter. Das normale Google-Passwort funktioniert dann nicht.',
    },
  },
  {
    id: 'gmx',
    label: 'GMX',
    emoji: '📬',
    host: 'smtp.gmx.net',
    port: '587',
    tls: true,
    hint: {
      type: 'info',
      text: 'SMTP-Zugang in GMX aktivieren: Einstellungen → E-Mail → POP3/IMAP Abruf → SMTP-Zugang aktivieren.',
    },
  },
  {
    id: 'webde',
    label: 'web.de',
    emoji: '📮',
    host: 'smtp.web.de',
    port: '587',
    tls: true,
    hint: {
      type: 'info',
      text: 'SMTP-Zugang in web.de aktivieren: Einstellungen → E-Mail → Externe Programme.',
    },
  },
  {
    id: 'custom',
    label: 'Eigener Server',
    emoji: '🖥️',
    host: null,
    port: null,
    tls: null,
    hint: null,
  },
]

// ── Tab: E-Mail ───────────────────────────────────────────────────────────────
function TabEmail({ settings, onSaved }) {
  const [host,      setHost]      = useState(settings.smtp_host      || '')
  const [port,      setPort]      = useState(settings.smtp_port      || '587')
  const [user,      setUser]      = useState(settings.smtp_user      || '')
  const [password,  setPassword]  = useState('')
  const [fromName,  setFromName]  = useState(settings.smtp_from_name  || '')
  const [fromEmail, setFromEmail] = useState(settings.smtp_from_email || '')
  const [tls,       setTls]       = useState(settings.smtp_tls !== 'false')
  const [showPass,  setShowPass]  = useState(false)
  const [saving,    setSaving]    = useState(false)
  const [testEmail, setTestEmail] = useState('')
  const [testing,   setTesting]   = useState(false)
  const [activeProvider, setActiveProvider] = useState(null)

  const selectProvider = (provider) => {
    setActiveProvider(provider.id)
    if (provider.host !== null) {
      setHost(provider.host)
      setPort(provider.port)
      setTls(provider.tls)
    }
  }

  const currentHint = EMAIL_PROVIDERS.find(p => p.id === activeProvider)?.hint

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = { smtp_host: host, smtp_port: port, smtp_user: user, smtp_from_name: fromName, smtp_from_email: fromEmail, smtp_tls: tls ? 'true' : 'false' }
      if (password) payload.smtp_password = password
      await settingsApi.update(payload)
      toast.success('E-Mail-Einstellungen gespeichert')
      setPassword('')
      onSaved()
    } catch { toast.error('Fehler beim Speichern') }
    finally { setSaving(false) }
  }

  const handleTest = async () => {
    if (!testEmail) return toast.error('Bitte eine Empfänger-E-Mail eingeben')
    setTesting(true)
    try {
      const res = await settingsApi.testEmail(testEmail)
      toast.success(res.data.message || 'Test-Mail gesendet!')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Versand fehlgeschlagen')
    } finally { setTesting(false) }
  }

  return (
    <div className="space-y-5">

      {/* Anbieter-Schnellauswahl */}
      <div>
        <p className="text-sm font-medium text-gray-700 mb-2">Anbieter auswählen</p>
        <div className="flex flex-wrap gap-2">
          {EMAIL_PROVIDERS.map(provider => (
            <button
              key={provider.id}
              type="button"
              onClick={() => selectProvider(provider)}
              className={`flex items-center gap-2 px-3 py-2 rounded-xl border-2 text-sm font-medium transition ${
                activeProvider === provider.id
                  ? 'border-primary-500 bg-primary-50 text-primary-700'
                  : 'border-gray-200 text-gray-600 hover:border-gray-300 hover:bg-gray-50'
              }`}
            >
              <span>{provider.emoji}</span>
              {provider.label}
            </button>
          ))}
        </div>
      </div>

      {/* Anbieter-Hinweis */}
      {currentHint && (
        <div className={`p-4 rounded-xl text-sm ${
          currentHint.type === 'warning'
            ? 'bg-amber-50 border border-amber-200 text-amber-800'
            : 'bg-blue-50 border border-blue-200 text-blue-800'
        }`}>
          <div className="flex gap-2 mb-2 font-medium">
            <span>{currentHint.type === 'warning' ? '⚠️' : 'ℹ️'}</span>
            <span>{currentHint.type === 'warning' ? 'Wichtige Hinweise zur Einrichtung' : 'Hinweis'}</span>
          </div>
          {currentHint.steps ? (
            <ol className="space-y-2 ml-1">
              {currentHint.steps.map((step, i) => (
                <li key={i} className="flex gap-2">
                  <span className="font-bold flex-shrink-0">{i + 1}.</span>
                  <span><span className="font-semibold">{step.label}:</span> {step.text}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="leading-relaxed ml-1">{currentHint.text}</p>
          )}
        </div>
      )}

      {/* Formular */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="SMTP-Server (Host)">
          <Input value={host} onChange={setHost} placeholder="smtp.example.com" />
        </Field>
        <Field label="Port">
          <Input value={port} onChange={setPort} placeholder="587" />
        </Field>
        <Field label="Benutzername">
          <Input value={user} onChange={setUser} placeholder="user@example.com" />
        </Field>
        <Field label="Passwort" hint="Leer lassen um das gespeicherte Passwort zu behalten">
          <div className="relative">
            <input
              type={showPass ? 'text' : 'password'} value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder="••••••••"
              className="w-full px-3 py-2 pr-10 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
            <button type="button" onClick={() => setShowPass(p => !p)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600">
              {showPass ? <EyeOff size={14} /> : <Eye size={14} />}
            </button>
          </div>
        </Field>
        <Field label="Absender-Name">
          <Input value={fromName} onChange={setFromName} placeholder="DeineZeit" />
        </Field>
        <Field label="Absender-E-Mail">
          <Input value={fromEmail} onChange={setFromEmail} placeholder="noreply@firma.at" type="email" />
        </Field>
      </div>

      <div className="flex items-center gap-3">
        <input type="checkbox" id="tls" checked={tls} onChange={e => setTls(e.target.checked)}
          className="w-4 h-4 rounded accent-primary-600" />
        <label htmlFor="tls" className="text-sm font-medium text-gray-700 cursor-pointer">
          STARTTLS verwenden (empfohlen für Port 587)
        </label>
      </div>

      <div className="flex justify-end pt-2">
        <button onClick={handleSave} disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />}
          Speichern
        </button>
      </div>

      <hr className="border-gray-100" />

      {/* Test-Mail */}
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Test-E-Mail senden</label>
        <p className="text-xs text-gray-400 mb-3">
          Sendet eine Test-Mail um die Konfiguration zu überprüfen. Zuerst speichern, dann testen.
        </p>
        <div className="flex gap-3">
          <input
            type="email" value={testEmail} onChange={e => setTestEmail(e.target.value)}
            placeholder="empfaenger@example.com"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <button onClick={handleTest} disabled={testing || !host}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition">
            {testing ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
            Senden
          </button>
        </div>
        {!host && <p className="text-xs text-orange-500 mt-2">Bitte zuerst SMTP-Server eingeben und speichern.</p>}
      </div>
    </div>
  )
}

// ── Tab: System & Updates ─────────────────────────────────────────────────────
function TabSystem() {
  const [versionInfo, setVersionInfo]     = useState(null)
  const [changelog, setChangelog]         = useState('')
  const [showChangelog, setShowChangelog] = useState(false)
  const [activeUsers, setActiveUsers]     = useState(0)
  const [loading, setLoading]             = useState(true)
  const [checking, setChecking]           = useState(false)
  const [starting, setStarting]           = useState(false)
  const [cancelling, setCancelling]       = useState(false)
  const [updateStatus, setUpdateStatus]   = useState(null)

  useEffect(() => {
    loadVersionInfo()
    loadActiveUsers()
  }, [])

  const loadVersionInfo = async () => {
    setLoading(true)
    try {
      const res = await systemApi.getVersion()
      setVersionInfo(res.data)
    } catch {
      // ignorieren
    } finally {
      setLoading(false)
    }
  }

  const loadActiveUsers = async () => {
    try {
      const res = await systemApi.getActiveUsers()
      setActiveUsers(res.data.active_users || 0)
    } catch { /* ignorieren */ }
  }

  const handleCheckUpdate = async () => {
    setChecking(true)
    try {
      const res = await systemApi.getVersion()
      setVersionInfo(res.data)
      if (!res.data.update_available) {
        toast.success('Sie verwenden bereits die neueste Version.')
      }
    } catch {
      toast.error('Versionsprüfung fehlgeschlagen.')
    } finally {
      setChecking(false)
    }
  }

  const handleShowChangelog = async () => {
    if (showChangelog) { setShowChangelog(false); return }
    try {
      const res = await systemApi.getChangelog()
      setChangelog(res.data.content)
      setShowChangelog(true)
    } catch {
      toast.error('Changelog konnte nicht geladen werden.')
    }
  }

  const handleStartUpdate = async () => {
    if (!window.confirm(
      `Update starten?\n\nAlle angemeldeten Benutzer werden in 2 Minuten automatisch abgemeldet.\nDas System ist danach kurzzeitig nicht erreichbar.`
    )) return

    setStarting(true)
    try {
      await systemApi.startUpdate()
      toast.success('Update eingeleitet — Benutzer werden benachrichtigt.')
      const res = await systemApi.getUpdateStatus()
      setUpdateStatus(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Update konnte nicht gestartet werden.')
    } finally {
      setStarting(false)
    }
  }

  const handleCancelUpdate = async () => {
    setCancelling(true)
    try {
      await systemApi.cancelUpdate()
      toast.success('Update wurde abgebrochen.')
      setUpdateStatus(null)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Abbrechen nicht möglich.')
    } finally {
      setCancelling(false)
    }
  }

  const updatePending = updateStatus?.status === 'notifying'

  return (
    <div className="space-y-6">
      {/* Versions-Info */}
      <div>
        <h3 className="text-base font-semibold text-gray-900 mb-3 flex items-center gap-2">
          <Cpu size={16} className="text-primary-500" />
          Versionsinformation
        </h3>

        {loading ? (
          <div className="flex items-center gap-2 text-gray-400 text-sm">
            <Loader2 size={15} className="animate-spin" /> Wird geladen…
          </div>
        ) : (
          <div className="bg-gray-50 rounded-xl p-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Installierte Version</span>
              <span className="font-mono font-semibold text-gray-800">v{versionInfo?.current}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Neueste Version</span>
              <span className="font-mono font-semibold text-gray-800">v{versionInfo?.latest}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-500">Status</span>
              {versionInfo?.update_available ? (
                <span className="flex items-center gap-1 text-amber-600 font-medium">
                  <AlertTriangle size={13} />
                  Update verfügbar
                </span>
              ) : (
                <span className="flex items-center gap-1 text-green-600 font-medium">
                  <CheckCircle2 size={13} />
                  Aktuell
                </span>
              )}
            </div>
          </div>
        )}

        <div className="flex gap-2 mt-3">
          <button onClick={handleCheckUpdate} disabled={checking}
            className="btn-secondary text-sm py-1.5 px-3 flex items-center gap-1.5">
            {checking ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            Auf Updates prüfen
          </button>
          <button onClick={handleShowChangelog}
            className="btn-secondary text-sm py-1.5 px-3 flex items-center gap-1.5">
            {showChangelog ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            Änderungsprotokoll
          </button>
        </div>

        {showChangelog && changelog && (
          <div className="mt-3 bg-gray-50 rounded-xl p-4 max-h-64 overflow-y-auto">
            <pre className="text-xs text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">
              {changelog}
            </pre>
          </div>
        )}
      </div>

      <hr className="border-gray-100" />

      {/* Update starten */}
      <div>
        <h3 className="text-base font-semibold text-gray-900 mb-3 flex items-center gap-2">
          <ArrowUpCircle size={16} className="text-primary-500" />
          System-Update
        </h3>

        {/* Aktive Benutzer */}
        <div className="flex items-center gap-2 text-sm text-gray-600 mb-4">
          <Users size={14} className="text-gray-400" />
          {activeUsers === 0
            ? 'Keine weiteren Benutzer angemeldet.'
            : `${activeUsers} weitere Benutzer${activeUsers === 1 ? '' : ''} angemeldet — werden 2 Minuten vor dem Update benachrichtigt.`
          }
        </div>

        {updatePending ? (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-3">
            <p className="text-sm font-medium text-amber-800 flex items-center gap-2">
              <AlertTriangle size={15} />
              Update läuft in Kürze — Countdown aktiv
            </p>
            <p className="text-xs text-amber-700">{updateStatus.message}</p>
            <button onClick={handleCancelUpdate} disabled={cancelling}
              className="btn-secondary text-sm py-1.5 px-3 flex items-center gap-1.5 border-amber-300 text-amber-700 hover:bg-amber-100">
              {cancelling ? <Loader2 size={13} className="animate-spin" /> : <XCircle size={13} />}
              Update abbrechen
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {versionInfo?.update_available ? (
              <div className="bg-primary-50 border border-primary-200 rounded-xl p-3 text-sm text-primary-800">
                Version <strong>v{versionInfo.latest}</strong> ist verfügbar.
                Alle Benutzer werden 2 Minuten vor dem Neustart benachrichtigt.
              </div>
            ) : (
              <div className="bg-gray-50 rounded-xl p-3 text-sm text-gray-600">
                Sie können auch ein erneutes Update der aktuellen Version erzwingen
                (z.B. um Konfigurationsänderungen einzuspielen).
              </div>
            )}
            <button
              onClick={handleStartUpdate}
              disabled={starting}
              className="btn-primary text-sm py-2 px-4 flex items-center gap-2"
            >
              {starting ? <Loader2 size={14} className="animate-spin" /> : <ArrowUpCircle size={14} />}
              {versionInfo?.update_available ? `Update auf v${versionInfo.latest} starten` : 'System neu starten / Update erzwingen'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Tab: Rechnungen ───────────────────────────────────────────────────────────
const TEMPLATE_NAMES = {
  1: 'Klassisch',
  2: 'Modern',
  3: 'Kompakt',
  4: 'Elegant',
  5: 'Farbenfroh',
}

const TEMPLATE_DESCRIPTIONS = {
  1: 'Zweispaltig, Logo rechts — seriöser Stil für alle Branchen',
  2: 'Dunkler Header-Block, minimalistische Typografie',
  3: 'Dichtes Layout, ideal für kurze Rechnungen',
  4: 'Goldene Linie, Serif-Schrift, viel Weißraum',
  5: 'Primärfarbe als Akzent, auffällig und modern',
}

function TabRechnung({ embedded = false }) { // eslint-disable-line
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [customCss, setCustomCss] = useState('')
  const [showCustomEditor, setShowCustomEditor] = useState(false)
  const [previewTemplate, setPreviewTemplate] = useState(null) // null = kein Popup
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewLoading, setPreviewLoading] = useState(false)

  const [bankIban, setBankIban] = useState('')
  const [bankBic, setBankBic] = useState('')
  const [bankName, setBankName] = useState('')
  const [defaultTemplate, setDefaultTemplate] = useState(1)
  const [defaultTaxRate, setDefaultTaxRate] = useState(20)
  const [paymentDays, setPaymentDays] = useState(30)
  const [kleinunternehmerText, setKleinunternehmerText] = useState('')
  const [contactHint, setContactHint] = useState('')  // Info ob Bankdaten aus Kontakt kamen

  // Bankfelder aus Kontakt-Daten erkennen (sucht nach IBAN/BIC/Bank in allen Feldern)
  function extractBankFromContact(data) {
    if (!data) return {}
    const result = {}
    const keys = Object.keys(data)
    for (const k of keys) {
      const kl = k.toLowerCase()
      const v = String(data[k] || '').trim()
      if (!v) continue
      if (!result.iban && (kl.includes('iban'))) result.iban = v
      if (!result.bic  && (kl.includes('bic') || kl.includes('swift'))) result.bic = v
      if (!result.bank && (kl.includes('bank') && !kl.includes('iban') && !kl.includes('bic'))) result.bank = v
    }
    return result
  }

  useEffect(() => {
    Promise.all([
      invoiceApi.getSettings(),
      settingsApi.getCompanyContact(),
    ]).then(([invRes, contactRes]) => {
      const s = invRes.data
      const bank = s.bank || {}
      const savedIban = typeof bank === 'object' ? bank.iban || '' : ''
      const savedBic  = typeof bank === 'object' ? bank.bic  || '' : ''
      const savedBank = typeof bank === 'object' ? bank.bank || '' : ''
      setBankIban(savedIban); setBankBic(savedBic); setBankName(savedBank)
      setDefaultTemplate(s.default_template || 1)
      setCustomCss(s.custom_template_css || '')
      setDefaultTaxRate(s.default_tax_rate || 20)
      setPaymentDays(s.default_payment_days || 30)
      setKleinunternehmerText(typeof s.kleinunternehmer_text === 'string' ? s.kleinunternehmer_text.replace(/^"|"$/g, '') : '')
      const contact = contactRes.data?.contact
      if (contact?.data) {
        const fc = extractBankFromContact(contact.data)
        if (!savedIban && fc.iban) setBankIban(fc.iban)
        if (!savedBic  && fc.bic)  setBankBic(fc.bic)
        if (!savedBank && fc.bank) setBankName(fc.bank)
        if (fc.iban || fc.bic || fc.bank) setContactHint(`Bankdaten aus Kontakt "${contact.display_name}" übernommen`)
      }
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  async function handleSave() {
    setSaving(true)
    try {
      await Promise.all([
        invoiceApi.updateSetting('bank', { iban: bankIban, bic: bankBic, bank: bankName }),
        invoiceApi.updateSetting('default_template', Number(defaultTemplate)),
        invoiceApi.updateSetting('default_tax_rate', Number(defaultTaxRate)),
        invoiceApi.updateSetting('default_payment_days', Number(paymentDays)),
        invoiceApi.updateSetting('kleinunternehmer_text', kleinunternehmerText),
        showCustomEditor && invoiceApi.updateSetting('custom_template_css', customCss),
      ].filter(Boolean))
      toast.success('Belegeinstellungen gespeichert')
    } catch { toast.error('Fehler beim Speichern') }
    finally { setSaving(false) }
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 size={24} className="animate-spin text-neutral-400" /></div>

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Bankverbindung</h3>
        {contactHint && (
          <div className="mb-3 flex items-center gap-2 text-xs text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
            <CheckCircle2 size={13} /> {contactHint}
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div><label className="block text-xs font-medium text-neutral-600 mb-1">IBAN</label>
            <input value={bankIban} onChange={e => setBankIban(e.target.value)} placeholder="AT12 3456 7890 1234 5678" className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" /></div>
          <div><label className="block text-xs font-medium text-neutral-600 mb-1">BIC</label>
            <input value={bankBic} onChange={e => setBankBic(e.target.value)} placeholder="BKAUATWW" className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" /></div>
          <div><label className="block text-xs font-medium text-neutral-600 mb-1">Bankname</label>
            <input value={bankName} onChange={e => setBankName(e.target.value)} placeholder="Bank Austria" className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" /></div>
        </div>
      </div>
      <hr className="border-gray-100" />
      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">Standard-Einstellungen</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div><label className="block text-xs font-medium text-neutral-600 mb-1">Standard-MwSt.-Satz (%)</label>
            <select value={defaultTaxRate} onChange={e => setDefaultTaxRate(e.target.value)} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
              <option value={20}>20 %</option><option value={10}>10 %</option><option value={0}>0 %</option>
            </select></div>
          <div><label className="block text-xs font-medium text-neutral-600 mb-1">Standard-Zahlungsziel (Tage)</label>
            <input type="number" value={paymentDays} onChange={e => setPaymentDays(e.target.value)} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" min={0} max={365} /></div>
        </div>
        <div className="mt-3"><label className="block text-xs font-medium text-neutral-600 mb-1">Kleinunternehmer-Hinweistext</label>
          <textarea value={kleinunternehmerText} onChange={e => setKleinunternehmerText(e.target.value)} rows={2} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm resize-none" /></div>
      </div>
      <hr className="border-gray-100" />
      <div>
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">PDF-Vorlage</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
          {[1, 2, 3, 4, 5].map(n => (
            <div key={n} className={`flex flex-col rounded-xl border-2 transition-all overflow-hidden ${Number(defaultTemplate) === n ? 'border-primary-500' : 'border-neutral-200'}`}>
              <button onClick={() => setDefaultTemplate(n)} className={`flex flex-col items-center gap-2 p-3 w-full ${Number(defaultTemplate) === n ? 'bg-primary-50' : 'bg-white hover:bg-neutral-50'}`}>
                <FileText size={24} className={Number(defaultTemplate) === n ? 'text-primary-600' : 'text-neutral-400'} />
                <span className={`text-xs font-semibold ${Number(defaultTemplate) === n ? 'text-primary-700' : 'text-neutral-700'}`}>{TEMPLATE_NAMES[n]}</span>
                <span className="text-xs text-neutral-400 text-center leading-tight">{TEMPLATE_DESCRIPTIONS[n]}</span>
                {Number(defaultTemplate) === n && <span className="text-xs bg-primary-600 text-white px-2 py-0.5 rounded-full">Standard</span>}
              </button>
              <button onClick={async () => {
                setPreviewTemplate(n); setPreviewHtml(''); setPreviewLoading(true)
                try {
                  const token = localStorage.getItem('access_token')
                  const res = await fetch(`/api/invoices/template-preview/${n}`, { headers: { Authorization: `Bearer ${token}` } })
                  setPreviewHtml(await res.text())
                } catch { setPreviewHtml('<p style="padding:2rem;color:red">Fehler</p>') }
                finally { setPreviewLoading(false) }
              }} className="w-full py-1.5 text-xs text-neutral-500 hover:text-primary-600 hover:bg-neutral-50 border-t border-neutral-100 flex items-center justify-center gap-1">
                <Eye size={12} /> Vorschau
              </button>
            </div>
          ))}
        </div>
        {previewTemplate && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-2xl shadow-2xl flex flex-col w-full max-w-4xl" style={{height: '90vh'}}>
              <div className="flex items-center justify-between px-5 py-3 border-b border-neutral-200">
                <span className="font-semibold text-neutral-800">Vorschau: {TEMPLATE_NAMES[previewTemplate]}</span>
                <div className="flex gap-2">
                  <button onClick={() => { setDefaultTemplate(previewTemplate); setPreviewTemplate(null) }} className="px-3 py-1.5 text-xs bg-primary-600 text-white rounded-lg hover:bg-primary-700">Als Standard verwenden</button>
                  <button onClick={() => setPreviewTemplate(null)} className="p-1.5 rounded-lg hover:bg-neutral-100 text-neutral-500"><XCircle size={18} /></button>
                </div>
              </div>
              <div className="flex-1 overflow-hidden rounded-b-2xl relative">
                {previewLoading && <div className="absolute inset-0 flex items-center justify-center bg-white z-10"><Loader2 size={28} className="animate-spin text-neutral-400" /></div>}
                <iframe srcdoc={previewHtml} className="w-full h-full border-0" sandbox="allow-same-origin" />
              </div>
            </div>
          </div>
        )}
        <div className="border border-neutral-200 rounded-xl overflow-hidden">
          <button onClick={() => setShowCustomEditor(!showCustomEditor)} className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-neutral-700 hover:bg-neutral-50">
            <span className="flex items-center gap-2"><FileText size={15} /> Eigene Vorlage (CSS-Editor)</span>
            {showCustomEditor ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          </button>
          {showCustomEditor && (
            <div className="border-t border-neutral-100 p-4">
              <p className="text-xs text-neutral-500 mb-2">Überschreibe das Standard-CSS. Selektoren: <code className="bg-neutral-100 px-1 rounded">.positions</code>, <code className="bg-neutral-100 px-1 rounded">h1</code>, <code className="bg-neutral-100 px-1 rounded">.bank-box</code> etc.</p>
              <textarea value={customCss} onChange={e => setCustomCss(e.target.value)} rows={10} placeholder="/* body { font-family: Georgia, serif; } */" className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-xs font-mono resize-y" spellCheck={false} />
            </div>
          )}
        </div>
      </div>
      <div className="flex justify-end pt-2">
        <button onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700 disabled:opacity-60">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Speichern
        </button>
      </div>
    </div>
  )
}

// ── Belegnummern-Sektion ──────────────────────────────────────────────────────
const DOC_TYPE_META = {
  rechnung:     { label: 'Rechnung',     prefix: 'RE' },
  angebot:      { label: 'Angebot',      prefix: 'AN' },
  gutschrift:   { label: 'Gutschrift',   prefix: 'GS' },
  lieferschein: { label: 'Lieferschein', prefix: 'LS' },
}

function BelegnummernSection() {
  const [sequences, setSequences] = useState([])
  const [loading, setLoading] = useState(true)
  const [year, setYear] = useState(new Date().getFullYear())
  const [edits, setEdits] = useState({})
  const [saving, setSaving] = useState({})

  async function load() {
    setLoading(true)
    try {
      const res = await invoiceApi.getNumberSequences(year)
      setSequences(res.data)
      const e = {}
      res.data.forEach(s => { e[s.doc_type] = { format: s.format, last_sequence: String(s.last_sequence) } })
      setEdits(e)
    } catch { toast.error('Fehler beim Laden der Belegnummern') }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [year]) // eslint-disable-line

  function preview(docType) {
    const e = edits[docType]; if (!e) return '—'
    try {
      const seq = parseInt(e.last_sequence || 0) + 1
      return e.format.replace('{year}', year).replace('{seq:03d}', String(seq).padStart(3,'0')).replace('{seq:04d}', String(seq).padStart(4,'0')).replace('{seq}', String(seq))
    } catch { return '—' }
  }

  async function handleSave(docType) {
    setSaving(s => ({...s, [docType]: true}))
    try {
      await invoiceApi.updateNumberSequence(docType, { year, format: edits[docType].format, last_sequence: parseInt(edits[docType].last_sequence) })
      toast.success(`${DOC_TYPE_META[docType]?.label} gespeichert`)
      load()
    } catch (err) { toast.error(err.response?.data?.detail || 'Fehler') }
    finally { setSaving(s => ({...s, [docType]: false})) }
  }

  if (loading) return <div className="flex justify-center py-4"><Loader2 size={20} className="animate-spin text-neutral-400" /></div>

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs text-neutral-500">
          Platzhalter: <code className="bg-neutral-100 px-1 rounded">{'{year}'}</code> = Jahr,{' '}
          <code className="bg-neutral-100 px-1 rounded">{'{seq:03d}'}</code> = 3-stellige Nummer
        </p>
        <div className="flex items-center gap-2">
          <label className="text-xs text-neutral-500">Jahr:</label>
          <select value={year} onChange={e => setYear(Number(e.target.value))} className="border border-neutral-200 rounded px-2 py-1 text-sm">
            {[0,1,2,3].map(i => { const y = new Date().getFullYear() - i + 1; return <option key={y} value={y}>{y}</option> })}
          </select>
        </div>
      </div>
      <div className="space-y-3">
        {sequences.map(seq => {
          const meta = DOC_TYPE_META[seq.doc_type] || {}
          const e = edits[seq.doc_type] || {}
          return (
            <div key={seq.doc_type} className="border border-neutral-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold bg-neutral-100 text-neutral-600 px-2 py-0.5 rounded">{meta.prefix}</span>
                  <span className="text-sm font-medium text-neutral-800">{meta.label}</span>
                </div>
                <span className="text-xs text-neutral-400">Nächste: <strong className="text-neutral-700 font-mono">{preview(seq.doc_type)}</strong></span>
              </div>
              <div className="grid grid-cols-12 gap-3 items-end">
                <div className="col-span-6">
                  <label className="block text-xs font-medium text-neutral-500 mb-1">Nummernformat</label>
                  <input value={e.format || ''} onChange={ev => setEdits(d => ({...d, [seq.doc_type]: {...d[seq.doc_type], format: ev.target.value}}))}
                    placeholder={`${meta.prefix}-{year}-{seq:03d}`} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm font-mono" />
                </div>
                <div className="col-span-3">
                  <label className="block text-xs font-medium text-neutral-500 mb-1">Letzter Zähler {year}</label>
                  <input type="number" min={0} value={e.last_sequence ?? seq.last_sequence}
                    onChange={ev => setEdits(d => ({...d, [seq.doc_type]: {...d[seq.doc_type], last_sequence: ev.target.value}}))}
                    className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm text-right" />
                </div>
                <div className="col-span-3">
                  <button onClick={() => handleSave(seq.doc_type)} disabled={saving[seq.doc_type]}
                    className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-60">
                    {saving[seq.doc_type] ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Speichern
                  </button>
                </div>
              </div>
              {seq.last_sequence > 0 && <p className="text-xs text-neutral-400 mt-2">{seq.last_sequence} Belege in {year} · Nächste freie Nr.: {seq.next_sequence}</p>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Tab: Kontenplan ───────────────────────────────────────────────────────────
const TYP_LABELS = { aktiv:'Aktiv', passiv:'Passiv', ertrag:'Ertrag', aufwand:'Aufwand', neutral:'Neutral' }
const TYP_COLORS = { aktiv:'bg-blue-50 text-blue-700', passiv:'bg-purple-50 text-purple-700', ertrag:'bg-green-50 text-green-700', aufwand:'bg-red-50 text-red-700', neutral:'bg-neutral-100 text-neutral-600' }

function TabBuchhaltung({ embedded = false }) { // eslint-disable-line
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [editRow, setEditRow] = useState(null)
  const [editData, setEditData] = useState({})
  const [showNew, setShowNew] = useState(false)
  const [newData, setNewData] = useState({ nr:'', name:'', typ:'ertrag', ust_code:'', beschreibung:'' })
  const [typFilter, setTypFilter] = useState('')
  const [search, setSearch] = useState('')

  async function load() {
    setLoading(true)
    try { const res = await accountingApi.listAccounts({ active_only: false }); setAccounts(res.data) }
    catch { toast.error('Fehler beim Laden') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const filtered = accounts.filter(a => {
    if (typFilter && a.typ !== typFilter) return false
    if (search) { const s = search.toLowerCase(); return a.nr.includes(s) || a.name.toLowerCase().includes(s) }
    return true
  })

  async function handleSave(id) {
    try { await accountingApi.updateAccount(id, editData); toast.success('Gespeichert'); setEditRow(null); load() }
    catch { toast.error('Fehler') }
  }
  async function handleCreate() {
    try { await accountingApi.createAccount(newData); toast.success(`Konto ${newData.nr} angelegt`); setShowNew(false); setNewData({ nr:'', name:'', typ:'ertrag', ust_code:'', beschreibung:'' }); load() }
    catch (e) { toast.error(e.response?.data?.detail || 'Fehler') }
  }
  async function handleDelete(id, nr) {
    if (!window.confirm(`Konto ${nr} wirklich löschen?`)) return
    try { await accountingApi.deleteAccount(id); toast.success('Gelöscht'); load() }
    catch { toast.error('Fehler') }
  }
  async function handleSetDefault(id) {
    try { await accountingApi.setDefaultErloes(id); toast.success('Standard-Erlöskonto gesetzt'); load() }
    catch { toast.error('Fehler') }
  }

  if (loading) return <div className="flex justify-center py-8"><Loader2 size={24} className="animate-spin text-neutral-400" /></div>

  return (
    <div>
      <p className="text-xs text-neutral-400 mb-4">
        Vorbefüllt mit dem österreichischen EKR. <Star size={11} className="inline mb-0.5" />-Konto = Standard-Erlöskonto für neue Positionen.
      </p>
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Nr. oder Name…" className="flex-1 max-w-xs border border-neutral-200 rounded-lg px-3 py-1.5 text-sm" />
        <select value={typFilter} onChange={e => setTypFilter(e.target.value)} className="text-sm border border-neutral-200 rounded-lg px-3 py-1.5">
          <option value="">Alle Typen</option>
          {Object.entries(TYP_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button onClick={() => setShowNew(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"><Plus size={14} /> Konto hinzufügen</button>
      </div>
      {showNew && (
        <div className="border border-primary-200 bg-primary-50 rounded-xl p-4 mb-3 grid grid-cols-12 gap-2 items-center">
          <input value={newData.nr} onChange={e => setNewData({...newData, nr: e.target.value})} placeholder="Nr." className="col-span-2 border border-neutral-200 rounded px-2 py-1.5 text-sm" />
          <input value={newData.name} onChange={e => setNewData({...newData, name: e.target.value})} placeholder="Bezeichnung" className="col-span-4 border border-neutral-200 rounded px-2 py-1.5 text-sm" />
          <select value={newData.typ} onChange={e => setNewData({...newData, typ: e.target.value})} className="col-span-2 border border-neutral-200 rounded px-2 py-1.5 text-sm">
            {Object.entries(TYP_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input value={newData.ust_code} onChange={e => setNewData({...newData, ust_code: e.target.value})} placeholder="USt-Code" className="col-span-2 border border-neutral-200 rounded px-2 py-1.5 text-sm" />
          <div className="col-span-2 flex gap-1">
            <button onClick={handleCreate} className="flex-1 px-2 py-1.5 text-xs bg-primary-600 text-white rounded hover:bg-primary-700">Anlegen</button>
            <button onClick={() => setShowNew(false)} className="px-2 py-1.5 text-xs border rounded hover:bg-neutral-50">✕</button>
          </div>
        </div>
      )}
      <div className="border border-neutral-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="bg-neutral-50 border-b border-neutral-100">
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-20">Nr.</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500">Bezeichnung</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-24">Typ</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-20">USt-Code</th>
            <th className="px-3 py-2.5 w-28"></th>
          </tr></thead>
          <tbody className="divide-y divide-neutral-50">
            {filtered.map(a => (
              <tr key={a.id} className={`hover:bg-neutral-50 ${!a.is_active ? 'opacity-40' : ''}`}>
                {editRow === a.id ? (
                  <>
                    <td className="px-2 py-1.5"><input value={editData.nr} onChange={e => setEditData({...editData, nr: e.target.value})} className="w-full border border-neutral-200 rounded px-2 py-1 text-sm font-mono" /></td>
                    <td className="px-2 py-1.5"><input value={editData.name} onChange={e => setEditData({...editData, name: e.target.value})} className="w-full border border-neutral-200 rounded px-2 py-1 text-sm" /></td>
                    <td className="px-2 py-1.5"><select value={editData.typ} onChange={e => setEditData({...editData, typ: e.target.value})} className="w-full border border-neutral-200 rounded px-1 py-1 text-xs">{Object.entries(TYP_LABELS).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                    <td className="px-2 py-1.5"><input value={editData.ust_code || ''} onChange={e => setEditData({...editData, ust_code: e.target.value})} className="w-full border border-neutral-200 rounded px-2 py-1 text-xs" /></td>
                    <td className="px-2 py-1.5"><div className="flex gap-1">
                      <button onClick={() => handleSave(a.id)} className="px-2 py-1 text-xs bg-primary-600 text-white rounded hover:bg-primary-700"><Save size={12} /></button>
                      <button onClick={() => setEditRow(null)} className="px-2 py-1 text-xs border rounded hover:bg-neutral-50">✕</button>
                    </div></td>
                  </>
                ) : (
                  <>
                    <td className="px-3 py-2.5 font-mono font-medium text-neutral-800">{a.nr}{a.is_default_erloes && <Star size={11} className="inline ml-1 text-amber-500 mb-0.5" fill="currentColor" />}</td>
                    <td className="px-3 py-2.5 text-neutral-700">{a.name}</td>
                    <td className="px-3 py-2.5"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYP_COLORS[a.typ] || 'bg-neutral-100 text-neutral-600'}`}>{TYP_LABELS[a.typ] || a.typ}</span></td>
                    <td className="px-3 py-2.5 text-xs text-neutral-500 font-mono">{a.ust_code || '—'}</td>
                    <td className="px-3 py-2.5"><div className="flex gap-1 justify-end">
                      {!a.is_default_erloes && a.typ === 'ertrag' && <button onClick={() => handleSetDefault(a.id)} title="Standard-Erlöskonto" className="p-1 text-neutral-400 hover:text-amber-500"><Star size={13} /></button>}
                      <button onClick={() => { setEditRow(a.id); setEditData({nr:a.nr, name:a.name, typ:a.typ, ust_code:a.ust_code||'', beschreibung:a.beschreibung||'', is_active:a.is_active, is_default_erloes:a.is_default_erloes}) }} className="p-1 text-neutral-400 hover:text-neutral-700"><Eye size={13} /></button>
                      <button onClick={() => handleDelete(a.id, a.nr)} className="p-1 text-neutral-400 hover:text-red-500"><Trash2 size={13} /></button>
                    </div></td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && <div className="text-center py-8 text-sm text-neutral-400">Keine Konten gefunden</div>}
      </div>
      <p className="text-xs text-neutral-400 mt-2">{filtered.length} von {accounts.length} Konten</p>
    </div>
  )
}

// ── Tab: Allgemein + Design (horizontale Unter-Tabs) ─────────────────────────
function TabAllgemeinWrapper({ settings, onSaved }) {
  const [sub, setSub] = useState('firma')
  const subTabs = [
    { id: 'firma',  label: 'Firmendaten' },
    { id: 'design', label: 'Design'      },
  ]
  return (
    <div>
      <div className="flex gap-1 bg-neutral-100 p-1 rounded-lg mb-5 w-fit">
        {subTabs.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)}
            className={`px-4 py-1.5 text-sm rounded-md transition-all ${sub === t.id ? 'bg-white text-neutral-900 shadow-sm font-medium' : 'text-neutral-600 hover:text-neutral-800'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {sub === 'firma'  && <TabAllgemein settings={settings} onSaved={onSaved} />}
      {sub === 'design' && <TabDesign    settings={settings} onSaved={onSaved} />}
    </div>
  )
}

// ── Tab: Parameter (horizontale Unter-Tabs) ───────────────────────────────────
function TabParameter() {
  const [sub, setSub] = useState('belege')
  const subTabs = [
    { id: 'belege',   label: 'Belegeinstellungen' },
    { id: 'nummern',  label: 'Belegnummern'       },
    { id: 'konten',   label: 'Kontenplan (EKR)'   },
  ]
  return (
    <div>
      <div className="flex gap-1 bg-neutral-100 p-1 rounded-lg mb-5 w-fit">
        {subTabs.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)}
            className={`px-4 py-1.5 text-sm rounded-md transition-all ${sub === t.id ? 'bg-white text-neutral-900 shadow-sm font-medium' : 'text-neutral-600 hover:text-neutral-800'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {sub === 'belege'  && <TabRechnung embedded />}
      {sub === 'nummern' && <BelegnummernSection />}
      {sub === 'konten'  && <TabBuchhaltung embedded />}
    </div>
  )
}

// ── Tab: System + Backup (horizontale Unter-Tabs) ────────────────────────────
function TabSystemWrapper({ settings, onSaved }) {
  const [sub, setSub] = useState('system')
  const subTabs = [
    { id: 'system', label: 'System' },
    { id: 'backup', label: 'Backup' },
  ]
  return (
    <div>
      <div className="flex gap-1 bg-neutral-100 p-1 rounded-lg mb-5 w-fit">
        {subTabs.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)}
            className={`px-4 py-1.5 text-sm rounded-md transition-all ${sub === t.id ? 'bg-white text-neutral-900 shadow-sm font-medium' : 'text-neutral-600 hover:text-neutral-800'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {sub === 'system' && <TabSystem />}
      {sub === 'backup' && <TabBackup settings={settings} onSaved={onSaved} />}
    </div>
  )
}

// ── Hauptseite ────────────────────────────────────────────────────────────────
export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('allgemein')
  const { settings, loading, loadSettings } = useSettings()

  const tabs = [
    { id: 'allgemein',  label: 'Allgemein',  icon: Building2 },
    { id: 'parameter',  label: 'Parameter',  icon: BookOpen  },
    { id: 'email',      label: 'E-Mail',     icon: Mail      },
    { id: 'system',     label: 'System',     icon: Cpu       },
  ]

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 size={28} className="animate-spin text-primary-400" />
    </div>
  )

  return (
    <div className="max-w-3xl mx-auto p-4 sm:p-6 lg:p-8">
      <div className="flex items-center gap-3 mb-8">
        <div className="p-2 bg-primary-50 rounded-xl"><Settings2 size={22} className="text-primary-600" /></div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Einstellungen</h1>
          <p className="text-sm text-gray-400 mt-0.5">Programm konfigurieren</p>
        </div>
        <button onClick={loadSettings} className="ml-auto p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition" title="Neu laden"><RefreshCw size={16} /></button>
      </div>
      <div className="flex gap-2 mb-6 flex-wrap">
        {tabs.map(t => <Tab key={t.id} {...t} active={activeTab === t.id} onClick={setActiveTab} />)}
      </div>
      <div className="card p-6">
        {activeTab === 'allgemein'  && <TabAllgemeinWrapper settings={settings} onSaved={loadSettings} />}
        {activeTab === 'parameter'  && <TabParameter />}
        {activeTab === 'email'      && <TabEmail      settings={settings} onSaved={loadSettings} />}
        {activeTab === 'system'     && <TabSystemWrapper settings={settings} onSaved={loadSettings} />}
      </div>
    </div>
  )
}
