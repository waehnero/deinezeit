import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { purchaseApi, masterdataApi } from '../services/api'
import toast from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import {
  FileInput, ArrowLeft, RefreshCw, Plus, Trash2, Paperclip, Search,
  Wallet, X as XIcon, AlertTriangle,
} from 'lucide-react'

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
function fmtEuro(n) {
  return Number(n || 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}
function heute() { return new Date().toISOString().slice(0, 10) }

const STEUERARTEN = [
  ['normal',         'Inland mit Vorsteuer'],
  ['reverse_charge', 'Reverse Charge (§ 19)'],
  ['ig_erwerb',      'Innergemeinschaftlicher Erwerb'],
  ['einfuhr',        'Einfuhr (Drittland)'],
  ['ohne_vorsteuer', 'Ohne Vorsteuerabzug'],
]

const STATUS_FARBEN = {
  offen:       'bg-amber-50 text-amber-700',
  teilbezahlt: 'bg-blue-50 text-blue-700',
  bezahlt:     'bg-green-50 text-green-700',
  storniert:   'bg-neutral-100 text-neutral-500',
}

/**
 * Eingangsrechnungen.
 *
 * Bewusst ohne Positionen: Eine Lieferantenrechnung wird nicht erzeugt,
 * sondern abgeschrieben. Erfasst wird, was gebucht und für die Voranmeldung
 * gebraucht wird — Kopfdaten und die Beträge je Steuersatz. Das Original hängt
 * als PDF dran.
 */
export default function EingangsrechnungenPage() {
  const navigate = useNavigate()
  const [liste, setListe] = useState([])
  const [laden, setLaden] = useState(true)
  const [suche, setSuche] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [formular, setFormular] = useState(null)     // null | {} = neu | Beleg = bearbeiten
  const [zahlung, setZahlung] = useState(null)

  const holen = useCallback(async () => {
    setLaden(true)
    try {
      const res = await purchaseApi.list({
        search: suche || undefined,
        status: statusFilter || undefined,
      })
      setListe(res.data)
    } catch { toast.error('Eingangsrechnungen konnten nicht geladen werden') }
    finally { setLaden(false) }
  }, [suche, statusFilter])

  useEffect(() => { holen() }, [holen])

  const offenGesamt = liste
    .filter(b => b.status !== 'storniert')
    .reduce((s, b) => s + Number(b.open_amount || 0), 0)
  const ohneBeleg = liste.filter(b => !b.has_file && b.status !== 'storniert').length

  async function stornieren(beleg) {
    if (!window.confirm(`${beleg.internal_number} wirklich stornieren? Der Beleg bleibt ` +
                        `erhalten, zählt aber in keiner Auswertung mehr mit.`)) return
    try {
      await purchaseApi.cancel(beleg.id)
      toast.success('Storniert')
      holen()
    } catch (e) { toast.error(e.response?.data?.detail || 'Storno nicht möglich') }
  }

  async function dateiWaehlen(beleg, datei) {
    if (!datei) return
    try {
      await purchaseApi.uploadFile(beleg.id, datei)
      toast.success('Original hinterlegt')
      holen()
    } catch (e) { toast.error(e.response?.data?.detail || 'Datei konnte nicht abgelegt werden') }
  }

  async function originalOeffnen(beleg) {
    try {
      const token = localStorage.getItem('access_token')
      const res = await fetch(purchaseApi.fileUrl(beleg.id),
                              { headers: { Authorization: 'Bearer ' + token } })
      if (!res.ok) throw new Error()
      window.open(URL.createObjectURL(await res.blob()), '_blank')
    } catch { toast.error('Das Original konnte nicht geöffnet werden') }
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/buchhaltung')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
          <ArrowLeft size={18} />
        </button>
        <PageHeader icon={FileInput} title="Eingangsrechnungen"
          subtitle="Lieferantenrechnungen erfassen — Grundlage für den Vorsteuerabzug">
          <button onClick={() => setFormular({})}
            className="flex items-center gap-1.5 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
            <Plus size={15} /> Erfassen
          </button>
        </PageHeader>
      </div>

      {ohneBeleg > 0 && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>
            {ohneBeleg} {ohneBeleg === 1 ? 'Rechnung hat' : 'Rechnungen haben'} kein
            hinterlegtes Original. Ohne Beleg ist der Vorsteuerabzug im Prüfungsfall
            gefährdet (§ 12 iVm § 11 UStG).
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative flex-1 max-w-xs">
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input value={suche} onChange={e => setSuche(e.target.value)}
            placeholder="Lieferant, Rechnungs-Nr., Betreff…"
            className="w-full border border-neutral-200 rounded-lg pl-9 pr-3 py-2 text-sm" />
        </div>
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
          className="border border-neutral-200 rounded-lg px-3 py-2 text-sm">
          <option value="">Alle Status</option>
          <option value="offen">Offen</option>
          <option value="teilbezahlt">Teilbezahlt</option>
          <option value="bezahlt">Bezahlt</option>
          <option value="storniert">Storniert</option>
        </select>
        <span className="text-sm text-neutral-500 ml-auto">
          Offen gesamt <strong className="text-neutral-900">{fmtEuro(offenGesamt)}</strong>
        </span>
      </div>

      {laden ? (
        <div className="flex justify-center py-16"><RefreshCw size={22} className="animate-spin text-neutral-400" /></div>
      ) : liste.length === 0 ? (
        <div className="bg-surface border border-neutral-200 rounded-xl py-16 text-center text-neutral-400">
          <FileInput size={28} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">Noch keine Eingangsrechnung erfasst.</p>
        </div>
      ) : (
        <div className="bg-surface border border-neutral-200 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Beleg</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Lieferant</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500 hidden md:table-cell">Datum</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500 hidden lg:table-cell">Fällig</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500 hidden lg:table-cell">Netto</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500">Brutto</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500">Offen</th>
                <th className="px-4 py-3 w-32"></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {liste.map(b => (
                <tr key={b.id} className="hover:bg-neutral-50">
                  <td className="px-4 py-3">
                    <button onClick={() => setFormular(b)}
                      className="font-medium text-neutral-800 hover:text-primary-600">
                      {b.internal_number}
                    </button>
                    <span className="block text-xs text-neutral-400">{b.supplier_number || '—'}</span>
                  </td>
                  <td className="px-4 py-3 text-neutral-700">
                    {b.supplier_name || '—'}
                    {b.title && <span className="block text-xs text-neutral-400">{b.title}</span>}
                  </td>
                  <td className="px-4 py-3 text-neutral-600 hidden md:table-cell whitespace-nowrap">{fmtDate(b.date)}</td>
                  <td className="px-4 py-3 text-neutral-600 hidden lg:table-cell whitespace-nowrap">{fmtDate(b.due_date)}</td>
                  <td className="px-4 py-3 text-right text-neutral-500 hidden lg:table-cell">{fmtEuro(b.net_total)}</td>
                  <td className="px-4 py-3 text-right font-medium text-neutral-800">{fmtEuro(b.gross_total)}</td>
                  <td className="px-4 py-3 text-right">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_FARBEN[b.status] || ''}`}>
                      {b.status === 'bezahlt' ? 'bezahlt' : fmtEuro(b.open_amount)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      {b.has_file ? (
                        <button onClick={() => originalOeffnen(b)} title="Original öffnen"
                          className="p-1 text-primary-600 hover:text-primary-700"><Paperclip size={14} /></button>
                      ) : (
                        <label title="Original hinterlegen"
                          className="p-1 text-neutral-300 hover:text-neutral-600 cursor-pointer">
                          <Paperclip size={14} />
                          <input type="file" className="hidden" accept=".pdf,image/*"
                            onChange={e => dateiWaehlen(b, e.target.files?.[0])} />
                        </label>
                      )}
                      {b.status !== 'storniert' && (
                        <>
                          <button onClick={() => setZahlung(b)} title="Zahlungen"
                            className="p-1 text-neutral-400 hover:text-neutral-700"><Wallet size={14} /></button>
                          <button onClick={() => stornieren(b)} title="Stornieren"
                            className="p-1 text-neutral-400 hover:text-red-500"><XIcon size={14} /></button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {formular && (
        <ErfassungsDialog beleg={formular} onClose={() => setFormular(null)}
          onSaved={() => { setFormular(null); holen() }} />
      )}
      {zahlung && (
        <ZahlungsDialog beleg={zahlung} onClose={() => setZahlung(null)}
          onChanged={holen} />
      )}
    </div>
  )
}


/** Erfassen und Bearbeiten. */
function ErfassungsDialog({ beleg, onClose, onSaved }) {
  const neu = !beleg.id
  const [lieferanten, setLieferanten] = useState([])
  const [f, setF] = useState({
    supplier_id: beleg.supplier_id || '',
    supplier_number: beleg.supplier_number || '',
    date: beleg.date || heute(),
    delivery_date: beleg.delivery_date || '',
    due_date: beleg.due_date || '',
    tax_kind: beleg.tax_kind || 'normal',
    vat_deductible: beleg.vat_deductible !== false,
    vat_note: beleg.vat_note || '',
    account_nr: beleg.account_nr || '',
    title: beleg.title || '',
    note: beleg.note || '',
  })
  const [zeilen, setZeilen] = useState(
    (beleg.taxes || []).length
      ? beleg.taxes.map(z => ({ tax_rate: z.tax_rate ?? '', net_amount: z.net_amount, tax_amount: z.tax_amount }))
      : [{ tax_rate: '20', net_amount: '', tax_amount: '' }]
  )
  const [speichert, setSpeichert] = useState(false)

  useEffect(() => {
    masterdataApi.listRecords('kontakte', { limit: 500 })
      .then(r => setLieferanten(r.data.items || r.data || []))
      .catch(() => {})
  }, [])

  const netto = zeilen.reduce((s, z) => s + (parseFloat(z.net_amount) || 0), 0)
  const steuer = zeilen.reduce((s, z) => s + (parseFloat(z.tax_amount) || 0), 0)
  // Bei Reverse Charge und innergemeinschaftlichem Erwerb steht auf der
  // Rechnung keine Steuer — der Zahlbetrag ist das Netto.
  const ohneSteuerImBetrag = ['reverse_charge', 'ig_erwerb'].includes(f.tax_kind)
  const brutto = ohneSteuerImBetrag ? netto : netto + steuer

  function zeileSetzen(i, feld, wert) {
    setZeilen(l => l.map((z, j) => j === i ? { ...z, [feld]: wert } : z))
  }

  async function speichern() {
    if (!zeilen.some(z => parseFloat(z.net_amount) || parseFloat(z.tax_amount))) {
      toast.error('Bitte mindestens einen Betrag erfassen'); return
    }
    setSpeichert(true)
    const daten = {
      ...f,
      supplier_id: f.supplier_id || null,
      delivery_date: f.delivery_date || null,
      due_date: f.due_date || null,
      account_nr: f.account_nr || null,
      taxes: zeilen
        .filter(z => parseFloat(z.net_amount) || parseFloat(z.tax_amount))
        .map(z => ({
          tax_rate: z.tax_rate === '' ? null : z.tax_rate,
          net_amount: z.net_amount || 0,
          tax_amount: z.tax_amount || 0,
        })),
    }
    try {
      if (neu) await purchaseApi.create(daten)
      else await purchaseApi.update(beleg.id, daten)
      toast.success(neu ? 'Erfasst' : 'Gespeichert')
      onSaved()
    } catch (e) { toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen') }
    finally { setSpeichert(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-xl shadow-xl p-6 w-full max-w-2xl">
        <h2 className="text-base font-semibold mb-4">
          {neu ? 'Eingangsrechnung erfassen' : `Eingangsrechnung ${beleg.internal_number}`}
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Lieferant</label>
            <select value={f.supplier_id} onChange={e => setF({ ...f, supplier_id: e.target.value })}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
              <option value="">— ohne Kontakt —</option>
              {lieferanten.map(l => (
                <option key={l.id} value={l.id}>{l.display_name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Rechnungs-Nr. des Lieferanten</label>
            <input value={f.supplier_number} onChange={e => setF({ ...f, supplier_number: e.target.value })}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Rechnungsdatum</label>
            <input type="date" value={f.date} onChange={e => setF({ ...f, date: e.target.value })}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
            <p className="text-xs text-neutral-400 mt-1">Bestimmt den Voranmeldungszeitraum</p>
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Leistungsdatum</label>
            <input type="date" value={f.delivery_date} onChange={e => setF({ ...f, delivery_date: e.target.value })}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Fällig am</label>
            <input type="date" value={f.due_date} onChange={e => setF({ ...f, due_date: e.target.value })}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Aufwandskonto</label>
            <input value={f.account_nr} onChange={e => setF({ ...f, account_nr: e.target.value })}
              placeholder="z.B. 7600"
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="md:col-span-2">
            <label className="block text-sm font-medium text-neutral-700 mb-1">Betreff</label>
            <input value={f.title} onChange={e => setF({ ...f, title: e.target.value })}
              placeholder="z.B. Büromaterial Juli"
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Steuerart</label>
            <select value={f.tax_kind} onChange={e => setF({ ...f, tax_kind: e.target.value })}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
              {STEUERARTEN.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Vorsteuerabzug</label>
            <label className="flex items-center gap-2 text-sm text-neutral-700 mt-2">
              <input type="checkbox" checked={f.vat_deductible}
                onChange={e => setF({ ...f, vat_deductible: e.target.checked })} />
              abziehbar (§ 12 UStG)
            </label>
          </div>
          {!f.vat_deductible && (
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-neutral-700 mb-1">Warum nicht abziehbar</label>
              <input value={f.vat_note} onChange={e => setF({ ...f, vat_note: e.target.value })}
                placeholder="z.B. PKW, § 12 Abs. 2 UStG"
                className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
            </div>
          )}
        </div>

        <h3 className="text-sm font-semibold text-neutral-700 mb-1">Beträge je Steuersatz</h3>
        <p className="text-xs text-neutral-500 mb-2">
          Der Steuerbetrag wird erfasst, nicht gerechnet — maßgeblich ist der Betrag auf
          der Rechnung des Lieferanten.
        </p>
        <div className="space-y-2 mb-3">
          <div className="hidden sm:grid grid-cols-12 gap-2 px-1 text-xs font-medium text-neutral-500">
            <span className="col-span-3">Satz %</span>
            <span className="col-span-4">Netto</span>
            <span className="col-span-4">Steuer</span>
          </div>
          {zeilen.map((z, i) => (
            <div key={i} className="grid grid-cols-12 gap-2 items-center">
              <input value={z.tax_rate} onChange={e => zeileSetzen(i, 'tax_rate', e.target.value)}
                placeholder="20" className="col-span-3 border border-neutral-200 rounded-lg px-2 py-1.5 text-sm text-right" />
              <input type="number" step="0.01" value={z.net_amount}
                onChange={e => zeileSetzen(i, 'net_amount', e.target.value)}
                className="col-span-4 border border-neutral-200 rounded-lg px-2 py-1.5 text-sm text-right" />
              <input type="number" step="0.01" value={z.tax_amount}
                onChange={e => zeileSetzen(i, 'tax_amount', e.target.value)}
                className="col-span-4 border border-neutral-200 rounded-lg px-2 py-1.5 text-sm text-right" />
              <button type="button" onClick={() => setZeilen(l => l.filter((_, j) => j !== i))}
                className="col-span-1 p-1 text-neutral-400 hover:text-red-500"><Trash2 size={14} /></button>
            </div>
          ))}
        </div>
        <button type="button"
          onClick={() => setZeilen(l => [...l, { tax_rate: '', net_amount: '', tax_amount: '' }])}
          className="flex items-center gap-1.5 text-sm text-primary-600 hover:underline mb-4">
          <Plus size={14} /> Steuersatz hinzufügen
        </button>

        <div className="flex justify-end gap-6 border-t pt-3 text-sm">
          <span className="text-neutral-500">Netto <strong className="text-neutral-800">{fmtEuro(netto)}</strong></span>
          <span className="text-neutral-500">Steuer <strong className="text-neutral-800">{fmtEuro(steuer)}</strong></span>
          <span className="text-neutral-500">
            Zahlbetrag <strong className="text-neutral-900">{fmtEuro(brutto)}</strong>
          </span>
        </div>
        {ohneSteuerImBetrag && (
          <p className="text-xs text-neutral-500 text-right mt-1">
            Bei dieser Steuerart schuldest du die Steuer dem Finanzamt, nicht dem Lieferanten —
            der Zahlbetrag ist deshalb das Netto.
          </p>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
          <button onClick={speichern} disabled={speichert}
            className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-60">
            {neu ? 'Erfassen' : 'Speichern'}
          </button>
        </div>
      </div>
    </div>
  )
}


/** Zahlungsausgänge zu einer Eingangsrechnung. */
function ZahlungsDialog({ beleg, onClose, onChanged }) {
  const [stand, setStand] = useState(null)
  const [datum, setDatum] = useState(heute())
  const [betrag, setBetrag] = useState('')
  const [zahlart, setZahlart] = useState('bank')
  const [laeuft, setLaeuft] = useState(false)

  const laden = useCallback(async () => {
    try {
      const res = await purchaseApi.listPayments(beleg.id)
      setStand(res.data)
      setBetrag(Number(res.data.open_amount).toFixed(2))
    } catch { toast.error('Zahlungen konnten nicht geladen werden') }
  }, [beleg.id])

  useEffect(() => { laden() }, [laden])

  async function erfassen() {
    if (!betrag || Number(betrag) === 0) { toast.error('Bitte einen Betrag angeben'); return }
    setLaeuft(true)
    try {
      const res = await purchaseApi.addPayment(beleg.id, {
        paid_at: datum, amount: betrag, method: zahlart,
      })
      setStand(res.data)
      setBetrag(Number(res.data.open_amount).toFixed(2))
      toast.success(res.data.status === 'bezahlt' ? 'Rechnung ist beglichen' : 'Zahlung erfasst')
      onChanged?.()
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler beim Erfassen') }
    finally { setLaeuft(false) }
  }

  async function zuruecknehmen(id) {
    if (!window.confirm('Diese Zahlung wirklich zurücknehmen?')) return
    try {
      const res = await purchaseApi.deletePayment(id)
      setStand(res.data)
      setBetrag(Number(res.data.open_amount).toFixed(2))
      onChanged?.()
    } catch { toast.error('Fehler') }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-xl shadow-xl p-6 w-full max-w-lg">
        <h2 className="text-base font-semibold mb-1">Zahlungen zu {beleg.internal_number}</h2>
        <p className="text-sm text-neutral-500 mb-4">{beleg.supplier_name}</p>

        {stand && (
          <div className="flex items-center gap-4 text-sm mb-4 pb-3 border-b">
            <span className="text-neutral-500">Gesamt <strong className="text-neutral-800">{fmtEuro(stand.gross_total)}</strong></span>
            <span className="text-neutral-500">Gezahlt <strong className="text-neutral-800">{fmtEuro(stand.paid_total)}</strong></span>
            <span className={Number(stand.open_amount) === 0 ? 'text-green-600' : 'text-amber-600'}>
              Offen <strong>{fmtEuro(stand.open_amount)}</strong>
            </span>
          </div>
        )}

        {stand?.payments?.length > 0 && (
          <div className="mb-4 divide-y border rounded-lg">
            {stand.payments.map(z => (
              <div key={z.id} className="flex items-center justify-between px-3 py-2 text-sm">
                <span>
                  <strong className="text-neutral-800">{fmtEuro(z.amount)}</strong>
                  <span className="text-neutral-400 ml-2">{fmtDate(z.paid_at)}</span>
                </span>
                <button onClick={() => zuruecknehmen(z.id)}
                  className="p-1 text-neutral-400 hover:text-red-500"><Trash2 size={13} /></button>
              </div>
            ))}
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Zahlungsdatum</label>
            <input type="date" value={datum} onChange={e => setDatum(e.target.value)}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-sm font-medium text-neutral-700 mb-1">Betrag</label>
            <input type="number" step="0.01" value={betrag} onChange={e => setBetrag(e.target.value)}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm text-right" />
          </div>
          <div className="col-span-2">
            <label className="block text-sm font-medium text-neutral-700 mb-1">Zahlungsart</label>
            <select value={zahlart} onChange={e => setZahlart(e.target.value)}
              className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
              <option value="bank">Überweisung</option>
              <option value="bar">Bar</option>
              <option value="karte">Karte</option>
              <option value="lastschrift">Lastschrift</option>
              <option value="verrechnung">Verrechnung</option>
              <option value="sonstige">Sonstige</option>
            </select>
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Schließen</button>
          <button onClick={erfassen} disabled={laeuft}
            className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-60">
            Zahlung erfassen
          </button>
        </div>
      </div>
    </div>
  )
}
