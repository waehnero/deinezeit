import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoiceApi } from '../services/api'
import toast from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { Bell, RefreshCw, ArrowLeft, Lock, FileText, AlertTriangle } from 'lucide-react'

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
function fmtEuro(n) {
  return Number(n || 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

/**
 * Mahnlauf.
 *
 * Zeigt bewusst auch die NICHT mahnbaren Belege mit Begründung — sonst sucht
 * man vergeblich nach einer Rechnung, die man erwartet hätte. Auswählbar sind
 * nur die mahnbaren; verschickt wird erst auf Klick.
 */
export default function MahnlaufPage() {
  const navigate = useNavigate()
  const [daten, setDaten] = useState(null)
  const [laden, setLaden] = useState(true)
  const [auswahl, setAuswahl] = useState([])
  const [laeuft, setLaeuft] = useState(false)
  const [nurMahnbare, setNurMahnbare] = useState(true)

  const holen = useCallback(async () => {
    setLaden(true)
    try {
      const res = await invoiceApi.dunningRun({})
      setDaten(res.data)
      setAuswahl((res.data.items || []).filter(z => z.dunnable).map(z => z.invoice_id))
    } catch {
      toast.error('Der Mahnlauf konnte nicht geladen werden')
    } finally {
      setLaden(false)
    }
  }, [])

  useEffect(() => { holen() }, [holen])

  const zeilen = (daten?.items || []).filter(z => !nurMahnbare || z.dunnable)
  const gewaehlt = zeilen.filter(z => auswahl.includes(z.invoice_id) && z.dunnable)
  const summeOffen = gewaehlt.reduce((s, z) => s + Number(z.open_amount || 0), 0)

  const umschalten = (id) =>
    setAuswahl(a => a.includes(id) ? a.filter(x => x !== id) : [...a, id])

  const mahnen = async () => {
    if (gewaehlt.length === 0) return
    setLaeuft(true)
    try {
      const res = await invoiceApi.dunningBatch({ invoice_ids: gewaehlt.map(z => z.invoice_id) })
      toast.success(`${res.data.length} ${res.data.length === 1 ? 'Mahnung' : 'Mahnungen'} erstellt`)
      await holen()
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Der Mahnlauf ist fehlgeschlagen')
    } finally {
      setLaeuft(false)
    }
  }

  if (laden) return <div className="flex justify-center py-16"><RefreshCw size={22} className="animate-spin text-neutral-400" /></div>

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/buchhaltung')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
          <ArrowLeft size={18} />
        </button>
        <PageHeader icon={Bell} title="Mahnlauf"
          subtitle="Überfällige Rechnungen prüfen und mahnen" />
      </div>

      {daten?.interest_hint && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{daten.interest_hint}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-4 mb-4 text-sm">
        <span className="text-neutral-500">
          Mahnbar <strong className="text-neutral-900 text-base">{daten?.dunnable_count || 0}</strong>
          <span className="text-neutral-400"> von {daten?.items?.length || 0}</span>
        </span>
        <label className="flex items-center gap-2 text-neutral-600">
          <input type="checkbox" checked={nurMahnbare} onChange={e => setNurMahnbare(e.target.checked)} />
          nur mahnbare zeigen
        </label>
        <button onClick={holen} className="text-neutral-500 hover:text-neutral-800 flex items-center gap-1">
          <RefreshCw size={14} /> neu laden
        </button>
      </div>

      {zeilen.length === 0 ? (
        <div className="bg-surface border border-neutral-200 rounded-xl py-16 text-center text-neutral-400">
          <Bell size={28} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">Nichts zu mahnen — alle Rechnungen sind im Rahmen.</p>
        </div>
      ) : (
        <div className="bg-surface border border-neutral-200 rounded-xl overflow-hidden mb-5">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 border-b">
              <tr>
                <th className="w-10 px-3 py-3"></th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Beleg</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500 hidden sm:table-cell">Kunde</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500 hidden md:table-cell">Fällig</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500">Offen</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Nächste Stufe</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500 hidden lg:table-cell">Gebühr / Zinsen</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {zeilen.map(z => (
                <tr key={z.invoice_id} className={z.dunnable ? 'hover:bg-neutral-50' : 'bg-neutral-50/60'}>
                  <td className="px-3 py-3">
                    <input type="checkbox" disabled={!z.dunnable}
                      checked={auswahl.includes(z.invoice_id) && z.dunnable}
                      onChange={() => umschalten(z.invoice_id)} />
                  </td>
                  <td className="px-4 py-3">
                    <button onClick={() => navigate(`/invoices/${z.invoice_id}`)}
                      className="font-medium text-neutral-800 hover:text-primary-600">
                      {z.number || 'Entwurf'}
                    </button>
                    <span className="block text-xs text-neutral-400">
                      {z.days_overdue} Tage überfällig
                    </span>
                  </td>
                  <td className="px-4 py-3 text-neutral-600 hidden sm:table-cell">{z.contact_name || '—'}</td>
                  <td className="px-4 py-3 text-neutral-600 hidden md:table-cell whitespace-nowrap">{fmtDate(z.due_date)}</td>
                  <td className="px-4 py-3 text-right font-semibold text-neutral-900">{fmtEuro(z.open_amount)}</td>
                  <td className="px-4 py-3">
                    {z.dunnable ? (
                      <span className="text-neutral-700">{z.next_label}</span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-neutral-500">
                        <Lock size={12} /> {z.reason}
                      </span>
                    )}
                    {z.current_level > 0 && (
                      <span className="block text-xs text-neutral-400">
                        zuletzt Stufe {z.current_level} am {fmtDate(z.last_dunned_at)}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right text-neutral-500 hidden lg:table-cell whitespace-nowrap">
                    {z.dunnable ? `${fmtEuro(z.fee)} / ${fmtEuro(z.interest)}` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {gewaehlt.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 bg-surface border border-neutral-200 rounded-xl px-5 py-4">
          <div className="text-sm text-neutral-600">
            <strong className="text-neutral-900">{gewaehlt.length}</strong>{' '}
            {gewaehlt.length === 1 ? 'Beleg' : 'Belege'} ausgewählt ·{' '}
            offen {fmtEuro(summeOffen)}
            <span className="block text-xs text-neutral-400 mt-0.5">
              Belege desselben Kunden kommen auf ein gemeinsames Schreiben.
            </span>
          </div>
          <button onClick={mahnen} disabled={laeuft}
            className="inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50">
            {laeuft ? <RefreshCw size={15} className="animate-spin" /> : <FileText size={15} />}
            Mahnungen erstellen
          </button>
        </div>
      )}
    </div>
  )
}
