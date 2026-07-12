/**
 * BerichtDialog – Projektzeitbericht erstellen
 * Features: Zeitraum-Presets, Aufgaben-Filter, Rundung, Vorschau, PDF, Dateiname
 */
import { useState, useEffect } from 'react'
import { reportsApi, usersApi } from '../services/api'
import toast from 'react-hot-toast'
import {
  X, FileText, Download, Loader2, Users, Briefcase,
  Eye, Pencil, ChevronDown, ChevronUp,
} from 'lucide-react'

// ── Datum-Hilfsfunktionen ─────────────────────────────────────────────────────
const fmt = (d) => d.toISOString().slice(0, 10)

function getPresetRange(preset) {
  const now = new Date()
  const y   = now.getFullYear()
  const m   = now.getMonth()

  switch (preset) {
    case 'heute':
      return { from: fmt(now), to: fmt(now) }
    case 'woche': {
      const dow  = (now.getDay() + 6) % 7      // Mo=0 … So=6
      const mon  = new Date(now); mon.setDate(now.getDate() - dow)
      const sun  = new Date(mon); sun.setDate(mon.getDate() + 6)
      return { from: fmt(mon), to: fmt(sun) }
    }
    case 'monat':
      return {
        from: fmt(new Date(y, m, 1)),
        to:   fmt(new Date(y, m + 1, 0)),
      }
    case 'quartal': {
      const q    = Math.floor(m / 3)
      return {
        from: fmt(new Date(y, q * 3, 1)),
        to:   fmt(new Date(y, q * 3 + 3, 0)),
      }
    }
    case 'jahr':
      return { from: fmt(new Date(y, 0, 1)), to: fmt(new Date(y, 11, 31)) }
    case 'gesamt':
      return { from: '2000-01-01', to: fmt(now) }
    default:
      return null
  }
}

/** Liest den Detail-Text aus einem Axios-Fehler — auch wenn responseType 'blob' war. */
async function readErrorDetail(err) {
  if (!err.response) return err.message || 'Unbekannter Fehler'
  const data = err.response.data
  if (data instanceof Blob) {
    try {
      const text = await data.text()
      const json = JSON.parse(text)
      return json?.detail || text || 'Unbekannter Fehler'
    } catch {
      return 'Unbekannter Fehler'
    }
  }
  return data?.detail || JSON.stringify(data) || 'Unbekannter Fehler'
}

// ── Kleines Formularfeld ──────────────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  )
}

const inputCls  = "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
const selectCls = "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface"

const PRESETS = [
  { id: 'heute',   label: 'Heute' },
  { id: 'woche',   label: 'Diese Woche' },
  { id: 'monat',   label: 'Dieser Monat' },
  { id: 'quartal', label: 'Dieses Quartal' },
  { id: 'jahr',    label: 'Dieses Jahr' },
  { id: 'gesamt',  label: 'Gesamt' },
  { id: 'frei',    label: 'Frei' },
]

// ── Hauptkomponente ───────────────────────────────────────────────────────────
export default function BerichtDialog({ onClose }) {
  // Zeitraum
  const [activePreset, setActivePreset] = useState('monat')
  const [dateFrom,     setDateFrom]     = useState(() => getPresetRange('monat').from)
  const [dateTo,       setDateTo]       = useState(() => getPresetRange('monat').to)

  // Gruppierung
  const [groupBy, setGroupBy] = useState('aufgabe')

  // Filter
  const [contactName,  setContactName]  = useState('')
  const [contactInput, setContactInput] = useState('')
  const [contactOpen,  setContactOpen]  = useState(false)
  const [contacts,     setContacts]     = useState([])

  const [taskName,  setTaskName]  = useState('')
  const [tasks,     setTasks]     = useState([])

  const [userId, setUserId] = useState('')
  const [users,  setUsers]  = useState([])

  const [billable, setBillable] = useState('all')

  // Rundung
  const [roundTo,  setRoundTo]  = useState(15)    // 0 = keine
  const [roundDir, setRoundDir] = useState('up')

  // Erweiterte Filter aufgeklappt?
  const [showExtended, setShowExtended] = useState(false)

  // Dateiname
  const [filenameInput, setFilenameInput] = useState('')
  const [editFilename,  setEditFilename]  = useState(false)

  // Loading
  const [loadingPdf,  setLoadingPdf]  = useState(false)
  const [loadingHtml, setLoadingHtml] = useState(false)

  useEffect(() => {
    usersApi.list().then(r => setUsers(r.data)).catch(() => {})
    reportsApi.getContacts().then(r => setContacts(r.data.contacts || [])).catch(() => {})
    reportsApi.getTasks().then(r => setTasks(r.data.tasks || [])).catch(() => {})
  }, [])

  // ── Preset-Auswahl ────────────────────────────────────────────────────────
  const handlePreset = (id) => {
    setActivePreset(id)
    if (id !== 'frei') {
      const range = getPresetRange(id)
      setDateFrom(range.from)
      setDateTo(range.to)
    }
  }

  const handleDateChange = (field, val) => {
    setActivePreset('frei')
    if (field === 'from') setDateFrom(val)
    else setDateTo(val)
  }

  // ── Standard-Dateiname ────────────────────────────────────────────────────
  const defaultFilename = (() => {
    const cf = contactName ? `_${contactName.replace(/\s+/g, '_')}` : ''
    const tf = taskName    ? `_${taskName.replace(/\s+/g, '_')}`    : ''
    return `Projektzeitbericht${cf}${tf}_${dateFrom}_${dateTo}`
  })()

  // ── Parameter zusammenstellen ─────────────────────────────────────────────
  const buildParams = (extra = {}) => {
    const params = {
      date_from: dateFrom,
      date_to:   dateTo,
      group_by:  groupBy,
      round_to:  roundTo,
      round_dir: roundDir,
      ...extra,
    }
    if (contactName) params.contact_name = contactName
    if (taskName)    params.project_name = taskName
    if (userId)      params.user_id      = userId
    if (billable !== 'all') params.billable = billable
    if (filenameInput.trim()) params.filename = filenameInput.trim()
    return params
  }

  const filteredContacts = contacts.filter(c =>
    c.toLowerCase().includes(contactInput.toLowerCase())
  )

  // ── PDF herunterladen ─────────────────────────────────────────────────────
  const handleDownload = async () => {
    setLoadingPdf(true)
    try {
      const res = await reportsApi.downloadZeiterfassung(buildParams({ format: 'pdf' }))
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a   = document.createElement('a')
      const cd  = res.headers['content-disposition'] || ''
      const m   = cd.match(/filename="?([^"]+)"?/)
      a.href     = url
      a.download = m ? m[1] : `${filenameInput.trim() || defaultFilename}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
      toast.success('Bericht heruntergeladen')
    } catch (err) {
      const msg = err.response?.status === 404
        ? 'Keine Zeiteinträge für die gewählten Filter gefunden'
        : await readErrorDetail(err)
      toast.error(msg)
    } finally {
      setLoadingPdf(false)
    }
  }

  // ── HTML-Vorschau ─────────────────────────────────────────────────────────
  const handlePreview = async () => {
    setLoadingHtml(true)
    try {
      const res  = await reportsApi.previewZeiterfassung(buildParams())
      const blob = new Blob([res.data], { type: 'text/html; charset=utf-8' })
      const url  = window.URL.createObjectURL(blob)
      window.open(url, '_blank')
      setTimeout(() => window.URL.revokeObjectURL(url), 10_000)
    } catch (err) {
      const msg = err.response?.status === 404
        ? 'Keine Zeiteinträge für die gewählten Filter gefunden'
        : (err.response?.data || err.message || 'Vorschau konnte nicht geladen werden')
      toast.error(typeof msg === 'string' ? msg : 'Vorschau konnte nicht geladen werden')
    } finally {
      setLoadingHtml(false)
    }
  }

  const busy = loadingPdf || loadingHtml

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />

      {/* Dialog */}
      <div className="relative bg-surface rounded-2xl shadow-2xl w-full max-w-xl overflow-hidden flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary-50 rounded-xl">
              <FileText size={18} className="text-primary-600" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-gray-900">Projektzeitbericht</h2>
              <p className="text-xs text-gray-400">PDF erstellen oder Vorschau anzeigen</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400">
            <X size={18} />
          </button>
        </div>

        {/* Scrollbarer Body */}
        <div className="overflow-y-auto flex-1 px-6 py-5 space-y-5">

          {/* ── Zeitraum-Presets ────────────────────────────────────────────── */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-2">Zeitraum</label>
            <div className="flex flex-wrap gap-1.5 mb-3">
              {PRESETS.map(p => (
                <button key={p.id} onClick={() => handlePreset(p.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                    activePreset === p.id
                      ? 'border-primary-400 bg-primary-50 text-primary-700'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}>
                  {p.label}
                </button>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Von">
                <input type="date" value={dateFrom}
                  onChange={e => handleDateChange('from', e.target.value)}
                  className={inputCls} />
              </Field>
              <Field label="Bis">
                <input type="date" value={dateTo}
                  onChange={e => handleDateChange('to', e.target.value)}
                  className={inputCls} />
              </Field>
            </div>
          </div>

          {/* ── Gruppierung ─────────────────────────────────────────────────── */}
          <Field label="Gruppierung">
            <div className="grid grid-cols-2 gap-2">
              {[
                { id: 'aufgabe',  icon: Briefcase, label: 'Nach Aufgabe',  desc: 'Aufgaben als Abschnitte' },
                { id: 'benutzer', icon: Users,     label: 'Nach Benutzer', desc: 'Mitarbeiter als Abschnitte' },
              ].map(opt => (
                <button key={opt.id} onClick={() => setGroupBy(opt.id)}
                  className={`flex items-start gap-2 p-3 rounded-xl border-2 text-left transition ${
                    groupBy === opt.id
                      ? 'border-primary-400 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}>
                  <opt.icon size={15} className={groupBy === opt.id ? 'text-primary-600 mt-0.5' : 'text-gray-400 mt-0.5'} />
                  <div>
                    <div className={`text-xs font-semibold ${groupBy === opt.id ? 'text-primary-700' : 'text-gray-700'}`}>
                      {opt.label}
                    </div>
                    <div className="text-xs text-gray-400">{opt.desc}</div>
                  </div>
                </button>
              ))}
            </div>
          </Field>

          {/* ── Rundung ─────────────────────────────────────────────────────── */}
          <div className="p-3 bg-gray-50 rounded-xl border border-gray-200">
            <label className="block text-xs font-medium text-gray-500 mb-2">Zeitrundung</label>
            <div className="flex gap-3 items-center">
              <div className="flex-1">
                <select value={roundTo} onChange={e => setRoundTo(Number(e.target.value))}
                  className={selectCls}>
                  <option value={0}>Keine Rundung</option>
                  <option value={5}>5 Minuten</option>
                  <option value={10}>10 Minuten</option>
                  <option value={15}>15 Minuten</option>
                  <option value={30}>30 Minuten</option>
                  <option value={60}>60 Minuten</option>
                </select>
              </div>
              {roundTo > 0 && (
                <div className="flex gap-1">
                  {[
                    { id: 'up',   label: 'Aufrunden' },
                    { id: 'down', label: 'Abrunden' },
                  ].map(opt => (
                    <button key={opt.id} onClick={() => setRoundDir(opt.id)}
                      className={`px-3 py-2 rounded-lg text-xs font-medium border transition ${
                        roundDir === opt.id
                          ? 'border-primary-400 bg-primary-50 text-primary-700'
                          : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}>
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {roundTo > 0 && (
              <p className="text-xs text-gray-400 mt-1.5">
                Jeder Zeiteintrag wird einzeln auf {roundTo} Minuten {roundDir === 'up' ? 'aufgerundet' : 'abgerundet'}.
              </p>
            )}
          </div>

          {/* ── Basis-Filter ─────────────────────────────────────────────────── */}
          <div className="grid grid-cols-2 gap-3">

            {/* Kontakt/Kunde */}
            <Field label="Kontakt / Kunde">
              <div className="relative">
                <input
                  type="text"
                  value={contactInput || contactName}
                  onChange={e => { setContactInput(e.target.value); setContactName(e.target.value); setContactOpen(true) }}
                  onFocus={() => setContactOpen(true)}
                  onBlur={() => setTimeout(() => setContactOpen(false), 150)}
                  placeholder="Alle Kunden"
                  className={inputCls}
                />
                {contactOpen && filteredContacts.length > 0 && (
                  <div className="absolute z-10 top-full left-0 right-0 mt-1 bg-surface border border-gray-200 rounded-lg shadow-lg max-h-36 overflow-y-auto">
                    <div className="px-3 py-1.5 text-xs text-gray-400 border-b cursor-pointer hover:bg-gray-50"
                      onMouseDown={() => { setContactName(''); setContactInput(''); setContactOpen(false) }}>
                      — Alle Kunden —
                    </div>
                    {filteredContacts.map(c => (
                      <div key={c}
                        onMouseDown={() => { setContactName(c); setContactInput(''); setContactOpen(false) }}
                        className="px-3 py-1.5 text-sm hover:bg-primary-50 cursor-pointer">
                        {c}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </Field>

            {/* Benutzer */}
            <Field label="Benutzer">
              <select value={userId} onChange={e => setUserId(e.target.value)} className={selectCls}>
                <option value="">Alle Benutzer</option>
                {users.map(u => (
                  <option key={u.id} value={u.id}>{u.full_name}</option>
                ))}
              </select>
            </Field>

          </div>

          {/* ── Verrechenbar ─────────────────────────────────────────────────── */}
          <Field label="Verrechenbar">
            <div className="flex gap-2">
              {[
                { id: 'all', label: 'Alle' },
                { id: 'yes', label: 'Nur verrechenbar' },
                { id: 'no',  label: 'Nur nicht verrechenbar' },
              ].map(opt => (
                <button key={opt.id} onClick={() => setBillable(opt.id)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition ${
                    billable === opt.id
                      ? 'border-primary-400 bg-primary-50 text-primary-700'
                      : 'border-gray-200 text-gray-600 hover:border-gray-300'
                  }`}>
                  {opt.label}
                </button>
              ))}
            </div>
          </Field>

          {/* ── Erweiterte Filter ─────────────────────────────────────────────── */}
          <div className="border border-gray-200 rounded-xl overflow-hidden">
            <button
              onClick={() => setShowExtended(v => !v)}
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-gray-600 hover:bg-gray-50 transition">
              <span>Weitere Filter</span>
              {showExtended ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showExtended && (
              <div className="px-4 pb-4 pt-1 border-t border-gray-100">
                <Field label="Aufgabe">
                  <select value={taskName} onChange={e => setTaskName(e.target.value)} className={selectCls}>
                    <option value="">Alle Aufgaben</option>
                    {tasks.map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </Field>
              </div>
            )}
          </div>

          {/* ── Dateiname ─────────────────────────────────────────────────────── */}
          <Field label="Dateiname">
            {editFilename ? (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={filenameInput}
                  onChange={e => setFilenameInput(e.target.value)}
                  placeholder={defaultFilename}
                  className={inputCls}
                  autoFocus
                  onBlur={() => { if (!filenameInput.trim()) setEditFilename(false) }}
                />
                <span className="text-xs text-gray-400 whitespace-nowrap">.pdf</span>
              </div>
            ) : (
              <button
                onClick={() => setEditFilename(true)}
                className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-primary-600 transition">
                <Pencil size={12} className="shrink-0" />
                <span className="truncate">
                  {filenameInput.trim() || defaultFilename}
                  <span className="text-gray-300">.pdf</span>
                </span>
              </button>
            )}
          </Field>

        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between bg-gray-50 shrink-0">
          <p className="text-xs text-gray-400">
            PDF mit Firmenlogo und Adresse
          </p>
          <div className="flex gap-2">
            <button onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition">
              Abbrechen
            </button>
            <button onClick={handlePreview} disabled={busy || !dateFrom || !dateTo}
              className="flex items-center gap-2 px-4 py-2 border border-primary-300 bg-surface hover:bg-primary-50 disabled:opacity-50 text-primary-700 text-sm font-medium rounded-xl transition">
              {loadingHtml
                ? <><Loader2 size={14} className="animate-spin" /> Lade…</>
                : <><Eye size={14} /> Vorschau</>
              }
            </button>
            <button onClick={handleDownload} disabled={busy || !dateFrom || !dateTo}
              className="flex items-center gap-2 px-5 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white text-sm font-medium rounded-xl transition">
              {loadingPdf
                ? <><Loader2 size={14} className="animate-spin" /> Erstelle PDF…</>
                : <><Download size={14} /> PDF herunterladen</>
              }
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
