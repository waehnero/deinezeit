/**
 * Zeitprojekt-Suche – Auswahl des Stammsatzes, auf den gebucht wird.
 *
 * Sucht in den Zeitprojekten; ist der eingegebene Name unbekannt, lässt er
 * sich direkt hier anlegen und ist danach sofort ausgewählt. Zeigt zusätzlich
 * den Rest des Stundenkontos (BudgetBadge), damit beim Buchen auffällt, wenn
 * das Budget aufgebraucht ist.
 *
 * Begriffe: Zeitprojekt = Stammsatz, Projektzeit = einzelner Zeiteintrag.
 */
import { useState, useEffect, useRef } from 'react'
import { Plus, X, AlertTriangle, Search } from 'lucide-react'
import toast from 'react-hot-toast'
import { masterdataApi, zeiterfassungApi } from '../services/api'
import RecordModal from './RecordModal'
import { fmtBudgetMinutes } from './StundenkontenPanel'
import { ZEITPROJEKTE_SLUG } from '../utils/zeitprojekte'

export function BudgetBadge({ budget }) {
  if (!budget || !budget.has_budget) return null
  if (budget.exhausted) {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[11px] font-medium bg-red-50 text-red-600 border border-red-200 whitespace-nowrap"
        title="Budget verbraucht – dem Kunden ein neues Stundenkonto anbieten">
        <AlertTriangle size={10} />
        Rest {fmtBudgetMinutes(budget.remaining_minutes)} h
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[11px] font-medium bg-green-50 text-green-700 border border-green-200 whitespace-nowrap">
      Rest {fmtBudgetMinutes(budget.remaining_minutes)} h
    </span>
  )
}


export default function ZeitprojektSuche({ value, onChange, disabled, placeholder = 'Zeitprojekt suchen…', initialSearch = '' }) {
  const [search, setSearch] = useState(initialSearch)
  const [results, setResults] = useState([])
  // Mit vorbefülltem Suchbegriff (z.B. gesprochener Projektname aus dem
  // Sprach-Nachtragen) öffnet die Vorschlagsliste sofort zur Auswahl
  const [isOpen, setIsOpen] = useState(!!initialSearch && !value?.projectId)
  const [loading, setLoading] = useState(false)
  const [budgets, setBudgets] = useState({})          // { [projectId]: ProjectBudget }
  const [selectedBudget, setSelectedBudget] = useState(null)
  const [createType, setCreateType] = useState(null)  // EntityType der Zeitprojekte für den Anlegedialog
  const [createName, setCreateName] = useState('')
  const ref = useRef(null)

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setIsOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  useEffect(() => {
    if (!isOpen) return
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await masterdataApi.listRecords(ZEITPROJEKTE_SLUG, { search: search || undefined, page_size: 20 })
        const items = res.data.items.map(r => ({
          id: r.id,
          name: r.display_name,
          contactName: r.data?.kontakt?.display_name || r.data?.kunde?.display_name || '',
        }))
        setResults(items)
        // Rest-Budgets für die Vorschläge nachladen (Zusatzinfo, nicht blockierend)
        if (items.length) {
          zeiterfassungApi.getBudgets(items.map(i => i.id))
            .then(b => setBudgets(Object.fromEntries(b.data.map(x => [x.project_id, x]))))
            .catch(() => {})
        }
      } catch { setResults([]) }
      finally { setLoading(false) }
    }, 200)
    return () => clearTimeout(t)
  }, [search, isOpen])

  // Budget-Stand des ausgewählten Projekts laden
  useEffect(() => {
    if (!value?.projectId) { setSelectedBudget(null); return }
    zeiterfassungApi.getBudgets([value.projectId])
      .then(b => setSelectedBudget(b.data[0] || null))
      .catch(() => setSelectedBudget(null))
  }, [value?.projectId])

  const handleSelect = (item) => {
    onChange({ projectId: item.id, projectName: item.name, contactName: item.contactName })
    setIsOpen(false); setSearch('')
  }

  // Anlegedialog der Zeitprojekte öffnen (mit vorbefülltem Namen)
  const openCreate = async () => {
    try {
      const res = await masterdataApi.getType(ZEITPROJEKTE_SLUG)
      setCreateName(search.trim())
      setCreateType(res.data)
      setIsOpen(false)
    } catch {
      toast.error('Stammdaten-Typ „Zeitprojekte" nicht gefunden')
    }
  }

  // Vorbefüllung: eingegebener Name ins erste Textfeld des Typs
  const createInitialValues = () => {
    if (!createType || !createName) return null
    const firstText = [...createType.fields]
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
      .find(f => f.field_type === 'text')
    return firstText ? { [firstText.key]: createName } : null
  }

  const handleCreated = (record) => {
    onChange({
      projectId: record.id,
      projectName: record.display_name || createName,
      contactName: record.data?.kontakt?.display_name || record.data?.kunde?.display_name || '',
    })
    setCreateType(null)
    setSearch('')
  }

  const base = "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 transition disabled:bg-gray-50"

  // Exakter Treffer vorhanden? Sonst Anlegen anbieten
  const term = search.trim()
  const hasExactMatch = results.some(r => (r.name || '').toLowerCase() === term.toLowerCase())

  const createOption = term && !loading && !hasExactMatch && (
    <div className="border-t border-gray-100 px-3 py-2.5 bg-gray-50">
      <p className="text-xs text-gray-500 mb-1.5">
        „{term}" ist als Zeitprojekt nicht angelegt. Jetzt anlegen?
      </p>
      <button type="button" onClick={openCreate}
        className="flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:text-primary-700 transition">
        <Plus size={13} /> „{term}" als Zeitprojekt anlegen
      </button>
    </div>
  )

  if (value?.projectId) {
    return (
      <div>
        <div className="flex items-center gap-2 px-3 py-2 border rounded-lg bg-primary-50 border-primary-200">
          <span className="text-sm text-primary-800 flex-1 min-w-0 truncate">
            {value.contactName && <span className="text-primary-400">{value.contactName} / </span>}
            <span className="font-medium">{value.projectName}</span>
          </span>
          <BudgetBadge budget={selectedBudget} />
          {!disabled && (
            <button type="button" onClick={() => onChange({ projectId: null, projectName: '', contactName: '' })}
              className="text-primary-400 hover:text-red-500 transition">
              <X size={13} />
            </button>
          )}
        </div>
        {selectedBudget?.exhausted && (
          <p className="flex items-center gap-1.5 text-xs text-red-600 mt-1">
            <AlertTriangle size={12} className="flex-shrink-0" />
            Budget verbraucht – dem Kunden ein neues Stundenkonto anbieten.
          </p>
        )}
      </div>
    )
  }

  return (
    <div ref={ref} className="relative">
      <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
      <input type="text" value={search}
        onChange={(e) => { setSearch(e.target.value); setIsOpen(true) }}
        onFocus={() => setIsOpen(true)}
        placeholder={placeholder}
        className={`${base} pl-8`}
        disabled={disabled}
      />
      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-surface border border-gray-200 rounded-xl shadow-lg z-30 overflow-hidden">
          {results.length > 0 ? (
            <>
              <ul className="max-h-52 overflow-y-auto">
                {results.map(item => (
                  <li key={item.id}>
                    <button type="button" onClick={() => handleSelect(item)}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-primary-50 transition flex items-center gap-2">
                      <span className="flex flex-col flex-1 min-w-0">
                        <span className="font-medium text-gray-800 truncate">{item.name}</span>
                        {item.contactName && <span className="text-xs text-gray-400 truncate">{item.contactName}</span>}
                      </span>
                      <BudgetBadge budget={budgets[item.id]} />
                    </button>
                  </li>
                ))}
              </ul>
              {createOption}
            </>
          ) : (
            <>
              <div className="px-4 py-3 text-sm text-gray-400 text-center">
                {loading ? 'Suche…' : term ? 'Kein Zeitprojekt gefunden' : 'Namen des Zeitprojekts eingeben…'}
              </div>
              {createOption}
            </>
          )}
        </div>
      )}

      {/* Anlegedialog für ein neues Zeitprojekt */}
      {createType && (
        <RecordModal
          entityType={createType}
          record={null}
          initialValues={createInitialValues()}
          onClose={() => setCreateType(null)}
          onSaved={handleCreated}
        />
      )}
    </div>
  )
}
