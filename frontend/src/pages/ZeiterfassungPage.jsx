import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { zeiterfassungApi, masterdataApi, usersApi } from '../services/api'
import toast from 'react-hot-toast'
import {
  Play, Square, Plus, Trash2, Search, ChevronLeft, ChevronRight,
  Clock, Loader2, X, Check, Settings2, Timer, Euro,
  PauseCircle, RefreshCw, FileText
} from 'lucide-react'
import BerichtDialog from '../components/BerichtDialog'
import AttachmentPanel from '../components/AttachmentPanel'

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────
function fmtMinutes(min) {
  if (min === null || min === undefined) return '—'
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${h}:${String(m).padStart(2, '0')}`
}

function fmtElapsed(startedAt) {
  const sec = Math.floor((Date.now() - new Date(startedAt)) / 1000)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' })
}

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('de-AT', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' })
}

function nowIso() { return new Date().toISOString() }
function isoToDateLocal(iso) { return iso ? new Date(iso).toISOString().slice(0, 10) : '' }
function isoToTimeLocal(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
function localToIso(date, time) {
  if (!date || !time) return null
  return new Date(`${date}T${time}:00`).toISOString()
}
function calcDuration(startedAt, endedAt, pauseMin) {
  if (!startedAt || !endedAt) return 0
  const delta = (new Date(endedAt) - new Date(startedAt)) / 60000
  return Math.max(0, Math.round(delta) - (pauseMin || 0))
}

// ── Projekt-Suche ─────────────────────────────────────────────────────────────
function ProjectSearch({ value, onChange, disabled, placeholder = 'Projekt suchen…' }) {
  const [search, setSearch] = useState('')
  const [results, setResults] = useState([])
  const [isOpen, setIsOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setIsOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  useEffect(() => {
    if (!isOpen) return
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await masterdataApi.listRecords('projekte', { search: search || undefined, page_size: 20 })
        setResults(res.data.items.map(r => ({
          id: r.id,
          name: r.display_name,
          contactName: r.data?.kontakt?.display_name || r.data?.kunde?.display_name || '',
        })))
      } catch { setResults([]) }
      finally { setLoading(false) }
    }, 200)
    return () => clearTimeout(t)
  }, [search, isOpen])

  const handleSelect = (item) => {
    onChange({ projectId: item.id, projectName: item.name, contactName: item.contactName })
    setIsOpen(false); setSearch('')
  }

  const base = "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 transition disabled:bg-gray-50"

  if (value?.projectId) {
    return (
      <div className="flex items-center gap-2 px-3 py-2 border rounded-lg bg-primary-50 border-primary-200">
        <span className="text-sm text-primary-800 flex-1">
          {value.contactName && <span className="text-primary-400">{value.contactName} / </span>}
          <span className="font-medium">{value.projectName}</span>
        </span>
        {!disabled && (
          <button type="button" onClick={() => onChange({ projectId: null, projectName: '', contactName: '' })}
            className="text-primary-400 hover:text-red-500 transition">
            <X size={13} />
          </button>
        )}
      </div>
    )
  }

  return (
    <div ref={ref} className="relative">
      <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
      <input type="text" value={search}
        onChange={(e) => { setSearch(e.target.value); setIsOpen(true) }}
        onFocus={() => setIsOpen(true)}
        placeholder={placeholder}
        className={`${base} pl-8`}
        disabled={disabled}
      />
      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg z-30 overflow-hidden">
          {results.length > 0 ? (
            <ul className="max-h-52 overflow-y-auto">
              {results.map(item => (
                <li key={item.id}>
                  <button type="button" onClick={() => handleSelect(item)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-primary-50 transition flex flex-col">
                    <span className="font-medium text-gray-800">{item.name}</span>
                    {item.contactName && <span className="text-xs text-gray-400">{item.contactName}</span>}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="px-4 py-3 text-sm text-gray-400 text-center">
              {loading ? 'Suche…' : search ? 'Keine Projekte gefunden' : 'Projektnamen eingeben…'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Laufender Timer (Karte im Screenshot-Stil) ────────────────────────────────
function RunningTimerCard({ entry, onStop, onPause, onSwitch, onDelete, onUpdate }) {
  const [elapsed, setElapsed] = useState(() => fmtElapsed(entry.started_at))
  const [note, setNote] = useState(entry.note || '')
  const [billable, setBillable] = useState(entry.billable)
  const [project, setProject] = useState({
    projectId: entry.project_id,
    projectName: entry.project_name || '',
    contactName: entry.contact_name || '',
  })
  const [pause, setPause] = useState(entry.pause_minutes || 0)

  // Sekunden-Ticker
  useEffect(() => {
    const id = setInterval(() => setElapsed(fmtElapsed(entry.started_at)), 1000)
    return () => clearInterval(id)
  }, [entry.started_at])

  // Felder live speichern (Debounce)
  useEffect(() => {
    const t = setTimeout(() => {
      onUpdate({ note, billable, project, pause })
    }, 800)
    return () => clearTimeout(t)
  }, [note, billable, project, pause])

  return (
    <div className={`bg-white rounded-2xl border-2 overflow-hidden mb-6 ${billable ? 'border-green-400' : 'border-orange-400'}`}>
      {/* Farbiger Akzent-Streifen oben */}
      <div className={`h-1 ${billable ? 'bg-gradient-to-r from-green-400 to-green-500' : 'bg-gradient-to-r from-orange-400 to-orange-500'}`} />

      <div className="p-5">
        <div className="flex gap-6">
          {/* Stoppuhr-Icon */}
          <div className="flex-shrink-0 pt-1">
            <div className="w-9 h-9 rounded-xl bg-green-50 flex items-center justify-center">
              <Timer size={18} className="text-green-600" />
            </div>
          </div>

          {/* Linke Spalte: Aufgabe + Notiz */}
          <div className="flex-1 min-w-0 grid grid-cols-1 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Aufgabe</label>
              <ProjectSearch value={project} onChange={setProject} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Notiz</label>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                placeholder="Was machst du gerade?"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
              />
            </div>
          </div>

          {/* Rechte Spalte: Startzeit, Endzeit (live), Pause, Verrechenbar */}
          <div className="flex-shrink-0 w-48 grid grid-cols-1 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Startzeit</label>
              <div className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg bg-gray-50">
                <Clock size={13} className="text-gray-400 flex-shrink-0" />
                <span className="text-sm text-gray-700">{fmtTime(entry.started_at)}</span>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Endzeit</label>
              <div className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg bg-gray-50">
                <Clock size={13} className="text-gray-400 flex-shrink-0" />
                <LiveTime />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Pause</label>
              <div className="flex items-center gap-2">
                <input type="number" value={pause} onChange={(e) => setPause(Number(e.target.value))} min={0}
                  className="w-16 px-2 py-2 border border-gray-300 rounded-lg text-sm text-center focus:outline-none focus:ring-2 focus:ring-primary-500" />
                <span className="text-xs text-gray-400">min</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="run-billable" checked={billable} onChange={(e) => setBillable(e.target.checked)}
                className="w-4 h-4 rounded accent-primary-600" />
              <label htmlFor="run-billable" className="text-sm text-gray-700 cursor-pointer">Verrechenbar</label>
            </div>
          </div>
        </div>

        {/* Action-Bar */}
        <div className="flex items-center mt-4 pt-4 border-t border-gray-100">
          {/* Löschen */}
          <button onClick={onDelete}
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition border border-gray-200">
            Löschen
          </button>

          {/* Elapsed */}
          <div className="flex items-center gap-2 mx-auto">
            <div className="w-3 h-3 bg-red-500 rounded-full animate-pulse" />
            <span className="text-xl font-bold text-gray-800 tabular-nums">{elapsed}</span>
          </div>

          {/* Pause / Wechseln / Stop */}
          <div className="flex items-center gap-2">
            <button onClick={onPause}
              className="px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-300 rounded-lg hover:bg-gray-50 transition">
              Pause
            </button>
            <button onClick={onSwitch}
              className="px-3 py-1.5 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition">
              Wechseln
            </button>
            <button onClick={() => onStop({ note, billable, project, pause })}
              className="px-3 py-1.5 text-sm font-medium text-white bg-gray-700 hover:bg-gray-800 rounded-lg transition flex items-center gap-1.5">
              <Square size={12} fill="white" />
              Stop
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// Aktuelle Uhrzeit (live, jede Minute)
function LiveTime() {
  const [time, setTime] = useState(fmtTime(new Date().toISOString()))
  useEffect(() => {
    const id = setInterval(() => setTime(fmtTime(new Date().toISOString())), 10000)
    return () => clearInterval(id)
  }, [])
  return <span className="text-sm text-gray-700">{time}</span>
}

// ── Start-Formular (kein laufender Timer) ─────────────────────────────────────
function StartTimerCard({ onStart }) {
  const [project, setProject] = useState({ projectId: null, projectName: '', contactName: '' })
  const [note, setNote] = useState('')
  const [billable, setBillable] = useState(true)
  const [starting, setStarting] = useState(false)

  const handleStart = async () => {
    setStarting(true)
    try {
      await onStart({ project, note, billable })
      setNote('')
      setProject({ projectId: null, projectName: '', contactName: '' })
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden mb-6">
      <div className="h-1 bg-gray-100" />
      <div className="p-5">
        <div className="flex gap-6">
          <div className="flex-shrink-0 pt-1">
            <div className="w-9 h-9 rounded-xl bg-gray-50 flex items-center justify-center">
              <Timer size={18} className="text-gray-400" />
            </div>
          </div>

          <div className="flex-1 min-w-0 grid grid-cols-1 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Aufgabe</label>
              <ProjectSearch value={project} onChange={setProject} />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Notiz</label>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Was machst du gerade?"
                onKeyDown={(e) => e.key === 'Enter' && handleStart()}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          </div>

          <div className="flex-shrink-0 w-48 flex flex-col gap-3 justify-between">
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Startzeit</label>
              <div className="flex items-center gap-2 px-3 py-2 border border-gray-200 rounded-lg bg-gray-50">
                <Clock size={13} className="text-gray-400 flex-shrink-0" />
                <LiveTime />
              </div>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="start-billable" checked={billable} onChange={(e) => setBillable(e.target.checked)}
                className="w-4 h-4 rounded accent-primary-600" />
              <label htmlFor="start-billable" className="text-sm text-gray-700 cursor-pointer">Verrechenbar</label>
            </div>
            <button onClick={handleStart} disabled={starting}
              className="w-full py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-lg transition flex items-center justify-center gap-2">
              {starting ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} fill="white" />}
              Start
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Ring-Diagramm ─────────────────────────────────────────────────────────────
// Zeigt zwei Bögen: grün = verrechenbar, orange = nicht verrechenbar
function RingChart({ label, minutes, billableMinutes, targetMinutes }) {
  const r = 36, cx = 44, cy = 44, circ = 2 * Math.PI * r

  const nonBillable = Math.max(0, minutes - billableMinutes)
  const billablePct    = targetMinutes > 0 ? Math.min(1, billableMinutes / targetMinutes) : 0
  const nonBillablePct = targetMinutes > 0 ? Math.min(1 - billablePct, nonBillable / targetMinutes) : 0

  const billableLen    = billablePct * circ
  const nonBillableLen = nonBillablePct * circ
  // Oranger Bogen beginnt dort wo der grüne aufhört
  const orangeRotation = -90 + billablePct * 360

  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-xs text-gray-400 font-medium uppercase tracking-wide">{label}</span>
      <div className="relative">
        <svg width={88} height={88}>
          {/* Hintergrund-Ring (Ziel) */}
          <circle cx={cx} cy={cy} r={r} fill="none" stroke="#f3f4f6" strokeWidth={7} />

          {/* Oranger Bogen — nicht verrechenbar (beginnt nach dem grünen) */}
          {nonBillableLen > 0 && (
            <circle cx={cx} cy={cy} r={r} fill="none"
              stroke="#f97316" strokeWidth={7}
              strokeDasharray={`${nonBillableLen} ${circ - nonBillableLen}`}
              strokeLinecap="round"
              transform={`rotate(${orangeRotation} ${cx} ${cy})`} />
          )}

          {/* Grüner Bogen — verrechenbar (beginnt oben) */}
          {billableLen > 0 && (
            <circle cx={cx} cy={cy} r={r} fill="none"
              stroke="#16a34a" strokeWidth={7}
              strokeDasharray={`${billableLen} ${circ - billableLen}`}
              strokeLinecap="round"
              transform={`rotate(-90 ${cx} ${cy})`} />
          )}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-base font-bold text-gray-800">{fmtMinutes(minutes)}</span>
          <span className="text-[10px] text-gray-400">{fmtMinutes(targetMinutes)}</span>
        </div>
      </div>
    </div>
  )
}

// ── Nachtragen / Bearbeiten Modal ─────────────────────────────────────────────
function EntryModal({ entry, onClose, onSaved }) {
  const isEdit = !!entry
  const now = new Date()
  const [project, setProject] = useState(entry ? {
    projectId: entry.project_id, projectName: entry.project_name || '',
    contactName: entry.contact_name || '',
  } : { projectId: null, projectName: '', contactName: '' })
  const [startDate, setStartDate] = useState(entry ? isoToDateLocal(entry.started_at) : isoToDateLocal(now.toISOString()))
  const [startTime, setStartTime] = useState(entry ? isoToTimeLocal(entry.started_at) : isoToTimeLocal(now.toISOString()))
  const [endDate, setEndDate] = useState(entry?.ended_at ? isoToDateLocal(entry.ended_at) : isoToDateLocal(now.toISOString()))
  const [endTime, setEndTime] = useState(entry?.ended_at ? isoToTimeLocal(entry.ended_at) : isoToTimeLocal(now.toISOString()))
  const [pause, setPause] = useState(entry?.pause_minutes ?? 0)
  const [note, setNote] = useState(entry?.note ?? '')
  const [billable, setBillable] = useState(entry?.billable ?? true)
  const [loading, setLoading] = useState(false)
  const [createAnother, setCreateAnother] = useState(false)

  const startedAt = localToIso(startDate, startTime)
  const endedAt = localToIso(endDate, endTime)
  const durationMin = calcDuration(startedAt, endedAt, pause)

  const handleSave = async () => {
    if (!startedAt) return toast.error('Bitte Startzeit angeben')
    setLoading(true)
    try {
      const payload = {
        project_id: project.projectId || null,
        project_name: project.projectName || null,
        contact_id: null, contact_name: project.contactName || null,
        started_at: startedAt, ended_at: endedAt || null,
        pause_minutes: Number(pause) || 0,
        note: note || null, billable, data: {},
      }
      if (isEdit) {
        await zeiterfassungApi.updateEntry(entry.id, payload)
        toast.success('Zeiteintrag aktualisiert')
      } else {
        await zeiterfassungApi.createEntry(payload)
        toast.success('Zeiteintrag gespeichert')
      }
      if (createAnother && !isEdit) {
        setNote(''); setPause(0)
        setStartTime(endTime); setStartDate(endDate)
        setEndTime(isoToTimeLocal(new Date().toISOString()))
      } else { onSaved() }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern')
    } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-8">
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-900">
            {isEdit ? 'Zeiteintrag bearbeiten' : 'Projektzeit nachtragen'}
          </h2>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition">
            <X size={20} />
          </button>
        </div>
        <div className="p-5 grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Projekt</label>
            <ProjectSearch value={project} onChange={setProject} />
          </div>
          <div className="col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
              placeholder="Was wurde gemacht?"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Startzeit</label>
            <div className="flex gap-2">
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                className="flex-1 px-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
              <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)}
                className="w-24 px-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Endzeit</label>
            <div className="flex gap-2">
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                className="flex-1 px-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
              <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)}
                className="w-24 px-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pause (Minuten)</label>
            <input type="number" value={pause} onChange={(e) => setPause(e.target.value)} min={0}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Dauer</label>
            <div className="px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-600 font-medium">
              {fmtMinutes(durationMin)} h
            </div>
          </div>
          <div className="col-span-2 flex items-center gap-3">
            <input type="checkbox" id="modal-billable" checked={billable} onChange={(e) => setBillable(e.target.checked)}
              className="w-5 h-5 rounded accent-primary-600" />
            <label htmlFor="modal-billable" className="text-sm font-medium text-gray-700 cursor-pointer">Verrechenbar</label>
          </div>
        </div>
        <div className="flex items-center gap-3 p-5 border-t border-gray-100">
          {!isEdit && (
            <label className="flex items-center gap-2 text-sm text-gray-500 cursor-pointer mr-auto">
              <input type="checkbox" checked={createAnother} onChange={(e) => setCreateAnother(e.target.checked)}
                className="w-4 h-4 rounded accent-primary-600" />
              Weiteren erstellen
            </label>
          )}
          <button onClick={onClose} className="px-5 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition">
            Abbrechen
          </button>
          <button onClick={handleSave} disabled={loading}
            className="px-6 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center gap-2">
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
            Speichern
          </button>
        </div>

        {/* Anhänge – nur bei bestehenden Einträgen */}
        {isEdit && (
          <div className="px-5 pb-5 border-t border-gray-100">
            <AttachmentPanel entityType="zeiterfassung" entityId={entry.id} />
          </div>
        )}
      </div>
    </div>
  )
}

// ── Zeiteintrag Zeile ─────────────────────────────────────────────────────────
function EntryRow({ entry, onEdit, onDelete, onRepeat }) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const sameDay = entry.ended_at
    ? isoToDateLocal(entry.started_at) === isoToDateLocal(entry.ended_at) : true

  return (
    <tr className="hover:bg-gray-50 transition cursor-pointer group" onClick={() => onEdit(entry)}>
      <td className="py-3 pl-0 pr-0 w-1">
        <div className={`w-1 h-full min-h-[48px] rounded-sm ${entry.billable ? 'bg-green-400' : 'bg-orange-400'}`} />
      </td>
      <td className="px-4 py-3">
        <div className="text-sm font-medium text-gray-800">{entry.project_name || '—'}</div>
        {entry.contact_name && <div className="text-xs text-gray-400">{entry.contact_name}</div>}
      </td>
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="text-sm text-gray-700">
          {fmtTime(entry.started_at)} → {entry.ended_at
            ? fmtTime(entry.ended_at)
            : <span className="text-green-600 font-medium">läuft…</span>}
        </div>
        <div className="text-xs text-gray-400">
          {fmtDate(entry.started_at)}
          {!sameDay && entry.ended_at && <> → {fmtDate(entry.ended_at)}</>}
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-gray-500 text-center">{entry.pause_minutes || 0}</td>
      <td className="px-4 py-3 text-sm font-medium text-gray-800 text-center">
        {entry.is_running ? <RunningMin startedAt={entry.started_at} /> : fmtMinutes(entry.duration_minutes)}
      </td>
      <td className="px-4 py-3 text-sm text-gray-600 max-w-xs">
        <span className="line-clamp-2">{entry.note || '—'}</span>
      </td>
      <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-1 justify-end opacity-0 group-hover:opacity-100 transition">
          <button onClick={() => onRepeat(entry)} title="Erneut starten"
            className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
            <Play size={13} />
          </button>
          <span title={entry.billable ? 'Verrechenbar' : 'Nicht verrechenbar'}
            className={`p-1.5 rounded-lg ${entry.billable ? 'text-green-500' : 'text-gray-300'}`}>
            <Euro size={13} />
          </span>
          <button
            onClick={() => { if (confirmDelete) onDelete(entry); else setConfirmDelete(true) }}
            onBlur={() => setTimeout(() => setConfirmDelete(false), 200)}
            className={`p-1.5 rounded-lg transition ${confirmDelete ? 'bg-red-100 text-red-600' : 'text-gray-400 hover:text-red-500 hover:bg-red-50'}`}>
            <Trash2 size={13} />
          </button>
        </div>
      </td>
    </tr>
  )
}

function RunningMin({ startedAt }) {
  const [min, setMin] = useState(() => Math.floor((Date.now() - new Date(startedAt)) / 60000))
  useEffect(() => {
    const id = setInterval(() => setMin(Math.floor((Date.now() - new Date(startedAt)) / 60000)), 10000)
    return () => clearInterval(id)
  }, [startedAt])
  return <span className="text-green-600 font-medium">{fmtMinutes(min)}</span>
}

// ── Hauptseite ────────────────────────────────────────────────────────────────
export default function ZeiterfassungPage() {
  const navigate = useNavigate()
  const [running, setRunning] = useState(null)
  const [stats, setStats] = useState(null)
  const [entries, setEntries] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 50
  const [search, setSearch] = useState('')
  const [filterUserId, setFilterUserId] = useState('')
  const [users, setUsers] = useState([])
  const [modalEntry, setModalEntry] = useState(undefined)
  const [berichtOpen, setBerichtOpen] = useState(false)

  const loadAll = useCallback(async () => {
    try {
      const [runRes, statsRes, entriesRes] = await Promise.all([
        zeiterfassungApi.getRunning(),
        zeiterfassungApi.getStats(filterUserId || undefined),
        zeiterfassungApi.listEntries({ page, page_size: PAGE_SIZE, search: search || undefined, user_id: filterUserId || undefined }),
      ])
      setRunning(runRes.data)
      setStats(statsRes.data)
      setEntries(entriesRes.data.items)
      setTotal(entriesRes.data.total)
    } catch { toast.error('Fehler beim Laden') }
    finally { setLoading(false) }
  }, [page, search, filterUserId])

  useEffect(() => { loadAll() }, [loadAll])
  useEffect(() => { usersApi.list().then(r => setUsers(r.data)).catch(() => {}) }, [])

  const handleStart = async ({ project, note, billable }) => {
    try {
      const res = await zeiterfassungApi.startTimer({
        project_id: project.projectId || null,
        project_name: project.projectName || null,
        contact_id: null,
        contact_name: project.contactName || null,
        started_at: nowIso(),
        note: note || null,
        billable,
        data: {},
      })
      setRunning(res.data)
      toast.success('Timer gestartet')
      loadAll()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Starten')
      throw err
    }
  }

  const handleStop = async ({ note, billable, project, pause }) => {
    if (!running) return
    try {
      // Felder erst aktualisieren, dann stoppen
      await zeiterfassungApi.updateEntry(running.id, {
        note: note || null,
        billable,
        project_id: project?.projectId || running.project_id,
        project_name: project?.projectName || running.project_name,
        contact_name: project?.contactName || running.contact_name,
        pause_minutes: Number(pause) || 0,
      })
      await zeiterfassungApi.stopTimer(running.id, { ended_at: nowIso(), pause_minutes: Number(pause) || 0 })
      setRunning(null)
      toast.success('Timer gestoppt')
      loadAll()
    } catch (err) { toast.error('Fehler beim Stoppen') }
  }

  const handlePause = async () => {
    if (!running) return
    try {
      await zeiterfassungApi.stopTimer(running.id, { ended_at: nowIso(), pause_minutes: 0 })
      setRunning(null)
      toast.success('Timer pausiert')
      loadAll()
    } catch { toast.error('Fehler') }
  }

  const handleSwitch = async () => {
    // Aktuellen Timer stoppen, dann neuen Start-Formular zeigen
    if (running) {
      try {
        await zeiterfassungApi.stopTimer(running.id, { ended_at: nowIso(), pause_minutes: 0 })
      } catch {}
    }
    setRunning(null)
    loadAll()
  }

  const handleDelete = async (entry) => {
    if (!entry) return
    try {
      if (entry.id === running?.id) setRunning(null)
      await zeiterfassungApi.deleteEntry(entry.id)
      toast.success('Zeiteintrag gelöscht')
      loadAll()
    } catch { toast.error('Löschen fehlgeschlagen') }
  }

  const handleUpdate = async ({ note, billable, project, pause }) => {
    if (!running) return
    try {
      await zeiterfassungApi.updateEntry(running.id, {
        note: note || null, billable,
        project_id: project?.projectId || null,
        project_name: project?.projectName || null,
        contact_name: project?.contactName || null,
        pause_minutes: Number(pause) || 0,
      })
    } catch {}
  }

  const handleRepeat = async (entry) => {
    try {
      const res = await zeiterfassungApi.startTimer({
        project_id: entry.project_id, project_name: entry.project_name,
        contact_id: entry.contact_id, contact_name: entry.contact_name,
        started_at: nowIso(), note: entry.note, billable: entry.billable, data: {},
      })
      setRunning(res.data)
      toast.success('Timer erneut gestartet')
      loadAll()
    } catch { toast.error('Fehler beim Starten') }
  }

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary-50 rounded-xl">
            <Timer size={22} className="text-primary-600" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900">Projektzeit</h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => navigate('/zeiterfassung/felder')} title="Custom-Felder"
            className="p-2.5 border border-gray-300 rounded-xl text-gray-500 hover:bg-gray-50 transition">
            <Settings2 size={16} />
          </button>
          <button onClick={() => setBerichtOpen(true)}
            className="flex items-center gap-2 px-4 py-2.5 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition">
            <FileText size={16} />
            Bericht erstellen
          </button>
          <button onClick={() => setModalEntry(null)}
            className="flex items-center gap-2 px-4 py-2.5 border border-gray-300 rounded-xl text-sm font-medium text-gray-700 hover:bg-gray-50 transition">
            <Plus size={16} />
            Projektzeit nachtragen
          </button>
        </div>
      </div>

      {/* Timer-Bereich */}
      {running ? (
        <RunningTimerCard
          entry={running}
          onStop={handleStop}
          onPause={handlePause}
          onSwitch={handleSwitch}
          onDelete={() => handleDelete(running)}
          onUpdate={handleUpdate}
        />
      ) : (
        <StartTimerCard onStart={handleStart} />
      )}

      {/* Statistik-Ringe */}
      {stats && (
        <div className="flex justify-around bg-white rounded-2xl border border-gray-200 p-5 mb-6">
          <RingChart label="Heute" minutes={stats.today_minutes} billableMinutes={stats.today_billable_minutes ?? stats.today_minutes} targetMinutes={stats.today_target_minutes} />
          <RingChart label="Woche" minutes={stats.week_minutes} billableMinutes={stats.week_billable_minutes ?? stats.week_minutes} targetMinutes={stats.week_target_minutes} />
          <RingChart label="Monat" minutes={stats.month_minutes} billableMinutes={stats.month_billable_minutes ?? stats.month_minutes} targetMinutes={stats.month_target_minutes} />
        </div>
      )}

      {/* Filter */}
      <div className="flex gap-3 mb-4">
        <div className="relative flex-1">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input type="text" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="In Einträgen suchen…"
            className="w-full pl-9 pr-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white" />
        </div>
        <select value={filterUserId} onChange={(e) => { setFilterUserId(e.target.value); setPage(1) }}
          className="px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white">
          <option value="">Alle Benutzer</option>
          {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
        </select>
      </div>

      {/* Tabelle */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={28} className="animate-spin text-primary-400" />
          </div>
        ) : entries.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Clock size={40} className="mx-auto mb-3 text-gray-200" />
            <p className="font-medium">{search ? 'Keine Einträge gefunden' : 'Noch keine Zeiteinträge'}</p>
            {!search && (
              <button onClick={() => setModalEntry(null)} className="mt-3 text-primary-600 hover:underline text-sm">
                Ersten Eintrag nachtragen
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  <th className="w-1 p-0" />
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Projekt</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Zeit</th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">Pause</th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-gray-500 uppercase tracking-wide">Dauer</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Notiz</th>
                  <th className="px-4 py-3 w-24"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {entries.map(entry => (
                  <EntryRow key={entry.id} entry={entry}
                    onEdit={(e) => setModalEntry(e)}
                    onDelete={handleDelete}
                    onRepeat={handleRepeat}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
            <span className="text-sm text-gray-500">
              {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} von {total}
            </span>
            <div className="flex gap-2">
              <button onClick={() => setPage(p => p - 1)} disabled={page === 1}
                className="p-2 rounded-lg border border-gray-200 text-gray-500 disabled:opacity-40 hover:bg-gray-50 transition">
                <ChevronLeft size={16} />
              </button>
              <button onClick={() => setPage(p => p + 1)} disabled={page === totalPages}
                className="p-2 rounded-lg border border-gray-200 text-gray-500 disabled:opacity-40 hover:bg-gray-50 transition">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      {modalEntry !== undefined && (
        <EntryModal entry={modalEntry} onClose={() => setModalEntry(undefined)}
          onSaved={() => { setModalEntry(undefined); loadAll() }} />
      )}

      {berichtOpen && (
        <BerichtDialog onClose={() => setBerichtOpen(false)} />
      )}
    </div>
  )
}
