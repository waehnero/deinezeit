import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoiceApi } from '../services/api'
import toast from 'react-hot-toast'
import {
  Plus, Search, FileText, RefreshCw, Download,
  CheckCircle2, Clock, XCircle, Send, Eye,
  MoreHorizontal, Book, RotateCcw, Mail, MailCheck, MailX,
  Paperclip, X, HardDrive, Upload
} from 'lucide-react'
import { datacenterApi } from '../services/api'

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
function fmtEuro(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

const DOC_TYPES = [
  { key: '',                     label: 'Alle' },
  { key: 'rechnung',             label: 'Rechnungen' },
  { key: 'angebot',              label: 'Angebote' },
  { key: 'auftragsbestaetigung', label: 'Auftragsbestätigungen' },
  { key: 'gutschrift',           label: 'Gutschriften' },
  { key: 'lieferschein',         label: 'Lieferscheine' },
]

const STATUS_BADGE = {
  entwurf:      { label: 'Entwurf',    cls: 'bg-neutral-100 text-neutral-600' },
  gesendet:     { label: 'Gesendet',   cls: 'bg-blue-100 text-blue-700' },
  offen:        { label: 'Offen',      cls: 'bg-amber-100 text-amber-700' },
  bezahlt:      { label: 'Bezahlt',    cls: 'bg-green-100 text-green-700' },
  ueberfaellig: { label: 'Überfällig', cls: 'bg-red-100 text-red-700' },
  storniert:    { label: 'Storniert',  cls: 'bg-neutral-200 text-neutral-500 line-through' },
  angenommen:   { label: 'Angenommen', cls: 'bg-green-100 text-green-700' },
  abgelehnt:    { label: 'Abgelehnt',  cls: 'bg-red-100 text-red-700' },
}

function StatusBadge({ status }) {
  const s = STATUS_BADGE[status] || { label: status, cls: 'bg-neutral-100 text-neutral-600' }
  return <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.cls}`}>{s.label}</span>
}

function DocTypeBadge({ type }) {
  const map = { rechnung: 'RE', angebot: 'AN', auftragsbestaetigung: 'AB', gutschrift: 'GS', lieferschein: 'LS' }
  return <span className="text-xs font-mono font-bold text-neutral-400">{map[type] || type}</span>
}

export default function InvoicePage() {
  const navigate = useNavigate()
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState('')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [actionMenu, setActionMenu] = useState(null)
  const [cancelDialog, setCancelDialog] = useState(null)
  const [paidDialog, setPaidDialog] = useState(null)
  const [sendDialog, setSendDialog] = useState(null)
  const [selected, setSelected] = useState(new Set())
  const [sentStatus, setSentStatus] = useState({}) // id → 'ok' | 'error'

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (activeTab) params.doc_type = activeTab
      if (search) params.search = search
      if (statusFilter) params.status = statusFilter
      const res = await invoiceApi.list(params)
      setInvoices(res.data)
    } catch { toast.error('Fehler beim Laden') }
    finally { setLoading(false) }
  }, [activeTab, search, statusFilter])

  useEffect(() => { load() }, [load])
  useEffect(() => { const t = setTimeout(() => load(), 400); return () => clearTimeout(t) }, [search]) // eslint-disable-line

  async function handleCancel(invoice, mode) {
    try {
      await invoiceApi.cancel(invoice.id, mode)
      toast.success(mode === 'with_credit' ? 'Storniert + Gutschrift erstellt' : 'Storniert')
      setCancelDialog(null); load()
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler') }
  }

  async function handleMarkPaid(invoice, paidAt) {
    try {
      await invoiceApi.markPaid(invoice.id, { paid_at: paidAt })
      toast.success('Als bezahlt markiert'); setPaidDialog(null); load()
    } catch { toast.error('Fehler') }
  }

  async function handleSetStatus(invoice, status) {
    const labels = { offen: 'Als offen markiert', gesendet: 'Als gesendet markiert', angenommen: 'Als angenommen markiert', abgelehnt: 'Als abgelehnt markiert' }
    try {
      await invoiceApi.setStatus(invoice.id, status)
      toast.success(labels[status] || 'Status geändert'); load()
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler') }
  }

  async function handleConvertToAb(invoice) {
    try {
      const res = await invoiceApi.convertToAb(invoice.id)
      toast.success(`Auftragsbestätigung ${res.data.number} erstellt`)
      navigate(`/invoices/${res.data.id}`)
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler') }
  }

  async function handleConvertToInvoice(invoice) {
    try {
      const res = await invoiceApi.convertToInvoice(invoice.id)
      toast.success(`Rechnung ${res.data.number} erstellt`)
      navigate(`/invoices/${res.data.id}`)
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler') }
  }

  async function handleDelete(invoice) {
    if (!window.confirm(`${invoice.number} wirklich löschen?`)) return
    try {
      await invoiceApi.delete(invoice.id); toast.success('Gelöscht'); load()
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler') }
  }

  function toggleSelect(id) {
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  }
  function toggleAll() {
    setSelected(s => s.size === invoices.length ? new Set() : new Set(invoices.map(i => i.id)))
  }

  return (
    <div className="p-4 md:p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900">Belege</h1>
          <p className="text-sm text-neutral-500 mt-0.5">Rechnungen · Angebote · Auftragsbestätigungen · Gutschriften · Lieferscheine</p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <button onClick={() => setSendDialog({ invoices: invoices.filter(i => selected.has(i.id)), mode: 'bulk' })}
              className="flex items-center gap-1.5 px-3 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              <Mail size={15} /> {selected.size} Beleg{selected.size > 1 ? 'e' : ''} senden
            </button>
          )}
          <button onClick={() => navigate('/invoices/book')}
            className="flex items-center gap-1.5 px-3 py-2 text-sm text-neutral-600 border border-neutral-200 rounded-lg hover:bg-neutral-50">
            <Book size={15} /> Belegbuch
          </button>
          <button onClick={() => navigate('/invoices/new' + (activeTab ? '?type=' + activeTab : ''))}
            className="flex items-center gap-1.5 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
            <Plus size={15} /> Neu erstellen
          </button>
        </div>
      </div>

      <div className="flex gap-1 bg-neutral-100 p-1 rounded-lg mb-4 w-fit flex-wrap">
        {DOC_TYPES.map(t => (
          <button key={t.key} onClick={() => setActiveTab(t.key)}
            className={`px-3 py-1.5 text-sm rounded-md transition-all ${activeTab === t.key ? 'bg-white text-neutral-900 shadow-sm font-medium' : 'text-neutral-600 hover:text-neutral-800'}`}>
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-sm">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Nummer, Titel, Referenz…"
            className="w-full pl-9 pr-3 py-2 text-sm border border-neutral-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-300" />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="text-sm border border-neutral-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-300">
          <option value="">Alle Status</option>
          {Object.entries(STATUS_BADGE).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
        </select>
        <button onClick={load} className="p-2 text-neutral-500 hover:text-neutral-800">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      <div className="bg-white border border-neutral-200 rounded-xl overflow-visible">
        {loading && invoices.length === 0 ? (
          <div className="flex items-center justify-center py-16 text-neutral-400">
            <RefreshCw size={20} className="animate-spin mr-2" /> Laden…
          </div>
        ) : invoices.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-neutral-400">
            <FileText size={40} className="mb-3 opacity-30" />
            <p className="text-sm">Keine Dokumente gefunden</p>
            <button onClick={() => navigate('/invoices/new' + (activeTab ? '?type=' + activeTab : ''))} className="mt-3 text-sm text-primary-600 hover:underline">Erstes Dokument erstellen</button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-100 bg-neutral-50">
                <th className="px-3 py-3 w-10">
                  <input type="checkbox" checked={selected.size === invoices.length && invoices.length > 0}
                    onChange={toggleAll} className="w-4 h-4 rounded cursor-pointer" />
                </th>
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
                <tr key={inv.id}
                  className={`hover:bg-neutral-50 cursor-pointer ${selected.has(inv.id) ? 'bg-blue-50' : ''}`}
                  onClick={() => navigate(`/invoices/${inv.id}`)}>
                  <td className="px-3 py-3" onClick={e => { e.stopPropagation(); toggleSelect(inv.id) }}>
                    <input type="checkbox" checked={selected.has(inv.id)} onChange={() => toggleSelect(inv.id)} className="w-4 h-4 rounded cursor-pointer" />
                  </td>
                  <td className="px-4 py-3"><DocTypeBadge type={inv.doc_type} /></td>
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
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <StatusBadge status={inv.status} />
                      {sentStatus[inv.id] === 'ok' && (
                        <MailCheck size={15} className="text-green-500 shrink-0" title="Erfolgreich versendet" />
                      )}
                      {sentStatus[inv.id] === 'error' && (
                        <MailX size={15} className="text-orange-500 shrink-0" title="Versand fehlgeschlagen" />
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3" onClick={e => e.stopPropagation()}>
                    <div className="relative">
                      <button onClick={() => setActionMenu(actionMenu === inv.id ? null : inv.id)}
                        className="p-1 rounded hover:bg-neutral-100 text-neutral-400 hover:text-neutral-700">
                        <MoreHorizontal size={16} />
                      </button>
                      {actionMenu === inv.id && (
                        <ActionMenu invoice={inv}
                          onClose={() => setActionMenu(null)}
                          onSetStatus={s => { setActionMenu(null); handleSetStatus(inv, s) }}
                          onConvertToAb={() => { setActionMenu(null); handleConvertToAb(inv) }}
                          onConvertToInvoice={() => { setActionMenu(null); handleConvertToInvoice(inv) }}
                          onSend={() => { setActionMenu(null); setSendDialog({ invoices: [inv], mode: 'single' }) }}
                          onCancel={() => { setActionMenu(null); setCancelDialog(inv) }}
                          onPaid={() => { setActionMenu(null); setPaidDialog(inv) }}
                          onDelete={() => { setActionMenu(null); handleDelete(inv) }}
                          onEdit={() => navigate(`/invoices/${inv.id}/edit`)} />
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {sendDialog && (
        <SendDialog invoices={sendDialog.invoices} onClose={() => setSendDialog(null)}
          onSent={(ids, status, close = true) => {
            setSentStatus(prev => {
              const next = { ...prev }
              ids.forEach(id => { next[id] = status })
              return next
            })
            if (close) { setSendDialog(null); setSelected(new Set()); load() }
          }} />
      )}
      {cancelDialog && (
        <CancelDialog invoice={cancelDialog} onClose={() => setCancelDialog(null)}
          onConfirm={mode => handleCancel(cancelDialog, mode)} />
      )}
      {paidDialog && (
        <PaidDialog invoice={paidDialog} onClose={() => setPaidDialog(null)}
          onConfirm={paidAt => handleMarkPaid(paidDialog, paidAt)} />
      )}
    </div>
  )
}

function ActionMenu({ invoice, onClose, onSetStatus, onConvertToAb, onConvertToInvoice, onSend, onCancel, onPaid, onDelete, onEdit }) {
  useEffect(() => {
    const h = () => onClose()
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [onClose])

  const { status, doc_type } = invoice
  const isRe = doc_type === 'rechnung'
  const isAn = doc_type === 'angebot'
  const isAb = doc_type === 'auftragsbestaetigung'
  const isGs = doc_type === 'gutschrift'

  return (
    <div className="absolute right-0 top-7 bg-white border border-neutral-200 rounded-lg shadow-lg py-1 w-56" style={{zIndex: 9999}}>
      <button onClick={onEdit} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2">
        <Eye size={14} /> Öffnen / Bearbeiten
      </button>
      <div className="border-t border-neutral-100 my-1" />

      {status === 'entwurf' && !isAn && !isAb && (
        <button onClick={() => onSetStatus('offen')} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-amber-600">
          <Clock size={14} /> Als offen markieren
        </button>
      )}
      {status === 'entwurf' && (
        <button onClick={() => onSetStatus('gesendet')} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-blue-600">
          <Send size={14} /> Als gesendet markieren
        </button>
      )}
      {status === 'gesendet' && isRe && (
        <button onClick={() => onSetStatus('offen')} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-amber-600">
          <Clock size={14} /> Als offen markieren
        </button>
      )}
      {['offen', 'gesendet', 'ueberfaellig'].includes(status) && (isRe || isGs) && (
        <button onClick={onPaid} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-green-600">
          <CheckCircle2 size={14} /> Als bezahlt markieren
        </button>
      )}
      {isAn && status === 'gesendet' && (
        <>
          <button onClick={() => onSetStatus('angenommen')} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-green-600">
            <CheckCircle2 size={14} /> Als angenommen markieren
          </button>
          <button onClick={() => onSetStatus('abgelehnt')} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-red-500">
            <XCircle size={14} /> Als abgelehnt markieren
          </button>
        </>
      )}
      {isAn && ['entwurf', 'gesendet', 'angenommen'].includes(status) && (
        <button onClick={onConvertToAb} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-blue-600">
          <RotateCcw size={14} /> → Auftragsbestätigung
        </button>
      )}
      {(isAn || isAb) && ['entwurf', 'gesendet', 'angenommen', 'offen'].includes(status) && (
        <button onClick={onConvertToInvoice} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-primary-600">
          <RotateCcw size={14} /> → Rechnung umwandeln
        </button>
      )}

      {status !== 'storniert' && (
        <>
          <div className="border-t border-neutral-100 my-1" />
          <button onClick={onSend} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-blue-600">
            <Mail size={14} /> Per E-Mail senden
          </button>
        </>
      )}

      {isRe && !['storniert', 'bezahlt'].includes(status) && (
        <>
          <div className="border-t border-neutral-100 my-1" />
          <button onClick={onCancel} className="w-full text-left px-4 py-2 text-sm hover:bg-neutral-50 flex items-center gap-2 text-red-500">
            <XCircle size={14} /> Stornieren
          </button>
        </>
      )}
      {['entwurf', 'storniert'].includes(status) && (
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
            <div><p className="text-sm font-medium">Stornieren + Gutschrift erstellen</p><p className="text-xs text-neutral-500">Buchhalterisch korrekt — automatische Gegenbuchung</p></div>
          </label>
          <label className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-neutral-50">
            <input type="radio" name="mode" value="status_only" checked={mode === 'status_only'} onChange={() => setMode('status_only')} className="mt-0.5" />
            <div><p className="text-sm font-medium">Nur Status ändern</p><p className="text-xs text-neutral-500">Rechnung wird als storniert markiert, keine Gutschrift</p></div>
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

function PaidDialog({ invoice, onClose, onConfirm }) {
  const [paidAt, setPaidAt] = useState(new Date().toISOString().slice(0, 10))
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-sm">
        <h2 className="text-base font-semibold mb-4">Als bezahlt markieren</h2>
        <label className="block text-sm font-medium text-neutral-700 mb-1">Zahlungsdatum</label>
        <input type="date" value={paidAt} onChange={e => setPaidAt(e.target.value)}
          className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm mb-4" />
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
          <button onClick={() => onConfirm(paidAt)} className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700">Speichern</button>
        </div>
      </div>
    </div>
  )
}

// ── Datacenter-Browser (Anhang auswählen) ────────────────────────────────────
function DatacenterPicker({ onAdd, onClose }) {
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState(new Set())

  useEffect(() => {
    datacenterApi.listAll()
      .then(r => setFiles((r.data.attachments || []).filter(f => f.type === 'file')))
      .catch(() => toast.error('Datacenter konnte nicht geladen werden'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = files.filter(f =>
    (f.display_name || f.filename || '').toLowerCase().includes(search.toLowerCase())
  )

  function fmtSize(b) {
    if (!b) return ''
    if (b < 1024) return `${b} B`
    if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
    return `${(b / 1024 / 1024).toFixed(1)} MB`
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]">
      <div className="bg-white rounded-xl shadow-xl p-5 w-full max-w-md">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-neutral-900 flex items-center gap-2">
            <HardDrive size={15} className="text-primary-600" /> Aus Datacenter auswählen
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-neutral-100"><X size={16} /></button>
        </div>
        <input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Dateiname suchen…"
          className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm mb-3"
        />
        <div className="max-h-64 overflow-y-auto divide-y border border-neutral-100 rounded-lg">
          {loading && <div className="py-8 text-center text-neutral-400 text-sm">Lädt…</div>}
          {!loading && filtered.length === 0 && <div className="py-8 text-center text-neutral-400 text-sm">Keine Dateien gefunden</div>}
          {filtered.map(f => (
            <label key={f.id} className="flex items-center gap-3 px-3 py-2 hover:bg-neutral-50 cursor-pointer">
              <input type="checkbox"
                checked={selected.has(f.id)}
                onChange={() => setSelected(prev => {
                  const n = new Set(prev)
                  n.has(f.id) ? n.delete(f.id) : n.add(f.id)
                  return n
                })}
                className="w-4 h-4 rounded"
              />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-neutral-800 truncate">{f.display_name || f.filename}</p>
                <p className="text-xs text-neutral-400">{f.mimetype || ''} {fmtSize(f.filesize)}</p>
              </div>
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-3 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
          <button
            disabled={selected.size === 0}
            onClick={() => {
              const chosen = filtered.filter(f => selected.has(f.id))
              onAdd(chosen.map(f => ({ type: 'datacenter', id: f.id, name: f.display_name || f.filename || 'Anhang' })))
              onClose()
            }}
            className="px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {selected.size > 0 ? `${selected.size} hinzufügen` : 'Auswählen'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── SendDialog ────────────────────────────────────────────────────────────────
function SendDialog({ invoices, onClose, onSent }) {
  const [sending, setSending] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [attachments, setAttachments] = useState([])   // {type, id|file, name, mime_type?}
  const [showDcPicker, setShowDcPicker] = useState(false)
  const isBulk = invoices.length > 1
  const single = invoices[0]

  function removeAttachment(idx) {
    setAttachments(a => a.filter((_, i) => i !== idx))
  }

  async function fileToB64(file) {
    return new Promise((res, rej) => {
      const r = new FileReader()
      r.onload = () => res(r.result.split(',')[1])
      r.onerror = rej
      r.readAsDataURL(file)
    })
  }

  async function buildExtraAttachments() {
    const out = []
    for (const att of attachments) {
      if (att.type === 'datacenter') {
        out.push({ type: 'datacenter', id: att.id })
      } else if (att.type === 'local') {
        const data_b64 = await fileToB64(att.file)
        out.push({ type: 'local', filename: att.name, mime_type: att.mime_type, data_b64 })
      }
    }
    return out
  }

  async function handleSend() {
    setSending(true)
    setError(null)
    try {
      const extra = await buildExtraAttachments()
      if (isBulk) {
        const res = await invoiceApi.bulkSendEmail(invoices.map(i => i.id))
        setResults(res.data.results)
        const ok = res.data.results.filter(r => r.ok).length
        toast.success(`${ok} von ${invoices.length} Belegen versendet`)
      } else {
        await invoiceApi.sendEmail(single.id, null, extra)
        toast.success(`${single.number} versendet`)
        onSent([single.id], 'ok', true)
        return
      }
    } catch (e) {
      const msg = e.response?.data?.detail || 'Fehler beim Versenden'
      setError(msg)
      onSent(invoices.map(i => i.id), 'error', false)
    }
    finally { setSending(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
        <h2 className="text-base font-semibold mb-1 flex items-center gap-2">
          <Mail size={16} className="text-blue-600" />
          {isBulk ? `${invoices.length} Belege per E-Mail senden` : `${single.number} per E-Mail senden`}
        </h2>
        <p className="text-xs text-neutral-500 mb-4">
          PDF wird generiert und an die E-Mail-Adresse des Kontakts gesendet. Status wird auf „Gesendet" gesetzt.
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 whitespace-pre-wrap">
            <strong>Fehler:</strong> {error}
          </div>
        )}

        {!results ? (
          <>
            {/* Belegliste */}
            <div className="bg-neutral-50 rounded-lg p-3 mb-3 max-h-32 overflow-y-auto divide-y">
              {invoices.map(inv => (
                <div key={inv.id} className="py-2 flex items-center justify-between text-sm">
                  <span className="font-medium text-neutral-700">{inv.number}</span>
                  <span className="text-neutral-500 text-xs truncate max-w-[200px]">{inv.title || '—'}</span>
                </div>
              ))}
            </div>

            {/* Anhänge */}
            {attachments.length > 0 && (
              <div className="mb-3 space-y-1">
                {attachments.map((att, i) => (
                  <div key={i} className="flex items-center gap-2 bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-1.5 text-sm">
                    <Paperclip size={13} className="text-neutral-400 shrink-0" />
                    <span className="flex-1 truncate text-neutral-700">{att.name}</span>
                    <span className="text-xs text-neutral-400 shrink-0">
                      {att.type === 'datacenter' ? 'Datacenter' : 'Lokal'}
                    </span>
                    <button onClick={() => removeAttachment(i)} className="p-0.5 rounded hover:bg-neutral-200 text-neutral-400 hover:text-neutral-600">
                      <X size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Aktionsleiste */}
            <div className="flex items-center justify-between gap-2 mt-1">
              {/* Anhang hinzufügen */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowDcPicker(true)}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50 text-neutral-600"
                >
                  <Paperclip size={14} />
                  Anhang hinzufügen
                </button>
                {/* Versteckter File-Input für lokalen Upload */}
                <label className="flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50 text-neutral-600 cursor-pointer" title="Lokale Datei hochladen">
                  <Upload size={14} />
                  <span className="sr-only">Lokale Datei</span>
                  <input type="file" multiple className="hidden"
                    onChange={e => {
                      const newAtts = Array.from(e.target.files).map(f => ({
                        type: 'local', file: f, name: f.name, mime_type: f.type || 'application/octet-stream'
                      }))
                      setAttachments(a => [...a, ...newAtts])
                      e.target.value = ''
                    }}
                  />
                  Lokale Datei
                </label>
              </div>

              {/* Senden / Abbrechen */}
              <div className="flex items-center gap-2">
                <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
                <button onClick={handleSend} disabled={sending}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60">
                  {sending ? <RefreshCw size={14} className="animate-spin" /> : <Mail size={14} />}
                  {sending ? 'Wird gesendet…' : 'Jetzt senden'}
                </button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="space-y-2 mb-4 max-h-48 overflow-y-auto">
              {results.map(r => (
                <div key={r.id} className={`flex items-center gap-2 text-sm p-2 rounded ${r.ok ? 'bg-green-50' : 'bg-red-50'}`}>
                  {r.ok ? <CheckCircle2 size={14} className="text-green-600 shrink-0" /> : <XCircle size={14} className="text-red-500 shrink-0" />}
                  <span className="font-medium">{r.number}</span>
                  {r.ok ? <span className="text-neutral-500 text-xs">→ {r.to}</span> : <span className="text-red-500 text-xs">{r.error}</span>}
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <button onClick={() => {
                const okIds = results.filter(r => r.ok).map(r => r.id)
                const errIds = results.filter(r => !r.ok).map(r => r.id)
                if (okIds.length) onSent(okIds, 'ok', false)
                if (errIds.length) onSent(errIds, 'error', false)
                onSent([], 'ok', true)
              }} className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">Schließen</button>
            </div>
          </>
        )}
      </div>

      {showDcPicker && (
        <DatacenterPicker
          onAdd={items => setAttachments(a => [...a, ...items])}
          onClose={() => setShowDcPicker(false)}
        />
      )}
    </div>
  )
}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-neutral-800 truncate">{f.display_name || f.filename}</p>
                <p className="text-xs text-neutral-400">{f.mimetype || ''} {fmtSize(f.filesize)}</p>
              </div>
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-2 mt-4">
          <button onClick={onClose} className="px-3 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
          <button
            disabled={selected.size === 0}
            onClick={() => {
              const chosen = filtered.filter(f => selected.has(f.id))
              onAdd(chosen.map(f => ({ type: 'datacenter', id: f.id, name: f.display_name || f.filename || 'Anhang' })))
              onClose()
            }}
            className="px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
          >
            {selected.size > 0 ? `${selected.size} hinzufügen` : 'Auswählen'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── SendDialog ────────────────────────────────────────────────────────────────
function SendDialog({ invoices, onClose, onSent }) {
  const [sending, setSending] = useState(false)
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [attachments, setAttachments] = useState([])
  const [showDcPicker, setShowDcPicker] = useState(false)
  const isBulk = invoices.length > 1
  const single = invoices[0]

  function removeAttachment(idx) {
    setAttachments(a => a.filter((_, i) => i !== idx))
  }

  async function fileToB64(file) {
    return new Promise((res, rej) => {
      const r = new FileReader()
      r.onload = () => res(r.result.split(',')[1])
      r.onerror = rej
      r.readAsDataURL(file)
    })
  }

  async function buildExtraAttachments() {
    const out = []
    for (const att of attachments) {
      if (att.type === 'datacenter') {
        out.push({ type: 'datacenter', id: att.id })
      } else if (att.type === 'local') {
        const data_b64 = await fileToB64(att.file)
        out.push({ type: 'local', filename: att.name, mime_type: att.mime_type, data_b64 })
      }
    }
    return out
  }

  async function handleSend() {
    setSending(true)
    setError(null)
    try {
      const extra = await buildExtraAttachments()
      if (isBulk) {
        const res = await invoiceApi.bulkSendEmail(invoices.map(i => i.id))
        setResults(res.data.results)
        const ok = res.data.results.filter(r => r.ok).length
        toast.success(`${ok} von ${invoices.length} Belegen versendet`)
      } else {
        await invoiceApi.sendEmail(single.id, null, extra)
        toast.success(`${single.number} versendet`)
        onSent([single.id], 'ok', true)
        return
      }
    } catch (e) {
      const msg = e.response?.data?.detail || 'Fehler beim Versenden'
      setError(msg)
      onSent(invoices.map(i => i.id), 'error', false)
    }
    finally { setSending(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
        <h2 className="text-base font-semibold mb-1 flex items-center gap-2">
          <Mail size={16} className="text-blue-600" />
          {isBulk ? `${invoices.length} Belege per E-Mail senden` : `${single.number} per E-Mail senden`}
        </h2>
        <p className="text-xs text-neutral-500 mb-4">
          PDF wird generiert und an die E-Mail-Adresse des Kontakts gesendet. Status wird auf Gesendet gesetzt.
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 whitespace-pre-wrap">
            <strong>Fehler:</strong> {error}
          </div>
        )}

        {!results ? (
          <>
            <div className="bg-neutral-50 rounded-lg p-3 mb-3 max-h-32 overflow-y-auto divide-y">
              {invoices.map(inv => (
                <div key={inv.id} className="py-2 flex items-center justify-between text-sm">
                  <span className="font-medium text-neutral-700">{inv.number}</span>
                  <span className="text-neutral-500 text-xs truncate max-w-[200px]">{inv.title || '—'}</span>
                </div>
              ))}
            </div>

            {attachments.length > 0 && (
              <div className="mb-3 space-y-1">
                {attachments.map((att, i) => (
                  <div key={i} className="flex items-center gap-2 bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-1.5 text-sm">
                    <Paperclip size={13} className="text-neutral-400 shrink-0" />
                    <span className="flex-1 truncate text-neutral-700">{att.name}</span>
                    <span className="text-xs text-neutral-400 shrink-0">
                      {att.type === 'datacenter' ? 'Datacenter' : 'Lokal'}
                    </span>
                    <button onClick={() => removeAttachment(i)} className="p-0.5 rounded hover:bg-neutral-200 text-neutral-400 hover:text-neutral-600">
                      <X size={13} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center justify-between gap-2 mt-1">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowDcPicker(true)}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50 text-neutral-600"
                >
                  <Paperclip size={14} /> Anhang hinzufügen
                </button>
                <label className="flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50 text-neutral-600 cursor-pointer">
                  <Upload size={14} /> Lokale Datei
                  <input type="file" multiple className="hidden"
                    onChange={e => {
                      const newAtts = Array.from(e.target.files).map(f => ({
                        type: 'local', file: f, name: f.name, mime_type: f.type || 'application/octet-stream'
                      }))
                      setAttachments(a => [...a, ...newAtts])
                      e.target.value = ''
                    }}
                  />
                </label>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
                <button onClick={handleSend} disabled={sending}
                  className="flex items-center gap-2 px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-60">
                  {sending ? <RefreshCw size={14} className="animate-spin" /> : <Mail size={14} />}
                  {sending ? 'Wird gesendet…' : 'Jetzt senden'}
                </button>
              </div>
            </div>
          </>
        ) : (
          <>
            <div className="space-y-2 mb-4 max-h-48 overflow-y-auto">
              {results.map(r => (
                <div key={r.id} className={`flex items-center gap-2 text-sm p-2 rounded ${r.ok ? 'bg-green-50' : 'bg-red-50'}`}>
                  {r.ok ? <CheckCircle2 size={14} className="text-green-600 shrink-0" /> : <XCircle size={14} className="text-red-500 shrink-0" />}
                  <span className="font-medium">{r.number}</span>
                  {r.ok ? <span className="text-neutral-500 text-xs">{r.to}</span> : <span className="text-red-500 text-xs">{r.error}</span>}
                </div>
              ))}
            </div>
            <div className="flex justify-end">
              <button onClick={() => {
                const okIds = results.filter(r => r.ok).map(r => r.id)
                const errIds = results.filter(r => !r.ok).map(r => r.id)
                if (okIds.length) onSent(okIds, 'ok', false)
                if (errIds.length) onSent(errIds, 'error', false)
                onSent([], 'ok', true)
              }} className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">Schließen</button>
            </div>
          </>
        )}
      </div>

      {showDcPicker && (
        <DatacenterPicker
          onAdd={items => setAttachments(a => [...a, ...items])}
          onClose={() => setShowDcPicker(false)}
        />
      )}
    </div>
  )
}
                onSent([], 'ok', true)
              }} className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">Schließen</button>
            </div>
          </>
        )}
      </div>

      {showDcPicker && (
        <DatacenterPicker
          onAdd={items => setAttachments(a => [...a, ...items])}
          onClose={() => setShowDcPicker(false)}
        />
      )}
    </div>
  )
}
