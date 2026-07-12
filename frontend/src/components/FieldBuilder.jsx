import { useState, useEffect } from 'react'
import { masterdataApi } from '../services/api'
import toast from 'react-hot-toast'
import {
  Plus, Trash2, GripVertical, ChevronDown, ChevronUp,
  Type, Hash, Calendar, Mail, Phone, List, CheckSquare,
  AlignLeft, Link, Loader2, Pencil, Check, X, GitMerge
} from 'lucide-react'

// Feldtypen mit Icon und Label
export const FIELD_TYPES = [
  { key: 'text',     label: 'Text (einzeilig)',   icon: Type },
  { key: 'textarea', label: 'Text (mehrzeilig)',   icon: AlignLeft },
  { key: 'number',   label: 'Zahl',               icon: Hash },
  { key: 'date',     label: 'Datum',              icon: Calendar },
  { key: 'email',    label: 'E-Mail',             icon: Mail },
  { key: 'phone',    label: 'Telefon',            icon: Phone },
  { key: 'dropdown', label: 'Auswahlliste',       icon: List },
  { key: 'checkbox', label: 'Ja/Nein',            icon: CheckSquare },
  { key: 'url',      label: 'Webseite (URL)',     icon: Link },
  { key: 'relation', label: 'Verknüpfung',        icon: GitMerge },
]

// Neues Feld hinzufügen – Formular
function AddFieldForm({ slug, onAdded, onCancel }) {
  const [name, setName] = useState('')
  const [fieldType, setFieldType] = useState('text')
  const [isRequired, setIsRequired] = useState(false)
  const [showInList, setShowInList] = useState(true)
  const [options, setOptions] = useState('')  // kommagetrennt für Dropdown
  const [placeholder, setPlaceholder] = useState('')
  const [linkedTypeSlug, setLinkedTypeSlug] = useState('')
  const [availableTypes, setAvailableTypes] = useState([])
  const [loading, setLoading] = useState(false)

  // EntityTypes für Relation-Picker laden
  useEffect(() => {
    if (fieldType === 'relation') {
      masterdataApi.listTypes().then(res => {
        setAvailableTypes(res.data.filter(t => t.slug !== slug))
      }).catch(() => {})
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
      const payload = {
        name: name.trim(),
        key: name.trim(),
        field_type: fieldType,
        is_required: isRequired,
        show_in_list: showInList,
        placeholder: placeholder || null,
        options: fieldType === 'dropdown'
          ? options.split(',').map(o => o.trim()).filter(Boolean)
          : null,
        linked_type_slug: fieldType === 'relation' ? linkedTypeSlug : null,
      }
      const res = await masterdataApi.addField(slug, payload)
      toast.success(`Feld '${name}' wurde hinzugefügt`)
      onAdded(res.data)
      setName('')
      setFieldType('text')
      setIsRequired(false)
      setOptions('')
      setPlaceholder('')
      setLinkedTypeSlug('')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Hinzufügen')
    } finally {
      setLoading(false)
    }
  }

  const TypeIcon = FIELD_TYPES.find(t => t.key === fieldType)?.icon || Type

  return (
    <div className="bg-blue-50 border-2 border-blue-200 rounded-2xl p-5">
      <h4 className="font-semibold text-blue-900 mb-4 flex items-center gap-2">
        <Plus size={16} /> Neues Feld hinzufügen
      </h4>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Feldname */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Feldbezeichnung *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
              className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="z.B. Geburtstag, Umsatz, Kategorie …"
            />
          </div>

          {/* Feldtyp */}
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Feldtyp</label>
            <div className="relative">
              <TypeIcon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <select
                value={fieldType}
                onChange={(e) => setFieldType(e.target.value)}
                className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 appearance-none bg-surface"
              >
                {FIELD_TYPES.map(({ key, label }) => (
                  <option key={key} value={key}>{label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Dropdown-Optionen */}
        {fieldType === 'dropdown' && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Optionen (kommagetrennt) *
            </label>
            <input
              type="text"
              value={options}
              onChange={(e) => setOptions(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="Option 1, Option 2, Option 3"
            />
          </div>
        )}

        {/* Relation: Ziel-Typ auswählen */}
        {fieldType === 'relation' && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Verknüpft mit *
            </label>
            {availableTypes.length === 0 ? (
              <p className="text-xs text-gray-400 py-2">Keine anderen Stammdaten-Typen vorhanden</p>
            ) : (
              <select
                value={linkedTypeSlug}
                onChange={(e) => setLinkedTypeSlug(e.target.value)}
                required
                className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 appearance-none bg-surface"
              >
                <option value="">— Typ auswählen —</option>
                {availableTypes.map(t => (
                  <option key={t.slug} value={t.slug}>{t.name}</option>
                ))}
              </select>
            )}
          </div>
        )}

        {/* Platzhalter */}
        {!['checkbox', 'date', 'relation'].includes(fieldType) && (
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Platzhaltertext (optional)
            </label>
            <input
              type="text"
              value={placeholder}
              onChange={(e) => setPlaceholder(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="Hinweis im leeren Eingabefeld"
            />
          </div>
        )}

        {/* Optionen */}
        <div className="flex flex-wrap gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={isRequired}
              onChange={(e) => setIsRequired(e.target.checked)}
              className="w-4 h-4 rounded accent-primary-600"
            />
            Pflichtfeld
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={showInList}
              onChange={(e) => setShowInList(e.target.checked)}
              className="w-4 h-4 rounded accent-primary-600"
            />
            In Listenansicht anzeigen
          </label>
        </div>

        {/* Buttons */}
        <div className="flex gap-2 pt-1">
          <button
            type="submit"
            disabled={loading || !name.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white text-sm font-medium rounded-xl transition"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            Feld speichern
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 text-gray-600 text-sm rounded-xl hover:bg-gray-50 transition"
          >
            <X size={14} /> Abbrechen
          </button>
        </div>
      </form>
    </div>
  )
}

// Einzelnes Feld in der Liste
function FieldRow({ field, slug, onUpdated, onDeleted }) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(field.name)
  const [isRequired, setIsRequired] = useState(field.is_required)
  const [showInList, setShowInList] = useState(field.show_in_list)
  const [loading, setLoading] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const TypeInfo = FIELD_TYPES.find(t => t.key === field.field_type) || FIELD_TYPES[0]
  const TypeIcon = TypeInfo.icon

  const handleSave = async () => {
    if (!name.trim()) return
    setLoading(true)
    try {
      const res = await masterdataApi.updateField(slug, field.id, {
        name: name.trim(),
        is_required: isRequired,
        show_in_list: showInList,
      })
      toast.success('Feld aktualisiert')
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
      toast.success(`Feld '${field.name}' entfernt`)
      onDeleted(field.id)
    } catch {
      toast.error('Fehler beim Löschen')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className={`bg-surface border rounded-xl p-4 transition ${
      editing ? 'border-primary-300 shadow-sm' : 'border-gray-200 hover:border-gray-300'
    }`}>
      {editing ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <TypeIcon size={16} className="text-gray-400 flex-shrink-0" />
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              className="flex-1 px-2 py-1 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input type="checkbox" checked={isRequired}
                onChange={(e) => setIsRequired(e.target.checked)}
                className="w-4 h-4 accent-primary-600" />
              Pflichtfeld
            </label>
            <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
              <input type="checkbox" checked={showInList}
                onChange={(e) => setShowInList(e.target.checked)}
                className="w-4 h-4 accent-primary-600" />
              In Liste anzeigen
            </label>
          </div>
          <div className="flex gap-2">
            <button onClick={handleSave} disabled={loading}
              className="flex items-center gap-1 px-3 py-1.5 bg-primary-600 text-white text-xs rounded-lg transition hover:bg-primary-700">
              {loading ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
              Speichern
            </button>
            <button onClick={() => { setEditing(false); setName(field.name) }}
              className="px-3 py-1.5 border border-gray-300 text-gray-600 text-xs rounded-lg hover:bg-gray-50 transition">
              Abbrechen
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3">
          <GripVertical size={16} className="text-gray-300 flex-shrink-0 cursor-grab" />
          <TypeIcon size={16} className="text-gray-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <span className="font-medium text-gray-800 text-sm">{field.name}</span>
            <div className="flex flex-wrap items-center gap-2 mt-0.5">
              <span className="text-xs text-gray-400">{TypeInfo.label}</span>
              {field.is_required && (
                <span className="text-xs bg-red-50 text-red-600 px-1.5 py-0.5 rounded-full">
                  Pflichtfeld
                </span>
              )}
              {field.show_in_list && (
                <span className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full">
                  In Liste
                </span>
              )}
              {field.options?.length > 0 && (
                <span className="text-xs text-gray-400 truncate max-w-[200px]">
                  {field.options.join(', ')}
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 flex-shrink-0">
            <button onClick={() => setEditing(true)}
              className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
              <Pencil size={14} />
            </button>
            <button
              onClick={handleDelete}
              disabled={loading}
              className={`p-1.5 rounded-lg transition ${
                confirmDelete
                  ? 'bg-red-100 text-red-600 hover:bg-red-200'
                  : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
              }`}
              title={confirmDelete ? 'Nochmal klicken zum Bestätigen' : 'Feld entfernen'}
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Hauptkomponente: Feld-Builder ─────────────────────────────────────────────
export default function FieldBuilder({ entityType, onFieldsChanged }) {
  const [fields, setFields] = useState(entityType.fields || [])
  const [showAddForm, setShowAddForm] = useState(false)
  const [showBuilder, setShowBuilder] = useState(false)

  const handleAdded = (newField) => {
    const updated = [...fields, newField]
    setFields(updated)
    setShowAddForm(false)
    onFieldsChanged?.(updated)
  }

  const handleUpdated = (updatedField) => {
    const updated = fields.map(f => f.id === updatedField.id ? updatedField : f)
    setFields(updated)
    onFieldsChanged?.(updated)
  }

  const handleDeleted = (fieldId) => {
    const updated = fields.filter(f => f.id !== fieldId)
    setFields(updated)
    onFieldsChanged?.(updated)
  }

  return (
    <div className="bg-surface rounded-2xl border border-gray-200">
      {/* Header – klappbar */}
      <button
        onClick={() => setShowBuilder(!showBuilder)}
        className="w-full flex items-center justify-between p-4 sm:p-5 hover:bg-gray-50 transition rounded-2xl"
      >
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gray-100 rounded-xl">
            <List size={18} className="text-gray-600" />
          </div>
          <div className="text-left">
            <p className="font-semibold text-gray-900 text-sm">Felder verwalten</p>
            <p className="text-xs text-gray-500">{fields.length} Felder definiert</p>
          </div>
        </div>
        {showBuilder
          ? <ChevronUp size={18} className="text-gray-400" />
          : <ChevronDown size={18} className="text-gray-400" />
        }
      </button>

      {showBuilder && (
        <div className="px-4 sm:px-5 pb-5 space-y-2 border-t border-gray-100 pt-4">
          {/* Bestehende Felder */}
          {fields
            .slice()
            .sort((a, b) => a.sort_order - b.sort_order)
            .map(field => (
              <FieldRow
                key={field.id}
                field={field}
                slug={entityType.slug}
                onUpdated={handleUpdated}
                onDeleted={handleDeleted}
              />
            ))
          }

          {fields.length === 0 && !showAddForm && (
            <p className="text-center text-sm text-gray-400 py-4">
              Noch keine Felder definiert
            </p>
          )}

          {/* Neues Feld hinzufügen */}
          {showAddForm ? (
            <AddFieldForm
              slug={entityType.slug}
              onAdded={handleAdded}
              onCancel={() => setShowAddForm(false)}
            />
          ) : (
            <button
              onClick={() => setShowAddForm(true)}
              className="w-full py-2.5 border-2 border-dashed border-gray-200 hover:border-primary-400 hover:bg-primary-50 rounded-xl text-sm text-gray-400 hover:text-primary-600 transition flex items-center justify-center gap-2"
            >
              <Plus size={16} />
              Neues Feld hinzufügen
            </button>
          )}
        </div>
      )}
    </div>
  )
}
