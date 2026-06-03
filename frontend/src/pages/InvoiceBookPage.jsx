import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoiceApi } from '../services/api'
import toast from 'react-hot-toast'
import { ArrowLeft, Download, RefreshCw, FileText, Mail, Filter } from 'lucide-react'

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
function fmtEuro(n) {
  return Number(n || 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

const THIS_YEAR = new Date().getFullYear()
const THIS_MONTH = new Date().getMonth() + 1

function periodOptions() {
  const opts = [{ value: '', label: 'Alle Zeiträume' }]
  // Jahres-Optionen
  for (let y = THIS_YEAR; y >= THIS_YEAR - 3; y--) {
    opts.push({ value: `year:${y}`, label: `Jahr ${y}` })
  }
  // Quartale aktuelles Jahr
  for (let q = 4; q >= 1; q--) {
    opts.push({ value: `quarter:${THIS_YEAR}-Q${q}`, label: `Q${q} ${THIS_YEAR}` })
  }
  // Monate aktuelles Jahr
  const monthNames = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
  for (let m = THIS_MONTH; m >= 1; m--) {
    opts.push({ value: `month:${THIS_YEAR}-${String(m).padStart(2, '0')}`, label: `${monthNames[m - 1]} ${THIS_YEAR}` })
  }
  return opts
}

function parsePeriod(val) {
  if (!val) return {}
  const [type, code] = val.split(':')
  if (type === 'year') {
    return { date_from: `${code}-01-01`, date_to: `${code}-12-31` }
  }
  if (type === 'quarter') {
    const [y, q] = code.split('-Q')
    const startMonth = (parseInt(q) - 1) * 3 + 1
    const endMonth = startMonth + 2
    const endDay = endMonth === 3 || endMonth === 12 ? 31 : endMonth === 6 ? 30 : 30
    return {
      date_from: `${y}-${String(startMonth).padStart(2, '0')}-01`,
      date_to: `${y}-${String(endMonth).padStart(2, '0')}-${endDay}`,
    }
  }
  if (type === 'month') {
    const [y, m] = code.split('-')
    const lastDay = new Date(parseInt(y), parseInt(m), 0).getDate()
    return { date_from: `${y}-${m}-01`, date_to: `${y}-${m}-${lastDay}` }
  }
  return {}
}

export default function InvoiceBookPage() {
  const navigate = useNavigate()
  const [period, setPeriod] = useState(`year:${THIS_YEAR}`)
  const [docType, setDocType] = useState('')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { ...parsePeriod(period) }
      if (docType) params.doc_type = docType
      const res = await invoiceApi.book(params)
      setData(res.data)
    } catch {
      toast.error('Fehler beim Laden')
    } finally {
      setLoading(false)
    }
  }, [period, docType])

  async function downloadCsv() {
    try {
      const params = { ...parsePeriod(period) }
      if (docType) params.doc_type = docType
      const res = await invoiceApi.bookCsv(params)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `rechnungsbuch_${period || 'alle'}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      toast.error('Fehler beim Export')
    }
  }

  const STATUS_COLORS = {
    entwurf: 'text-neutral-400',
    offen: 'text-amber-600',
    bezahlt: 'text-green-600',
    ueberfaellig: 'text-red-600',
    storniert: 'text-neutral-400 line-through',
    gesendet: 'text-blue-600',
    angenommen: 'text-green-600',
    abgelehnt: 'text-red-500',
  }

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/invoices')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-neutral-900">Rechnungsbuch</h1>
            <p className="text-sm text-neutral-500 mt-0.5">Übersicht aller Dokumente nach Zeitraum</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <button
              onClick={downloadCsv}
              className="flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50"
            >
              <Download size={14} /> CSV Export
            </button>
          )}
        </div>
      </div>

      {/* Filter */}
      <div className="bg-white border border-neutral-200 rounded-xl p-4 mb-5 flex flex-wrap items-end gap-4">
        <div>
          <label className="block text-xs font-medium text-neutral-500 mb-1">Zeitraum</label>
          <select
            value={period}
            onChange={e => setPeriod(e.target.value)}
            className="border border-neutral-200 rounded-lg px-3 py-2 text-sm"
          >
            {periodOptions().map(o => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-neutral-500 mb-1">Dokumenttyp</label>
          <select
            value={docType}
            onChange={e => setDocType(e.target.value)}
            className="border border-neutral-200 rounded-lg px-3 py-2 text-sm"
          >
            <option value="">Alle Typen</option>
            <option value="rechnung">Rechnungen</option>
            <option value="angebot">Angebote</option>
            <option value="gutschrift">Gutschriften</option>
            <option value="lieferschein">Lieferscheine</option>
          </select>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white rounded-lg text-sm hover:bg-primary-700"
        >
          {loading ? <RefreshCw size={14} className="animate-spin" /> : <Filter size={14} />}
          Anzeigen
        </button>
      </div>

      {/* Ergebnisse */}
      {data && (
        <>
          {/* Zusammenfassung */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
            {[
              { label: 'Dokumente', value: data.summary.count, plain: true },
              { label: 'Netto', value: fmtEuro(data.summary.total_net) },
              { label: 'MwSt.', value: fmtEuro(data.summary.total_tax) },
              { label: 'Brutto', value: fmtEuro(data.summary.total_gross), highlight: true },
            ].map(s => (
              <div key={s.label} className={`rounded-xl p-4 border ${s.highlight ? 'bg-primary-50 border-primary-200' : 'bg-white border-neutral-200'}`}>
                <p className="text-xs text-neutral-500 mb-1">{s.label}</p>
                <p className={`text-lg font-semibold ${s.highlight ? 'text-primary-700' : 'text-neutral-800'}`}>
                  {s.plain ? data.summary.count : s.value}
                </p>
              </div>
            ))}
          </div>

          {/* Tabelle */}
          <div className="bg-white border border-neutral-200 rounded-xl overflow-hidden">
            {data.invoices.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-neutral-400">
                <FileText size={36} className="mb-2 opacity-30" />
                <p className="text-sm">Keine Dokumente für diesen Zeitraum</p>
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-neutral-100 bg-neutral-50">
                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Nummer</th>
                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Datum</th>
                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Fällig</th>
                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Titel</th>
                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Netto</th>
                    <th className="text-right px-4 py-3 font-medium text-neutral-500">MwSt.</th>
                    <th className="text-right px-4 py-3 font-medium text-neutral-500">Brutto</th>
                    <th className="text-left px-4 py-3 font-medium text-neutral-500">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-neutral-50">
                  {data.invoices.map(inv => (
                    <tr
                      key={inv.id}
                      className="hover:bg-neutral-50 cursor-pointer"
                      onClick={() => navigate(`/invoices/${inv.id}`)}
                    >
                      <td className="px-4 py-2.5 font-mono font-medium text-neutral-800">{inv.number}</td>
                      <td className="px-4 py-2.5 text-neutral-600">{fmtDate(inv.date)}</td>
                      <td className="px-4 py-2.5 text-neutral-600">{fmtDate(inv.due_date)}</td>
                      <td className="px-4 py-2.5 text-neutral-700">{inv.title || '—'}</td>
                      <td className="px-4 py-2.5 text-right text-neutral-700">{fmtEuro(inv.subtotal)}</td>
                      <td className="px-4 py-2.5 text-right text-neutral-500">{fmtEuro(inv.tax_total)}</td>
                      <td className="px-4 py-2.5 text-right font-medium text-neutral-800">{fmtEuro(inv.total)}</td>
                      <td className="px-4 py-2.5">
                        <span className={`text-xs font-medium ${STATUS_COLORS[inv.status] || 'text-neutral-600'}`}>
                          {inv.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
                {/* Summenzeile */}
                <tfoot>
                  <tr className="border-t-2 border-neutral-200 bg-neutral-50 font-semibold">
                    <td colSpan={4} className="px-4 py-3 text-neutral-700">Gesamt ({data.summary.count})</td>
                    <td className="px-4 py-3 text-right text-neutral-800">{fmtEuro(data.summary.total_net)}</td>
                    <td className="px-4 py-3 text-right text-neutral-600">{fmtEuro(data.summary.total_tax)}</td>
                    <td className="px-4 py-3 text-right text-primary-700">{fmtEuro(data.summary.total_gross)}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            )}
          </div>
        </>
      )}

      {!data && !loading && (
        <div className="flex flex-col items-center justify-center py-20 text-neutral-400">
          <Filter size={36} className="mb-3 opacity-30" />
          <p className="text-sm">Zeitraum auswählen und auf „Anzeigen" klicken</p>
        </div>
      )}
    </div>
  )
}
