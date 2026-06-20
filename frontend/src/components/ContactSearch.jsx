import { useState, useEffect } from 'react'
import { Search, X, User } from 'lucide-react'
import { masterdataApi } from '../services/api'

/**
 * Wiederverwendbare Kontaktsuche über die Stammdaten (Slug: kontakte).
 *
 * Props:
 *   contactId   – aktuell gewählte Kontakt-ID (oder null)
 *   contactName – Anzeigename des gewählten Kontakts
 *   onChange(id, name) – Callback bei Auswahl/Entfernen (id/name = null beim Entfernen)
 *   placeholder, inheritedHint (optionaler Hinweistext, z. B. "vom Projekt geerbt")
 */
export default function ContactSearch({ contactId, contactName, onChange, placeholder = 'Kontakt suchen…', inheritedHint }) {
  const [search, setSearch] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!open) return
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await masterdataApi.listRecords('kontakte', { search: search || undefined, page_size: 20 })
        setResults(res.data.items || [])
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [search, open])

  // Bereits ein Kontakt gewählt -> kompakte Anzeige mit Entfernen
  if (contactId) {
    return (
      <div className="flex items-center gap-2 border border-gray-300 rounded-lg px-3 py-2">
        <User size={15} className="text-primary-500 shrink-0" />
        <span className="flex-1 text-sm text-gray-900 truncate">{contactName || 'Kontakt'}</span>
        {inheritedHint && <span className="text-[11px] text-gray-400 shrink-0">{inheritedHint}</span>}
        <button type="button" onClick={() => onChange(null, null)} className="text-gray-400 hover:text-red-600 shrink-0">
          <X size={15} />
        </button>
      </div>
    )
  }

  return (
    <div className="relative">
      <div className="flex items-center border border-gray-300 rounded-lg px-3 focus-within:border-primary-400">
        <Search size={15} className="text-gray-400 shrink-0" />
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); setOpen(true) }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder={placeholder}
          className="w-full py-2 px-2 text-sm focus:outline-none bg-transparent"
        />
      </div>
      {open && (
        <div className="absolute z-50 top-full left-0 right-0 bg-white border border-gray-200 rounded-lg shadow-lg mt-1 max-h-52 overflow-y-auto">
          {loading ? (
            <div className="px-3 py-2 text-xs text-gray-400">Suche…</div>
          ) : results.length === 0 ? (
            <div className="px-3 py-2 text-xs text-gray-400">
              {search ? 'Keine Kontakte gefunden' : 'Namen eingeben…'}
            </div>
          ) : (
            results.map((r) => (
              <button
                key={r.id} type="button"
                onMouseDown={() => { onChange(r.id, r.display_name); setSearch(''); setOpen(false) }}
                className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 border-b border-gray-100 last:border-0"
              >
                <p className="font-medium text-gray-800">{r.display_name}</p>
                {(r.data?.ort || r.data?.typ) && (
                  <p className="text-xs text-gray-400">{[r.data?.typ, r.data?.ort].filter(Boolean).join(' · ')}</p>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
