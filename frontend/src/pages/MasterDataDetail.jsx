import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { masterdataApi, zeiterfassungApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import GridFieldBuilder from '../components/GridFieldBuilder'
import RecordModal from '../components/RecordModal'
import { fmtBudgetMinutes } from '../components/StundenkontenPanel'
import {
  Plus, Search, ArrowLeft, Trash2, Pencil,
  Loader2, Database, ChevronLeft, ChevronRight,
  AlertTriangle, Archive, ArchiveRestore
} from 'lucide-react'
import { CsvExportButton, CsvImportButton } from '../components/CsvImportExport'
import PageHeader from '../components/PageHeader'
import ResponsiveTable from '../components/ResponsiveTable'
import Fab from '../components/Fab'
import { ICONS } from './MasterDataOverview'

// ── Rest-Budget-Zelle (nur Projektzeiten) ─────────────────────────────────────
function BudgetCell({ budget }) {
  if (!budget || !budget.has_budget) return <span className="text-gray-300">—</span>
  if (budget.exhausted) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-600 border border-red-200"
        title="Budget verbraucht – dem Kunden ein neues Stundenkonto anbieten">
        <AlertTriangle size={11} />
        {fmtBudgetMinutes(budget.remaining_minutes)} h
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
      {fmtBudgetMinutes(budget.remaining_minutes)} h
    </span>
  )
}

// ── Datensatz-Zeile in der Tabelle ────────────────────────────────────────────
// Feldwert für Listen-/Kartenansicht formatieren (je nach Feldtyp)
function formatFieldValue(field, value) {
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

// Aktions-Knöpfe je Datensatz (Bearbeiten/Archivieren/Löschen) — von
// ResponsiveTable rechts in der Tabellenzeile bzw. auf der Karte gerendert
function RecordActions({ record, onEdit, onDelete, onArchive, onRestore,
                         isAdmin = false, archivedView = false }) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmArchive, setConfirmArchive] = useState(false)
  return (
    <>
      <button onClick={() => onEdit(record)}
        className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
        <Pencil size={14} />
      </button>
      {isAdmin && archivedView && (
        <button
          onClick={() => onRestore(record)}
          className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition"
          title="Wiederherstellen">
          <ArchiveRestore size={14} />
        </button>
      )}
      {isAdmin && !archivedView && (
        <button
          onClick={() => { if (confirmArchive) { onArchive(record); setConfirmArchive(false) } else setConfirmArchive(true) }}
          onBlur={() => setTimeout(() => setConfirmArchive(false), 200)}
          className={`p-1.5 rounded-lg transition ${
            confirmArchive ? 'bg-amber-100 text-amber-600' : 'text-gray-400 hover:text-amber-600 hover:bg-amber-50'
          }`}
          title={confirmArchive ? 'Nochmal klicken um zu archivieren' : 'Archivieren (aus Listen ausblenden, wiederherstellbar)'}>
          <Archive size={14} />
        </button>
      )}
      {isAdmin && (
        <button
          onClick={() => { if (confirmDelete) onDelete(record); else setConfirmDelete(true) }}
          onBlur={() => setTimeout(() => setConfirmDelete(false), 200)}
          className={`p-1.5 rounded-lg transition ${
            confirmDelete ? 'bg-red-100 text-red-600' : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
          }`}
          title={confirmDelete ? 'Nochmal klicken um endgültig zu löschen' : 'Endgültig löschen (nur ohne Verknüpfungen möglich)'}>
          <Trash2 size={14} />
        </button>
      )}
    </>
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
  const [budgets, setBudgets] = useState({}) // nur bei slug === 'projektzeiten': { [recordId]: ProjectBudget }
  const [showArchived, setShowArchived] = useState(false) // Archiv-Ansicht (nur Admin relevant)

  const isProjektzeiten = slug === 'projektzeiten'

  // Rest-Budgets für die sichtbaren Projektzeiten laden
  const loadBudgets = useCallback(async (items) => {
    if (!isProjektzeiten || !items?.length) return
    try {
      const res = await zeiterfassungApi.getBudgets(items.map(r => r.id))
      setBudgets(Object.fromEntries(res.data.map(b => [b.project_id, b])))
    } catch { /* Budgets sind Zusatzinfo – Fehler nicht blockierend */ }
  }, [isProjektzeiten])

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
        archived: showArchived ? 'only' : 'active',
        ...(typFilter ? { filter_field: 'typ', filter_value: typFilter } : {}),
      })
      setRecords(res.data.items)
      setTotal(res.data.total)
      loadBudgets(res.data.items)
    } catch {
      toast.error('Datensätze konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }, [slug, entityType, search, page, typFilter, showArchived])

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
    // Budgets können sich durch Stundenkonto-Änderungen im Modal geändert haben
    if (isProjektzeiten) loadBudgets(modalRecord ? records : [saved, ...records])
  }

  const handleDelete = async (record) => {
    try {
      await masterdataApi.deleteRecord(slug, record.id)
      setRecords(records.filter(r => r.id !== record.id))
      setTotal(total - 1)
      toast.success('Datensatz endgültig gelöscht')
    } catch (err) {
      // 409 = Datensatz wird noch verwendet → Meldung mit Details vom Backend
      const detail = err?.response?.data?.detail
      const msg = typeof detail === 'object' ? detail?.message : detail
      toast.error(msg || 'Löschen fehlgeschlagen', { duration: 8000 })
    }
  }

  const handleArchive = async (record) => {
    try {
      await masterdataApi.archiveRecord(slug, record.id)
      setRecords(records.filter(r => r.id !== record.id))
      setTotal(total - 1)
      toast.success('Datensatz archiviert — über die Archiv-Ansicht wiederherstellbar')
    } catch (err) {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Archivieren fehlgeschlagen')
    }
  }

  const handleRestore = async (record) => {
    try {
      await masterdataApi.restoreRecord(slug, record.id)
      setRecords(records.filter(r => r.id !== record.id))
      setTotal(total - 1)
      toast.success('Datensatz wiederhergestellt')
    } catch (err) {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Wiederherstellen fehlgeschlagen')
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
    <div>
      <PageHeader
        icon={ICONS[entityType.icon] || Database}
        title={entityType.name}
        subtitle={`${total} ${total === 1 ? 'Eintrag' : 'Einträge'}${showArchived ? ' · Archiv' : ''}`}
      >
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <button onClick={() => navigate('/masterdata')}
            className="flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium border bg-surface text-gray-600 border-gray-300 hover:bg-neutral-50 transition">
            <ArrowLeft size={16} /> Zurück
          </button>
          {isAdmin && (
            <button
              onClick={() => { setShowArchived(v => !v); setPage(1) }}
              className={`flex items-center justify-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium border transition ${
                showArchived
                  ? 'bg-amber-50 text-amber-700 border-amber-300'
                  : 'bg-surface text-gray-600 border-gray-300 hover:border-amber-400 hover:text-amber-600'
              }`}
              title="Archivierte Datensätze anzeigen/ausblenden">
              <Archive size={16} />
              {showArchived ? 'Zurück zu Aktiv' : 'Archiv'}
            </button>
          )}
          <div className="flex items-center gap-2">
            <CsvExportButton slug={entityType.slug} entityName={entityType.name} />
            <CsvImportButton
              slug={entityType.slug}
              entityType={entityType}
              onImported={() => loadRecords()}
            />
          </div>
          {!showArchived && (
            <button
              onClick={() => setModalRecord(null)}
              className="hidden sm:flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-4 py-2.5 rounded-xl font-medium transition"
            >
              <Plus size={18} />
              Neu anlegen
            </button>
          )}
          {!showArchived && <Fab onClick={() => setModalRecord(null)} title="Neu anlegen" />}
        </div>
      </PageHeader>

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
          className="w-full pl-9 pr-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface"
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
                  : 'bg-surface text-gray-600 border-gray-300 hover:border-primary-400 hover:text-primary-600'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Tabelle */}
      <div className="bg-surface rounded-2xl border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <Loader2 size={28} className="animate-spin text-primary-400" />
          </div>
        ) : records.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Database size={40} className="mx-auto mb-3 text-gray-200" />
            <p className="font-medium">
              {search ? 'Keine Ergebnisse gefunden'
                : showArchived ? 'Keine archivierten Einträge'
                : 'Noch keine Einträge vorhanden'}
            </p>
            {!search && !showArchived && (
              <button onClick={() => setModalRecord(null)}
                className="mt-3 text-primary-600 hover:underline text-sm">
                Ersten Eintrag anlegen
              </button>
            )}
          </div>
        ) : (
          <ResponsiveTable
            columns={[
              ...listFields.map(f => ({
                key: f.key, label: f.name,
                render: r => formatFieldValue(f, r.data[f.key]),
              })),
              ...(isProjektzeiten ? [{
                key: '_budget', label: 'Stundenkonto',
                render: r => <BudgetCell budget={budgets[r.id]} />,
              }] : []),
              {
                key: 'updated_at', label: 'Geändert', muted: true,
                render: r => new Date(r.updated_at).toLocaleDateString('de-AT'),
              },
            ]}
            rows={records}
            onRowClick={r => setModalRecord(r)}
            actions={r => (
              <RecordActions record={r} onEdit={x => setModalRecord(x)}
                onDelete={handleDelete} onArchive={handleArchive} onRestore={handleRestore}
                isAdmin={isAdmin} archivedView={showArchived} />
            )}
          />
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
          onClose={() => {
            setModalRecord(undefined)
            // Stundenkonten könnten im Modal geändert worden sein → Restwerte aktualisieren
            if (isProjektzeiten) loadBudgets(records)
          }}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
