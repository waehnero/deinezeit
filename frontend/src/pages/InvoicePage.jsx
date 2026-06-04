import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoiceApi, masterdataApi } from '../services/api'
import toast from 'react-hot-toast'
import {
  Plus, Search, FileText, RefreshCw, Download, ChevronDown,
  CheckCircle2, Clock, AlertCircle, XCircle, Send, Eye,
  MoreHorizontal, Book, RotateCcw, Repeat
} from 'lucide-react'

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────
function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
function fmtEuro(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

const DOC_TYPES = [
  { key: '',           label: 'Alle' },
  { key: 'rechnung',   label: 'Rechnungen' },
  { key: 'angebot',    label: 'Angebote' },
  { key: 'gutschrift', label: 'Gutschriften' },
  { key: 'lieferschein', label: 'Lieferscheine' },
]

const STATUS_BADGE = {
  entwurf:    { label: 'Entwurf',    cls: 'bg-neutral-100 text-neutral-600' },
  gesendet:   { label: 'Gesendet',   cls: 'bg-blue-100 text-blue-700' },
  offen:      { label: 'Offen',      cls: 'bg-amber-100 text-amber-700' },
  bezahlt:    { label: 'Bezahlt',    cls: 'bg-green-100 text-green-700' },
  ueberfaellig:{ label: 'Überfällig', cls: 'bg-red-100 text-red-700' },
  storniert:  { label: 'Storniert',  cls: 'bg-neutral-200 text-neutral-500 line-through' },
  angenommen: { label: 'Angenommen', cls: 'bg-green-100 text-green-700' },
  abgelehnt:  { label: 'Abgelehnt', cls: 'bg-red-100 text-red-700' },
}

function StatusBadge({ status }) {
  const s = STATUS_BADGE[status] || { label: status, cls: 'bg-neutral-100 text-neutral-600' }
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.cls}`}>{s.label}</span>
}

function DocTypeBadge({ type }) {
  const map = {
    rechnung:     'RE',
    angebot:      'AN',
    gutschrift:   'GS',
    lieferschein: 'LS',
  }
  return (
    <span className="text-xs font-mono font-bold text-neutral-400">
      {map[type] || type}
    </span>
  )
}

export default function InvoicePage() {
  const navigate = useNavigate()
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [actionMenu, setActionMenu] = useState(null)   // invoice id
  const [cancelDialog, setCancelDialog] = useState(null)
  const [paidDialog, setPaidDialog] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (activeTab) params.doc_type = activeTab
      if (search) params.search = search
      if (statusFilter) params.status = statusFilter
      const res = await invoiceApi.list(params)
      setInvoices(res.data)
    } catch {
      toast.error('Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }, [activeTab, search, statusFilter])

  useEffect(() => { load() }, [load])

  // Suchverzögerung
  useEffect(() => {
    const t = setTimeout(() => load(), 400)
    return () => clearTimeout(t)
  }, [search]) // eslint-disable-line

  async function handleCancel(invoice, mode) {
    try {
      await invoiceApi.cancel(invoice.id, mode)
      toast.success(mode === 'with_credit' ? 'Storniert + Gutschrift erstellt' : 'Storniert')
      setCancelDialog(null)
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Stornieren')
    }
  }

  async function handleMarkPaid(invoice, paidAt) {
    try {
      await invoiceApi.markPaid(invoice.id, { paid_at: paidAt })
      toast.success('Als bezahlt markiert')
      setPaidDialog(null)
      load()
    } catch {
      toast.error('Fehler')
    }
  }

  async function handleConvert(invoice) {
    try {
      const res = await invoiceApi.convertToInvoice(invoice.id)
      toast.success(`Rechnung ${res.data.number} erstellt`)
      navigate(`/invoices/${res.data.id}`)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler')
    }
  }

  async function handleDelete(invoice) {
    if (!window.confirm(`${invoice.number} wirklich löschen?`)) return
    try {
      await invoiceApi.delete(invoice.id)
      toast.success('Gelöscht')
      load()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler')
    }
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900">Belege</h1>
          <p className="text-sm text-neutral-500 mt-0.5">Rechnungen · Angebote · Gutschriften · Lieferscheine</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/invoices/book')}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-neutral-600 border border-neutral-200 rounded-lg hover:bg-neutral-50"
          >
            <Book size={15} /> Belegbuch
          </button>
          <button
            onClick={() => navigate('/invoices/new')}
            className="flex items-center gap-1.5 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          >
            <Plus size={15} /> Neu erstellen
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-neutral-100 p-1 rounded-lg mb-4 w-fit">
        {DOC_TYPES.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            className={`px-3 py-1.5 text-sm rounded-md transition-all ${
              activeTab === t.key
                ? 'bg-white text-neutral-900 shadow-sm font-medium'
                : 'text-neutral-600 hover:text-neutral-800'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Filter-Zeile */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-sm">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Nummer, Titel, Referenz…"
            className="w-full pl-9 pr-3 py-2 text-sm border border-neutral-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-300"
          />
        </div>
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value)}
          className="text-sm border border-neutral-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-300"
        >
          <option value="">Alle Status</option>
          {Object.entries(STATUS_BADGE).map(([k, v]) => (
            <option key={k} value={k}>{v.label}</option>
          ))}
        </select>
        <button onClick={load} className="p-2 text-neutral-500 hover:text-neutral-800">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Tabelle */}
      <div className="bg-white border border-neutral-200 rounded-xl overflow-visible">
        {loading && invoices.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-neutral-400">
            <RefreshCw size={20} className="animate-spin mr-2" /> Laden…
          </div>
        ) : invoices.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-neutral-400">
            <FileText size={40} className="mb-3 opacity-30" />
            <p className="text-sm">Keine Dokumente gefunden</p>
            <button
              onClick={() => navigate('/invoices/new')}
              className="mt-3 text-sm text-primary-600 hover:underline"
            >
              Erstes Dokument erstellen
            </button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-100 bg-neutral-50">
                <th className="text-left px-4 py-3 font-medium text-neutral-500 w-8"></th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Nummer</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Datum</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Fällig</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Titel / Kontakt</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500">Betrag</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Status</th>
                <th className="px-4 py-3 w-10"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-50">
              {invoices.map(inv => (
                <tr
                  key={inv.id}
                  className="hover:bg-neutral-50 cursor-pointer"
                  onClick={() => navigate(`/invoices/${inv.id}`)}
                >
                  <td className="px-4 py-3">
                    <DocTypeBadge type={inv.doc_type} />
                  </td>
                  <td className="px-4 py-3 font-mono font-medium text-neutral-800">{inv.number}</td>
                  <td className="px-4 py-3 text-neutral-600">{fmtDate(inv.date)}</td>
                  <td className="px-4 py-3 text-neutral-600">
                    {inv.due_date ? (
                      <span className={new Date(inv.due_date) < new Date() && inv.status === 'offen' ? 'text-red-600 font-medium' : ''}>
                        {fmtDate(inv.due_date)}
                      </span>
                    ) : '—'}
                  </td>
                  <td className="px-4 py-3 text-neutral-700">{inv.title || '—'}</td>
                  <td className="px-4 py-3 text-right font-medium text-neutral-800">{fmtEuro(inv.total)}</td>
                  <td className="px-4 py-3"><StatusBadge status={inv.status} /></td>
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <div className="relative">
                      <button
                        onClick={() => setActionMenu(actionMenu === inv.id ? null : inv.id)}
                        className="p-1 rounded hover:bg-neutral-100 text-neutral-400 hover:text-neutral-700"
                      >
                        <MoreHorizontal size={16} />
                      </button>
                      {actionMenu === inv.id && (
                        <ActionMenu
                          invoice={inv}
                          onClose={() => setActionMenu(null)}
                          onCancel={() => { setActionMenu(null); setCancelDialog(inv) }}
                          onPaid={() => { setActionMenu(null); setPaidDialog(inv) }}
                          onConvert={() => { setActionMenu(null); handleConvert(inv) }}
                          onDelete={() => { setActionMenu(null); handleDelete(inv) }}
                          onEdit={() => navigate(`/invoices/${inv.id}/edit`)}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Stornodialog */}
      {cancelDialog && (
        <CancelDialog
          invoice={cancelDialog}
          onClose={() => setCancelDialog(null)}
          onConfirm={(mode) => handleCancel(cancelDialog, mode)}
        />
      )}

      {/* Bezahlt-Dialog */}
      {paidDialog && (
        <PaidDialog
          invoice={paidDialog}
          onClose={() => setPaidDialog(null)}
          onConfirm={(paidAt) => handleMarkPaid(paidDialog, paidAt)}
        />
      )}
    </div>
  )
}

// ── Aktionsmenü ────────────────────────────────────────────────────────────────
function ActionMenu({ invoice, onClose, onCancel, onPaid, onConvert, onDelete, onEdit }) {
  useEffect(() => {
    const h = () => onClose()
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [onClose])

  return (
    <div className="absolute right-0 top-7 bg-white border border-neutral-200 rounded-lg shadow-lg py-1 w-48" style={{zIndex: 9999}}>
      <button onClick={onEdit} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2">
        <Eye size={14} /> Öffnen / Bearbeiten
      </button>
      {invoice.doc_type === 'angebot' && invoice.status !== 'storniert' && (
        <button onClick={onConvert} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-blue-600">
          <RotateCcw size={14} /> → Rechnung umwandeln
        </button>
      )}
      {invoice.doc_type === 'rechnung' && invoice.status === 'offen' && (
        <button onClick={onPaid} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-green-600">
          <CheckCircle2 size={14} /> Als bezahlt markieren
        </button>
      )}
      {invoice.doc_type === 'rechnung' && invoice.status !== 'storniert' && (
        <button onClick={onCancel} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-red-500">
          <XCircle size={14} /> Stornieren
        </button>
      )}
      {['entwurf', 'storniert'].includes(invoice.status) && (
        <>
          <div className="border-t border-neutral-100 my-1" />
          <button onClick={onDelete} className="w-full text-left px-4 py-2 text-sm hover:bg-red-50 flex items-center gap-2 text-red-500">
            <XCircle size={14} /> Löschen
          </button>
        </>
      )}
    </div>
  )
}

// ── Storno-Dialog ─────────────────────────────────────────────────────────────
function CancelDialog({ invoice, onClose, onConfirm }) {
  const [mode, setMode] = useState('with_credit')
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
        <h2 className="text-base font-semibold mb-1">Rechnung stornieren</h2>
        <p className="text-sm text-neutral-500 mb-4">{invoice.number} — {Number(invoice.total).toLocaleString('de-AT', { minimumFractionDigits: 2 })} €</p>
        <div className="space-y-2 mb-6">
          <label className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-neutral-50">
            <input type="radio" name="mode" value="with_credit" checked={mode === 'with_credit'} onChange={() => setMode('with_credit')} className="mt-0.5" />
            <div>
              <p className="text-sm font-medium">Stornieren + Gutschrift erstellen</p>
              <p className="text-xs text-neutral-500">Buchhalterisch korrekt — automatische Gegenbuchung</p>
            </div>
          </label>
          <label className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-neutral-50">
            <input type="radio" name="mode" value="status_only" checked={mode === 'status_only'} onChange={() => setMode('status_only')} className="mt-0.5" />
            <div>
              <p className="text-sm font-medium">Nur Status ändern</p>
              <p className="text-xs text-neutral-500">Rechnung wird als storniert markiert, keine Gutschrift</p>
            </div>
          </label>
        </div>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
          <button onClick={() => onConfirm(mode)} className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700">Stornieren</button>
        </div>
      </div>
    </div>
  )
}

// ── Bezahlt-Dialog ────────────────────────────────────────────────────────────
function PaidDialog({ invoice, onClose, onConfirm }) {
  const [paidAt, setPaidAt] = useState(new Date().toISOString().slice(0, 10))
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm">
        <h2 className="text-base font-semibold mb-4">Als bezahlt markieren</h2>
        <label className="block text-sm font-medium text-neutral-700 mb-1">Zahlungsdatum</label>
        <input
          type="date"
          value={paidAt}
          onChange={e => setPaidAt(e.target.value)}
          className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm mb-4"
        />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
          <button onClick={() => onConfirm(paidAt)} className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700">Speichern</button>
        </div>
      </div>
    </div>
  )
}
