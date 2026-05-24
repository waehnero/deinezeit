import { useState, useEffect, useRef } from 'react'
import { FIELD_TYPES } from './FieldBuilder'
import { masterdataApi } from '../services/api'
import toast from 'react-hot-toast'
import { Search, X, Plus, Loader2, GitMerge, ExternalLink } from 'lucide-react'

/**
 * Generiert ein Formular automatisch aus den Felddefinitionen.
 * Wird sowohl für "Neu anlegen" als auch "Bearbeiten" verwendet.
 */
const COL_CLASSES = {
  3:  'col-span-12 sm:col-span-3',
  4:  'col-span-12 sm:col-span-4',
  6:  'col-span-12 sm:col-span-6',
  9:  'col-span-12 sm:col-span-9',
  12: 'col-span-12',
}

export default function DynamicForm({ fields, values, onChange, disabled = false }) {
  const sorted = [...fields].sort((a, b) => a.sort_order - b.sort_order)

  const handleChange = (key, value) => {
    onChange({ ...values, [key]: value })
  }

  return (
    <div className="grid grid-cols-12 gap-4">
      {sorted.map((field) => {
        const colClass = COL_CLASSES[field.col_span] || 'col-span-12'
        return (
          <div key={field.id} className={colClass}>
            <FieldInput
              field={field}
              value={values[field.key] ?? field.default_value ?? ''}
              onChange={(val) => handleChange(field.key, val)}
              disabled={disabled}
            />
          </div>
        )
      })}
    </div>
  )
}

// ── Modal zum Anlegen eines verknüpften Datensatzes ───────────────────────────
// WICHTIG: Kein <form> verwenden – dieses Modal wird innerhalb eines äußeren
// <form> gerendert. Verschachtelte Forms sind in HTML ungültig und verursachen
// Probleme beim Speichern. Stattdessen: div + onClick auf dem Button.
function InlineCreateModal({ entityType, onClose, onCreated }) {
  const [values, setValues] = useState({})
  const [loading, setLoading] = useState(false)

  const handleSave = async () => {
    setLoading(true)
    try {
      const res = await masterdataApi.createRecord(entityType.slug, values)
      toast.success(`${res.data.display_name} wurde in „${entityType.name}" angelegt`)
      onCreated(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Anlegen')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-[60] flex items-start justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-xl my-8">
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-100">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-primary-50 rounded-lg">
              <GitMerge size={16} className="text-primary-600" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-neutral-900">
                Neuen Eintrag in „{entityType.name}" anlegen
              </h2>
              <p className="text-xs text-neutral-400">Wird direkt in {entityType.name} gespeichert und verknüpft</p>
            </div>
          </div>
          <button type="button" onClick={onClose} className="p-1.5 text-neutral-400 hover:text-neutral-600 hover:bg-neutral-100 rounded-lg transition">
            <X size={18} />
          </button>
        </div>
        <div className="px-6 py-5">
          {entityType.fields.length === 0 ? (
            <p className="text-sm text-neutral-400 text-center py-4">
              Keine Felder für {entityType.name} definiert.
            </p>
          ) : (
            <DynamicForm
              fields={entityType.fields}
              values={values}
              onChange={setValues}
            />
          )}
        </div>
        <div className="flex gap-3 px-6 pb-5 border-t border-neutral-100 pt-4">
          <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">
            Abbrechen
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={loading || entityType.fields.length === 0}
            className="btn-primary flex-1 justify-center"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
            Anlegen & verknüpfen
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Verknüpfungs-Feld ─────────────────────────────────────────────────────────
function RelationField({ field, value, onChange, disabled }) {
  const linkedSlug = field.linked_type_slug
  const [linkedEntityType, setLinkedEntityType] = useState(null)
  const [search, setSearch] = useState('')
  const [results, setResults] = useState([])
  const [isOpen, setIsOpen] = useState(false)
  const [loadingResults, setLoadingResults] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const dropdownRef = useRef(null)

  // Gespeicherter Wert: { id, display_name } oder leer
  const selected = value && typeof value === 'object' && value.id ? value : null

  // EntityType für das Anlegen-Modal laden
  useEffect(() => {
    if (!linkedSlug) return
    masterdataApi.getType(linkedSlug)
      .then(res => setLinkedEntityType(res.data))
      .catch(() => {})
  }, [linkedSlug])

  // Datensätze suchen (mit Debounce)
  useEffect(() => {
    if (!linkedSlug || !isOpen) return
    const timer = setTimeout(async () => {
      setLoadingResults(true)
      try {
        const res = await masterdataApi.listRecords(linkedSlug, {
          search: search || undefined,
          page_size: 10,
        })
        setResults(res.data.items)
      } catch {
        setResults([])
      } finally {
        setLoadingResults(false)
      }
    }, 250)
    return () => clearTimeout(timer)
  }, [search, isOpen, linkedSlug])

  // Klick außerhalb schließt Dropdown
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = (record) => {
    onChange({ id: record.id, display_name: record.display_name })
    setIsOpen(false)
    setSearch('')
  }

  const handleClear = () => {
    onChange(null)
    setSearch('')
  }

  const handleCreated = (record) => {
    onChange({ id: record.id, display_name: record.display_name })
    setShowCreateModal(false)
  }

  const baseInput = "w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition disabled:bg-gray-50 disabled:text-gray-500"

  const label = (
    <label className="block text-sm font-medium text-gray-700 mb-1">
      {field.name}
      {field.is_required && <span className="text-red-500 ml-1">*</span>}
      {linkedEntityType && (
        <span className="ml-2 text-xs text-neutral-400 font-normal">→ {linkedEntityType.name}</span>
      )}
    </label>
  )

  if (!linkedSlug) {
    return (
      <div>
        {label}
        <div className="px-4 py-2.5 border border-dashed border-red-200 rounded-xl text-sm text-red-400">
          Kein Ziel-Typ konfiguriert
        </div>
      </div>
    )
  }

  return (
    <div>
      {label}

      {selected ? (
        // Ausgewählter Datensatz
        <div className={`flex items-center gap-2 px-3 py-2.5 border rounded-xl ${disabled ? 'bg-gray-50 border-gray-200' : 'bg-primary-50 border-primary-200'}`}>
          <GitMerge size={14} className="text-primary-500 flex-shrink-0" />
          <span className="text-sm text-primary-800 flex-1 font-medium">{selected.display_name}</span>
          {!disabled && (
            <button
              type="button"
              onClick={handleClear}
              className="p-0.5 text-primary-400 hover:text-red-500 transition"
              title="Verknüpfung aufheben"
            >
              <X size={14} />
            </button>
          )}
        </div>
      ) : (
        // Suche + Dropdown
        <div className="space-y-1.5" ref={dropdownRef}>
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input
              type="text"
              value={search}
              onChange={(e) => { setSearch(e.target.value); setIsOpen(true) }}
              onFocus={() => setIsOpen(true)}
              placeholder={`${linkedEntityType?.name || field.name} suchen…`}
              className={`${baseInput} pl-9`}
              disabled={disabled}
            />
            {loadingResults && (
              <Loader2 size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 animate-spin" />
            )}

            {/* Suchergebnis-Dropdown */}
            {isOpen && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-xl shadow-lg z-20 overflow-hidden">
                {results.length > 0 ? (
                  <ul className="max-h-48 overflow-y-auto">
                    {results.map(record => (
                      <li key={record.id}>
                        <button
                          type="button"
                          onClick={() => handleSelect(record)}
                          className="w-full text-left px-4 py-2.5 text-sm text-gray-700 hover:bg-primary-50 hover:text-primary-700 transition flex items-center gap-2"
                        >
                          <span className="flex-1">{record.display_name}</span>
                          <ExternalLink size={12} className="text-gray-300" />
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="px-4 py-3 text-sm text-gray-400 text-center">
                    {loadingResults ? 'Suche läuft…' : search ? 'Keine Ergebnisse' : 'Suchbegriff eingeben…'}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Neu anlegen */}
          {!disabled && linkedEntityType && (
            <button
              type="button"
              onClick={() => setShowCreateModal(true)}
              className="flex items-center gap-1.5 text-xs text-primary-600 hover:text-primary-700 transition font-medium"
            >
              <Plus size={13} />
              Neu in „{linkedEntityType.name}" anlegen
            </button>
          )}
        </div>
      )}

      {/* Modal: Verknüpften Datensatz neu anlegen */}
      {showCreateModal && linkedEntityType && (
        <InlineCreateModal
          entityType={linkedEntityType}
          onClose={() => setShowCreateModal(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  )
}

// ── Einzelnes Feld rendern ────────────────────────────────────────────────────
function FieldInput({ field, value, onChange, disabled }) {
  const TypeInfo = FIELD_TYPES.find(t => t.key === field.field_type)
  const Icon = TypeInfo?.icon

  const baseInput = "w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition disabled:bg-gray-50 disabled:text-gray-500"

  const label = (
    <label className="block text-sm font-medium text-gray-700 mb-1">
      {field.name}
      {field.is_required && <span className="text-red-500 ml-1">*</span>}
    </label>
  )

  switch (field.field_type) {
    case 'relation':
      return (
        <RelationField
          field={field}
          value={value}
          onChange={onChange}
          disabled={disabled}
        />
      )

    case 'textarea':
      return (
        <div>
          {label}
          <textarea
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={field.is_required}
            placeholder={field.placeholder || ''}
            rows={3}
            className={`${baseInput} resize-y`}
          />
        </div>
      )

    case 'checkbox':
      return (
        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={!!value}
            onChange={(e) => onChange(e.target.checked)}
            disabled={disabled}
            className="w-5 h-5 rounded accent-primary-600"
            id={`field-${field.id}`}
          />
          <label htmlFor={`field-${field.id}`} className="text-sm font-medium text-gray-700 cursor-pointer">
            {field.name}
            {field.is_required && <span className="text-red-500 ml-1">*</span>}
          </label>
        </div>
      )

    case 'dropdown':
      return (
        <div>
          {label}
          <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={field.is_required}
            className={`${baseInput} appearance-none bg-white`}
          >
            <option value="">— bitte wählen —</option>
            {(field.options || []).map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        </div>
      )

    case 'number':
      return (
        <div>
          {label}
          <input
            type="number"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={field.is_required}
            placeholder={field.placeholder || '0'}
            step="any"
            className={baseInput}
          />
        </div>
      )

    case 'date':
      return (
        <div>
          {label}
          <input
            type="date"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={field.is_required}
            className={baseInput}
          />
        </div>
      )

    case 'email':
      return (
        <div>
          {label}
          <input
            type="email"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={field.is_required}
            placeholder={field.placeholder || 'name@firma.at'}
            className={baseInput}
          />
        </div>
      )

    case 'phone':
      return (
        <div>
          {label}
          <input
            type="tel"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={field.is_required}
            placeholder={field.placeholder || '+43 1 234 567'}
            className={baseInput}
          />
        </div>
      )

    case 'url':
      return (
        <div>
          {label}
          <input
            type="url"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            required={field.is_required}
            placeholder={field.placeholder || 'https://'}
            className={baseInput}
          />
        </div>
      )

    default: // text
      return (
        <div>
          {label}
          <div className="relative">
            {Icon && (
              <Icon size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            )}
            <input
              type="text"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              disabled={disabled}
              required={field.is_required}
              placeholder={field.placeholder || ''}
              className={`${baseInput} ${Icon ? 'pl-9' : ''}`}
            />
          </div>
        </div>
      )
  }
}
