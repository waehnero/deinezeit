import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { masterdataApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import GridFieldBuilder from '../components/GridFieldBuilder'
import DynamicForm from '../components/DynamicForm'
import AttachmentPanel from '../components/AttachmentPanel'
import {
  Plus, Search, ArrowLeft, Trash2, Pencil, X,
  Loader2, Database, ChevronLeft, ChevronRight,
  SlidersHorizontal
} from 'lucide-react'
import { CsvExportButton, CsvImportButton } from '../components/CsvImportExport'

// ── Datensatz-Formular Modal ───────────────────────────────────────────────────
function RecordModal({ entityType, record, onClose, onSaved }) {
  const isEdit = !!record
  const [values, setValues] = useState(record?.data || {})
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      let res
      if (isEdit) {
        res = await masterdataApi.updateRecord(entityType.slug, record.id, values)
        toast.success('Datensatz aktualisiert')
      } else {
        res = await masterdataApi.createRecord(entityType.slug, values)
        toast.success('Datensatz angelegt')
      }
      onSaved(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center p-4 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl my-4">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-900">
            {isEdit ? 'Datensatz bearbeiten' : `Neuen ${entityType.name.replace(/en$/, '').replace(/s$/, '')} anlegen`}
          </h2>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition">
            <X size={20} />
          </button>
        </div>

        {/* Formular */}
        <form onSubmit={handleSubmit}>
          <div className="p-5">
            {entityType.fields.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <Database size={32} className="mx-auto mb-2 text-gray-200" />
                <p className="text-sm">Noch keine Felder definiert.</p>
                <p className="text-sm">Klicken Sie auf „Felder verwalten" um Felder hinzuzufügen.</p>
              </div>
            ) : (
              <DynamicForm
                fields={entityType.fields}
                tabs={entityType.tabs || []}
                values={values}
                onChange={setValues}
              />
            )}
          </div>

          <div className="flex gap-3 p-5 border-t border-gray-100">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition">
              Abbrechen
            </button>
            <button type="submit" disabled={loading || entityType.fields.length === 0}
              className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2">
              {loading ? <Loader2 size={16} className="animate-spin" /> : null}
              {isEdit ? 'Speichern' : 'Anlegen'}
            </button>
          </div>
        </form>

        {/* Anhänge – nur bei bestehenden Datensätzen */}
        {isEdit && (
          <div className="px-5 pb-5 border-t border-gray-100">
            <AttachmentPanel entityType={entityType.slug} entityId={record.id} />
          </div>
        )}
      </div>
    </div>
  )
}

// ── Datensatz-Zeile in der Tabelle ────────────────────────────────────────────
function RecordRow({ record, fields, onEdit, onDelete }) {
  const listFields = fields.filter(f => f.show_in_list).slice(0, 5)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const formatValue = (field, value) => {
    if (value === null || value === undefined || value === '') return '—'
    if (field.field_type === 'checkbox') return value ? '✓ Ja' : '✗ Nein'
    if (field.field_type === 'date') {
      try { return new Date(value).toLocaleDateString('de-AT') } catch { return value }
    }
    if (field.field_type === 'relation') {
      if (typeof value === 'object' && value?.display_name) return value.display_name
      return '—'
    }
    if (field.field_type === 'url') return (
      <a href={value} target="_blank" rel="noopener noreferrer"
        className="text-primary-600 hover:underline truncate block max-w-[200px]"
        onClick={(e) => e.stopPropagation()}>
        {value}
      </a>
    )
    return String(value).length > 60 ? String(value).slice(0, 60) + '…' : value
  }

  return (
    <tr className="hover:bg-gray-50 transition cursor-pointer" onClick={() => onEdit(record)}>
      {listFields.map((field) => (
        <td key={field.id} className="px-4 py-3 text-sm text-gray-700">
          {formatValue(field, record.data[field.key])}
        </td>
      ))}
      <td className="px-4 py-3 text-sm text-gray-400 whitespace-nowrap">
        {new Date(record.updated_at).toLocaleDateString('de-AT')}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
          <button onClick={() => onEdit(record)}
            className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
            <Pencil size={14} />
          </button>
          <button
            onClick={() => { if (confirmDelete) onDelete(record); else setConfirmDelete(true) }}
            onBlur={() => setTimeout(() => setConfirmDelete(false), 200)}
            className={`p-1.5 rounded-lg transition ${
              confirmDelete ? 'bg-red-100 text-red-600' : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
            }`}
            title={confirmDelete ? 'Nochmal klicken um zu löschen' : 'Löschen'}>
            <Trash2 size={14} />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Hauptseite ────────────────────────────────────────────────────────────────
export default function MasterDataDetail() {
  const { slug } = useParams()
  const navigate = useNavigate()
  const { isAdmin } = useAuth()

  const [entityType, setEntityType] = useState(null)
  const [records, setRecords] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 50

  const [modalRecord, setModalRecord] = useState(undefined) // undefined=geschlossen, null=neu, obj=bearbeiten
  const [typFilter, setTypFilter] = useState('') // nur bei slug === 'kontakte' genutzt

  const loadType = useCallback(async () => {
    try {
      const res = await masterdataApi.getType(slug)
      setEntityType(res.data)
    } catch {
      toast.error('Stammdaten-Typ nicht gefunden')
      navigate('/masterdata')
    }
  }, [slug])

  const loadRecords = useCallback(async () => {
    if (!entityType) return
    try {
      const res = await masterdataApi.listRecords(slug, {
        search: search || undefined,
        page,
        page_size: PAGE_SIZE,
        ...(typFilter ? { filter_field: 'typ', filter_value: typFilter } : {}),
      })
      setRecords(res.data.items)
      setTotal(res.data.total)
    } catch {
      toast.error('Datensätze konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }, [slug, entityType, search, page, typFilter])

  useEffect(() => { loadType() }, [loadType])
  useEffect(() => { if (entityType) loadRecords() }, [loadRecords])

  const handleSaved = (saved) => {
    if (modalRecord) {
      setRecords(records.map(r => r.id === saved.id ? saved : r))
    } else {
      setRecords([saved, ...records])
      setTotal(total + 1)
    }
    setModalRecord(undefined)
  }

  const handleDelete = async (record) => {
    try {
      await masterdataApi.deleteRecord(slug, record.id)
      setRecords(records.filter(r => r.id !== record.id))
      setTotal(total - 1)
      toast.success('Datensatz gelöscht')
    } catch {
      toast.error('Löschen fehlgeschlagen')
    }
  }

  const handleFieldsChanged = () => {
    loadType()
  }

  if (!entityType) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={32} className="animate-spin text-primary-500" />
      </div>
    )
  }

  const listFields = entityType.fields.filter(f => f.show_in_list).slice(0, 5)
  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 mb-6">
        <button onClick={() => navigate('/masterdata')}
          className="flex items-center gap-1 text-gray-400 hover:text-gray-700 transition text-sm">
          <ArrowLeft size={16} /> Zurück
        </button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-gray-900">{entityType.name}</h1>
          <p className="text-gray-400 text-sm mt-0.5">
            {total} {total === 1 ? 'Eintrag' : 'Einträge'}
          </p>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <div className="flex items-center gap-2">
            <CsvExportButton slug={entityType.slug} entityName={entityType.name} />
            <CsvImportButton
              slug={entityType.slug}
              entityType={entityType}
              onImported={() => loadRecords()}
            />
          </div>
          <button
            onClick={() => setModalRecord(null)}
            className="flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-4 py-2.5 rounded-xl font-medium transition"
          >
            <Plus size={18} />
            Neu anlegen
          </button>
        </div>
      </div>

      {/* Grid Feld-Builder – nur für Admins */}
      {isAdmin && (
        <div className="mb-4">
          <GridFieldBuilder entityType={entityType} onFieldsChanged={handleFieldsChanged} />
        </div>
      )}

      {/* Suche */}
      <div className="relative mb-4">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1) }}
          placeholder={`In ${entityType.name} suchen…`}
          className="w-full pl-9 pr-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-white"
        />
      </div>

      {/* Typ-Filter (nur bei Kontakte) */}
      {slug === 'kontakte' && (
        <div className="flex gap-2 mb-4 overflow-x-auto flex-nowrap sm:flex-wrap -mx-4 px-4 sm:mx-0 sm:px-0">
          {[
            { value: '',            label: 'Alle' },
            { value: 'Kunde',       label: 'Kunden' },
            { value: 'Lieferant',   label: 'Lieferanten' },
            { value: 'Interessent', label: 'Interessenten' },
          ].map(({ value, label }) => (
            <button
              key={value}
              onClick={() => { setTypFilter(value); setPage(1) }}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition border whitespace-nowrap shrink-0 ${
                typFilter === value
                  ? 'bg-primary-600 text-white border-primary-600'
                  : 'bg-white text-gray-600 border-gray-300 hover:border-primary-400 hover:text-primary-600'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Tabelle */}
      <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={28} className="animate-spin text-primary-400" />
          </div>
        ) : records.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Database size={40} className="mx-auto mb-3 text-gray-200" />
            <p className="font-medium">
              {search ? 'Keine Ergebnisse gefunden' : 'Noch keine Einträge vorhanden'}
            </p>
            {!search && (
              <button onClick={() => setModalRecord(null)}
                className="mt-3 text-primary-600 hover:underline text-sm">
                Ersten Eintrag anlegen
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {listFields.map(f => (
                    <th key={f.id} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      {f.name}
                    </th>
                  ))}
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">
                    Geändert
                  </th>
                  <th className="px-4 py-3 w-20"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {records.map(record => (
                  <RecordRow
                    key={record.id}
                    record={record}
                    fields={entityType.fields}
                    onEdit={(r) => setModalRecord(r)}
                    onDelete={handleDelete}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Paginierung */}
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

      {/* Modal */}
      {modalRecord !== undefined && (
        <RecordModal
          entityType={entityType}
          record={modalRecord}
          onClose={() => setModalRecord(undefined)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
