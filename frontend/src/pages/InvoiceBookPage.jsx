import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoiceApi, accountingApi } from '../services/api'
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

// Belegarten, die in der Buchhaltung ankommen (siehe accounting.py)
const BUCHUNGSRELEVANT = ['rechnung', 'gutschrift']

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
  const [uva, setUva] = useState(null)
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

    // Eigener Block: Scheitert die Umsatzsteuer-Auswertung, soll das Verkaufsbuch
    // trotzdem stehen — und der Fehler benennen, worum es ging, statt in einem
    // allgemeinen „Fehler beim Laden" unterzugehen.
    try {
      // Bewusst OHNE Belegart-Filter: Für die Voranmeldung zählen Rechnungen
      // und Gutschriften immer zusammen.
      const uvaRes = await invoiceApi.uva({ ...parsePeriod(period) })
      setUva(uvaRes.data)
    } catch (e) {
      setUva(null)
      toast.error(e.response?.data?.detail || 'Umsatzsteuer-Auswertung konnte nicht geladen werden')
    }
  }, [period, docType])

  // Beim Öffnen gleich laden — vorher blieb die Seite leer, bis jemand
  // „Anzeigen" drückte, und man hielt sie für kaputt.
  useEffect(() => { load() }, [load])

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
    <div className="">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/invoices')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-neutral-900">Verkaufsbuch</h1>
            <p className="text-sm text-neutral-500 mt-0.5">Übersicht aller Belege nach Zeitraum</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <div className="flex items-center gap-2">
              <button
                onClick={async () => {
                  try {
                    const params = { ...parsePeriod(period) }
                    if (docType) params.doc_type = docType
                    const res = await invoiceApi.bookPdf(params)
                    const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
                    const a = document.createElement('a'); a.href = url; a.download = `rechnungsbuch.pdf`; a.click()
                    URL.revokeObjectURL(url)
                  } catch { toast.error('PDF-Fehler') }
                }}
                className="flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50"
              >
                <Download size={14} /> PDF
              </button>
              <button
                onClick={downloadCsv}
                className="flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50"
              >
                <Download size={14} /> CSV
              </button>
              <button
                onClick={async () => {
                  try {
                    // Der Typfilter oben dient der Ansicht. Für die Buchhaltung
                    // zählen nur Rechnungen und Gutschriften — ist etwas anderes
                    // gewählt (z.B. Angebote), werden bewusst beide exportiert.
                    const params = { ...parsePeriod(period) }
                    if (BUCHUNGSRELEVANT.includes(docType)) params.doc_type = docType
                    const res = await accountingApi.exportBmd(params)
                    const url = URL.createObjectURL(new Blob([res.data], { type: 'text/csv' }))
                    const a = document.createElement('a'); a.href = url; a.download = `bmd_export.csv`; a.click()
                    URL.revokeObjectURL(url)
                  } catch (e) { toast.error(e.response?.data?.detail || 'BMD-Export-Fehler') }
                }}
                className="flex items-center gap-1.5 px-3 py-2 text-sm border border-primary-200 text-primary-700 rounded-lg hover:bg-primary-50"
                title="Rechnungen und Gutschriften als BMD-Buchungsjournal exportieren"
              >
                <Download size={14} /> BMD Export
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Filter */}
      <div className="bg-surface border border-neutral-200 rounded-xl p-4 mb-5 flex flex-wrap items-end gap-4">
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
              <div key={s.label} className={`rounded-xl p-4 border ${s.highlight ? 'bg-primary-50 border-primary-200' : 'bg-surface border-neutral-200'}`}>
                <p className="text-xs text-neutral-500 mb-1">{s.label}</p>
                <p className={`text-lg font-semibold ${s.highlight ? 'text-primary-700' : 'text-neutral-800'}`}>
                  {s.plain ? data.summary.count : s.value}
                </p>
              </div>
            ))}
          </div>

          {/* Umsatzsteuer-Auswertung für die Voranmeldung (Formular U30).
              Wird immer angezeigt, sobald geladen — ein leerer Zeitraum sagt
              das ausdrücklich, statt den Abschnitt wortlos wegzulassen. */}
          {uva && uva.zeilen.length === 0 && (
            <div className="bg-surface border border-neutral-200 rounded-xl p-5 mb-5">
              <h2 className="text-sm font-semibold text-neutral-700 mb-1">Umsatzsteuer-Auswertung</h2>
              <p className="text-xs text-neutral-500">
                Keine umsatzsteuerrelevanten Belege in diesem Zeitraum. Gezählt werden
                ausgestellte Rechnungen und Gutschriften — Entwürfe und Angebote nicht.
              </p>
            </div>
          )}
          {uva && uva.zeilen.length > 0 && (
            <div className="bg-surface border border-neutral-200 rounded-xl p-5 mb-5">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div>
                  <h2 className="text-sm font-semibold text-neutral-700 mb-1">Umsatzsteuer-Auswertung</h2>
                  <p className="text-xs text-neutral-500">
                    Aufbereitung für die Voranmeldung — Rechnungen und Gutschriften des
                    Zeitraums, unabhängig vom Belegart-Filter oben.
                  </p>
                </div>
                <button
                  onClick={async () => {
                    try {
                      const res = await invoiceApi.uvaPdf({ ...parsePeriod(period) })
                      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
                      const a = document.createElement('a'); a.href = url
                      a.download = 'umsatzsteuer.pdf'; a.click(); URL.revokeObjectURL(url)
                    } catch { toast.error('PDF-Fehler') }
                  }}
                  className="shrink-0 flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50">
                  <Download size={14} /> Ausdruck
                </button>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-neutral-500 border-b">
                    <th className="text-left py-2 font-medium">KZ</th>
                    <th className="text-left py-2 font-medium">Bezeichnung</th>
                    <th className="text-right py-2 font-medium">Bemessungsgrundlage</th>
                    <th className="text-right py-2 font-medium">Umsatzsteuer</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {uva.zeilen.map((z, i) => (
                    <tr key={i}>
                      <td className="py-2 font-mono text-neutral-700">
                        {z.kennzahl || <span className="text-amber-600" title="Kennzahl nicht zugeordnet">—</span>}
                      </td>
                      <td className="py-2 text-neutral-700">{z.bezeichnung}</td>
                      <td className="py-2 text-right text-neutral-800">{fmtEuro(z.bemessungsgrundlage)}</td>
                      <td className="py-2 text-right text-neutral-800">{fmtEuro(z.steuer)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 font-semibold">
                    <td className="py-2 font-mono text-neutral-700">000</td>
                    <td className="py-2 text-neutral-700">Gesamtbetrag der Bemessungsgrundlage</td>
                    <td className="py-2 text-right text-neutral-900">{fmtEuro(uva.kz_000)}</td>
                    <td className="py-2 text-right text-neutral-900">{fmtEuro(uva.steuer_gesamt)}</td>
                  </tr>
                </tfoot>
              </table>

              {uva.hinweise.length > 0 && (
                <div className="mt-4 bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-1">
                  {uva.hinweise.map((h, i) => (
                    <p key={i} className="text-xs text-amber-900">{h}</p>
                  ))}
                </div>
              )}
              <p className="text-xs text-neutral-400 mt-3">
                Aufbereitung, keine Steuerberatung — die Zuordnung von Sonderfällen
                gehört geprüft, bevor die Zahlen in die Voranmeldung gehen.
              </p>
            </div>
          )}

          {/* Tabelle */}
          <div className="bg-surface border border-neutral-200 rounded-xl overflow-hidden">
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
