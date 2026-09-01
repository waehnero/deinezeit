/**
 * Editierbares Uhrzeit-Feld mit Vorschlägen („Letzte Endzeit", „Jetzt").
 * Wird im Timer-Bereich und im Nachtragen-Dialog verwendet.
 */
import { useState, useEffect, useRef } from 'react'
import { Clock } from 'lucide-react'

export default function TimeSuggestInput({ value, onChange, suggestions = [], title }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  return (
    <div ref={ref} className="relative">
      <div className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-lg bg-surface focus-within:ring-2 focus-within:ring-primary-500">
        <Clock size={13} className="text-gray-400 flex-shrink-0" />
        <input type="time" value={value} title={title}
          onChange={(e) => { onChange(e.target.value); setOpen(false) }}
          onFocus={() => setOpen(true)}
          className="text-sm text-gray-700 bg-transparent outline-none w-full" />
      </div>
      {open && suggestions.filter(s => s.time).length > 0 && (
        <div className="absolute top-full right-0 mt-1 bg-surface border border-gray-200 rounded-xl shadow-lg z-30 overflow-hidden min-w-[11rem]">
          {suggestions.filter(s => s.time).map(s => (
            <button key={s.label} type="button"
              onMouseDown={(e) => e.preventDefault() /* Blur nicht vor Click */}
              onClick={() => { onChange(s.time); setOpen(false) }}
              className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-primary-50 transition">
              {s.label} <span className="text-gray-400">({s.time})</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
