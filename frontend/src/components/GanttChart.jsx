import { useMemo, useRef, useState, useCallback } from 'react'
import { projektplanApi } from '../services/api'
import toast from 'react-hot-toast'

// ── Datums-Helfer ─────────────────────────────────────────────────────────────
const DAY = 86400000
function parseDate(s) { if (!s) return null; const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d) }
function toISO(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}` }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x }
function diffDays(a, b) { return Math.round((b - a) / DAY) }
function startOfDay(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x }

const DAY_W = 28          // Pixel pro Tag
const ROW_H = 36          // Zeilenhöhe
const NAME_W = 160        // Breite der fixierten Namensspalte

/** Flacht den Aufgabenbaum zu einer Liste mit Tiefe ab. */
function flatten(tasks, depth = 0, out = []) {
  for (const t of tasks) {
    out.push({ ...t, _depth: depth })
    if (t.children?.length) flatten(t.children, depth + 1, out)
  }
  return out
}

export default function GanttChart({ project, onChanged }) {
  const scrollRef = useRef(null)
  const [drag, setDrag] = useState(null)   // { id, mode:'move'|'start'|'end', startX, origStart, origEnd }
  const [preview, setPreview] = useState({})  // id -> {start_date, due_date}

  const rows = useMemo(() => flatten(project.tasks || []), [project.tasks])

  // Zeitfenster bestimmen
  const { minDate, totalDays } = useMemo(() => {
    let min = null, max = null
    const consider = (d) => { if (!d) return; if (!min || d < min) min = d; if (!max || d > max) max = d }
    rows.forEach(t => { consider(parseDate(t.start_date)); consider(parseDate(t.due_date)) });
    (project.milestones || []).forEach(m => consider(parseDate(m.due_date)))
    consider(startOfDay(new Date()))
    if (!min) { min = startOfDay(new Date()); max = addDays(min, 14) }
    min = addDays(min, -2); max = addDays(max, 4)
    return { minDate: min, totalDays: Math.max(14, diffDays(min, max)) }
  }, [rows, project.milestones])

  const dateToX = useCallback((d) => diffDays(minDate, d) * DAY_W, [minDate])
  const today = startOfDay(new Date())

  // Tagesraster + Monatsbeschriftung
  const days = useMemo(() => Array.from({ length: totalDays + 1 }, (_, i) => addDays(minDate, i)), [minDate, totalDays])

  // ── Drag-Logik ──────────────────────────────────────────────────────────────
  const effDates = (t) => {
    const p = preview[t.id]
    return { s: parseDate(p?.start_date ?? t.start_date), e: parseDate(p?.due_date ?? t.due_date) }
  }

  const onPointerDown = (e, t, mode) => {
    e.preventDefault(); e.stopPropagation()
    const { s, e: end } = effDates(t)
    if (!s || !end) return
    setDrag({ id: t.id, mode, startX: e.clientX, origStart: s, origEnd: end })
  }

  const onPointerMove = (e) => {
    if (!drag) return
    const deltaDays = Math.round((e.clientX - drag.startX) / DAY_W)
    if (deltaDays === 0) { setPreview(p => { const n = { ...p }; delete n[drag.id]; return n }); return }
    let ns = drag.origStart, ne = drag.origEnd
    if (drag.mode === 'move') { ns = addDays(drag.origStart, deltaDays); ne = addDays(drag.origEnd, deltaDays) }
    else if (drag.mode === 'start') { ns = addDays(drag.origStart, deltaDays); if (ns >= ne) ns = addDays(ne, -1) }
    else if (drag.mode === 'end') { ne = addDays(drag.origEnd, deltaDays); if (ne <= ns) ne = addDays(ns, 1) }
    setPreview(p => ({ ...p, [drag.id]: { start_date: toISO(ns), due_date: toISO(ne) } }))
  }

  const onPointerUp = async () => {
    if (!drag) return
    const pv = preview[drag.id]
    setDrag(null)
    if (!pv) return
    try {
      await projektplanApi.updateTaskDates([{ id: drag.id, start_date: pv.start_date, due_date: pv.due_date }])
      toast.success('Termin aktualisiert')
      onChanged?.()
    } catch {
      toast.error('Termin konnte nicht gespeichert werden')
      setPreview(p => { const n = { ...p }; delete n[drag.id]; return n })
    }
  }

  // ── Balken-Geometrie je Aufgabe ──────────────────────────────────────────────
  const barFor = (t) => {
    const { s, e } = effDates(t)
    if (!s || !e) return null
    const x = dateToX(s)
    const w = Math.max(DAY_W, (diffDays(s, e) + 1) * DAY_W)
    return { x, w }
  }

  const gridW = (totalDays + 1) * DAY_W

  // Abhängigkeitslinien (predecessor-Ende -> successor-Start)
  const rowIndex = useMemo(() => { const m = {}; rows.forEach((t, i) => { m[t.id] = i }); return m }, [rows])
  const depLines = useMemo(() => {
    const lines = []
    for (const d of project.dependencies || []) {
      const pi = rowIndex[d.predecessor_id], si = rowIndex[d.successor_id]
      if (pi == null || si == null) continue
      const pt = rows[pi], st = rows[si]
      const pb = barFor(pt), sb = barFor(st)
      if (!pb || !sb) continue
      const x1 = pb.x + pb.w, y1 = pi * ROW_H + ROW_H / 2
      const x2 = sb.x, y2 = si * ROW_H + ROW_H / 2
      lines.push({ x1, y1, x2, y2, key: d.id })
    }
    return lines
  }, [project.dependencies, rowIndex, rows, preview])

  if (rows.length === 0) {
    return <p className="text-center text-gray-400 text-sm py-8">Noch keine Aufgaben für die Zeitschiene.</p>
  }

  const totalH = rows.length * ROW_H

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden bg-white"
      onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={onPointerUp}>
      <div className="flex">
        {/* Fixierte Namensspalte */}
        <div className="shrink-0 border-r border-gray-200" style={{ width: NAME_W }}>
          <div className="h-[34px] border-b border-gray-200 bg-gray-50 flex items-center px-3 text-xs text-gray-500">Aufgabe</div>
          {rows.map((t) => (
            <div key={t.id} className="flex items-center text-sm text-gray-800 border-b border-gray-100 px-3 truncate"
              style={{ height: ROW_H, paddingLeft: 12 + t._depth * 12 }}>
              {t.is_critical && <span className="w-1.5 h-1.5 rounded-full bg-red-500 mr-1.5 shrink-0" />}
              <span className="truncate">{t.title}</span>
            </div>
          ))}
        </div>

        {/* Scrollbares Zeitraster */}
        <div ref={scrollRef} className="overflow-x-auto flex-1">
          <div style={{ width: gridW, position: 'relative' }}>
            {/* Kopf: Tages-/Monatsskala */}
            <div className="h-[34px] border-b border-gray-200 bg-gray-50 relative">
              {days.map((d, i) => (
                <div key={i} className="absolute top-0 bottom-0 flex items-center justify-center text-[9px] text-gray-400 border-l border-gray-100"
                  style={{ left: i * DAY_W, width: DAY_W }}>
                  {d.getDate() === 1 || i === 0
                    ? <span className="font-medium text-gray-600">{d.toLocaleDateString('de-DE', { month: 'short' })}</span>
                    : d.getDate()}
                </div>
              ))}
            </div>

            {/* Raster-Hintergrund + Wochenend-Schattierung */}
            <div className="relative" style={{ height: totalH }}>
              {days.map((d, i) => {
                const we = d.getDay() === 0 || d.getDay() === 6
                return <div key={i} className={`absolute top-0 bottom-0 border-l border-gray-100 ${we ? 'bg-gray-50/60' : ''}`}
                  style={{ left: i * DAY_W, width: DAY_W }} />
              })}

              {/* Heute-Linie */}
              {today >= minDate && (
                <div className="absolute top-0 bottom-0 w-px bg-primary-500 z-10" style={{ left: dateToX(today) + DAY_W / 2 }}>
                  <span className="absolute -top-0 left-1 text-[9px] text-primary-600">heute</span>
                </div>
              )}

              {/* Abhängigkeitslinien */}
              <svg className="absolute inset-0 pointer-events-none" width={gridW} height={totalH} style={{ zIndex: 5 }}>
                <defs>
                  <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                    <path d="M0,0 L6,3 L0,6 Z" fill="#9ca3af" />
                  </marker>
                </defs>
                {depLines.map(l => {
                  const midX = Math.max(l.x1 + 8, l.x2 - 8)
                  return <path key={l.key}
                    d={`M ${l.x1} ${l.y1} H ${midX} V ${l.y2} H ${l.x2}`}
                    fill="none" stroke="#9ca3af" strokeWidth="1.2" markerEnd="url(#arrow)" />
                })}
              </svg>

              {/* Aufgabenbalken + Meilensteine */}
              {rows.map((t, i) => {
                const y = i * ROW_H
                if (t.is_milestone) {
                  const { s } = effDates(t)
                  const d = s || parseDate(t.due_date)
                  if (!d) return null
                  const cx = dateToX(d) + DAY_W / 2
                  return <div key={t.id} className="absolute z-20" title={t.title}
                    style={{ left: cx - 7, top: y + ROW_H / 2 - 7, width: 14, height: 14, background: '#534AB7', transform: 'rotate(45deg)', borderRadius: 2 }} />
                }
                const bar = barFor(t)
                if (!bar) return null
                const done = t.status === 'erledigt'
                const color = t.is_critical ? '#e24b4a' : done ? '#1d9e75' : '#378add'
                const pct = t.estimate_minutes ? Math.min(100, Math.round((t.logged_minutes / t.estimate_minutes) * 100)) : (t.progress || 0)
                return (
                  <div key={t.id} className="absolute z-20 group" style={{ left: bar.x, top: y + 7, width: bar.w, height: ROW_H - 14 }}>
                    <div className="relative h-full rounded-md cursor-move select-none"
                      style={{ background: color, opacity: done ? 0.55 : 1 }}
                      onPointerDown={(e) => onPointerDown(e, t, 'move')} title={t.title}>
                      {/* Fortschritt */}
                      {pct > 0 && <div className="absolute inset-y-0 left-0 rounded-md bg-black/20" style={{ width: `${pct}%` }} />}
                      {/* Resize-Griffe */}
                      <div className="absolute inset-y-0 left-0 w-2 cursor-ew-resize" onPointerDown={(e) => onPointerDown(e, t, 'start')} />
                      <div className="absolute inset-y-0 right-0 w-2 cursor-ew-resize" onPointerDown={(e) => onPointerDown(e, t, 'end')} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Legende */}
      <div className="flex items-center gap-4 px-3 py-2 border-t border-gray-100 text-[11px] text-gray-500">
        <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm" style={{ background: '#e24b4a' }} /> kritischer Pfad</span>
        <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm" style={{ background: '#378add' }} /> Aufgabe</span>
        <span className="flex items-center gap-1"><span className="w-3 h-2 rounded-sm" style={{ background: '#1d9e75' }} /> erledigt</span>
        <span className="flex items-center gap-1"><span className="inline-block" style={{ width: 8, height: 8, background: '#534AB7', transform: 'rotate(45deg)' }} /> Meilenstein</span>
      </div>
    </div>
  )
}
