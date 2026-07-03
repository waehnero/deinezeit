import { useState, useEffect, useMemo } from 'react'
import {
  Plus, ListTodo, Loader2, X, Search, CheckCircle2, Circle,
  CalendarDays, User as UserIcon, Link2, Trash2, GanttChartSquare, Database,
  Columns, List, Printer,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { aufgabenApi, usersApi, projektplanApi, masterdataApi } from '../services/api'
import AufgabenKanban from '../components/AufgabenKanban'
import AufgabenKalender from '../components/AufgabenKalender'
import MailVorschlaege from '../components/MailVorschlaege'
import AttachmentPanel from '../components/AttachmentPanel'

/* ─────────────────────────────────────────────────────────────────────────────
 * Aufgabenmodul – Etappe 1: Listenansicht
 * Kanban- und Kalenderansichten folgen in Etappe 2 (gleiche Datenbasis).
 * ──────────────────────────────────────────────────────────────────────────── */

const heute = () => new Date().toISOString().slice(0, 10)

function faelligkeitsGruppe(t) {
  if (!t.due_date) return 'ohne'
  const d = t.due_date
  const now = heute()
  if (d < now) return 'ueberfaellig'
  if (d === now) return 'heute'
  const inSieben = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10)
  if (d <= inSieben) return 'woche'
  return 'spaeter'
}

const GRUPPEN = [
  { id: 'ueberfaellig', label: 'Überfällig', color: 'text-red-600' },
  { id: 'heute',        label: 'Heute',       color: 'text-primary-700' },
  { id: 'woche',        label: 'Nächste 7 Tage', color: 'text-neutral-700' },
  { id: 'spaeter',      label: 'Später',      color: 'text-neutral-500' },
  { id: 'ohne',         label: 'Ohne Termin', color: 'text-neutral-400' },
]

function datumAnzeigen(d) {
  if (!d) return ''
  const [y, m, day] = d.split('-')
  return `${day}.${m}.${y}`
}

// ── Stammdaten-Datensatz suchen (Typ wählen + Volltext) ──────────────────────
function RecordSearch({ recordId, recordName, recordTypeSlug, onChange }) {
  const [types, setTypes] = useState([])
  const [slug, setSlug] = useState('')
  const [search, setSearch] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    masterdataApi.listTypes().then(r => {
      const active = (r.data || []).filter(t => t.is_active !== false)
      setTypes(active)
      if (active.length && !slug) setSlug(active[0].slug)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!open || !slug) return
    const t = setTimeout(async () => {
      try {
        const res = await masterdataApi.listRecords(slug, { search: search || undefined, page_size: 20 })
        setResults(res.data.items || [])
      } catch { setResults([]) }
    }, 300)
    return () => clearTimeout(t)
  }, [search, open, slug])

  if (recordId) {
    return (
      <div className="flex items-center gap-2 border border-gray-300 rounded-lg px-3 py-2">
        <Database size={15} className="text-primary-500 shrink-0" />
        <span className="flex-1 text-sm text-gray-900 truncate">
          {recordName || 'Datensatz'}
          {recordTypeSlug && <span className="text-gray-400 ml-1">({recordTypeSlug})</span>}
        </span>
        <button type="button" onClick={() => onChange(null)} className="text-gray-400 hover:text-red-600 shrink-0">
          <X size={15} />
        </button>
      </div>
    )
  }

  return (
    <div className="flex gap-2">
      <select value={slug} onChange={e => setSlug(e.target.value)}
        className="border border-gray-300 rounded-lg px-2 py-2 text-sm bg-white w-32 shrink-0">
        {types.map(t => <option key={t.slug} value={t.slug}>{t.name}</option>)}
      </select>
      <div className="relative flex-1">
        <div className="flex items-center border border-gray-300 rounded-lg px-3 focus-within:border-primary-400">
          <Search size={15} className="text-gray-400 shrink-0" />
          <input
            value={search}
            onChange={e => { setSearch(e.target.value); setOpen(true) }}
            onFocus={() => setOpen(true)}
            onBlur={() => setTimeout(() => setOpen(false), 150)}
            placeholder="Datensatz suchen…"
            className="w-full py-2 px-2 text-sm focus:outline-none bg-transparent"
          />
        </div>
        {open && results.length > 0 && (
          <div className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-52 overflow-auto">
            {results.map(r => (
              <button key={r.id} type="button"
                onMouseDown={() => { onChange(r.id, r.display_name, slug); setOpen(false) }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-neutral-50 truncate">
                {r.display_name || '—'}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Anlegen/Bearbeiten-Dialog ─────────────────────────────────────────────────
// Aufgabenbaum des Projektplans flach machen (inkl. Teilaufgaben)
function flacheTasks(tasks, out = [], tiefe = 0) {
  for (const t of tasks || []) {
    out.push({ ...t, tiefe })
    if (t.children?.length) flacheTasks(t.children, out, tiefe + 1)
  }
  return out
}

function TodoDialog({ todo, statuses, priorities, onClose, onSaved, onDeleted }) {
  const isNew = !todo?.id
  // Eingeblendete Projektplan-Aufgabe: Quelle bleibt das Projektmodul,
  // daher nur die dort vorhandenen Felder anbieten.
  const istProjektplan = todo?.source === 'projektplan'
  const [form, setForm] = useState({
    title: todo?.title || '',
    description: todo?.description || '',
    status: todo?.status || statuses[0]?.value || 'offen',
    priority: todo?.priority || 'mittel',
    start_date: todo?.start_date || '',
    due_date: todo?.due_date || '',
    due_time: todo?.due_time ? todo.due_time.slice(0, 5) : '',
    assignee_id: todo?.assignee_id || '',
    planning_project_id: todo?.planning_project_id || '',
    planning_task_id: todo?.planning_task_id || '',
    record_id: todo?.record_id || null,
    record_name: todo?.record_name || null,
    record_type_slug: todo?.record_type_slug || null,
  })
  const [users, setUsers] = useState([])
  const [projects, setProjects] = useState([])
  const [projectTasks, setProjectTasks] = useState([])
  const [saving, setSaving] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  useEffect(() => {
    usersApi.list().then(r => setUsers(r.data || [])).catch(() => {})
    projektplanApi.listProjects().then(r => setProjects(r.data || [])).catch(() => {})
  }, [])

  // Aufgaben des gewählten Planungsprojekts nachladen (Baum -> flache Liste)
  useEffect(() => {
    if (!form.planning_project_id) { setProjectTasks([]); return }
    projektplanApi.getProject(form.planning_project_id)
      .then(r => setProjectTasks(flacheTasks(r.data.tasks)))
      .catch(() => setProjectTasks([]))
  }, [form.planning_project_id])

  const speichern = async () => {
    const title = form.title.trim()
    if (!title) return toast.error('Bitte einen Titel eingeben')
    setSaving(true)
    const payload = {
      title,
      description: form.description || null,
      status: form.status,
      priority: form.priority,
      start_date: form.start_date || null,
      due_date: form.due_date || null,
      due_time: form.due_time || null,
      assignee_id: form.assignee_id || null,
      planning_project_id: form.planning_project_id || null,
      planning_task_id: form.planning_task_id || null,
      record_id: form.record_id || null,
    }
    try {
      if (isNew) {
        await aufgabenApi.create(payload)
        toast.success('Aufgabe angelegt')
      } else {
        await aufgabenApi.update(todo.id, payload)
        toast.success('Aufgabe gespeichert')
      }
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  const loeschen = async () => {
    if (!window.confirm('Aufgabe wirklich löschen?')) return
    try {
      await aufgabenApi.remove(todo.id)
      toast.success('Aufgabe gelöscht')
      onDeleted()
    } catch {
      toast.error('Fehler beim Löschen')
    }
  }

  const [printing, setPrinting] = useState(false)
  const drucken = async () => {
    setPrinting(true)
    try {
      const res = await aufgabenApi.printPdf(todo.id)
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      window.open(url, '_blank')
    } catch {
      toast.error('PDF konnte nicht erstellt werden')
    } finally {
      setPrinting(false)
    }
  }

  const inputCls = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400'

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-auto"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100">
          <div>
            <h2 className="font-semibold text-neutral-900">
              {isNew ? 'Neue Aufgabe' : 'Aufgabe bearbeiten'}
            </h2>
            {istProjektplan && (
              <p className="text-xs text-neutral-400 flex items-center gap-1 mt-0.5">
                <GanttChartSquare size={12} />
                Aus dem Projekt „{todo.planning_project_name}" — Änderungen wirken dort
              </p>
            )}
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-700"><X size={18} /></button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-neutral-500 mb-1">Titel *</label>
            <input autoFocus value={form.title} onChange={e => set('title', e.target.value)}
              onKeyDown={e => e.key === 'Enter' && speichern()} className={inputCls} />
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-500 mb-1">Beschreibung</label>
            <textarea rows={3} value={form.description} onChange={e => set('description', e.target.value)}
              className={inputCls} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-neutral-500 mb-1">Status</label>
              <select value={form.status} onChange={e => set('status', e.target.value)} className={inputCls}>
                {statuses.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-neutral-500 mb-1">Priorität</label>
              <select value={form.priority} onChange={e => set('priority', e.target.value)} className={inputCls}>
                {priorities.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
          </div>

          <div className={`grid gap-3 ${istProjektplan ? 'grid-cols-2' : 'grid-cols-3'}`}>
            <div>
              <label className="block text-xs font-medium text-neutral-500 mb-1">Start</label>
              <input type="date" value={form.start_date} onChange={e => set('start_date', e.target.value)} className={inputCls} />
            </div>
            <div>
              <label className="block text-xs font-medium text-neutral-500 mb-1">Fällig am</label>
              <input type="date" value={form.due_date} onChange={e => set('due_date', e.target.value)} className={inputCls} />
            </div>
            {!istProjektplan && (
              <div>
                <label className="block text-xs font-medium text-neutral-500 mb-1">Uhrzeit</label>
                <input type="time" value={form.due_time} onChange={e => set('due_time', e.target.value)} className={inputCls} />
              </div>
            )}
          </div>

          <div>
            <label className="block text-xs font-medium text-neutral-500 mb-1">Zugewiesen an</label>
            <select value={form.assignee_id} onChange={e => set('assignee_id', e.target.value)} className={inputCls}>
              <option value="">— niemand —</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name}</option>)}
            </select>
          </div>

          {/* Verknüpfungen (bei Projektplan-Aufgaben verwaltet das Projektmodul) */}
          {!istProjektplan && (
          <div className="border-t border-neutral-100 pt-3 space-y-3">
            <p className="text-xs font-medium text-neutral-400 uppercase tracking-wider flex items-center gap-1">
              <Link2 size={13} /> Verknüpfungen
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-neutral-500 mb-1">Planungsprojekt</label>
                <select value={form.planning_project_id}
                  onChange={e => setForm(f => ({ ...f, planning_project_id: e.target.value, planning_task_id: '' }))}
                  className={inputCls}>
                  <option value="">— keines —</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-500 mb-1">Projektplan-Aufgabe</label>
                <select value={form.planning_task_id} onChange={e => set('planning_task_id', e.target.value)}
                  disabled={!form.planning_project_id} className={`${inputCls} disabled:bg-neutral-50 disabled:text-neutral-400`}>
                  <option value="">— keine —</option>
                  {projectTasks.map(t => (
                    <option key={t.id} value={t.id}>{' '.repeat(t.tiefe * 2)}{t.title}</option>
                  ))}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-neutral-500 mb-1">Stammdaten (Kontakt, Artikel, …)</label>
              <RecordSearch
                recordId={form.record_id}
                recordName={form.record_name}
                recordTypeSlug={form.record_type_slug}
                onChange={(id, name, slug) => setForm(f => ({
                  ...f, record_id: id, record_name: name || null, record_type_slug: slug || null,
                }))}
              />
            </div>
          </div>
          )}

          {/* Anhänge (Datacenter, wie bei Projekt-Aufgaben). Erst nach dem
              Anlegen verfügbar — vorher gibt es noch keine Aufgaben-ID. */}
          {!isNew && (
            <div className="border-t border-neutral-100 pt-3">
              <AttachmentPanel
                entityType={istProjektplan ? 'planning_task' : 'todo'}
                entityId={todo.id}
              />
            </div>
          )}
        </div>

        <div className="flex items-center justify-between px-5 py-4 border-t border-neutral-100">
          <div className="flex items-center gap-4">
            {!isNew && !istProjektplan && (
              <button onClick={loeschen}
                className="flex items-center gap-1.5 text-sm text-red-600 hover:text-red-700">
                <Trash2 size={15} /> Löschen
              </button>
            )}
            {!isNew && (
              <button onClick={drucken} disabled={printing}
                title="Laufzettel drucken (A5-Infos + Notizraster + QR-Code)"
                className="flex items-center gap-1.5 text-sm text-neutral-500 hover:text-primary-600 disabled:opacity-50">
                {printing ? <Loader2 size={15} className="animate-spin" /> : <Printer size={15} />}
                Drucken
              </button>
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={onClose}
              className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-neutral-700 hover:bg-neutral-50">
              Abbrechen
            </button>
            <button onClick={speichern} disabled={saving}
              className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2">
              {saving && <Loader2 size={14} className="animate-spin" />}
              {isNew ? 'Anlegen' : 'Speichern'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Hauptseite ────────────────────────────────────────────────────────────────
export default function AufgabenPage() {
  const [todos, setTodos] = useState([])
  const [loading, setLoading] = useState(true)
  const [statuses, setStatuses] = useState([])
  const [priorities, setPriorities] = useState([])
  const [doneStatus, setDoneStatus] = useState('erledigt')

  // Filter
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [prioFilter, setPrioFilter] = useState('')
  const [nurMeine, setNurMeine] = useState(false)
  const [erledigteZeigen, setErledigteZeigen] = useState(false)

  // Ansicht: liste | kanban | kalender (Wahl wird gemerkt)
  const [ansicht, setAnsicht] = useState(() => {
    try { return localStorage.getItem('aufgaben_ansicht') || 'liste' } catch { return 'liste' }
  })
  const wechsleAnsicht = (a) => {
    setAnsicht(a)
    try { localStorage.setItem('aufgaben_ansicht', a) } catch {}
  }

  const [dialogTodo, setDialogTodo] = useState(null)  // null=zu, {}=neu, {…}=bearbeiten

  const statusLabel = v => statuses.find(s => s.value === v)?.label || v
  const statusColor = v => statuses.find(s => s.value === v)?.color || '#6b7280'
  const prioLabel   = v => priorities.find(p => p.value === v)?.label || v
  const prioColor   = v => priorities.find(p => p.value === v)?.color || '#6b7280'

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await aufgabenApi.list({ mine: nurMeine || undefined })
      setTodos(data)
    } catch {
      toast.error('Aufgaben konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [nurMeine])
  useEffect(() => {
    aufgabenApi.getSettings().then(r => {
      setStatuses(r.data.statuses || [])
      setPriorities(r.data.priorities || [])
      setDoneStatus(r.data.done_status || 'erledigt')
    }).catch(() => {})
  }, [])

  // Schnell erledigen / wieder öffnen
  const toggleErledigt = async (t) => {
    const neu = t.status === doneStatus ? 'offen' : doneStatus
    try {
      const { data } = await aufgabenApi.update(t.id, { status: neu })
      setTodos(list => list.map(x => x.id === t.id ? data : x))
    } catch {
      toast.error('Status konnte nicht geändert werden')
    }
  }

  const gefiltert = useMemo(() => {
    const s = search.trim().toLowerCase()
    return todos.filter(t => {
      // Kanban hat eine eigene Erledigt-Spalte -> Filter dort nicht anwenden
      if (ansicht !== 'kanban' && !erledigteZeigen && t.status === doneStatus) return false
      if (statusFilter && t.status !== statusFilter) return false
      if (prioFilter && t.priority !== prioFilter) return false
      if (s) {
        const hay = `${t.title} ${t.description || ''} ${t.assignee_name || ''} ${t.record_name || ''} ${t.planning_project_name || ''}`.toLowerCase()
        if (!hay.includes(s)) return false
      }
      return true
    })
  }, [todos, search, statusFilter, prioFilter, erledigteZeigen, doneStatus, ansicht])

  const gruppen = useMemo(() => {
    const map = {}
    for (const t of gefiltert) {
      const g = faelligkeitsGruppe(t)
      if (!map[g]) map[g] = []
      map[g].push(t)
    }
    return map
  }, [gefiltert])

  const offen = todos.filter(t => t.status !== doneStatus).length

  return (
    <div className="max-w-4xl mx-auto px-4 md:px-6 py-6 pb-28">
      {/* Kopf */}
      <div className="flex items-center gap-3 mb-1">
        <ListTodo className="text-primary-600" size={26} />
        <h1 className="text-xl font-semibold text-neutral-900">Aufgaben</h1>
        {/* Ansichts-Umschalter */}
        <div className="flex rounded-lg border border-gray-300 overflow-hidden ml-auto">
          {[
            { id: 'liste',    label: 'Liste',    Icon: List },
            { id: 'kanban',   label: 'Kanban',   Icon: Columns },
            { id: 'kalender', label: 'Kalender', Icon: CalendarDays },
          ].map(({ id, label, Icon }) => (
            <button key={id} onClick={() => wechsleAnsicht(id)} title={label}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-sm ${ansicht === id
                ? 'bg-primary-600 text-white' : 'bg-white text-neutral-600 hover:bg-neutral-50'}`}>
              <Icon size={15} /> <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </div>
      </div>
      <p className="text-sm text-neutral-500 mb-5">{offen} offene Aufgabe{offen === 1 ? '' : 'n'}</p>

      {/* KI-Vorschläge aus E-Mails (nur sichtbar, wenn offene existieren) */}
      <MailVorschlaege onAccepted={load} />

      {/* Filterzeile */}
      <div className="flex flex-wrap items-center gap-2 mb-5">
        <div className="flex items-center border border-gray-300 rounded-lg px-3 bg-white flex-1 min-w-[180px]">
          <Search size={15} className="text-gray-400 shrink-0" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Suchen…"
            className="w-full py-2 px-2 text-sm focus:outline-none bg-transparent" />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-2 py-2 text-sm bg-white">
          <option value="">Alle Status</option>
          {statuses.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <select value={prioFilter} onChange={e => setPrioFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-2 py-2 text-sm bg-white">
          <option value="">Alle Prioritäten</option>
          {priorities.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-neutral-600 cursor-pointer select-none">
          <input type="checkbox" checked={nurMeine} onChange={e => setNurMeine(e.target.checked)}
            className="rounded border-gray-300" /> Nur meine
        </label>
        <label className="flex items-center gap-1.5 text-sm text-neutral-600 cursor-pointer select-none">
          <input type="checkbox" checked={erledigteZeigen} onChange={e => setErledigteZeigen(e.target.checked)}
            className="rounded border-gray-300" /> Erledigte
        </label>
        <button onClick={() => setDialogTodo({})}
          className="ml-auto flex items-center gap-1.5 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium px-3.5 py-2 rounded-lg">
          <Plus size={16} /> Neue Aufgabe
        </button>
      </div>

      {/* Inhalt je Ansicht */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <Loader2 size={26} className="animate-spin text-primary-400" />
        </div>
      ) : ansicht === 'kanban' ? (
        <AufgabenKanban
          todos={gefiltert}
          statuses={statuses}
          priorities={priorities}
          onOpen={t => setDialogTodo(t)}
          onChanged={load}
        />
      ) : ansicht === 'kalender' ? (
        <AufgabenKalender
          todos={gefiltert}
          statuses={statuses}
          doneStatus={doneStatus}
          onOpen={t => setDialogTodo(t)}
          onCreate={iso => setDialogTodo({ due_date: iso })}
        />
      ) : gefiltert.length === 0 ? (
        <div className="text-center py-16 text-neutral-400">
          <ListTodo size={36} className="mx-auto mb-3 opacity-40" />
          <p className="text-sm">Keine Aufgaben gefunden</p>
        </div>
      ) : (
        <div className="space-y-6">
          {GRUPPEN.filter(g => gruppen[g.id]?.length).map(g => (
            <div key={g.id}>
              <h2 className={`text-xs font-semibold uppercase tracking-wider mb-2 ${g.color}`}>
                {g.label} <span className="font-normal text-neutral-400">({gruppen[g.id].length})</span>
              </h2>
              <div className="bg-white border border-neutral-200 rounded-xl divide-y divide-neutral-100">
                {gruppen[g.id].map(t => {
                  const erledigt = t.status === doneStatus
                  return (
                    <div key={t.id}
                      className="flex items-center gap-3 px-4 py-3 hover:bg-neutral-50 cursor-pointer group"
                      onClick={() => setDialogTodo(t)}>
                      <button onClick={e => { e.stopPropagation(); toggleErledigt(t) }}
                        className="shrink-0 text-neutral-300 hover:text-primary-600"
                        title={erledigt ? 'Wieder öffnen' : 'Erledigt'}>
                        {erledigt
                          ? <CheckCircle2 size={20} className="text-green-500" />
                          : <Circle size={20} />}
                      </button>

                      <div className="flex-1 min-w-0">
                        <p className={`text-sm font-medium truncate ${erledigt ? 'line-through text-neutral-400' : 'text-neutral-900'}`}>
                          {t.title}
                        </p>
                        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-0.5">
                          {t.planning_project_name && (
                            <span className="text-xs text-neutral-400 flex items-center gap-1 truncate">
                              <GanttChartSquare size={12} />
                              {t.planning_project_name}
                              {t.planning_task_title && ` › ${t.planning_task_title}`}
                            </span>
                          )}
                          {t.record_name && (
                            <span className="text-xs text-neutral-400 flex items-center gap-1 truncate">
                              <Database size={12} /> {t.record_name}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Badges */}
                      <span className="hidden sm:inline-flex text-xs px-2 py-0.5 rounded-full shrink-0"
                        style={{ backgroundColor: `${prioColor(t.priority)}20`, color: prioColor(t.priority) }}>
                        {prioLabel(t.priority)}
                      </span>
                      <span className="hidden sm:inline-flex text-xs px-2 py-0.5 rounded-full shrink-0"
                        style={{ backgroundColor: `${statusColor(t.status)}20`, color: statusColor(t.status) }}>
                        {statusLabel(t.status)}
                      </span>

                      {t.due_date && (
                        <span className={`text-xs flex items-center gap-1 shrink-0 ${
                          faelligkeitsGruppe(t) === 'ueberfaellig' && !erledigt ? 'text-red-600 font-medium' : 'text-neutral-500'}`}>
                          <CalendarDays size={13} />
                          {datumAnzeigen(t.due_date)}
                          {t.due_time && ` ${t.due_time.slice(0, 5)}`}
                        </span>
                      )}

                      {t.assignee_name && (
                        <span className="w-6 h-6 rounded-full bg-primary-100 text-primary-700 text-[10px] font-semibold flex items-center justify-center shrink-0"
                          title={t.assignee_name}>
                          {t.assignee_name.split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase()}
                        </span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Dialog */}
      {dialogTodo !== null && (
        <TodoDialog
          todo={dialogTodo}
          statuses={statuses}
          priorities={priorities}
          onClose={() => setDialogTodo(null)}
          onSaved={() => { setDialogTodo(null); load() }}
          onDeleted={() => { setDialogTodo(null); load() }}
        />
      )}
    </div>
  )
}
