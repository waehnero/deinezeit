import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoiceApi } from '../services/api'
import toast from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { Wallet, RefreshCw, ArrowLeft } from 'lucide-react'

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' })
}
function fmtEuro(n) {
  return Number(n || 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

// Die übliche Einteilung in Debitorenauswertungen — Reihenfolge wie im Backend
const STAFFEL = [
  ['nicht_faellig', 'Nicht fällig', 'text-neutral-600 bg-neutral-50'],
  ['b1_30',         '1–30 Tage',    'text-amber-700 bg-amber-50'],
  ['b31_60',        '31–60 Tage',   'text-orange-700 bg-orange-50'],
  ['b61_90',        '61–90 Tage',   'text-red-700 bg-red-50'],
  ['b90_plus',      'über 90 Tage', 'text-red-800 bg-red-100'],
]

export default function OpenItemsPage() {
  const navigate = useNavigate()
  const [daten, setDaten] = useState(null)
  const [laden, setLaden] = useState(true)
  const [staffel, setStaffel] = useState('')

  const holen = useCallback(async () => {
    setLaden(true)
    try {
      const res = await invoiceApi.openItems({})
      setDaten(res.data)
    } catch { toast.error('Offene Posten konnten nicht geladen werden') }
    finally { setLaden(false) }
  }, [])

  useEffect(() => { holen() }, [holen])

  const posten = (daten?.items || []).filter(p => !staffel || p.bucket === staffel)

  if (laden) return <div className="flex justify-center py-16"><RefreshCw size={22} className="animate-spin text-neutral-400" /></div>

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/buchhaltung')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
          <ArrowLeft size={18} />
        </button>
        <PageHeader icon={Wallet} title="Offene Posten"
          subtitle="Ausgestellte Belege, die noch nicht beglichen sind" />
      </div>

      {/* Fälligkeitsstaffel — zugleich Filter */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        {STAFFEL.map(([schluessel, label, farbe]) => (
          <button key={schluessel}
            onClick={() => setStaffel(s => s === schluessel ? '' : schluessel)}
            className={`text-left rounded-xl border p-3 transition-all ${farbe} ${
              staffel === schluessel ? 'border-primary-400 ring-2 ring-primary-100' : 'border-neutral-200'}`}>
            <p className="text-xs font-medium">{label}</p>
            <p className="text-lg font-semibold mt-0.5">{fmtEuro(daten?.buckets?.[schluessel])}</p>
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-baseline gap-4 mb-4 text-sm">
        <span className="text-neutral-500">
          Offen gesamt <strong className="text-neutral-900 text-base">{fmtEuro(daten?.total_open)}</strong>
        </span>
        <span className="text-neutral-400">{daten?.count || 0} Belege</span>
        {staffel && (
          <button onClick={() => setStaffel('')} className="text-primary-600 hover:underline text-xs">
            Filter aufheben
          </button>
        )}
      </div>

      {posten.length === 0 ? (
        <div className="bg-surface border border-neutral-200 rounded-xl py-16 text-center text-neutral-400">
          <Wallet size={28} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">Keine offenen Posten{staffel ? ' in dieser Staffel' : ''}.</p>
        </div>
      ) : (
        <div className="bg-surface border border-neutral-200 rounded-xl overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-neutral-500">Beleg</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500 hidden sm:table-cell">Kontakt</th>
                <th className="text-left px-4 py-3 font-medium text-neutral-500 hidden md:table-cell">Fällig</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500 hidden lg:table-cell">Gesamt</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500 hidden lg:table-cell">Bezahlt</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500">Offen</th>
                <th className="text-right px-4 py-3 font-medium text-neutral-500">Überfällig</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {posten.map(p => (
                <tr key={p.id} onClick={() => navigate(`/invoices/${p.id}`)}
                    className="hover:bg-neutral-50 cursor-pointer">
                  <td className="px-4 py-3 font-medium text-neutral-800">{p.number || 'Entwurf'}</td>
                  <td className="px-4 py-3 text-neutral-600 hidden sm:table-cell">{p.contact_name || '—'}</td>
                  <td className="px-4 py-3 text-neutral-600 hidden md:table-cell whitespace-nowrap">{fmtDate(p.due_date)}</td>
                  <td className="px-4 py-3 text-right text-neutral-500 hidden lg:table-cell">{fmtEuro(p.total)}</td>
                  <td className="px-4 py-3 text-right text-neutral-500 hidden lg:table-cell">{fmtEuro(p.paid_total)}</td>
                  <td className="px-4 py-3 text-right font-semibold text-neutral-900">{fmtEuro(p.open_amount)}</td>
                  <td className={`px-4 py-3 text-right whitespace-nowrap ${p.days_overdue > 0 ? 'text-red-600' : 'text-neutral-400'}`}>
                    {p.days_overdue > 0 ? `${p.days_overdue} Tage` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {daten?.by_contact?.length > 0 && (
        <div className="bg-surface border border-neutral-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-neutral-700 mb-3">Nach Kontakt</h2>
          <div className="divide-y">
            {daten.by_contact.map((k, i) => (
              <div key={k.contact_id || i} className="flex items-center justify-between py-2 text-sm">
                <span className="text-neutral-700">{k.contact_name || 'Ohne Kontakt'}</span>
                <span className="text-neutral-400 text-xs">
                  {k.count} {k.count === 1 ? 'Beleg' : 'Belege'}
                  <strong className="text-neutral-900 text-sm ml-3">{fmtEuro(k.open_amount)}</strong>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
