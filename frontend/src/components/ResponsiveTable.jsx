import { useState, useEffect, useMemo, useRef } from 'react'
import { ArrowUp, ArrowDown, ChevronUp, ChevronDown, SlidersHorizontal, RotateCcw, X } from 'lucide-react'
import {
  ladeTabellenEinstellungen,
  speichereTabellenEinstellungen,
  loescheTabellenEinstellungen,
} from '../utils/tabelle'

// Einheitliche Listenansicht (Design-Verfassung, Regel 3):
// Desktop/Tablet = Tabelle · Handy = Karten — beide zeigen dieselben Felder
// in derselben Reihenfolge. Neue Module verwenden IMMER diese Komponente
// statt eigener <table>-Markups, damit Listen überall gleich aussehen.
//
// Verwendung:
//   <ResponsiveTable
//     columns={[
//       { key: 'name',  label: 'Name' },                                // Wert aus row[key]
//       { key: 'kunde', label: 'Kunde', render: r => r.kunde?.name },   // eigenes Rendering
//       { key: 'datum', label: 'Geändert', muted: true },               // gedämpfte Darstellung
//     ]}
//     rows={eintraege}
//     onRowClick={r => öffnen(r)}
//     actions={r => <RecordActions record={r} … />}                     // Knöpfe rechts
//   />
//
// ── Spalten selbst einstellen (optional) ────────────────────────────────────
// Mit `tableId` bekommt die Liste ein Spaltenmenü: Breite ziehen, Reihenfolge
// ändern, Spalten aus-/einblenden, je Spalte sortieren. Alles wird pro
// Benutzer und Gerät im Browser gemerkt (utils/tabelle.js).
//
//   <ResponsiveTable
//     tableId="datacenter-dateien"
//     standardSortierung={{ key: 'name', richtung: 'auf' }}
//     columns={[
//       { key: 'name', label: 'Name', breite: 320, minBreite: 140, fix: true,
//         render: r => …, sortWert: r => r.display_name || r.filename },
//       …
//     ]}
//     …
//   />
//
// Spalten-Eigenschaften (alle optional):
//   breite      Startbreite in Pixel (Standard 180)
//   minBreite   kleinste Breite beim Ziehen (Standard 70)
//   fix         Spalte kann nicht ausgeblendet werden (z.B. der Name)
//   sortierbar  false = Sortieren für diese Spalte abschalten
//   sortWert    Funktion für den Sortierwert, wenn `render` etwas anderes zeigt
//   nurTabelle  auf der Handy-Karte nicht anzeigen

const STANDARD_BREITE = 180
const MIN_BREITE      = 70
const AKTIONEN_BREITE = 132

// Sortiervergleich: Zahlen numerisch, ISO-Daten chronologisch, sonst
// deutschsprachig alphabetisch. Leere Werte landen immer am Ende.
function vergleiche(a, b) {
  const aLeer = a === null || a === undefined || a === ''
  const bLeer = b === null || b === undefined || b === ''
  if (aLeer && bLeer) return 0
  if (aLeer) return 1
  if (bLeer) return -1
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (a instanceof Date || b instanceof Date) return new Date(a) - new Date(b)
  const as = String(a), bs = String(b)
  const istIso = /^\d{4}-\d{2}-\d{2}/
  if (istIso.test(as) && istIso.test(bs)) return as < bs ? -1 : as > bs ? 1 : 0
  return as.localeCompare(bs, 'de', { numeric: true, sensitivity: 'base' })
}

// ── Spaltenmenü ──────────────────────────────────────────────────────────────

function SpaltenMenue({ spalten, versteckt, onUmschalten, onVerschieben, onZuruecksetzen, onClose }) {
  const box = useRef(null)

  useEffect(() => {
    const ausserhalb = (e) => { if (box.current && !box.current.contains(e.target)) onClose() }
    const escape = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('mousedown', ausserhalb)
    document.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('mousedown', ausserhalb)
      document.removeEventListener('keydown', escape)
    }
  }, [onClose])

  return (
    <div ref={box}
      className="absolute right-0 top-9 z-30 w-64 bg-surface border border-neutral-200 rounded-xl shadow-xl p-2">
      <div className="flex items-center justify-between px-2 py-1.5">
        <span className="text-xs font-semibold text-neutral-500 uppercase tracking-wide">Spalten</span>
        <button type="button" onClick={onClose}
          className="p-1 text-neutral-400 hover:text-neutral-700 rounded-lg" aria-label="Schließen">
          <X size={14} />
        </button>
      </div>

      <ul className="max-h-72 overflow-y-auto">
        {spalten.map((c, i) => {
          const sichtbar = c.fix || !versteckt.includes(c.key)
          return (
            <li key={c.key} className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-neutral-50">
              <input
                type="checkbox"
                checked={sichtbar}
                disabled={c.fix}
                onChange={() => onUmschalten(c.key)}
                className="w-4 h-4 rounded border-neutral-300 text-primary-600 focus:ring-primary-500 disabled:opacity-40"
              />
              <span className={`flex-1 min-w-0 truncate text-sm ${sichtbar ? 'text-neutral-700' : 'text-neutral-400'}`}>
                {c.label}
              </span>
              <button type="button" onClick={() => onVerschieben(i, -1)} disabled={i === 0}
                className="p-1 text-neutral-400 hover:text-neutral-700 disabled:opacity-25 rounded"
                aria-label="Nach vorne">
                <ChevronUp size={14} />
              </button>
              <button type="button" onClick={() => onVerschieben(i, 1)} disabled={i === spalten.length - 1}
                className="p-1 text-neutral-400 hover:text-neutral-700 disabled:opacity-25 rounded"
                aria-label="Nach hinten">
                <ChevronDown size={14} />
              </button>
            </li>
          )
        })}
      </ul>

      <button type="button" onClick={onZuruecksetzen}
        className="mt-1 w-full flex items-center justify-center gap-1.5 px-2 py-2 text-xs text-neutral-500 hover:text-neutral-800 hover:bg-neutral-50 rounded-lg">
        <RotateCcw size={13} /> Standard wiederherstellen
      </button>
    </div>
  )
}

// ── Tabelle ──────────────────────────────────────────────────────────────────

export default function ResponsiveTable({
  columns,
  rows,
  rowKey = (r) => r.id,
  onRowClick,
  zeileKlickbar = () => true,   // z.B. nur Zeilen mit Vorschau anklickbar machen
  actions,
  emptyText = 'Keine Einträge',
  tableId,                 // gesetzt = Spalten einstellbar und gespeichert
  standardSortierung = null,
  aktionenBreite = AKTIONEN_BREITE,   // Platz für die Knöpfe rechts
}) {
  const einstellbar = Boolean(tableId)

  const [einst, setEinst] = useState(() => {
    const geladen = ladeTabellenEinstellungen(tableId)
    return { ...geladen, sortierung: geladen.sortierung || standardSortierung }
  })
  const [menueOffen, setMenueOffen] = useState(false)

  // aktueller Stand für Handler, die außerhalb des Renders laufen (Ziehen)
  const einstRef = useRef(einst)
  einstRef.current = einst

  // Tabellen-ID gewechselt (andere Liste) → Einstellungen neu laden
  useEffect(() => {
    const geladen = ladeTabellenEinstellungen(tableId)
    setEinst({ ...geladen, sortierung: geladen.sortierung || standardSortierung })
  }, [tableId])   // eslint-disable-line react-hooks/exhaustive-deps

  const setzen = (patch, speichern = true) => {
    setEinst(prev => {
      const next = { ...prev, ...(typeof patch === 'function' ? patch(prev) : patch) }
      einstRef.current = next
      if (speichern && einstellbar) speichereTabellenEinstellungen(tableId, next)
      return next
    })
  }

  // Reihenfolge anwenden; Spalten, die es beim Speichern noch nicht gab,
  // hängen hinten an
  const geordnet = useMemo(() => {
    const offen = new Map(columns.map(c => [c.key, c]))
    const out = []
    einst.reihenfolge.forEach(k => {
      if (offen.has(k)) { out.push(offen.get(k)); offen.delete(k) }
    })
    columns.forEach(c => { if (offen.has(c.key)) out.push(c) })
    return out
  }, [columns, einst.reihenfolge])

  const sichtbare = geordnet.filter(c => c.fix || !einst.versteckt.includes(c.key))

  const breiteVon = (c) => einst.breiten[c.key] || c.breite || STANDARD_BREITE
  const gesamtBreite = sichtbare.reduce((s, c) => s + breiteVon(c), 0) + (actions ? aktionenBreite : 0)

  // Sortieren
  const sortierteZeilen = useMemo(() => {
    const s = einst.sortierung
    if (!einstellbar || !s?.key) return rows
    const c = columns.find(x => x.key === s.key)
    if (!c) return rows
    const wert = c.sortWert || ((r) => r[c.key])
    const faktor = s.richtung === 'ab' ? -1 : 1
    return [...(rows || [])].sort((a, b) => faktor * vergleiche(wert(a), wert(b)))
  }, [rows, columns, einst.sortierung, einstellbar])

  const sortierenNach = (c) => {
    if (!einstellbar || c.sortierbar === false) return
    const s = einst.sortierung
    // Klickfolge: aufsteigend → absteigend → keine Sortierung
    if (s?.key !== c.key)          setzen({ sortierung: { key: c.key, richtung: 'auf' } })
    else if (s.richtung === 'auf') setzen({ sortierung: { key: c.key, richtung: 'ab' } })
    else                           setzen({ sortierung: null })
  }

  // Breite ziehen (Maus und Touch über Pointer-Events)
  const zieheStart = (e, c) => {
    e.preventDefault()
    e.stopPropagation()
    const startX = e.clientX
    const startBreite = breiteVon(c)
    const min = c.minBreite || MIN_BREITE
    const bewegen = (ev) => {
      const neu = Math.max(min, Math.round(startBreite + (ev.clientX - startX)))
      // während des Ziehens nur anzeigen, nicht bei jedem Pixel speichern
      setzen(prev => ({ breiten: { ...prev.breiten, [c.key]: neu } }), false)
    }
    const ende = () => {
      window.removeEventListener('pointermove', bewegen)
      window.removeEventListener('pointerup', ende)
      document.body.style.userSelect = ''
      if (einstellbar) speichereTabellenEinstellungen(tableId, einstRef.current)
    }
    document.body.style.userSelect = 'none'
    window.addEventListener('pointermove', bewegen)
    window.addEventListener('pointerup', ende)
  }

  const umschalten = (key) => setzen(prev => ({
    versteckt: prev.versteckt.includes(key)
      ? prev.versteckt.filter(k => k !== key)
      : [...prev.versteckt, key],
  }))

  const verschieben = (index, richtung) => {
    const ziel = index + richtung
    if (ziel < 0 || ziel >= geordnet.length) return
    const keys = geordnet.map(c => c.key)
    const [k] = keys.splice(index, 1)
    keys.splice(ziel, 0, k)
    setzen({ reihenfolge: keys })
  }

  const zuruecksetzen = () => {
    loescheTabellenEinstellungen(tableId)
    setEinst({ breiten: {}, reihenfolge: [], versteckt: [], sortierung: standardSortierung })
    setMenueOffen(false)
  }

  const zelle = (c, r) => (c.render ? c.render(r) : (r[c.key] ?? '—'))
  const [erste, ...rest] = sichtbare.length ? sichtbare : columns

  if (!rows || rows.length === 0) {
    return <p className="px-4 py-10 text-sm text-neutral-400 text-center">{emptyText}</p>
  }

  return (
    <>
      {/* ── Leiste mit Spaltenmenü (nur Desktop/Tablet, nur wenn einstellbar) ── */}
      {einstellbar && (
        <div className="hidden md:flex justify-end px-3 pt-2 relative">
          <button type="button" onClick={() => setMenueOffen(o => !o)}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-neutral-500 hover:text-neutral-800 hover:bg-neutral-100 rounded-lg transition"
            title="Spalten einstellen">
            <SlidersHorizontal size={14} /> Spalten
          </button>
          {menueOffen && (
            <SpaltenMenue
              spalten={geordnet}
              versteckt={einst.versteckt}
              onUmschalten={umschalten}
              onVerschieben={verschieben}
              onZuruecksetzen={zuruecksetzen}
              onClose={() => setMenueOffen(false)}
            />
          )}
        </div>
      )}

      {/* ── Desktop / Tablet: Tabelle ── */}
      <div className="hidden md:block overflow-x-auto">
        <table
          className={`w-full ${einstellbar ? 'table-fixed' : ''}`}
          style={einstellbar ? { minWidth: gesamtBreite } : undefined}
        >
          {einstellbar && (
            <colgroup>
              {sichtbare.map(c => <col key={c.key} style={{ width: breiteVon(c) }} />)}
              {/* Füllspalte: schluckt überschüssige Breite, damit die
                  eingestellten Spaltenbreiten exakt erhalten bleiben */}
              <col />
              {actions && <col style={{ width: aktionenBreite }} />}
            </colgroup>
          )}
          <thead>
            <tr className="border-b border-neutral-100 bg-neutral-50">
              {sichtbare.map(c => {
                const sortiert = einst.sortierung?.key === c.key
                const kannSortieren = einstellbar && c.sortierbar !== false
                return (
                  <th key={c.key}
                    className="relative px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">
                    <span
                      onClick={() => sortierenNach(c)}
                      className={`flex items-center gap-1 select-none ${kannSortieren ? 'cursor-pointer hover:text-neutral-800' : ''}`}
                      title={kannSortieren ? 'Sortieren' : undefined}
                    >
                      <span className="truncate">{c.label}</span>
                      {sortiert && (einst.sortierung.richtung === 'auf'
                        ? <ArrowUp size={12} className="text-primary-600 flex-shrink-0" />
                        : <ArrowDown size={12} className="text-primary-600 flex-shrink-0" />)}
                    </span>
                    {einstellbar && (
                      // Ziehgriff am rechten Spaltenrand
                      <span
                        onPointerDown={(e) => zieheStart(e, c)}
                        onClick={(e) => e.stopPropagation()}
                        className="absolute top-0 right-0 h-full w-2 cursor-col-resize group/griff flex justify-center"
                        title="Breite ziehen"
                      >
                        <span className="w-px h-full bg-neutral-200 group-hover/griff:bg-primary-400" />
                      </span>
                    )}
                  </th>
                )
              })}
              {einstellbar && <th className="p-0" aria-hidden="true" />}
              {actions && (
                <th className="px-4 py-3 w-20 sticky right-0 bg-neutral-50 shadow-[-8px_0_8px_-8px_rgba(0,0,0,0.08)]" />
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-50">
            {sortierteZeilen.map(r => {
              const klickbar = Boolean(onRowClick) && zeileKlickbar(r)
              return (
              <tr key={rowKey(r)}
                className={`group transition hover:bg-neutral-50 ${klickbar ? 'cursor-pointer' : ''}`}
                onClick={() => { if (klickbar) onRowClick(r) }}>
                {sichtbare.map(c => (
                  <td key={c.key}
                    className={`px-4 py-3 text-sm ${c.muted ? 'text-neutral-400 whitespace-nowrap' : 'text-neutral-700'} ${einstellbar ? 'overflow-hidden' : ''}`}>
                    {zelle(c, r)}
                  </td>
                ))}
                {einstellbar && <td className="p-0" />}
                {actions && (
                  <td className="px-4 py-3 sticky right-0 bg-surface group-hover:bg-neutral-50 shadow-[-8px_0_8px_-8px_rgba(0,0,0,0.08)]">
                    <div className="flex items-center justify-end gap-1" onClick={e => e.stopPropagation()}>
                      {actions(r)}
                    </div>
                  </td>
                )}
              </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* ── Handy: Karten mit identischer Feldreihenfolge ── */}
      <div className="md:hidden divide-y divide-neutral-100">
        {sortierteZeilen.map(r => (
          <div key={rowKey(r)}
            className={`p-4 ${onRowClick && zeileKlickbar(r) ? 'active:bg-neutral-50' : ''}`}
            onClick={() => { if (onRowClick && zeileKlickbar(r)) onRowClick(r) }}>
            <div className="flex items-start justify-between gap-3">
              <div className="text-sm font-semibold text-neutral-900 min-w-0 pt-1">{zelle(erste, r)}</div>
              {actions && (
                <div className="flex items-center gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
                  {actions(r)}
                </div>
              )}
            </div>
            {rest.filter(c => !c.nurTabelle).length > 0 && (
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5">
                {rest.filter(c => !c.nurTabelle).map(c => (
                  <div key={c.key} className="min-w-0">
                    <dt className="text-[10px] uppercase tracking-wide text-neutral-400">{c.label}</dt>
                    <dd className="text-sm text-neutral-700 truncate">{zelle(c, r)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        ))}
      </div>
    </>
  )
}
