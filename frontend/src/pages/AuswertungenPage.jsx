import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { invoiceApi } from '../services/api'
import toast from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { BarChart3, ArrowLeft, RefreshCw, Info } from 'lucide-react'

function fmtEuro(n) {
  return Number(n || 0).toLocaleString('de-AT', {
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  }) + ' €'
}
function fmtProzent(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('de-AT', { maximumFractionDigits: 1 }) + ' %'
}

const MONATE = ['Jän', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun',
                'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

/**
 * Umsatzauswertungen (C-15).
 *
 * Alle Zahlen sind **netto** und nach **Belegdatum** abgegrenzt — dieselbe
 * Abgrenzung wie Verkaufsbuch und Umsatzsteuer-Auswertung. Das steht auch auf
 * der Seite: Eine Umsatzzahl ohne Angabe, wann sie zählt, lädt zum
 * Missverstehen ein.
 */
export default function AuswertungenPage() {
  const navigate = useNavigate()
  const heute = new Date()
  const [jahr, setJahr] = useState(heute.getFullYear())
  const [monate, setMonate] = useState(null)
  const [kunden, setKunden] = useState(null)
  const [artikel, setArtikel] = useState(null)
  const [quote, setQuote] = useState(null)
  const [laden, setLaden] = useState(true)

  const holen = useCallback(async () => {
    setLaden(true)
    const zeitraum = { date_from: `${jahr}-01-01`, date_to: `${jahr}-12-31` }
    try {
      const [m, k, a, q] = await Promise.all([
        invoiceApi.umsatzJahr(jahr),
        invoiceApi.umsatzKunden({ ...zeitraum, limit: 15 }),
        invoiceApi.umsatzArtikel({ ...zeitraum, limit: 15 }),
        invoiceApi.angebotsquote(zeitraum),
      ])
      setMonate(m.data); setKunden(k.data); setArtikel(a.data); setQuote(q.data)
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Die Auswertung konnte nicht geladen werden')
    } finally {
      setLaden(false)
    }
  }, [jahr])

  useEffect(() => { holen() }, [holen])

  const jahre = [heute.getFullYear(), heute.getFullYear() - 1, heute.getFullYear() - 2]
  const hoechstwert = Math.max(
    1, ...(monate?.monate || []).flatMap(m => [Number(m.netto), Number(m.vorjahr)]))

  return (
    <div>
      <div className="flex items-center gap-3 mb-2">
        <button onClick={() => navigate('/buchhaltung')}
          className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
          <ArrowLeft size={18} />
        </button>
        <PageHeader icon={BarChart3} title="Auswertungen"
          subtitle="Umsatz je Monat, Kunde und Artikel — und was aus den Angeboten wird">
          <div className="flex items-center gap-2">
            <select value={jahr} onChange={e => setJahr(Number(e.target.value))}
              className="border border-neutral-200 rounded-lg px-3 py-2 text-sm">
              {jahre.map(j => <option key={j} value={j}>{j}</option>)}
            </select>
            <button onClick={holen}
              className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500" title="Neu laden">
              <RefreshCw size={16} className={laden ? 'animate-spin' : ''} />
            </button>
          </div>
        </PageHeader>
      </div>

      {/* Die Abgrenzung gehört sichtbar dazu, nicht in eine Fußnote. */}
      <div className="flex items-start gap-2 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3 mb-6 text-sm text-neutral-600">
        <Info size={15} className="mt-0.5 shrink-0 text-neutral-400" />
        <span>
          Alle Beträge sind <strong>netto</strong> und zählen im Monat des
          <strong> Belegdatums</strong> — dieselbe Abgrenzung wie Verkaufsbuch und
          Umsatzsteuer. Offene Forderungen sind enthalten; wer den Zahlungseingang
          sucht, findet ihn unter Offene Posten. Entwürfe und stornierte Belege
          ohne Gutschrift bleiben draußen.
        </span>
      </div>

      {laden && !monate ? (
        <div className="flex justify-center py-16">
          <RefreshCw size={22} className="animate-spin text-neutral-400" />
        </div>
      ) : (
        <div className="space-y-6">

          {/* ── Jahresverlauf ────────────────────────────────────────────── */}
          <div className="bg-surface border border-neutral-200 rounded-xl p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2 mb-5">
              <h2 className="text-sm font-semibold text-neutral-700">Umsatz {jahr}</h2>
              <div className="flex items-baseline gap-4 text-sm">
                <span className="text-neutral-500">
                  {monate?.belege_gesamt || 0} Belege
                </span>
                <span className="text-neutral-500">
                  Vorjahr <span className="text-neutral-700">{fmtEuro(monate?.vorjahr_gesamt)}</span>
                </span>
                <span className="text-xl font-semibold text-neutral-900">
                  {fmtEuro(monate?.netto_gesamt)}
                </span>
              </div>
            </div>

            <div className="flex items-end gap-1.5 h-40">
              {(monate?.monate || []).map(m => {
                const h = (Number(m.netto) / hoechstwert) * 100
                const hv = (Number(m.vorjahr) / hoechstwert) * 100
                return (
                  <div key={m.monat} className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full flex items-end justify-center gap-0.5 h-full">
                      {/* Vorjahr blass daneben statt dahinter — überlagert
                          liest man nicht, welcher Balken welcher ist. */}
                      <div className="w-1/3 bg-neutral-200 rounded-t"
                        style={{ height: `${Math.max(hv, 0)}%` }}
                        title={`${MONATE[m.monat - 1]} ${jahr - 1}: ${fmtEuro(m.vorjahr)}`} />
                      <div className="w-1/2 bg-primary-500 rounded-t"
                        style={{ height: `${Math.max(h, 0)}%` }}
                        title={`${MONATE[m.monat - 1]} ${jahr}: ${fmtEuro(m.netto)} · ${m.belege} Belege`} />
                    </div>
                    <span className="text-[10px] text-neutral-400">{MONATE[m.monat - 1]}</span>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* ── Kunden ─────────────────────────────────────────────────── */}
            <div className="bg-surface border border-neutral-200 rounded-xl overflow-hidden">
              <div className="px-5 py-3 border-b border-neutral-100 flex items-baseline justify-between">
                <h2 className="text-sm font-semibold text-neutral-700">Umsatz je Kunde</h2>
                <span className="text-xs text-neutral-400">{kunden?.kunden || 0} Kunden</span>
              </div>
              {(kunden?.zeilen || []).length === 0 ? (
                <p className="px-5 py-10 text-center text-sm text-neutral-400">
                  Im Jahr {jahr} noch kein Umsatz erfasst.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-neutral-100">
                    {kunden.zeilen.map((z, i) => (
                      <tr key={z.contact_id || `ohne-${i}`} className="hover:bg-neutral-50">
                        <td className="px-5 py-2.5 text-neutral-400 w-8">{i + 1}</td>
                        <td className="px-2 py-2.5 text-neutral-800">{z.name}</td>
                        <td className="px-2 py-2.5 text-neutral-400 text-xs whitespace-nowrap hidden sm:table-cell">
                          {z.belege} {z.belege === 1 ? 'Beleg' : 'Belege'}
                        </td>
                        <td className="px-2 py-2.5 text-right text-neutral-500 text-xs whitespace-nowrap">
                          {fmtProzent(z.anteil)}
                        </td>
                        <td className="px-5 py-2.5 text-right font-medium text-neutral-900 whitespace-nowrap">
                          {fmtEuro(z.netto)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* ── Artikel ────────────────────────────────────────────────── */}
            <div className="bg-surface border border-neutral-200 rounded-xl overflow-hidden">
              <div className="px-5 py-3 border-b border-neutral-100">
                <h2 className="text-sm font-semibold text-neutral-700">Umsatz je Artikel</h2>
              </div>

              {/* Die Güte der Liste steht ÜBER der Liste, nicht darunter:
                  Sind 80 % nicht zugeordnet, soll man das lesen, bevor man
                  die Rangliste für bare Münze nimmt. */}
              {Number(artikel?.ohne_artikel_netto) > 0 && (
                <div className="px-5 py-3 bg-amber-50 border-b border-amber-100 text-xs text-amber-800 leading-relaxed">
                  {fmtProzent(artikel.ohne_artikel_anteil)} des Umsatzes
                  ({fmtEuro(artikel.ohne_artikel_netto)}) stammt aus frei
                  geschriebenen Positionen ohne Artikelverknüpfung und taucht
                  unten nicht auf. Wer die Liste vollständig will, wählt die
                  Positionen aus den Stammdaten statt sie zu tippen.
                </div>
              )}

              {(artikel?.zeilen || []).length === 0 ? (
                <p className="px-5 py-10 text-center text-sm text-neutral-400">
                  Keine Position war mit einem Artikel verknüpft.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-neutral-100">
                    {artikel.zeilen.map((z, i) => (
                      <tr key={z.article_id || i} className="hover:bg-neutral-50">
                        <td className="px-5 py-2.5 text-neutral-400 w-8">{i + 1}</td>
                        <td className="px-2 py-2.5 text-neutral-800">{z.name}</td>
                        <td className="px-2 py-2.5 text-right text-neutral-500 text-xs whitespace-nowrap hidden sm:table-cell">
                          {Number(z.menge).toLocaleString('de-AT', { maximumFractionDigits: 2 })}
                        </td>
                        <td className="px-5 py-2.5 text-right font-medium text-neutral-900 whitespace-nowrap">
                          {fmtEuro(z.netto)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* ── Angebotsquote ───────────────────────────────────────────── */}
          <div className="bg-surface border border-neutral-200 rounded-xl p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2 mb-4">
              <h2 className="text-sm font-semibold text-neutral-700">Angebote {jahr}</h2>
              <span className="text-xs text-neutral-400">
                gezählt nach Angebotsdatum, nicht nach Annahme
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-neutral-500">Quote</p>
                <p className="text-2xl font-semibold text-neutral-900 mt-0.5">
                  {fmtProzent(quote?.quote)}
                </p>
                <p className="text-xs text-neutral-400 mt-0.5">
                  {quote?.quote === null || quote?.quote === undefined
                    ? 'noch nichts entschieden'
                    : 'der entschiedenen Angebote'}
                </p>
              </div>
              <div>
                <p className="text-xs text-neutral-500">Gewonnen</p>
                <p className="text-2xl font-semibold text-emerald-600 mt-0.5">{quote?.gewonnen ?? 0}</p>
                <p className="text-xs text-neutral-400 mt-0.5">{fmtEuro(quote?.gewonnen_netto)}</p>
              </div>
              <div>
                <p className="text-xs text-neutral-500">Verloren</p>
                <p className="text-2xl font-semibold text-neutral-700 mt-0.5">{quote?.verloren ?? 0}</p>
                <p className="text-xs text-neutral-400 mt-0.5">{fmtEuro(quote?.verloren_netto)}</p>
              </div>
              <div>
                <p className="text-xs text-neutral-500">Noch offen</p>
                <p className="text-2xl font-semibold text-amber-600 mt-0.5">{quote?.offen ?? 0}</p>
                <p className="text-xs text-neutral-400 mt-0.5">{fmtEuro(quote?.offen_netto)}</p>
              </div>
            </div>

            {quote?.tage_bis_entscheidung != null && (
              <p className="text-xs text-neutral-500 mt-4 pt-4 border-t border-neutral-100">
                Bis zur Zusage vergehen im Schnitt {quote.tage_bis_entscheidung} Tage.
                {' '}<span className="text-neutral-400">
                  Näherungswert — ein eigenes Annahmedatum führen wir nicht,
                  gerechnet wird bis zur letzten Änderung am Angebot.
                </span>
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
