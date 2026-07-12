import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, CornerDownLeft } from 'lucide-react'

// ⌘K-Befehlspalette (Design-Verfassung, Regel 5 · Musthave 2026):
// globale Suche über Module, Stammdaten-Typen und Aktionen.
// Öffnen: Cmd/Ctrl+K, Suchknopf im PageHeader (Custom-Event 'dz-palette')
// Bedienung: Tippen filtert · ↑/↓ wählt · Enter springt · Esc schließt
//
// `items`: [{ label, hint?, icon?, group, to? | action? }]

export function openCommandPalette() {
  window.dispatchEvent(new CustomEvent('dz-palette'))
}

export default function CommandPalette({ items = [] }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()

  // Öffnen per Tastatur (Cmd/Ctrl+K) und per Custom-Event (Suchknopf)
  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(o => !o)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    const onEvent = () => setOpen(true)
    window.addEventListener('keydown', onKey)
    window.addEventListener('dz-palette', onEvent)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('dz-palette', onEvent)
    }
  }, [])

  // Beim Öffnen: Eingabe fokussieren und zurücksetzen
  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
      setTimeout(() => inputRef.current?.focus(), 10)
    }
  }, [open])

  const gefiltert = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return items
    return items.filter(it =>
      it.label.toLowerCase().includes(q) ||
      (it.hint || '').toLowerCase().includes(q) ||
      (it.group || '').toLowerCase().includes(q)
    )
  }, [items, query])

  const ausfuehren = (it) => {
    setOpen(false)
    if (it.to) navigate(it.to)
    else if (it.action) it.action()
  }

  const onInputKey = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, gefiltert.length - 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setActive(a => Math.max(a - 1, 0)) }
    if (e.key === 'Enter' && gefiltert[active]) { e.preventDefault(); ausfuehren(gefiltert[active]) }
  }

  if (!open) return null

  // Gruppiert rendern (Module / Stammdaten / Aktionen), Reihenfolge der items
  const gruppen = []
  gefiltert.forEach(it => {
    let g = gruppen.find(x => x.name === it.group)
    if (!g) { g = { name: it.group, items: [] }; gruppen.push(g) }
    g.items.push(it)
  })
  let idx = -1

  return (
    <div className="fixed inset-0 z-[80] bg-neutral-900/40 backdrop-blur-sm flex items-start justify-center px-4 pt-[12vh] sheet-safe"
      onClick={() => setOpen(false)}>
      <div className="w-full max-w-xl bg-surface rounded-2xl shadow-2xl border border-neutral-200 overflow-hidden"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-3 px-4 border-b border-neutral-200">
          <Search size={17} className="text-neutral-400 flex-shrink-0" />
          <input ref={inputRef} value={query}
            onChange={e => { setQuery(e.target.value); setActive(0) }}
            onKeyDown={onInputKey}
            placeholder="Suchen oder Befehl eingeben…"
            className="w-full py-3.5 text-sm bg-transparent focus:outline-none text-neutral-900 placeholder-neutral-400" />
          <kbd className="hidden sm:block text-[10px] text-neutral-400 border border-neutral-200 rounded px-1.5 py-0.5 flex-shrink-0">Esc</kbd>
        </div>
        <div className="max-h-[50vh] overflow-y-auto py-2">
          {gefiltert.length === 0 && (
            <p className="px-4 py-6 text-sm text-neutral-400 text-center">Keine Treffer</p>
          )}
          {gruppen.map(g => (
            <div key={g.name}>
              <p className="px-4 pt-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-neutral-400">{g.name}</p>
              {g.items.map(it => {
                idx += 1
                const i = idx
                const Icon = it.icon
                return (
                  <button key={`${g.name}-${it.label}`} onClick={() => ausfuehren(it)}
                    onMouseEnter={() => setActive(i)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 text-sm text-left transition-colors ${
                      i === active ? 'bg-primary-50 text-primary-700' : 'text-neutral-700'
                    }`}>
                    {Icon && <Icon size={16} className={i === active ? 'text-primary-600' : 'text-neutral-400'} />}
                    <span className="flex-1 truncate">{it.label}</span>
                    {it.hint && <span className="text-xs text-neutral-400 truncate">{it.hint}</span>}
                    {i === active && <CornerDownLeft size={13} className="text-primary-400 flex-shrink-0" />}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
