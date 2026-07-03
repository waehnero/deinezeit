import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'

/**
 * Kalenderansicht für das Aufgabenmodul.
 * Modi: Arbeitswoche (Mo–Fr) · Woche (Mo–So) · Monat · Jahr.
 * Aufgaben werden über due_date einsortiert (due_time optional für Reihung).
 *
 * Props:
 *   todos       – gefilterte Aufgabenliste
 *   statuses    – [{value,label,color}] für die Farbgebung
 *   doneStatus  – Status-Wert, der als "erledigt" gilt
 *   onOpen(t)   – Aufgabe im Dialog öffnen
 *   onCreate(d) – neue Aufgabe mit vorbelegtem Fälligkeitsdatum (ISO-String)
 */

const MODI = [
  { id: 'arbeitswoche', label: 'Arbeitswoche' },
  { id: 'woche',        label: 'Woche' },
  { id: 'monat',        label: 'Monat' },
  { id: 'jahr',         label: 'Jahr' },
]

const WOCHENTAGE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

// ── Datums-Helfer (lokale Zeit, ISO-Strings yyyy-mm-dd) ───────────────────────
const pad = n => String(n).padStart(2, '0')
const toISO = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const heuteISO = () => toISO(new Date())
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x }
const startOfWeek = (d) => addDays(d, -((d.getDay() + 6) % 7))  // Montag

function kw(d) {
  // ISO-Kalenderwoche
  const x = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const day = x.getUTCDay() || 7
  x.setUTCDate(x.getUTCDate() + 4 - day)
  const jahrStart = new Date(Date.UTC(x.getUTCFullYear(), 0, 1))
  return Math.ceil(((x - jahrStart) / 86400000 + 1) / 7)
}

const monatLabel = d => d.toLocaleDateString('de-AT', { month: 'long', year: 'numeric' })
const kurzDatum  = d => `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.`

export default function AufgabenKalender({ todos, statuses, doneStatus, onOpen, onCreate }) {
  const [modus, setModus] = useState(() => {
    try { return localStorage.getItem('aufgaben_kalender_modus') || 'woche' } catch { return 'woche' }
  })
  const [datum, setDatum] = useState(() => new Date())

  const wechsleModus = (m) => {
    setModus(m)
    try { localStorage.setItem('aufgaben_kalender_modus', m) } catch {}
  }

  const statusColor = v => statuses.find(s => s.value === v)?.color || '#6b7280'

  // Aufgaben nach Fälligkeitsdatum gruppieren (due_time = Reihung im Tag)
  const proTag = useMemo(() => {
    const map = {}
    for (const t of todos) {
      if (!t.due_date) continue
      if (!map[t.due_date]) map[t.due_date] = []
      map[t.due_date].push(t)
    }
    for (const k of Object.keys(map)) {
      map[k].sort((a, b) => (a.due_time || '99') < (b.due_time || '99') ? -1 : 1)
    }
    return map
  }, [todos])

  // ── Navigation ──────────────────────────────────────────────────────────────
  const springe = (richtung) => {
    const d = new Date(datum)
    if (modus === 'arbeitswoche' || modus === 'woche') d.setDate(d.getDate() + 7 * richtung)
    else if (modus === 'monat') d.setMonth(d.getMonth() + richtung)
    else d.setFullYear(d.getFullYear() + richtung)
    setDatum(d)
  }

  const periodeLabel = () => {
    if (modus === 'monat') return monatLabel(datum)
    if (modus === 'jahr') return String(datum.getFullYear())
    const start = startOfWeek(datum)
    const ende = addDays(start, modus === 'arbeitswoche' ? 4 : 6)
    return `KW ${kw(datum)} · ${kurzDatum(start)} – ${kurzDatum(ende)}${ende.getFullYear()}`
  }

  const istErledigt = t => t.status === doneStatus
  const istUeberfaellig = t => t.due_date < heuteISO() && !istErledigt(t)

  // ── Aufgaben-Chip (überall gleich) ──────────────────────────────────────────
  const Chip = ({ t, mitZeit = false }) => (
    <button
      onClick={e => { e.stopPropagation(); onOpen(t) }}
      title={t.title}
      className={`w-full text-left text-[11px] leading-snug px-1.5 py-1 rounded border-l-2 truncate transition-colors
        ${istErledigt(t) ? 'line-through text-neutral-400 bg-neutral-50' : 'text-neutral-800 bg-white hover:bg-neutral-50'}
        ${istUeberfaellig(t) ? '!text-red-600' : ''}`}
      style={{ borderLeftColor: statusColor(t.status) }}>
      {mitZeit && t.due_time && <span className="font-medium mr-1">{t.due_time.slice(0, 5)}</span>}
      {t.title}
    </button>
  )

  // ── Wochenansicht (Arbeitswoche = 5, Woche = 7 Spalten) ─────────────────────
  const Woche = ({ tage }) => {
    const start = startOfWeek(datum)
    const heute = heuteISO()
    return (
      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${tage}, minmax(0, 1fr))` }}>
        {Array.from({ length: tage }, (_, i) => {
          const tag = addDays(start, i)
          const iso = toISO(tag)
          const liste = proTag[iso] || []
          const istHeute = iso === heute
          return (
            <div key={iso} className="min-w-0">
              <div className={`text-center text-xs font-medium mb-1.5 py-1 rounded-lg
                ${istHeute ? 'bg-primary-600 text-white' : 'text-neutral-500'}`}>
                {WOCHENTAGE[i]} {kurzDatum(tag)}
              </div>
              <div
                onClick={() => onCreate(iso)}
                className={`rounded-xl p-1.5 min-h-[240px] space-y-1 cursor-pointer group transition-colors
                  ${istHeute ? 'bg-primary-50/60' : 'bg-gray-50'} hover:bg-primary-50`}>
                {liste.map(t => <Chip key={t.id} t={t} mitZeit />)}
                <div className="opacity-0 group-hover:opacity-100 flex justify-center pt-1">
                  <Plus size={14} className="text-primary-400" />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    )
  }

  // ── Monatsansicht ───────────────────────────────────────────────────────────
  const Monat = () => {
    const erster = new Date(datum.getFullYear(), datum.getMonth(), 1)
    const start = startOfWeek(erster)
    const heute = heuteISO()
    const zellen = Array.from({ length: 42 }, (_, i) => addDays(start, i))
    return (
      <div>
        <div className="grid grid-cols-7 mb-1">
          {WOCHENTAGE.map(w => (
            <div key={w} className="text-center text-xs font-medium text-neutral-400 py-1">{w}</div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {zellen.map(tag => {
            const iso = toISO(tag)
            const liste = proTag[iso] || []
            const imMonat = tag.getMonth() === datum.getMonth()
            const istHeute = iso === heute
            return (
              <div key={iso}
                onClick={() => onCreate(iso)}
                className={`rounded-lg border p-1 min-h-[84px] cursor-pointer transition-colors hover:bg-primary-50
                  ${imMonat ? 'bg-white border-neutral-200' : 'bg-neutral-50/60 border-neutral-100'}`}>
                <div className={`text-[11px] mb-0.5 w-5 h-5 flex items-center justify-center rounded-full
                  ${istHeute ? 'bg-primary-600 text-white font-semibold'
                             : imMonat ? 'text-neutral-600' : 'text-neutral-300'}`}>
                  {tag.getDate()}
                </div>
                <div className="space-y-0.5">
                  {liste.slice(0, 3).map(t => <Chip key={t.id} t={t} />)}
                  {liste.length > 3 && (
                    <p className="text-[10px] text-neutral-400 px-1">+{liste.length - 3} weitere</p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  // ── Jahresansicht (12 Mini-Monate, Klick auf Tag -> Monatsansicht) ──────────
  const Jahr = () => {
    const jahr = datum.getFullYear()
    const heute = heuteISO()
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {Array.from({ length: 12 }, (_, m) => {
          const erster = new Date(jahr, m, 1)
          const start = startOfWeek(erster)
          const zellen = Array.from({ length: 42 }, (_, i) => addDays(start, i))
          return (
            <div key={m} className="bg-white border border-neutral-200 rounded-xl p-3">
              <button
                onClick={() => { setDatum(erster); wechsleModus('monat') }}
                className="text-sm font-medium text-neutral-800 hover:text-primary-700 mb-2">
                {erster.toLocaleDateString('de-AT', { month: 'long' })}
              </button>
              <div className="grid grid-cols-7 gap-y-0.5">
                {WOCHENTAGE.map(w => (
                  <div key={w} className="text-center text-[9px] text-neutral-300">{w[0]}</div>
                ))}
                {zellen.map(tag => {
                  const iso = toISO(tag)
                  const n = (proTag[iso] || []).length
                  const imMonat = tag.getMonth() === m
                  const istHeute = iso === heute
                  return (
                    <button key={iso}
                      onClick={() => { setDatum(tag); wechsleModus('monat') }}
                      title={n ? `${n} Aufgabe${n === 1 ? '' : 'n'}` : undefined}
                      className={`relative text-[10px] w-6 h-6 mx-auto flex items-center justify-center rounded-full
                        ${!imMonat ? 'text-transparent pointer-events-none'
                          : istHeute ? 'bg-primary-600 text-white font-semibold'
                          : n ? 'text-neutral-800 font-medium hover:bg-primary-50'
                          : 'text-neutral-400 hover:bg-neutral-50'}`}>
                      {tag.getDate()}
                      {imMonat && n > 0 && !istHeute && (
                        <span className="absolute bottom-0.5 w-1 h-1 rounded-full bg-primary-500" />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
    )
  }

  return (
    <div>
      {/* Kopfzeile: Modus + Navigation */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="flex rounded-lg border border-gray-300 overflow-hidden">
          {MODI.map(m => (
            <button key={m.id} onClick={() => wechsleModus(m.id)}
              className={`px-3 py-1.5 text-sm ${modus === m.id
                ? 'bg-primary-600 text-white' : 'bg-white text-neutral-600 hover:bg-neutral-50'}`}>
              {m.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 ml-auto">
          <button onClick={() => springe(-1)}
            className="p-1.5 rounded-lg border border-gray-300 text-neutral-500 hover:bg-neutral-50">
            <ChevronLeft size={16} />
          </button>
          <button onClick={() => setDatum(new Date())}
            className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 text-neutral-600 hover:bg-neutral-50">
            Heute
          </button>
          <button onClick={() => springe(1)}
            className="p-1.5 rounded-lg border border-gray-300 text-neutral-500 hover:bg-neutral-50">
            <ChevronRight size={16} />
          </button>
          <span className="text-sm font-medium text-neutral-800 ml-2 whitespace-nowrap">{periodeLabel()}</span>
        </div>
      </div>

      {modus === 'arbeitswoche' && <Woche tage={5} />}
      {modus === 'woche' && <Woche tage={7} />}
      {modus === 'monat' && <Monat />}
      {modus === 'jahr' && <Jahr />}
    </div>
  )
}
