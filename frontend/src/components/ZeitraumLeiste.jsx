/**
 * ZeitraumLeiste – Zeitraumwahl für die Berichte der Zeiterfassung
 *
 * Eine Leiste für alle drei Berichtsseiten: Voreinstellungen (Tag … Gesamt),
 * Blättern in Schritten der gewählten Voreinstellung und zwei Datumsfelder
 * für den freien Zeitraum.
 *
 * Absichtlich eine gemeinsame Komponente statt dreimal derselbe Code: Der
 * Zeitraum ist die eine Angabe, die auf allen Berichtsseiten identisch
 * funktionieren muss. Wo jede Seite ihre eigene Wochenberechnung mitbringt,
 * zeigen zwei Seiten irgendwann verschiedene Summen für „diese Woche" — und
 * der Fehler fällt erst auf, wenn jemand die Zahlen vergleicht.
 *
 * Wochenbeginn ist Montag (AT/DE), nicht Sonntag.
 */
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react'

// Lokales Datum als YYYY-MM-DD — bewusst NICHT über toISOString():
// das rechnet nach UTC um und verschiebt am Abend um einen Tag.
export const alsDatum = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export const VOREINSTELLUNGEN = [
  { id: 'tag',     label: 'Tag' },
  { id: 'woche',   label: 'Woche' },
  { id: 'monat',   label: 'Monat' },
  { id: 'quartal', label: 'Quartal' },
  { id: 'jahr',    label: 'Jahr' },
  { id: 'gesamt',  label: 'Gesamt' },
  { id: 'frei',    label: 'Frei' },
]

/**
 * Zeitraum einer Voreinstellung berechnen.
 * @param {string} id      tag | woche | monat | quartal | jahr | gesamt
 * @param {number} versatz 0 = aktueller Zeitraum, -1 = einer zurück, +1 = vor
 */
export function zeitraumBerechnen(id, versatz = 0) {
  const heute = new Date()
  const j = heute.getFullYear()
  const m = heute.getMonth()

  switch (id) {
    case 'tag': {
      const t = new Date(j, m, heute.getDate() + versatz)
      return { von: alsDatum(t), bis: alsDatum(t) }
    }
    case 'woche': {
      const wochentag = (heute.getDay() + 6) % 7          // Mo=0 … So=6
      const mo = new Date(j, m, heute.getDate() - wochentag + versatz * 7)
      const so = new Date(mo); so.setDate(mo.getDate() + 6)
      return { von: alsDatum(mo), bis: alsDatum(so) }
    }
    case 'monat':
      return {
        von: alsDatum(new Date(j, m + versatz, 1)),
        bis: alsDatum(new Date(j, m + versatz + 1, 0)),
      }
    case 'quartal': {
      const q = Math.floor(m / 3) + versatz
      return {
        von: alsDatum(new Date(j, q * 3, 1)),
        bis: alsDatum(new Date(j, q * 3 + 3, 0)),
      }
    }
    case 'jahr':
      return {
        von: alsDatum(new Date(j + versatz, 0, 1)),
        bis: alsDatum(new Date(j + versatz, 11, 31)),
      }
    case 'gesamt':
      return { von: '2000-01-01', bis: alsDatum(heute) }
    default:
      return null
  }
}

/**
 * Tagesgrenze als Zeitstempel MIT Zeitzonen-Versatz, z.B.
 * „2026-08-01" → „2026-08-01T00:00:00+02:00".
 *
 * Ohne den Versatz versteht der Server die Grenze als UTC-Mitternacht. In
 * Österreich (UTC+1/+2) verschiebt das den Zeitraum um ein bis zwei Stunden:
 * Ein Eintrag vom 01.09. um 01:15 Ortszeit liegt in UTC noch am 31.08. und
 * erschien dann im August-Bericht — während ein Eintrag vom 01.08. um 01:00
 * fehlte. Der Versatz wird für den jeweiligen Tag berechnet, damit auch die
 * Sommerzeit-Umstellung stimmt.
 */
function mitVersatz(datum, zeit) {
  const d = new Date(`${datum}T${zeit}`)              // lokal gelesen
  const min = -d.getTimezoneOffset()                  // Wien Sommer: +120
  const vz = min >= 0 ? '+' : '-'
  const hh = String(Math.floor(Math.abs(min) / 60)).padStart(2, '0')
  const mm = String(Math.abs(min) % 60).padStart(2, '0')
  return `${datum}T${zeit}${vz}${hh}:${mm}`
}

/** Beginn des Von-Tages (00:00:00 Ortszeit) als Zeitstempel mit Zeitzone. */
export const tagesbeginn = (datum) => mitVersatz(datum, '00:00:00')

/** Ende des Bis-Tages (23:59:59 Ortszeit) als Zeitstempel mit Zeitzone. */
export const tagesende = (datum) => mitVersatz(datum, '23:59:59')

/** Lesbare Beschriftung des aktuellen Zeitraums, z.B. „31.08. – 06.09.2026" */
export function zeitraumText(von, bis) {
  if (!von || !bis) return ''
  const f = (s) => new Date(s).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit', year: 'numeric' })
  return von === bis ? f(von) : `${f(von)} – ${f(bis)}`
}

export default function ZeitraumLeiste({
  voreinstellung, versatz = 0, von, bis,
  onChange,           // ({ voreinstellung, versatz, von, bis }) => void
}) {
  const setzeVoreinstellung = (id) => {
    if (id === 'frei') { onChange({ voreinstellung: 'frei', versatz: 0, von, bis }); return }
    const r = zeitraumBerechnen(id, 0)
    onChange({ voreinstellung: id, versatz: 0, von: r.von, bis: r.bis })
  }

  const blaettern = (richtung) => {
    // „Gesamt" und „Frei" haben keine Schrittweite — Blättern ist dort gesperrt
    if (voreinstellung === 'gesamt' || voreinstellung === 'frei') return
    const neu = versatz + richtung
    const r = zeitraumBerechnen(voreinstellung, neu)
    onChange({ voreinstellung, versatz: neu, von: r.von, bis: r.bis })
  }

  const blaetternMoeglich = voreinstellung !== 'gesamt' && voreinstellung !== 'frei'

  // Eigene Datumswahl schaltet automatisch auf „Frei" — sonst würde der
  // nächste Klick auf „◀" die Eingabe kommentarlos überschreiben.
  const setzeDatum = (feld, wert) => {
    onChange({
      voreinstellung: 'frei', versatz: 0,
      von: feld === 'von' ? wert : von,
      bis: feld === 'bis' ? wert : bis,
    })
  }

  const feldCls = "px-2 py-1.5 border-0 bg-transparent text-sm text-gray-700 focus:outline-none"

  return (
    <div className="flex flex-wrap items-center gap-2 mb-4">
      {/* Voreinstellungen */}
      <div className="inline-flex bg-surface border border-gray-200 rounded-xl p-1 gap-0.5 shadow-card">
        {VOREINSTELLUNGEN.map(v => (
          <button key={v.id} onClick={() => setzeVoreinstellung(v.id)}
            className={`px-3 py-1.5 rounded-lg text-[13px] font-medium transition ${
              voreinstellung === v.id
                ? 'bg-primary-500 text-on-accent'
                : 'text-gray-500 hover:bg-gray-100 hover:text-gray-900'
            }`}>
            {v.label}
          </button>
        ))}
      </div>

      {/* Blättern */}
      <div className="inline-flex bg-surface border border-gray-200 rounded-xl overflow-hidden shadow-card">
        <button onClick={() => blaettern(-1)} disabled={!blaetternMoeglich}
          title="Zeitraum zurück"
          className="px-3 py-2 text-gray-500 hover:bg-gray-100 disabled:opacity-40 disabled:hover:bg-transparent transition">
          <ChevronLeft size={15} />
        </button>
        <button onClick={() => blaettern(1)} disabled={!blaetternMoeglich}
          title="Zeitraum vor"
          className="px-3 py-2 text-gray-500 hover:bg-gray-100 border-l border-gray-200 disabled:opacity-40 disabled:hover:bg-transparent transition">
          <ChevronRight size={15} />
        </button>
      </div>

      {/* Freier Zeitraum */}
      <div className="inline-flex items-center gap-1.5 bg-surface border border-gray-200 rounded-xl px-2 shadow-card">
        <Calendar size={14} className="text-gray-400" />
        <span className="text-xs text-gray-400">von</span>
        <input type="date" value={von || ''} onChange={e => setzeDatum('von', e.target.value)}
          className={feldCls} />
      </div>
      <div className="inline-flex items-center gap-1.5 bg-surface border border-gray-200 rounded-xl px-2 shadow-card">
        <Calendar size={14} className="text-gray-400" />
        <span className="text-xs text-gray-400">bis</span>
        <input type="date" value={bis || ''} onChange={e => setzeDatum('bis', e.target.value)}
          className={feldCls} />
      </div>
    </div>
  )
}
