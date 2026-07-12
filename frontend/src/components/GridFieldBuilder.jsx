import { useState, useCallback, useEffect } from 'react'
import {
  DndContext,
  closestCenter,
  pointerWithin,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragOverlay,
  useDroppable,
} from '@dnd-kit/core'
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  rectSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { masterdataApi } from '../services/api'
import toast from 'react-hot-toast'
import {
  GripVertical, Plus, Trash2, Pencil, Check, X,
  ChevronDown, ChevronUp, Loader2, List,
  Layers, FolderPlus, ChevronRight
} from 'lucide-react'
import { FIELD_TYPES } from './FieldBuilder'

// Spaltenbreiten-Optionen
const COL_OPTIONS = [
  { span: 3,  label: '25%',  desc: 'Viertel' },
  { span: 4,  label: '33%',  desc: 'Drittel' },
  { span: 6,  label: '50%',  desc: 'Halb' },
  { span: 9,  label: '75%',  desc: 'Dreiviertel' },
  { span: 12, label: '100%', desc: 'Voll' },
]

const COL_CLASSES = {
  3:  'col-span-3',
  4:  'col-span-4',
  6:  'col-span-6',
  9:  'col-span-9',
  12: 'col-span-12',
}

// ── Drag-Overlay ───────────────────────────────────────────────────────────────
function DragPreview({ field }) {
  const TypeInfo = FIELD_TYPES.find(t => t.key === field.field_type) || FIELD_TYPES[0]
  return (
    <div className="bg-primary-50 border-2 border-primary-400 border-dashed rounded-xl p-3 opacity-90 shadow-lg">
      <div className="flex items-center gap-2">
        <GripVertical size={14} className="text-primary-400" />
        <span className="text-sm font-medium text-primary-700">{field.name}</span>
        <span className="text-xs text-primary-400">{TypeInfo.label}</span>
      </div>
    </div>
  )
}

// ── Einzelnes sortierbares Feld ───────────────────────────────────────────────
function SortableField({ field, slug, tabs, activeTab, onUpdated, onDeleted, onColSpanChange, onTabChange }) {
  const {
    attributes, listeners, setNodeRef,
    transform, transition, isDragging,
  } = useSortable({ id: field.id })

  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.3 : 1 }

  const [editing, setEditing]         = useState(false)
  const [name, setName]               = useState(field.name)
  const [isRequired, setIsRequired]   = useState(field.is_required)
  const [showInList, setShowInList]   = useState(field.show_in_list)
  const [loading, setLoading]         = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const TypeInfo = FIELD_TYPES.find(t => t.key === field.field_type) || FIELD_TYPES[0]
  const TypeIcon = TypeInfo.icon

  const handleSave = async () => {
    setLoading(true)
    try {
      const res = await masterdataApi.updateField(slug, field.id, {
        name: name.trim(),
        is_required: isRequired,
        show_in_list: showInList,
      })
      toast.success('Feld gespeichert')
      onUpdated(res.data)
      setEditing(false)
    } catch {
      toast.error('Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!confirmDelete) { setConfirmDelete(true); return }
    setLoading(true)
    try {
      await masterdataApi.deleteField(slug, field.id)
      toast.success(`'${field.name}' entfernt`)
      onDeleted(field.id)
    } catch {
      toast.error('Löschen fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  const colClass = COL_CLASSES[field.col_span] || 'col-span-12'

  return (
    <div ref={setNodeRef} style={style} className={`${colClass} group`}>
      <div className={`rounded-xl border transition h-full ${
        isDragging ? 'border-primary-300 bg-primary-50'
        : editing   ? 'border-primary-400 bg-surface shadow-sm'
                    : 'border-gray-200 bg-surface hover:border-gray-300 hover:shadow-sm'
      }`}>
        <div className="p-3">
          {editing ? (
            <div className="space-y-2">
              <input type="text" value={name} onChange={e => setName(e.target.value)} autoFocus
                className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
              <div className="flex gap-3 text-xs">
                <label className="flex items-center gap-1.5 cursor-pointer text-gray-600">
                  <input type="checkbox" checked={isRequired} onChange={e => setIsRequired(e.target.checked)}
                    className="w-3.5 h-3.5 accent-primary-600" />
                  Pflichtfeld
                </label>
                <label className="flex items-center gap-1.5 cursor-pointer text-gray-600">
                  <input type="checkbox" checked={showInList} onChange={e => setShowInList(e.target.checked)}
                    className="w-3.5 h-3.5 accent-primary-600" />
                  In Liste
                </label>
              </div>
              <div className="flex gap-1.5">
                <button onClick={handleSave} disabled={loading}
                  className="flex items-center gap-1 px-2 py-1 bg-primary-600 text-white text-xs rounded-lg hover:bg-primary-700 transition">
                  {loading ? <Loader2 size={11} className="animate-spin" /> : <Check size={11} />} OK
                </button>
                <button onClick={() => { setEditing(false); setName(field.name) }}
                  className="px-2 py-1 border border-gray-300 text-gray-500 text-xs rounded-lg hover:bg-gray-50 transition">
                  <X size={11} />
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-start gap-2">
              <button {...attributes} {...listeners}
                className="mt-0.5 text-gray-300 hover:text-gray-500 cursor-grab active:cursor-grabbing flex-shrink-0 touch-none"
                aria-label="Feld verschieben">
                <GripVertical size={15} />
              </button>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <TypeIcon size={13} className="text-gray-400 flex-shrink-0" />
                  <span className="text-sm font-medium text-gray-800 truncate">{field.name}</span>
                </div>
                <div className="flex flex-wrap gap-1 mt-1">
                  <span className="text-xs text-gray-400">{TypeInfo.label}</span>
                  {field.is_required && <span className="text-xs bg-red-50 text-red-500 px-1 rounded">Pflicht</span>}
                  {field.show_in_list && <span className="text-xs bg-blue-50 text-blue-500 px-1 rounded">Liste</span>}
                </div>
              </div>
              <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition flex-shrink-0">
                <button onClick={() => setEditing(true)}
                  className="p-1 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
                  <Pencil size={12} />
                </button>
                <button onClick={handleDelete} disabled={loading}
                  className={`p-1 rounded-lg transition ${
                    confirmDelete ? 'bg-red-100 text-red-500' : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
                  }`} title={confirmDelete ? 'Nochmal klicken' : 'Löschen'}>
                  {loading ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Untere Leiste: Breite + Tab-Zuweisung */}
        {!editing && (
          <div className="border-t border-gray-100 px-2 py-1.5 flex items-center gap-2">
            {/* Breitenauswahl */}
            <div className="flex gap-1">
              {COL_OPTIONS.map(opt => (
                <button key={opt.span} onClick={() => onColSpanChange(field.id, opt.span)}
                  title={`${opt.desc} (${opt.label})`}
                  className={`text-xs px-1.5 py-0.5 rounded transition ${
                    field.col_span === opt.span
                      ? 'bg-primary-600 text-white font-medium'
                      : 'text-gray-400 hover:bg-gray-100 hover:text-gray-700'
                  }`}>
                  {opt.label}
                </button>
              ))}
            </div>
            {/* Tab-Zuweisung (nur wenn Tabs definiert) */}
            {tabs.length > 0 && (
              <select
                value={field.tab || tabs[0]}
                onChange={e => onTabChange(field.id, e.target.value)}
                className="ml-auto text-xs border border-gray-200 rounded px-1.5 py-0.5 bg-surface text-gray-600 focus:outline-none focus:ring-1 focus:ring-primary-400"
                title="Tab-Zuweisung"
              >
                {tabs.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Neues Feld hinzufügen ─────────────────────────────────────────────────────
function AddFieldPanel({ slug, tabs, activeTab, onAdded }) {
  const [open, setOpen]               = useState(false)
  const [name, setName]               = useState('')
  const [fieldType, setFieldType]     = useState('text')
  const [colSpan, setColSpan]         = useState(12)
  const [isRequired, setIsRequired]   = useState(false)
  const [options, setOptions]         = useState('')
  const [placeholder, setPlaceholder] = useState('')
  const [linkedTypeSlug, setLinkedTypeSlug] = useState('')
  const [selectedTab, setSelectedTab] = useState(activeTab || (tabs[0] ?? null))
  const [availableTypes, setAvailableTypes] = useState([])
  const [loading, setLoading]         = useState(false)

  // Beim Öffnen des Panels immer den aktuell aktiven Tab übernehmen
  useEffect(() => {
    if (open) {
      setSelectedTab(activeTab || tabs[0] || null)
    }
  }, [open, activeTab, tabs])

  useEffect(() => {
    if (fieldType === 'relation') {
      masterdataApi.listTypes()
        .then(res => setAvailableTypes(res.data.filter(t => t.slug !== slug)))
        .catch(() => {})
    }
  }, [fieldType, slug])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    if (fieldType === 'relation' && !linkedTypeSlug) {
      toast.error('Bitte einen Ziel-Typ für die Verknüpfung auswählen')
      return
    }
    setLoading(true)
    try {
      const res = await masterdataApi.addField(slug, {
        name: name.trim(),
        key: name.trim(),
        field_type: fieldType,
        col_span: colSpan,
        is_required: isRequired,
        show_in_list: true,
        tab: tabs.length > 0 ? (selectedTab || tabs[0]) : null,
        placeholder: placeholder || null,
        options: fieldType === 'dropdown' ? options.split(',').map(o => o.trim()).filter(Boolean) : null,
        linked_type_slug: fieldType === 'relation' ? linkedTypeSlug : null,
      })
      toast.success(`Feld '${name}' hinzugefügt`)
      onAdded(res.data)
      setName(''); setFieldType('text'); setColSpan(12)
      setIsRequired(false); setOptions(''); setPlaceholder(''); setLinkedTypeSlug('')
      setOpen(false)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Hinzufügen')
    } finally {
      setLoading(false)
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="col-span-12 py-3 border-2 border-dashed border-gray-200 hover:border-primary-400 hover:bg-primary-50 rounded-xl text-sm text-gray-400 hover:text-primary-600 transition flex items-center justify-center gap-2">
        <Plus size={16} /> Neues Feld hinzufügen
      </button>
    )
  }

  return (
    <div className="col-span-12 bg-blue-50 border-2 border-blue-200 rounded-xl p-4">
      <p className="text-sm font-semibold text-blue-900 mb-3 flex items-center gap-2">
        <Plus size={14} /> Neues Feld
      </p>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Bezeichnung *</label>
            <input type="text" value={name} onChange={e => setName(e.target.value)} autoFocus required
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="z.B. Geburtsdatum, Umsatz …" />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Feldtyp</label>
            <select value={fieldType} onChange={e => setFieldType(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface">
              {FIELD_TYPES.map(({ key, label }) => <option key={key} value={key}>{label}</option>)}
            </select>
          </div>
        </div>

        {fieldType === 'relation' && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Verknüpft mit *</label>
            {availableTypes.length === 0 ? (
              <p className="text-xs text-gray-400 py-2">Keine anderen Stammdaten-Typen vorhanden</p>
            ) : (
              <select value={linkedTypeSlug} onChange={e => setLinkedTypeSlug(e.target.value)} required
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface">
                <option value="">— Typ auswählen —</option>
                {availableTypes.map(t => <option key={t.slug} value={t.slug}>{t.name}</option>)}
              </select>
            )}
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Breite im Formular</label>
          <div className="flex gap-1.5">
            {COL_OPTIONS.map(opt => (
              <button key={opt.span} type="button" onClick={() => setColSpan(opt.span)}
                className={`flex-1 py-1.5 text-xs rounded-lg border transition ${
                  colSpan === opt.span
                    ? 'bg-primary-600 text-white border-primary-600 font-medium'
                    : 'border-gray-300 text-gray-600 hover:border-primary-400 hover:text-primary-600'
                }`}>
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {tabs.length > 0 && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Tab-Zugehörigkeit</label>
            <select value={selectedTab || tabs[0]} onChange={e => setSelectedTab(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface">
              {tabs.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        )}

        {fieldType === 'dropdown' && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Optionen (kommagetrennt)</label>
            <input type="text" value={options} onChange={e => setOptions(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="Option A, Option B, Option C" />
          </div>
        )}

        {!['checkbox', 'date', 'relation'].includes(fieldType) && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Platzhalter (optional)</label>
            <input type="text" value={placeholder} onChange={e => setPlaceholder(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="Hinweistext im Eingabefeld" />
          </div>
        )}

        <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
          <input type="checkbox" checked={isRequired} onChange={e => setIsRequired(e.target.checked)}
            className="w-4 h-4 accent-primary-600" />
          Pflichtfeld
        </label>

        <div className="flex gap-2 pt-1">
          <button type="submit" disabled={loading || !name.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white text-sm font-medium rounded-lg transition">
            {loading ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
            Feld hinzufügen
          </button>
          <button type="button" onClick={() => setOpen(false)}
            className="px-4 py-2 border border-gray-300 text-gray-600 text-sm rounded-lg hover:bg-gray-50 transition">
            Abbrechen
          </button>
        </div>
      </form>
    </div>
  )
}

// ── Tab als Drop-Zone ────────────────────────────────────────────────────────
// Wird nur während eines Drag-Vorgangs als Ziel genutzt
function DroppableTab({ tab, isActive, fieldCount, isDragging, onClick }) {
  const { isOver, setNodeRef } = useDroppable({ id: `tab::${tab}` })
  return (
    <button
      ref={setNodeRef}
      type="button"
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium transition -mb-px border-b-2 rounded-t-lg ${
        isActive
          ? 'border-primary-500 text-primary-700 bg-primary-50'
          : isOver && isDragging
          ? 'border-amber-400 bg-amber-50 text-amber-800 scale-105'
          : isDragging
          ? 'border-dashed border-gray-300 text-gray-500 bg-gray-50'
          : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
      }`}
    >
      {tab}
      <span className={`ml-1.5 text-xs ${isOver && isDragging ? 'text-amber-600 font-semibold' : 'text-gray-400'}`}>
        ({fieldCount})
      </span>
      {isOver && isDragging && (
        <span className="ml-1 text-xs text-amber-600">← hier ablegen</span>
      )}
    </button>
  )
}

// ── Tab-Verwaltung ────────────────────────────────────────────────────────────
function TabManager({ slug, tabs, onTabsChanged }) {
  const [newTabName, setNewTabName]   = useState('')
  const [editingIdx, setEditingIdx]   = useState(null)
  const [editingName, setEditingName] = useState('')
  const [saving, setSaving]           = useState(false)

  const saveTabs = async (updatedTabs) => {
    setSaving(true)
    try {
      await masterdataApi.updateTabs(slug, updatedTabs)
      onTabsChanged(updatedTabs)
    } catch {
      toast.error('Tabs konnten nicht gespeichert werden')
    } finally {
      setSaving(false)
    }
  }

  const addTab = async () => {
    const name = newTabName.trim()
    if (!name || tabs.includes(name)) return
    const updated = [...tabs, name]
    setNewTabName('')
    await saveTabs(updated)
  }

  const renameTab = async (idx) => {
    const name = editingName.trim()
    if (!name) { setEditingIdx(null); return }
    const updated = tabs.map((t, i) => i === idx ? name : t)
    setEditingIdx(null)
    await saveTabs(updated)
  }

  const deleteTab = async (idx) => {
    const updated = tabs.filter((_, i) => i !== idx)
    await saveTabs(updated)
  }

  return (
    <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-xl">
      <div className="flex items-center gap-2 mb-3">
        <Layers size={15} className="text-amber-600" />
        <span className="text-sm font-semibold text-amber-900">Register (Tabs)</span>
        {saving && <Loader2 size={13} className="animate-spin text-amber-500" />}
      </div>

      {tabs.length === 0 ? (
        <p className="text-xs text-amber-700 mb-3">
          Noch keine Register angelegt. Erstelle Register um das Formular in übersichtliche Reiter aufzuteilen.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2 mb-3">
          {tabs.map((tab, idx) => (
            <div key={idx} className="flex items-center gap-1 bg-surface border border-amber-300 rounded-lg px-2 py-1">
              {editingIdx === idx ? (
                <>
                  <input
                    autoFocus
                    value={editingName}
                    onChange={e => setEditingName(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') renameTab(idx); if (e.key === 'Escape') setEditingIdx(null) }}
                    className="text-xs border-0 outline-none bg-transparent w-24 text-gray-800"
                  />
                  <button onClick={() => renameTab(idx)} className="text-green-600 hover:text-green-700">
                    <Check size={12} />
                  </button>
                  <button onClick={() => setEditingIdx(null)} className="text-gray-400 hover:text-gray-600">
                    <X size={12} />
                  </button>
                </>
              ) : (
                <>
                  <span className="text-xs font-medium text-gray-800">{tab}</span>
                  <button onClick={() => { setEditingIdx(idx); setEditingName(tab) }}
                    className="text-gray-400 hover:text-amber-600 transition">
                    <Pencil size={11} />
                  </button>
                  <button onClick={() => deleteTab(idx)}
                    className="text-gray-400 hover:text-red-500 transition">
                    <X size={11} />
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Neuen Tab hinzufügen */}
      <div className="flex gap-2">
        <input
          type="text"
          value={newTabName}
          onChange={e => setNewTabName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addTab() } }}
          placeholder="Register-Name, z.B. Bankdaten"
          className="flex-1 px-3 py-1.5 border border-amber-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 bg-surface"
        />
        <button
          onClick={addTab}
          disabled={!newTabName.trim() || tabs.includes(newTabName.trim())}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 disabled:bg-amber-300 text-white text-sm rounded-lg transition"
        >
          <FolderPlus size={14} />
          Hinzufügen
        </button>
      </div>
    </div>
  )
}

// ── Hauptkomponente ───────────────────────────────────────────────────────────
export default function GridFieldBuilder({ entityType, onFieldsChanged }) {
  const [fields, setFields] = useState(
    [...(entityType.fields || [])].sort((a, b) => a.sort_order - b.sort_order)
  )
  const [tabs, setTabs]         = useState(entityType.tabs || [])
  const [activeTab, setActiveTab] = useState(null)   // null = alle / erster Tab
  const [activeId, setActiveId] = useState(null)
  const [showBuilder, setShowBuilder] = useState(false)
  const [saving, setSaving]     = useState(false)

  // Wenn Tabs vorhanden, erster Tab als Default
  useEffect(() => {
    if (tabs.length > 0 && activeTab === null) {
      setActiveTab(tabs[0])
    }
    if (tabs.length === 0) {
      setActiveTab(null)
    }
  }, [tabs])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  const saveLayout = useCallback(async (updatedFields) => {
    setSaving(true)
    try {
      const layout = updatedFields.map((f, idx) => ({
        field_id:   f.id,
        sort_order: idx * 10,
        col_span:   f.col_span,
        tab:        f.tab ?? null,
      }))
      await masterdataApi.updateFieldsLayout(entityType.slug, layout)
    } catch {
      toast.error('Layout konnte nicht gespeichert werden')
    } finally {
      setSaving(false)
    }
  }, [entityType.slug])

  const handleDragStart = ({ active }) => setActiveId(active.id)

  const handleDragEnd = ({ active, over }) => {
    setActiveId(null)
    if (!over) return

    // ── Auf einen Tab-Button fallen gelassen → Feld in diesen Tab verschieben
    if (String(over.id).startsWith('tab::')) {
      const targetTab = String(over.id).replace('tab::', '')
      setFields(prev => {
        const updated = prev.map(f =>
          f.id === active.id ? { ...f, tab: targetTab } : f
        )
        saveLayout(updated)
        onFieldsChanged?.(updated)
        return updated
      })
      setActiveTab(targetTab)   // direkt zum Ziel-Tab wechseln
      return
    }

    // ── Normales Umsortieren innerhalb des aktiven Tabs
    if (active.id === over.id) return
    setFields(prev => {
      const oldIdx = prev.findIndex(f => f.id === active.id)
      const newIdx = prev.findIndex(f => f.id === over.id)
      const reordered = arrayMove(prev, oldIdx, newIdx)
      saveLayout(reordered)
      onFieldsChanged?.(reordered)
      return reordered
    })
  }

  const handleColSpanChange = (fieldId, colSpan) => {
    setFields(prev => {
      const updated = prev.map(f => f.id === fieldId ? { ...f, col_span: colSpan } : f)
      saveLayout(updated)
      onFieldsChanged?.(updated)
      return updated
    })
  }

  const handleTabChange = (fieldId, tab) => {
    setFields(prev => {
      const updated = prev.map(f => f.id === fieldId ? { ...f, tab } : f)
      saveLayout(updated)
      onFieldsChanged?.(updated)
      return updated
    })
  }

  const handleUpdated = (updated) => {
    setFields(prev => prev.map(f => f.id === updated.id ? { ...f, ...updated } : f))
  }

  const handleDeleted = (id) => {
    setFields(prev => {
      const updated = prev.filter(f => f.id !== id)
      onFieldsChanged?.(updated)
      return updated
    })
  }

  const handleAdded = (newField) => {
    setFields(prev => {
      const updated = [...prev, newField]
      onFieldsChanged?.(updated)
      return updated
    })
  }

  const handleTabsChanged = (newTabs) => {
    setTabs(newTabs)
    // Falls aktiver Tab gelöscht wurde → ersten Tab wählen
    if (activeTab && !newTabs.includes(activeTab)) {
      setActiveTab(newTabs[0] || null)
    }
    // Felder deren Tab nicht mehr existiert → erstem Tab zuweisen
    if (newTabs.length > 0) {
      setFields(prev => {
        const updated = prev.map(f =>
          f.tab && !newTabs.includes(f.tab) ? { ...f, tab: newTabs[0] } : f
        )
        saveLayout(updated)
        return updated
      })
    }
    // EntityType-Response für Parent aktualisieren
    onFieldsChanged?.()
  }

  // Felder für aktuellen Tab filtern
  const visibleFields = tabs.length > 0 && activeTab
    ? fields.filter(f => (f.tab || tabs[0]) === activeTab)
    : fields

  const activeField = fields.find(f => f.id === activeId)

  return (
    <div className="bg-surface rounded-2xl border border-gray-200">
      {/* Header */}
      <button
        onClick={() => setShowBuilder(!showBuilder)}
        className="w-full flex items-center justify-between p-4 sm:p-5 hover:bg-gray-50 transition rounded-2xl"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gray-100 rounded-xl">
            <List size={18} className="text-gray-600" />
          </div>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <p className="font-semibold text-gray-900 text-sm">Formular-Layout verwalten</p>
              {saving && <Loader2 size={13} className="animate-spin text-primary-400" />}
            </div>
            <p className="text-xs text-gray-500">
              {fields.length} Felder
              {tabs.length > 0 && ` · ${tabs.length} Register`}
              {' · Ziehen zum Sortieren · Breite frei wählbar'}
            </p>
          </div>
        </div>
        {showBuilder
          ? <ChevronUp size={18} className="text-gray-400" />
          : <ChevronDown size={18} className="text-gray-400" />
        }
      </button>

      {showBuilder && (
        <div className="border-t border-gray-100 p-4 sm:p-5">
          {/* Tab-Verwaltung */}
          <TabManager slug={entityType.slug} tabs={tabs} onTabsChanged={handleTabsChanged} />

          {/* 12-Spalten Grid — DndContext umschließt Tab-Navigation + Felder */}
          {/* pointerWithin erkennt Drop auf Tab-Buttons; closestCenter als Fallback für Sortierung */}
          <DndContext
            sensors={sensors}
            collisionDetection={(args) => pointerWithin(args).length > 0 ? pointerWithin(args) : closestCenter(args)}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
          {/* Tab-Navigation im Builder (Drop-Zonen während Drag) */}
          {tabs.length > 0 && (
            <div className="flex items-center gap-1 mb-4 border-b border-gray-200 pb-0">
              {tabs.map(tab => (
                <DroppableTab
                  key={tab}
                  tab={tab}
                  isActive={activeTab === tab}
                  fieldCount={fields.filter(f => (f.tab || tabs[0]) === tab).length}
                  isDragging={!!activeId}
                  onClick={() => setActiveTab(tab)}
                />
              ))}
              {activeId && (
                <span className="ml-3 text-xs text-amber-600 animate-pulse">
                  ↑ Feld auf Register-Reiter fallen lassen zum Verschieben
                </span>
              )}
            </div>
          )}

          {/* Raster-Hinweis */}
          <p className="text-xs text-gray-400 mb-3 flex items-center gap-1.5">
            <span className="inline-block w-3 h-3 border border-gray-300 rounded-sm"></span>
            Unsichtbares 12-Spalten-Raster · Felder einrasten automatisch
          </p>
            <SortableContext items={visibleFields.map(f => f.id)} strategy={rectSortingStrategy}>
              <div className="grid grid-cols-12 gap-3 auto-rows-auto">
                {visibleFields.map(field => (
                  <SortableField
                    key={field.id}
                    field={field}
                    slug={entityType.slug}
                    tabs={tabs}
                    activeTab={activeTab}
                    onUpdated={handleUpdated}
                    onDeleted={handleDeleted}
                    onColSpanChange={handleColSpanChange}
                    onTabChange={handleTabChange}
                  />
                ))}
                <AddFieldPanel
                  slug={entityType.slug}
                  tabs={tabs}
                  activeTab={activeTab}
                  onAdded={handleAdded}
                />
              </div>
            </SortableContext>

            <DragOverlay>
              {activeField ? <DragPreview field={activeField} /> : null}
            </DragOverlay>
          </DndContext>
        </div>
      )}
    </div>
  )
}
