/**
 * Auswertung – Stunden je Benutzer bzw. je Zeitprojekt.
 *
 * Eine Seite für beide Berichte: Sie unterscheiden sich nur in der
 * Gruppierung und in zwei Spalten. Zwei getrennte Dateien würden dieselbe
 * Zeitraum- und Summenlogik doppelt führen — und irgendwann verschieden.
 *
 * „Absolut/Relativ" schaltet zwischen Stunden und Prozentanteil um; die
 * Balken bleiben in beiden Fällen, weil erst der Vergleich die Zahl lesbar
 * macht.
 */
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import ZeitraumLeiste, { zeitraumBerechnen, tagesbeginn, tagesende } from '../components/ZeitraumLeiste'
import { reportsApi } from '../services/api'
import toast from 'react-hot-toast'
import { Users, FolderOpen, Loader2, AlertTriangle, Play } from 'lucide-react'

const fmtMinuten = (min) => `${Math.floor((min || 0) / 60)}:${String((min || 0) % 60).padStart(2, '0')}`
const fmtUhr = (iso) => iso ? new Date(iso).toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' }) : '—'

/** Rest-Stundenkonto als Markierung — dieselbe Sprache wie in der Erfassung. */
function BudgetBadge({ budget }) {
  if (!budget || !budget.has_budget) return <span className="text-gray-300 text-xs">kein Stundenkonto</span>
  const rest = fmtMinuten(Math.max(0, budget.remaining_minutes))
  if (budget.exhausted) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-600 border border-red-200"
        title="Budget verbraucht – dem Kunden ein neues Stundenkonto anbieten">
        <AlertTriangle size={11} /> Rest {rest}
      </span>
    )
  }
  return (
    <span className="inline-block px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
      Rest {rest}
    </span>
  )
}

/**
 * @param {'benutzer'|'zeitprojekt'} gruppierung
 */
export default function BerichtAuswertungPage({ gruppierung = 'benutzer' }) {
  const navigate = useNavigate()
  const istBenutzer = gruppierung === 'benutzer'

  const start = zeitraumBerechnen(istBenutzer ? 'woche' : 'monat', 0)
  const [zeitraum, setZeitraum] = useState({
    voreinstellung: istBenutzer ? 'woche' : 'monat', versatz: 0, von: start.von, bis: start.bis,
  })
  const [ansicht, setAnsicht] = useState('absolut')   // absolut | relativ
  const [daten,   setDaten]   = useState(null)
  const [laden,   setLaden]   = useState(true)

  // Zeitraumwechsel setzt die Ansicht nicht zurück — wer Prozente vergleicht,
  // will beim Blättern Prozente behalten.
  const holen = useCallback(async () => {
    setLaden(true)
    try {
      const res = await reportsApi.uebersicht({
        // mit Zeitzonen-Versatz — sonst zählt der Server den UTC-Tag
        date_from: tagesbeginn(zeitraum.von),
        date_to:   tagesende(zeitraum.bis),
        group_by:  gruppierung,
      })
      setDaten(res.data)
    } catch {
      toast.error('Auswertung konnte nicht geladen werden')
      setDaten(null)
    } finally {
      setLaden(false)
    }
  }, [zeitraum.von, zeitraum.bis, gruppierung])

  useEffect(() => { holen() }, [holen])

  // Zeile anklicken → gefiltert in den Bericht „Projektzeiten"
  const zurListe = (zeile) => {
    const p = new URLSearchParams({ von: zeitraum.von, bis: zeitraum.bis })
    if (istBenutzer) p.set('benutzer', zeile.schluessel)
    else p.set('zeitprojekt', zeile.name)
    navigate(`/zeiterfassung/berichte/projektzeiten?${p}`)
  }

  const zeilen = daten?.zeilen || []
  const summe  = daten?.summe
  const maxMin = Math.max(1, ...zeilen.map(z => z.minuten))

  /** Wert je nach Ansicht: Stunden oder Prozent vom Gesamtwert */
  const wert = (minuten) => ansicht === 'absolut'
    ? fmtMinuten(minuten)
    : `${summe?.minuten ? Math.round(minuten * 100 / summe.minuten) : 0} %`

  return (
    <div>
      <PageHeader
        icon={istBenutzer ? Users : FolderOpen}
        title={istBenutzer ? 'Benutzer-Auswertung' : 'Zeitprojekt-Auswertung'}
        subtitle={istBenutzer
          ? 'Stunden je Benutzer im gewählten Zeitraum'
          : 'Stunden je Zeitprojekt im gewählten Zeitraum'}
      >
        <div className="inline-flex bg-surface border border-gray-200 rounded-xl p-1 gap-0.5 shadow-card">
          {[{ id: 'absolut', label: 'Absolut' }, { id: 'relativ', label: 'Relativ' }].map(a => (
            <button key={a.id} onClick={() => setAnsicht(a.id)}
              className={`px-3 py-1.5 rounded-lg text-[13px] font-medium transition ${
                ansicht === a.id ? 'bg-primary-500 text-on-accent' : 'text-gray-500 hover:bg-gray-100'
              }`}>
              {a.label}
            </button>
          ))}
        </div>
      </PageHeader>

      <ZeitraumLeiste {...zeitraum} onChange={setZeitraum} />

      {/* ── Zusammenfassung ───────────────────────────────────────────────── */}
      <div className="bg-surface rounded-2xl shadow-card overflow-hidden">
        <div className="px-4 sm:px-5 py-3 border-b border-gray-100 flex items-center justify-between gap-3 flex-wrap">
          <h2 className="text-sm font-semibold text-gray-900">Zusammenfassung</h2>
          {summe && (
            <p className="text-xs text-gray-400">
              {summe.eintraege} {summe.eintraege === 1 ? 'Eintrag' : 'Einträge'} ·
              {' '}verrechenbar {summe.anteil_verrechenbar} %
            </p>
          )}
        </div>

        {laden ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={26} className="animate-spin text-primary-400" />
          </div>
        ) : zeilen.length === 0 ? (
          <p className="text-center text-gray-400 py-16 text-sm">Keine Zeiteinträge in diesem Zeitraum.</p>
        ) : (
          <>
            {/* Tabelle (ab Tablet) */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-neutral-50 border-b border-gray-200">
                    <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">
                      {istBenutzer ? 'Benutzer' : 'Zeitprojekt'}
                    </th>
                    {!istBenutzer && (
                      <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Kontakt</th>
                    )}
                    <th className="text-right px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Projektzeit</th>
                    <th className="text-right px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Verrechenbar</th>
                    <th className="text-right px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Nicht verrechenbar</th>
                    <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500 w-44">
                      {istBenutzer ? 'Anteil verrechenbar' : 'Stundenkonto'}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {zeilen.map(z => (
                    <tr key={z.schluessel} onClick={() => zurListe(z)}
                      title="Zeigt die einzelnen Einträge dieser Zeile"
                      className="border-b border-gray-100 hover:bg-primary-50/40 cursor-pointer transition">
                      <td className="px-4 py-2.5 font-medium text-gray-900">{z.name}</td>
                      {!istBenutzer && <td className="px-4 py-2.5 text-gray-500">{z.zusatz || '—'}</td>}
                      <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-gray-900">{wert(z.minuten)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-green-700">{wert(z.verrechenbar_minuten)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-gray-400">{wert(z.nicht_verrechenbar_minuten)}</td>
                      <td className="px-4 py-2.5">
                        {istBenutzer ? (
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden min-w-[60px]">
                              <div className="h-full bg-green-500 rounded-full"
                                style={{ width: `${z.anteil_verrechenbar}%` }} />
                            </div>
                            <span className="text-xs text-gray-400 tabular-nums w-9 text-right">{z.anteil_verrechenbar} %</span>
                          </div>
                        ) : (
                          <BudgetBadge budget={z.budget} />
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-neutral-50 border-t-2 border-gray-200 font-semibold">
                    <td className="px-4 py-3 text-gray-900" colSpan={istBenutzer ? 1 : 2}>Gesamt</td>
                    <td className="px-4 py-3 text-right tabular-nums">{fmtMinuten(summe?.minuten)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-green-700">{fmtMinuten(summe?.verrechenbar_minuten)}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-gray-400">{fmtMinuten(summe?.nicht_verrechenbar_minuten)}</td>
                    <td className="px-4 py-3" />
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* Karten (Handy) */}
            <div className="sm:hidden divide-y divide-gray-100">
              {zeilen.map(z => (
                <button key={z.schluessel} onClick={() => zurListe(z)}
                  className="w-full text-left p-4 hover:bg-primary-50/40 transition">
                  <div className="flex justify-between items-start gap-3">
                    <span className="font-medium text-gray-900 text-sm">{z.name}</span>
                    <span className="tabular-nums font-semibold text-gray-900 text-sm">{wert(z.minuten)}</span>
                  </div>
                  {!istBenutzer && z.zusatz && <p className="text-xs text-gray-400">{z.zusatz}</p>}
                  <div className="flex items-center gap-2 mt-2">
                    <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-primary-500 rounded-full"
                        style={{ width: `${Math.round(z.minuten * 100 / maxMin)}%` }} />
                    </div>
                    {istBenutzer
                      ? <span className="text-xs text-gray-400">{z.anteil_verrechenbar} % verr.</span>
                      : <BudgetBadge budget={z.budget} />}
                  </div>
                </button>
              ))}
              <div className="p-4 bg-neutral-50 flex justify-between text-sm font-semibold">
                <span>Gesamt</span>
                <span className="tabular-nums">{fmtMinuten(summe?.minuten)}</span>
              </div>
            </div>
          </>
        )}
      </div>

      {/* ── Jetzt aktiv (nur in der Benutzer-Auswertung) ───────────────────── */}
      {istBenutzer && (
        <>
          <div className="flex items-center gap-3 mt-6 mb-3">
            <h3 className="text-sm font-semibold text-gray-900">Jetzt aktiv</h3>
            <span className="flex-1 h-px bg-gray-200" />
            <span className="text-xs text-gray-400">laufende Zeitgeber</span>
          </div>
          <div className="bg-surface rounded-2xl shadow-card overflow-hidden">
            {(daten?.laufend || []).length === 0 ? (
              <p className="text-center text-gray-400 py-8 text-sm">Zurzeit läuft kein Zeitgeber.</p>
            ) : (
              <div className="divide-y divide-gray-100">
                {daten.laufend.map(l => (
                  <div key={l.id} className="flex items-center gap-3 px-4 py-3 flex-wrap">
                    <span className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
                    <span className="font-medium text-gray-900 text-sm">{l.benutzer}</span>
                    <span className="text-sm text-gray-600">{l.zeitprojekt || '—'}</span>
                    {l.notiz && <span className="text-xs text-gray-400 truncate max-w-[220px]">{l.notiz}</span>}
                    <span className="ml-auto text-xs text-gray-400 flex items-center gap-1">
                      <Play size={11} /> seit {fmtUhr(l.startzeit)}
                    </span>
                    <span className="tabular-nums font-semibold text-gray-900 text-sm w-16 text-right">
                      {fmtMinuten(l.dauer_minuten)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <p className="text-xs text-gray-400 mt-3">
        Ein Klick auf eine Zeile öffnet die einzelnen Einträge im Bericht „Projektzeiten".
      </p>
    </div>
  )
}
