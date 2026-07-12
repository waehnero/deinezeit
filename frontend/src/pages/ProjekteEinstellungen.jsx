import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { projektplanApi } from '../services/api'
import toast from 'react-hot-toast'
import errMsg from '../utils/errMsg'
import {
  ArrowLeft, Plus, Trash2, Loader2, GanttChartSquare, Tag as TagIcon, X, Pencil, Zap,
} from 'lucide-react'

const FIELD_TYPES = [
  { value: 'text',     label: 'Text' },
  { value: 'textarea', label: 'Mehrzeiliger Text' },
  { value: 'number',   label: 'Zahl' },
  { value: 'date',     label: 'Datum' },
  { value: 'dropdown', label: 'Auswahl (Dropdown)' },
  { value: 'checkbox', label: 'Ja/Nein' },
  { value: 'url',      label: 'Link (URL)' },
]

const COL_OPTIONS = [
  { value: 6,  label: '50%' },
  { value: 12, label: '100%' },
]

function Section({ title, desc, children }) {
  return (
    <div className="bg-surface border border-gray-200 rounded-xl p-5 mb-5">
      <h2 className="text-base font-medium text-gray-900">{title}</h2>
      {desc && <p className="text-sm text-gray-500 mt-0.5 mb-4">{desc}</p>}
      {children}
    </div>
  )
}

/** Erzeugt aus einem Label einen technischen Wert (Slug). */
function slugify(text) {
  const repl = { 'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss' }
  return (text || '')
    .toLowerCase()
    .replace(/[äöüß]/g, c => repl[c] || c)
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
}

/** Editierbare Werteliste (für Status / Prioritäten) */
function OptionListEditor({ items, onChange }) {
  const update = (i, patch) => onChange(items.map((it, idx) => idx === i ? { ...it, ...patch } : it))
  const remove = (i) => onChange(items.filter((_, idx) => idx !== i))
  // Neue Einträge bekommen _new: true -> ihr value wird live aus dem Label generiert.
  const add = () => onChange([...items, { value: '', label: '', color: '#6b7280', _new: true }])

  const onLabelChange = (i, it, label) => {
    // Bei NEUEN Einträgen value immer aus Label ableiten; bei bestehenden den
    // gespeicherten value NICHT ändern (sonst verwaisen vorhandene Aufgaben).
    const patch = { label }
    if (it._new || !it.value) patch.value = slugify(label)
    update(i, patch)
  }

  return (
    <div className="space-y-2">
      {items.map((it, i) => (
        <div key={i} className="flex items-center gap-2">
          <input
            type="color"
            value={it.color || '#6b7280'}
            onChange={(e) => update(i, { color: e.target.value })}
            className="w-9 h-9 rounded border border-gray-200 cursor-pointer shrink-0"
          />
          <input
            value={it.label}
            onChange={(e) => onLabelChange(i, it, e.target.value)}
            placeholder="Bezeichnung"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
          />
          <button onClick={() => remove(i)} className="text-gray-400 hover:text-red-600 shrink-0">
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      <button onClick={add} className="flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700 mt-1">
        <Plus size={15} /> Eintrag hinzufügen
      </button>
    </div>
  )
}

/** Kurzbeschreibung einer Regel für die Listenansicht */
function ruleSummary(r, statuses, taskTypes) {
  const stLabel = (v) => statuses.find(s => s.value === v)?.label || v
  const tyLabel = (v) => taskTypes.find(t => t.value === v)?.label || v
  const when = []
  if (r.trigger_progress_min != null) when.push(`Fortschritt ≥ ${r.trigger_progress_min}%`)
  if (r.trigger_status) when.push(`Status = ${stLabel(r.trigger_status)}`)
  const then = []
  if (r.action_email_assignee) then.push('E-Mail an Verantwortlichen')
  if (r.action_activate_successors) then.push('Nachfolger aktivieren')
  if (r.action_set_status) then.push(`Status → ${stLabel(r.action_set_status)}`)
  const scope = r.applies_to_type ? ` (nur ${tyLabel(r.applies_to_type)})` : ''
  return `WENN ${when.join(' oder ') || '–'} DANN ${then.join(', ') || '–'}${scope}`
}

/** Dialog zum Anlegen/Bearbeiten EINER Regel (Popup) */
function RuleDialog({ rule, statuses, taskTypes, onClose, onSave }) {
  const [r, setR] = useState(() => ({ ...rule }))
  const set = (patch) => setR(prev => ({ ...prev, ...patch }))
  const sel = 'border border-gray-300 rounded-lg px-2 py-1.5 text-sm'

  const valid = (r.trigger_progress_min != null || r.trigger_status) &&
    (r.action_email_assignee || r.action_activate_successors || r.action_set_status)

  return (
    <div className="fixed inset-0 z-[60] flex items-end md:items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-surface w-full md:max-w-lg rounded-t-2xl md:rounded-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <h2 className="text-base font-medium text-gray-900">{rule.name ? 'Regel bearbeiten' : 'Neue Regel'}</h2>
          <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Regelname</label>
            <input value={r.name || ''} onChange={(e) => set({ name: e.target.value })}
              placeholder="z. B. Bei 80% Verantwortlichen benachrichtigen"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>

          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-500">Gilt für Typ:</span>
            <select value={r.applies_to_type || ''} onChange={(e) => set({ applies_to_type: e.target.value || null })} className={sel}>
              <option value="">alle</option>
              {taskTypes.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>

          {/* Trigger */}
          <div className="bg-gray-50 rounded-lg p-3 space-y-2">
            <p className="text-xs font-medium text-gray-600">WENN (mindestens eine Bedingung)</p>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-gray-500">Fortschritt ≥</span>
              <input type="number" min="0" max="100" value={r.trigger_progress_min ?? ''}
                onChange={(e) => set({ trigger_progress_min: e.target.value === '' ? null : Number(e.target.value) })}
                placeholder="z. B. 80" className="w-20 border border-gray-300 rounded-lg px-2 py-1.5 text-sm" />
              <span className="text-gray-400">%</span>
              <span className="text-gray-400 mx-1">oder</span>
              <span className="text-gray-500">Status =</span>
              <select value={r.trigger_status || ''} onChange={(e) => set({ trigger_status: e.target.value || null })} className={sel}>
                <option value="">–</option>
                {statuses.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
          </div>

          {/* Aktionen */}
          <div className="bg-gray-50 rounded-lg p-3 space-y-2">
            <p className="text-xs font-medium text-gray-600">DANN</p>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!r.action_email_assignee} onChange={(e) => set({ action_email_assignee: e.target.checked })} />
              E-Mail an Verantwortlichen senden
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!r.action_activate_successors} onChange={(e) => set({ action_activate_successors: e.target.checked })} />
              Nachfolge-Aufgaben (Abhängigkeiten) auf „in Arbeit" setzen
            </label>
            <div className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!r.action_set_status}
                onChange={(e) => set({ action_set_status: e.target.checked ? (statuses[0]?.value || '') : '' })} />
              <span>Status der Aufgabe setzen auf:</span>
              <select value={r.action_set_status || ''} disabled={!r.action_set_status}
                onChange={(e) => set({ action_set_status: e.target.value })} className={sel}>
                {statuses.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="px-5 py-3 border-t border-gray-100">
          {!valid && <p className="text-[11px] text-amber-600 mb-2">Mindestens eine Bedingung UND eine Aktion wählen.</p>}
          <button onClick={() => onSave(r)} disabled={!valid}
            className="w-full bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-2.5 rounded-lg font-medium">
            Übernehmen
          </button>
        </div>
      </div>
    </div>
  )
}

/** Kompakte Regelliste + Popup zum Anlegen/Bearbeiten */
function RulesEditor({ rules, statuses, taskTypes, onChange }) {
  const [editIdx, setEditIdx] = useState(null)   // Index der zu bearbeitenden Regel, -1 = neu
  const list = rules || []

  const openNew = () => setEditIdx(-1)
  const openEdit = (i) => setEditIdx(i)
  const remove = (i) => onChange(list.filter((_, idx) => idx !== i))
  const toggle = (i, on) => onChange(list.map((r, idx) => idx === i ? { ...r, enabled: on } : r))

  const handleSave = (rule) => {
    if (editIdx === -1) {
      onChange([...list, { ...rule, id: rule.id || `r_${Date.now()}` }])
    } else {
      onChange(list.map((r, idx) => idx === editIdx ? rule : r))
    }
    setEditIdx(null)
  }

  const blank = {
    id: '', name: '', enabled: true, applies_to_type: '',
    trigger_progress_min: null, trigger_status: '',
    action_email_assignee: false, action_set_status: '', action_activate_successors: false,
  }

  return (
    <div className="space-y-2">
      {list.length === 0 && <p className="text-sm text-gray-400">Noch keine Regeln.</p>}
      {list.map((r, i) => (
        <div key={r.id || i} className={`flex items-center gap-3 border border-gray-200 rounded-lg px-3 py-2 ${r.enabled === false ? 'opacity-60' : ''}`}>
          <Zap size={15} className="text-primary-500 shrink-0" />
          <button onClick={() => openEdit(i)} className="flex-1 min-w-0 text-left">
            <p className="text-sm font-medium text-gray-900 truncate">{r.name || '(ohne Namen)'}</p>
            <p className="text-[11px] text-gray-500 truncate">{ruleSummary(r, statuses, taskTypes)}</p>
          </button>
          <label className="flex items-center gap-1 text-xs text-gray-500 shrink-0" title="aktiv">
            <input type="checkbox" checked={r.enabled !== false} onChange={(e) => toggle(i, e.target.checked)} />
          </label>
          <button onClick={() => openEdit(i)} className="text-gray-400 hover:text-primary-600 shrink-0"><Pencil size={15} /></button>
          <button onClick={() => remove(i)} className="text-gray-400 hover:text-red-600 shrink-0"><Trash2 size={15} /></button>
        </div>
      ))}
      <button onClick={openNew} className="flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700 mt-1">
        <Plus size={15} /> Regel hinzufügen
      </button>

      {editIdx !== null && (
        <RuleDialog
          rule={editIdx === -1 ? blank : list[editIdx]}
          statuses={statuses} taskTypes={taskTypes}
          onClose={() => setEditIdx(null)}
          onSave={handleSave}
        />
      )}
    </div>
  )
}

export default function ProjekteEinstellungen() {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [fields, setFields] = useState([])
  const [settings, setSettings] = useState({ statuses: [], priorities: [], tags: [], task_types: [], rules: [] })

  // Neues Feld
  const [showAddField, setShowAddField] = useState(false)
  const [fName, setFName] = useState('')
  const [fType, setFType] = useState('text')
  const [fCol, setFCol] = useState(12)
  const [fOptions, setFOptions] = useState('')
  const [fRequired, setFRequired] = useState(false)

  // Neuer Tag
  const [newTag, setNewTag] = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [f, s] = await Promise.all([
        projektplanApi.listFields(),
        projektplanApi.getSettings(),
      ])
      setFields(f.data)
      setSettings(s.data)
    } catch {
      toast.error('Einstellungen konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const addField = async () => {
    if (!fName.trim()) return toast.error('Bitte einen Feldnamen eingeben')
    setSaving(true)
    try {
      await projektplanApi.createField({
        name: fName.trim(),
        field_type: fType,
        col_span: fCol,
        is_required: fRequired,
        options: fType === 'dropdown'
          ? fOptions.split(',').map(o => o.trim()).filter(Boolean)
          : null,
      })
      toast.success('Feld hinzugefügt')
      setShowAddField(false)
      setFName(''); setFType('text'); setFCol(12); setFOptions(''); setFRequired(false)
      await load()
    } catch (err) {
      toast.error(errMsg(err, 'Fehler beim Anlegen'))
    } finally {
      setSaving(false)
    }
  }

  const removeField = async (id) => {
    try {
      await projektplanApi.deleteField(id)
      await load()
    } catch {
      toast.error('Feld konnte nicht gelöscht werden')
    }
  }

  const saveSettings = async (next) => {
    const raw = next || settings
    setSettings(raw)
    setSaving(true)
    // Internes _new-Flag entfernen + value/label sicherstellen, leere Einträge weglassen
    const clean = (list) => (list || [])
      .map(({ _new, ...rest }) => ({
        ...rest,
        label: (rest.label || '').trim(),
        value: (rest.value || slugify(rest.label || '')).trim(),
      }))
      .filter(it => it.label && it.value)
    // Regeln: nur solche mit Trigger UND mindestens einer Aktion behalten
    const cleanRules = (raw.rules || []).filter(r =>
      (r.trigger_progress_min != null || r.trigger_status) &&
      (r.action_email_assignee || r.action_activate_successors || r.action_set_status)
    )
    const payload = {
      ...raw,
      statuses: clean(raw.statuses),
      priorities: clean(raw.priorities),
      task_types: clean(raw.task_types),
      tags: (raw.tags || []).map(t => (t || '').trim()).filter(Boolean),
      rules: cleanRules,
    }
    try {
      await projektplanApi.updateSettings(payload)
      toast.success('Gespeichert')
    } catch (err) {
      toast.error(errMsg(err, 'Fehler beim Speichern'))
    } finally {
      setSaving(false)
    }
  }

  const addTag = () => {
    const t = newTag.trim()
    if (!t) return
    if (settings.tags.includes(t)) return setNewTag('')
    const next = { ...settings, tags: [...settings.tags, t] }
    setNewTag('')
    saveSettings(next)
  }
  const removeTag = (t) => saveSettings({ ...settings, tags: settings.tags.filter(x => x !== t) })

  if (loading) {
    return <div className="flex justify-center py-20"><Loader2 className="animate-spin text-primary-400" size={28} /></div>
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6">
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/projekte')} className="text-gray-400 hover:text-gray-700">
          <ArrowLeft size={20} />
        </button>
        <GanttChartSquare className="text-primary-600" size={24} />
        <h1 className="text-2xl font-medium text-gray-900">Projekt-Einstellungen</h1>
      </div>

      {/* Status */}
      <Section title="Status" desc="Welche Status-Werte können Aufgaben annehmen?">
        <OptionListEditor
          items={settings.statuses}
          onChange={(v) => setSettings({ ...settings, statuses: v })}
        />
        <button onClick={() => saveSettings()} disabled={saving}
          className="mt-3 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium">
          Status speichern
        </button>
      </Section>

      {/* Prioritäten */}
      <Section title="Prioritäten" desc="Welche Prioritätsstufen gibt es?">
        <OptionListEditor
          items={settings.priorities}
          onChange={(v) => setSettings({ ...settings, priorities: v })}
        />
        <button onClick={() => saveSettings()} disabled={saving}
          className="mt-3 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium">
          Prioritäten speichern
        </button>
      </Section>

      {/* Aufgaben-Typen */}
      <Section title="Aufgaben-Typen" desc="Welche Typen können Aufgaben haben? (z. B. Aufgabe, Meilenstein, GoLive). Der Typ Meilenstein wird automatisch als Raute im Gantt dargestellt.">
        <OptionListEditor
          items={settings.task_types || []}
          onChange={(v) => setSettings({ ...settings, task_types: v })}
        />
        <button onClick={() => saveSettings()} disabled={saving}
          className="mt-3 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium">
          Typen speichern
        </button>
      </Section>

      {/* Tags */}
      <Section title="Tags / Labels" desc="Vordefinierte Schlagwörter, die Aufgaben zugewiesen werden können.">
        <div className="flex flex-wrap gap-2 mb-3">
          {settings.tags.length === 0 && <span className="text-sm text-gray-400">Noch keine Tags.</span>}
          {settings.tags.map((t) => (
            <span key={t} className="flex items-center gap-1.5 bg-primary-50 text-primary-700 text-sm px-3 py-1 rounded-full">
              <TagIcon size={13} /> {t}
              <button onClick={() => removeTag(t)} className="hover:text-red-600"><X size={13} /></button>
            </span>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addTag()}
            placeholder="Neuer Tag, z. B. Dringend"
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
          />
          <button onClick={addTag} className="bg-primary-600 hover:bg-primary-700 text-white px-4 rounded-lg text-sm font-medium">
            Hinzufügen
          </button>
        </div>
      </Section>

      {/* Automatisierung */}
      <Section title="Automatisierung" desc="Regeln nach dem Muster WENN (Trigger) DANN (Aktion). Werden ausgewertet, sobald eine Aufgabe gespeichert wird. Jede Regel löst pro Aufgabe genau einmal aus.">
        <RulesEditor
          rules={settings.rules || []}
          statuses={settings.statuses || []}
          taskTypes={settings.task_types || []}
          onChange={(v) => setSettings({ ...settings, rules: v })}
        />
        <button onClick={() => saveSettings()} disabled={saving}
          className="mt-4 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-sm font-medium">
          Regeln speichern
        </button>
      </Section>

      {/* Eigene Felder */}
      <Section title="Eigene Aufgaben-Felder" desc="Zusätzliche Felder, die bei jeder Aufgabe erfasst werden können.">
        <div className="space-y-2 mb-4">
          {fields.length === 0 && <span className="text-sm text-gray-400">Noch keine eigenen Felder.</span>}
          {fields.map((f) => (
            <div key={f.id} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2">
              <div>
                <span className="text-sm font-medium text-gray-900">{f.name}</span>
                <span className="text-xs text-gray-500 ml-2">
                  {FIELD_TYPES.find(t => t.value === f.field_type)?.label || f.field_type}
                  {f.is_required ? ' · Pflicht' : ''}
                </span>
              </div>
              <button onClick={() => removeField(f.id)} className="text-gray-400 hover:text-red-600">
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>

        {!showAddField ? (
          <button onClick={() => setShowAddField(true)} className="flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700">
            <Plus size={15} /> Feld hinzufügen
          </button>
        ) : (
          <div className="border border-gray-200 rounded-lg p-4 space-y-3">
            <input
              autoFocus value={fName} onChange={(e) => setFName(e.target.value)}
              placeholder="Feldname, z. B. Gewerk"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
            />
            <div className="flex gap-2">
              <select value={fType} onChange={(e) => setFType(e.target.value)}
                className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm">
                {FIELD_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
              <select value={fCol} onChange={(e) => setFCol(Number(e.target.value))}
                className="border border-gray-300 rounded-lg px-3 py-2 text-sm">
                {COL_OPTIONS.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
              </select>
            </div>
            {fType === 'dropdown' && (
              <input
                value={fOptions} onChange={(e) => setFOptions(e.target.value)}
                placeholder="Optionen mit Komma trennen: Option A, Option B"
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400"
              />
            )}
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input type="checkbox" checked={fRequired} onChange={(e) => setFRequired(e.target.checked)} />
              Pflichtfeld
            </label>
            <div className="flex gap-2">
              <button onClick={() => setShowAddField(false)} className="flex-1 border border-gray-300 hover:bg-gray-50 text-gray-700 py-2 rounded-lg text-sm font-medium">
                Abbrechen
              </button>
              <button onClick={addField} disabled={saving} className="flex-1 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-2 rounded-lg text-sm font-medium">
                Feld anlegen
              </button>
            </div>
          </div>
        )}
      </Section>
    </div>
  )
}
