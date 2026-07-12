import { useState, useEffect, useRef, useMemo } from 'react'
import {
  X, Trash2, Paperclip, Upload, FileText, Image as ImageIcon,
  Loader2, Calendar, User as UserIcon, Flag, Tag as TagIcon, Save, GitBranch, Plus,
} from 'lucide-react'
import toast from 'react-hot-toast'
import errMsg from '../utils/errMsg'
import { projektplanApi, attachmentApi, usersApi } from '../services/api'
import ContactSearch from './ContactSearch'
import Checklist from './Checklist'

const DEP_TYPE_LABEL = {
  FS: 'Ende → Anfang (Standard)',
  SS: 'Anfang → Anfang',
  FF: 'Ende → Ende',
  SF: 'Anfang → Ende',
}

// Aufgabenbaum flach machen (für Auswahl-Dropdown)
function flattenTasks(tasks, out = []) {
  for (const t of tasks || []) {
    out.push(t)
    if (t.children?.length) flattenTasks(t.children, out)
  }
  return out
}

const ENTITY_TYPE = 'planning_task'

/**
 * Umfangreiches Aufgaben-Detail-Sheet:
 * Beschreibung, Verantwortlicher, Termine, Status, Priorität, Tags,
 * geschätzte Stunden, eigene (konfigurierbare) Felder und Anlagen.
 */
export default function TaskDetailSheet({ task, settings, fields, project, projectContact, onClose, onChanged }) {
  const [form, setForm] = useState(() => ({
    title: task.title || '',
    description: task.description || '',
    status: task.status || 'offen',
    priority: task.priority || 'mittel',
    assignee_id: task.assignee_id || '',
    assignee_name: task.assignee_name || '',
    contact_id: task.contact_id || null,
    contact_name: task.contact_name || '',
    start_date: task.start_date || '',
    due_date: task.due_date || '',
    estimate_hours: task.estimate_minutes ? (task.estimate_minutes / 60) : '',
    tags: task.data?.tags || [],
    task_type: task.data?.task_type || '',
    data: task.data || {},
  }))
  // Erbt die Aufgabe den Projekt-Kontakt? (gleiche ID wie Projekt)
  const isInherited = form.contact_id && projectContact?.contact_id &&
    String(form.contact_id) === String(projectContact.contact_id)
  const [users, setUsers] = useState([])
  const [saving, setSaving] = useState(false)

  const [attachments, setAttachments] = useState([])
  const [loadingAtt, setLoadingAtt] = useState(true)
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef(null)

  useEffect(() => {
    usersApi.list().then(r => setUsers(r.data)).catch(() => {})
    attachmentApi.list(ENTITY_TYPE, task.id)
      .then(r => setAttachments(r.data.attachments || []))
      .catch(() => {})
      .finally(() => setLoadingAtt(false))
  }, [task.id])

  const set = (patch) => setForm(f => ({ ...f, ...patch }))

  const toggleTag = (t) => {
    set({ tags: form.tags.includes(t) ? form.tags.filter(x => x !== t) : [...form.tags, t] })
  }

  const save = async () => {
    setSaving(true)
    try {
      const selUser = users.find(u => u.id === form.assignee_id)
      await projektplanApi.updateTask(task.id, {
        title: form.title.trim() || task.title,
        description: form.description || null,
        status: form.status,
        priority: form.priority,
        assignee_id: form.assignee_id || null,
        assignee_name: selUser ? (selUser.full_name || selUser.name || selUser.email) : null,
        contact_id: form.contact_id || null,
        contact_name: form.contact_name || null,
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        estimate_minutes: form.estimate_hours ? Math.round(Number(form.estimate_hours) * 60) : null,
        data: { ...form.data, tags: form.tags, task_type: form.task_type || null },
      })
      toast.success('Gespeichert')
      onChanged?.()
      onClose()
    } catch (err) {
      toast.error(errMsg(err, 'Fehler beim Speichern'))
    } finally {
      setSaving(false)
    }
  }

  const onUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const { data } = await attachmentApi.upload(ENTITY_TYPE, task.id, fd)
      setAttachments(a => [data, ...a])
      toast.success('Anlage hochgeladen')
    } catch (err) {
      toast.error(errMsg(err, 'Upload fehlgeschlagen'))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const removeAtt = async (id) => {
    try {
      await attachmentApi.remove(id)
      setAttachments(a => a.filter(x => x.id !== id))
    } catch {
      toast.error('Anlage konnte nicht gelöscht werden')
    }
  }

  const statuses = settings?.statuses?.length ? settings.statuses : [{ value: 'offen', label: 'Offen' }]
  const priorities = settings?.priorities?.length ? settings.priorities : [{ value: 'mittel', label: 'Mittel' }]
  // Typen aus den Einstellungen; Fallback auf sinnvolle Standardtypen, damit das
  // Dropdown auch dann erscheint, wenn noch keine Typen konfiguriert wurden.
  const taskTypes = settings?.task_types?.length ? settings.task_types : [
    { value: 'aufgabe', label: 'Aufgabe' },
    { value: 'meilenstein', label: 'Meilenstein' },
    { value: 'golive', label: 'GoLive' },
  ]
  const allTags = settings?.tags || []

  // ── Abhängigkeiten ──────────────────────────────────────────────────────────
  const allProjectTasks = useMemo(() => flattenTasks(project?.tasks || []), [project])
  const taskName = (id) => allProjectTasks.find(t => String(t.id) === String(id))?.title || '?'
  const deps = project?.dependencies || []
  const predecessors = deps.filter(d => String(d.successor_id) === String(task.id))   // diese hängt von …
  const successors = deps.filter(d => String(d.predecessor_id) === String(task.id))   // … hängt von dieser
  // Auswahl-Kandidaten: alle Aufgaben außer dieser
  const otherTasks = allProjectTasks.filter(t => String(t.id) !== String(task.id))

  const [depMode, setDepMode] = useState('pred')   // 'pred' = Vorgänger, 'succ' = Nachfolger
  const [depTaskId, setDepTaskId] = useState('')
  const [depType, setDepType] = useState('FS')
  const [depBusy, setDepBusy] = useState(false)

  const addDependency = async () => {
    if (!depTaskId) return toast.error('Bitte eine Aufgabe wählen')
    setDepBusy(true)
    try {
      // pred-Modus: gewählte Aufgabe ist Vorgänger DIESER Aufgabe
      const payload = depMode === 'pred'
        ? { predecessor_id: depTaskId, successor_id: task.id, dep_type: depType }
        : { predecessor_id: task.id, successor_id: depTaskId, dep_type: depType }
      await projektplanApi.createDependency(payload)
      toast.success('Verknüpfung hinzugefügt')
      setDepTaskId('')
      onChanged?.()   // lädt Projekt neu -> deps aktualisiert
    } catch (err) {
      toast.error(errMsg(err, 'Verknüpfung konnte nicht angelegt werden'))
    } finally {
      setDepBusy(false)
    }
  }

  const removeDependency = async (id) => {
    try {
      await projektplanApi.deleteDependency(id)
      onChanged?.()
    } catch {
      toast.error('Verknüpfung konnte nicht gelöscht werden')
    }
  }

  const renderCustomField = (f) => {
    const val = form.data?.[f.key] ?? ''
    const setVal = (v) => set({ data: { ...form.data, [f.key]: v } })
    const cls = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400'
    if (f.field_type === 'textarea')
      return <textarea value={val} onChange={e => setVal(e.target.value)} rows={2} className={cls} placeholder={f.placeholder || ''} />
    if (f.field_type === 'checkbox')
      return <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={!!val} onChange={e => setVal(e.target.checked)} /> {f.name}</label>
    if (f.field_type === 'dropdown')
      return (
        <select value={val} onChange={e => setVal(e.target.value)} className={cls}>
          <option value="">– bitte wählen –</option>
          {(f.options || []).map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      )
    const type = f.field_type === 'number' ? 'number' : f.field_type === 'date' ? 'date' : f.field_type === 'url' ? 'url' : 'text'
    return <input type={type} value={val} onChange={e => setVal(e.target.value)} className={cls} placeholder={f.placeholder || ''} />
  }

  const isImage = (a) => (a.mimetype || '').startsWith('image/')

  return (
    <div className="fixed inset-0 z-50 sheet-safe flex items-end md:items-center justify-center bg-black/40" onClick={onClose}>
      <div
        className="bg-surface w-full md:max-w-lg rounded-2xl max-h-full lg:max-h-[92vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Kopf */}
        <div className="sticky top-0 bg-surface border-b border-gray-100 px-5 py-3 flex items-center justify-between z-10">
          <span className="text-sm text-gray-500">Aufgabe bearbeiten</span>
          <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
        </div>

        <div className="p-5 space-y-4">
          {/* Titel */}
          <input
            value={form.title}
            onChange={(e) => set({ title: e.target.value })}
            className="w-full text-lg font-medium border-b border-gray-200 pb-2 focus:outline-none focus:border-primary-400"
          />

          {/* Beschreibung */}
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Beschreibung</label>
            <textarea
              value={form.description}
              onChange={(e) => set({ description: e.target.value })}
              rows={2}
              placeholder="Details, Notizen…"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
            />
          </div>

          {/* Status + Priorität */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Status</label>
              <select value={form.status} onChange={(e) => set({ status: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                {statuses.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Priorität</label>
              <select value={form.priority} onChange={(e) => set({ priority: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                {priorities.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
          </div>

          {/* Aufgaben-Typ */}
          {taskTypes.length > 0 && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Typ</label>
              <select value={form.task_type} onChange={(e) => set({ task_type: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
                <option value="">– Standard –</option>
                {taskTypes.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              {form.task_type === 'meilenstein' && (
                <p className="text-[11px] text-primary-500 mt-1">Wird im Gantt als Meilenstein-Raute dargestellt.</p>
              )}
            </div>
          )}

          {/* Verantwortlicher */}
          <div>
            <label className="text-xs text-gray-500 mb-1 block flex items-center gap-1"><UserIcon size={12} /> Verantwortlich</label>
            <select value={form.assignee_id} onChange={(e) => set({ assignee_id: e.target.value })}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm">
              <option value="">– niemand –</option>
              {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.name || u.email}</option>)}
            </select>
          </div>

          {/* Kontakt – default vom Projekt geerbt, überschreibbar */}
          <div>
            <label className="text-xs text-gray-500 mb-1 block flex items-center gap-1"><UserIcon size={12} /> Kontakt</label>
            <ContactSearch
              contactId={form.contact_id}
              contactName={form.contact_name}
              onChange={(id, name) => set({ contact_id: id, contact_name: name })}
              inheritedHint={isInherited ? 'vom Projekt' : undefined}
              placeholder="Anderen Kontakt suchen…"
            />
            {!form.contact_id && projectContact?.contact_id && (
              <button
                type="button"
                onClick={() => set({ contact_id: projectContact.contact_id, contact_name: projectContact.contact_name })}
                className="text-[11px] text-primary-600 hover:text-primary-700 mt-1"
              >
                Projekt-Kontakt übernehmen: {projectContact.contact_name}
              </button>
            )}
          </div>

          {/* Termine + Stunden */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block flex items-center gap-1"><Calendar size={12} /> Start</label>
              <input type="date" value={form.start_date || ''} onChange={(e) => set({ start_date: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block flex items-center gap-1"><Calendar size={12} /> Fällig</label>
              <input type="date" value={form.due_date || ''} onChange={(e) => set({ due_date: e.target.value })}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Geschätzte Stunden (Soll)</label>
            <input type="number" min="0" step="0.5" value={form.estimate_hours}
              onChange={(e) => set({ estimate_hours: e.target.value })}
              placeholder="z. B. 8"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>

          {/* Tags */}
          {allTags.length > 0 && (
            <div>
              <label className="text-xs text-gray-500 mb-1 block flex items-center gap-1"><TagIcon size={12} /> Tags</label>
              <div className="flex flex-wrap gap-2">
                {allTags.map(t => (
                  <button key={t} onClick={() => toggleTag(t)}
                    className={`text-xs px-3 py-1 rounded-full border transition ${
                      form.tags.includes(t)
                        ? 'bg-primary-50 border-primary-300 text-primary-700'
                        : 'border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}>
                    {t}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Eigene Felder */}
          {fields?.length > 0 && (
            <div className="space-y-3 border-t border-gray-100 pt-3">
              {fields.map(f => (
                <div key={f.id}>
                  {f.field_type !== 'checkbox' && (
                    <label className="text-xs text-gray-500 mb-1 block">{f.name}{f.is_required ? ' *' : ''}</label>
                  )}
                  {renderCustomField(f)}
                </div>
              ))}
            </div>
          )}

          {/* Abhängigkeiten */}
          <div className="border-t border-gray-100 pt-3">
            <label className="text-xs text-gray-500 mb-2 block flex items-center gap-1">
              <GitBranch size={12} /> Abhängigkeiten
            </label>

            {predecessors.length === 0 && successors.length === 0 && (
              <p className="text-xs text-gray-400 mb-2">Noch keine Verknüpfungen.</p>
            )}

            {predecessors.map(d => (
              <div key={d.id} className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-1.5 mb-1 text-sm">
                <span className="text-gray-400 text-[11px] shrink-0">hängt ab von</span>
                <span className="flex-1 min-w-0 truncate">{taskName(d.predecessor_id)}</span>
                <span className="text-[10px] text-gray-400 shrink-0">{d.dep_type}</span>
                <button onClick={() => removeDependency(d.id)} className="text-gray-400 hover:text-red-600 shrink-0"><Trash2 size={14} /></button>
              </div>
            ))}
            {successors.map(d => (
              <div key={d.id} className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-1.5 mb-1 text-sm">
                <span className="text-gray-400 text-[11px] shrink-0">Vorgänger von</span>
                <span className="flex-1 min-w-0 truncate">{taskName(d.successor_id)}</span>
                <span className="text-[10px] text-gray-400 shrink-0">{d.dep_type}</span>
                <button onClick={() => removeDependency(d.id)} className="text-gray-400 hover:text-red-600 shrink-0"><Trash2 size={14} /></button>
              </div>
            ))}

            {/* Hinzufügen */}
            {otherTasks.length > 0 && (
              <div className="mt-2 space-y-2">
                <div className="flex gap-2">
                  <select value={depMode} onChange={(e) => setDepMode(e.target.value)}
                    className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm">
                    <option value="pred">hängt ab von</option>
                    <option value="succ">Vorgänger von</option>
                  </select>
                  <select value={depTaskId} onChange={(e) => setDepTaskId(e.target.value)}
                    className="flex-1 min-w-0 border border-gray-300 rounded-lg px-2 py-1.5 text-sm">
                    <option value="">– Aufgabe wählen –</option>
                    {otherTasks.map(t => <option key={t.id} value={t.id}>{t.title}</option>)}
                  </select>
                </div>
                <div className="flex gap-2">
                  <select value={depType} onChange={(e) => setDepType(e.target.value)}
                    className="flex-1 border border-gray-300 rounded-lg px-2 py-1.5 text-sm">
                    {Object.entries(DEP_TYPE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                  <button onClick={addDependency} disabled={depBusy || !depTaskId}
                    className="flex items-center gap-1 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white px-3 rounded-lg text-sm">
                    <Plus size={15} /> Verknüpfen
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Checkliste */}
          <div className="border-t border-gray-100 pt-3">
            <Checklist parentType="task" parentId={task.id} onItemPromoted={onChanged} />
          </div>

          {/* Anlagen */}
          <div className="border-t border-gray-100 pt-3">
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs text-gray-500 flex items-center gap-1"><Paperclip size={12} /> Anlagen</label>
              <button onClick={() => fileRef.current?.click()} disabled={uploading}
                className="flex items-center gap-1 text-xs text-primary-600 hover:text-primary-700 disabled:opacity-50">
                {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />} Hochladen
              </button>
              <input ref={fileRef} type="file" className="hidden" onChange={onUpload}
                accept="image/*,application/pdf,.doc,.docx,.xls,.xlsx" />
            </div>

            {loadingAtt ? (
              <div className="text-xs text-gray-400">Lade Anlagen…</div>
            ) : attachments.length === 0 ? (
              <div className="text-xs text-gray-400">Keine Anlagen. Tippe „Hochladen" (auch Kamera/Foto möglich).</div>
            ) : (
              <div className="space-y-1.5">
                {attachments.map(a => (
                  <div key={a.id} className="flex items-center gap-2 bg-gray-50 rounded-lg px-3 py-2">
                    {isImage(a)
                      ? <ImageIcon size={16} className="text-gray-400 shrink-0" />
                      : <FileText size={16} className="text-gray-400 shrink-0" />}
                    <a href={attachmentApi.downloadUrl(a.id)} target="_blank" rel="noreferrer"
                      className="flex-1 min-w-0 text-sm text-gray-700 truncate hover:text-primary-600">
                      {a.display_name || a.filename}
                    </a>
                    <button onClick={() => removeAtt(a.id)} className="text-gray-400 hover:text-red-600 shrink-0">
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Aktionsleiste */}
        <div className="sticky bottom-0 bg-surface border-t border-gray-100 px-5 py-3 space-y-2">
          <button onClick={save} disabled={saving}
            className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-2.5 rounded-lg font-medium transition">
            <Save size={18} /> {saving ? 'Speichern…' : 'Speichern'}
          </button>
          <button onClick={() => onChanged?.('delete', task)}
            className="w-full flex items-center justify-center gap-2 text-red-600 hover:bg-red-50 py-2.5 rounded-lg text-sm font-medium transition">
            <Trash2 size={16} /> Aufgabe löschen
          </button>
        </div>
      </div>
    </div>
  )
}
