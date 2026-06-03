import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { invoiceApi, masterdataApi } from '../services/api'
import toast from 'react-hot-toast'
import {
  Save, ArrowLeft, Plus, Trash2, Search, ChevronDown,
  RefreshCw, GripVertical, FileText, Clock
} from 'lucide-react'

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────
function today() { return new Date().toISOString().slice(0, 10) }
function addDays(d, n) {
  const dt = new Date(d)
  dt.setDate(dt.getDate() + n)
  return dt.toISOString().slice(0, 10)
}
function calcLine(pos) {
  const qty = parseFloat(pos.quantity) || 0
  const price = parseFloat(pos.unit_price) || 0
  const disc = parseFloat(pos.discount_pct) || 0
  const base = qty * price * (1 - disc / 100)
  return Math.round(base * 100) / 100
}
function calcTotals(positions, taxMode) {
  let subtotal = 0, taxTotal = 0
  for (const p of positions) {
    const line = calcLine(p)
    subtotal += line
    if (taxMode !== 'kleinunternehmer' && p.tax_rate != null && p.tax_rate !== '') {
      taxTotal += line * parseFloat(p.tax_rate) / 100
    }
  }
  return {
    subtotal: Math.round(subtotal * 100) / 100,
    taxTotal: Math.round(taxTotal * 100) / 100,
    total: Math.round((subtotal + taxTotal) * 100) / 100,
  }
}
function fmtEuro(n) {
  return Number(n).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

const DOC_TYPE_LABELS = {
  rechnung: 'Rechnung',
  angebot: 'Angebot',
  gutschrift: 'Gutschrift',
  lieferschein: 'Lieferschein',
}

const EMPTY_POSITION = {
  pos_type: 'item',
  description: '',
  detail: '',
  quantity: '1',
  unit: 'Stk',
  unit_price: '0',
  discount_pct: '',
  tax_rate: '20',
  article_id: null,
  time_entry_id: null,
}

// ── Kontakt-Suche ─────────────────────────────────────────────────────────────
function ContactSearch({ value, label, onChange }) {
  const [search, setSearch] = useState(label || '')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const t = setTimeout(async () => {
      try {
        const res = await masterdataApi.listRecords('kontakte', { search: search || undefined, page_size: 20 })
        setResults(res.data.items || [])
      } catch { setResults([]) }
    }, 300)
    return () => clearTimeout(t)
  }, [search, open])

  return (
    <div className="relative">
      <input
        value={search}
        onChange={e => { setSearch(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder="Kontakt suchen…"
        className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
      />
      {open && results.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 bg-white border border-neutral-200 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto">
          {results.map(r => (
            <button
              key={r.id}
              className="w-full text-left px-3 py-2 text-sm hover:bg-neutral-50 border-b last:border-0"
              onMouseDown={() => {
                onChange(r.id, r.display_name)
                setSearch(r.display_name)
                setOpen(false)
              }}
            >
              <p className="font-medium text-neutral-800">{r.display_name}</p>
              <p className="text-xs text-neutral-400">{r.data?.typ || ''} · {r.data?.ort || ''}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Artikel-Suche für Position ────────────────────────────────────────────────
function ArticleSearch({ onSelect }) {
  const [search, setSearch] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const t = setTimeout(async () => {
      try {
        const res = await masterdataApi.listRecords('artikel', { search: search || undefined, page_size: 20 })
        setResults(res.data.items || [])
      } catch { setResults([]) }
    }, 300)
    return () => clearTimeout(t)
  }, [search, open])

  return (
    <div className="relative">
      <input
        value={search}
        onChange={e => { setSearch(e.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        placeholder="Artikel aus Stammdaten…"
        className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
      />
      {open && results.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 bg-white border border-neutral-200 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto">
          {results.map(r => (
            <button
              key={r.id}
              className="w-full text-left px-3 py-2 text-sm hover:bg-neutral-50 border-b last:border-0"
              onMouseDown={() => {
                onSelect({
                  article_id: r.id,
                  description: r.display_name,
                  unit_price: r.data?.preis || '0',
                  detail: r.data?.beschreibung || '',
                })
                setSearch('')
                setOpen(false)
              }}
            >
              <p className="font-medium text-neutral-800">{r.display_name}</p>
              <p className="text-xs text-neutral-400">{r.data?.artikelnummer || ''} · {r.data?.preis ? `${r.data.preis} €` : ''}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Zeiteinträge-Auswahl ──────────────────────────────────────────────────────
function TimeEntryPicker({ contactId, onAdd }) {
  const [entries, setEntries] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(new Set())

  async function load() {
    setLoading(true)
    try {
      const res = await invoiceApi.unbilledEntries(contactId ? { contact_id: contactId } : {})
      setEntries(res.data)
    } catch { toast.error('Fehler beim Laden der Zeiteinträge') }
    finally { setLoading(false) }
  }

  function toggle(id) {
    setSelected(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  }

  function addSelected() {
    const toAdd = entries.filter(e => selected.has(e.id))
    onAdd(toAdd)
    setOpen(false)
    setSelected(new Set())
  }

  return (
    <>
      <button
        type="button"
        onClick={() => { setOpen(true); load() }}
        className="flex items-center gap-1.5 text-sm text-blue-600 hover:underline"
      >
        <Clock size={14} /> Zeiteinträge übernehmen
      </button>
      {open && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-2xl max-h-[80vh] flex flex-col">
            <h2 className="text-base font-semibold mb-4">Nicht verrechnete Zeiteinträge</h2>
            {loading ? (
              <div className="flex-1 flex items-center justify-center"><RefreshCw size={20} className="animate-spin text-neutral-400" /></div>
            ) : entries.length === 0 ? (
              <p className="text-sm text-neutral-500 flex-1">Keine offenen Zeiteinträge gefunden.</p>
            ) : (
              <div className="flex-1 overflow-y-auto divide-y">
                {entries.map(e => (
                  <label key={e.id} className="flex items-center gap-3 py-2.5 hover:bg-neutral-50 cursor-pointer px-1">
                    <input type="checkbox" checked={selected.has(e.id)} onChange={() => toggle(e.id)} />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-neutral-800">{e.description || '(kein Titel)'}</p>
                      <p className="text-xs text-neutral-400">{e.project} · {new Date(e.started_at).toLocaleDateString('de-AT')}</p>
                    </div>
                    <span className="text-sm font-medium text-neutral-700">{Number(e.duration_hours).toFixed(2)} h</span>
                  </label>
                ))}
              </div>
            )}
            <div className="flex justify-end gap-2 mt-4 pt-4 border-t">
              <button onClick={() => setOpen(false)} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
              <button
                onClick={addSelected}
                disabled={selected.size === 0}
                className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                {selected.size} Eintrag/Einträge übernehmen
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ── Hauptformular ─────────────────────────────────────────────────────────────
export default function InvoiceFormPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const isNew = !id || id === 'new'

  const [docType, setDocType] = useState('rechnung')
  const [contactId, setContactId] = useState(null)
  const [contactLabel, setContactLabel] = useState('')
  const [projectId, setProjectId] = useState(null)
  const [title, setTitle] = useState('')
  const [date, setDate] = useState(today())
  const [dueDate, setDueDate] = useState(addDays(today(), 30))
  const [reference, setReference] = useState('')
  const [introText, setIntroText] = useState('')
  const [outroText, setOutroText] = useState('')
  const [notes, setNotes] = useState('')
  const [taxMode, setTaxMode] = useState('per_position')
  const [templateId, setTemplateId] = useState(1)
  const [positions, setPositions] = useState([{ ...EMPTY_POSITION }])
  const [nextNumber, setNextNumber] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(!isNew)

  // Defaulttexte laden
  useEffect(() => {
    invoiceApi.getSettings().then(res => {
      const s = res.data
      if (isNew) {
        setIntroText(s[`default_intro_${docType}`] || '')
        setOutroText(s[`default_outro_${docType}`] || '')
        if (s.default_payment_days) setDueDate(addDays(today(), parseInt(s.default_payment_days)))
        if (s.default_tax_rate) {
          setPositions([{ ...EMPTY_POSITION, tax_rate: String(s.default_tax_rate) }])
        }
      }
    }).catch(() => {})
  }, [docType]) // eslint-disable-line

  // Nächste Nummer
  useEffect(() => {
    if (!isNew) return
    invoiceApi.nextNumber(docType).then(res => setNextNumber(res.data.preview)).catch(() => {})
  }, [docType, isNew])

  // Bestehende Rechnung laden
  useEffect(() => {
    if (isNew) return
    setLoading(true)
    invoiceApi.get(id).then(res => {
      const inv = res.data
      setDocType(inv.doc_type)
      setContactId(inv.contact_id)
      setTitle(inv.title || '')
      setDate(inv.date)
      setDueDate(inv.due_date || '')
      setReference(inv.reference || '')
      setIntroText(inv.intro_text || '')
      setOutroText(inv.outro_text || '')
      setNotes(inv.notes || '')
      setTaxMode(inv.tax_mode)
      setTemplateId(inv.template_id)
      setPositions(inv.positions.length > 0 ? inv.positions.map(p => ({
        ...p,
        quantity: String(p.quantity),
        unit_price: String(p.unit_price),
        discount_pct: p.discount_pct != null ? String(p.discount_pct) : '',
        tax_rate: p.tax_rate != null ? String(p.tax_rate) : '',
      })) : [{ ...EMPTY_POSITION }])
    }).catch(() => toast.error('Fehler beim Laden')).finally(() => setLoading(false))
  }, [id, isNew])

  function addPosition(override = {}) {
    setPositions(p => [...p, { ...EMPTY_POSITION, ...override }])
  }

  function removePosition(i) {
    setPositions(p => p.filter((_, idx) => idx !== i))
  }

  function updatePosition(i, field, value) {
    setPositions(p => p.map((pos, idx) => idx === i ? { ...pos, [field]: value } : pos))
  }

  function addTimeEntries(entries) {
    const newPos = entries.map(e => ({
      ...EMPTY_POSITION,
      pos_type: 'time_entry',
      description: e.description || 'Zeitaufwand',
      quantity: String(e.duration_hours),
      unit: 'h',
      unit_price: '0',
      time_entry_id: e.id,
    }))
    setPositions(p => [...p, ...newPos])
  }

  const { subtotal, taxTotal, total } = calcTotals(positions, taxMode)

  async function handleSave() {
    if (positions.length === 0) { toast.error('Mindestens eine Position erforderlich'); return }
    setSaving(true)
    try {
      const payload = {
        doc_type: docType,
        contact_id: contactId || null,
        project_id: projectId || null,
        title: title || null,
        date,
        due_date: dueDate || null,
        reference: reference || null,
        intro_text: introText || null,
        outro_text: outroText || null,
        notes: notes || null,
        tax_mode: taxMode,
        template_id: templateId,
        positions: positions.map((p, i) => ({
          sort_order: i,
          pos_type: p.pos_type,
          description: p.description,
          detail: p.detail || null,
          quantity: parseFloat(p.quantity) || 1,
          unit: p.unit || null,
          unit_price: parseFloat(p.unit_price) || 0,
          discount_pct: p.discount_pct !== '' ? parseFloat(p.discount_pct) : null,
          tax_rate: p.tax_rate !== '' ? parseFloat(p.tax_rate) : null,
          article_id: p.article_id || null,
          time_entry_id: p.time_entry_id || null,
        })),
      }
      let res
      if (isNew) {
        res = await invoiceApi.create(payload)
        toast.success(`${DOC_TYPE_LABELS[docType]} ${res.data.number} erstellt`)
      } else {
        res = await invoiceApi.update(id, payload)
        toast.success('Gespeichert')
      }
      navigate(`/invoices/${res.data.id}`)
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <RefreshCw size={24} className="animate-spin text-neutral-400" />
    </div>
  )

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/invoices')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-neutral-900">
              {isNew ? `Neue ${DOC_TYPE_LABELS[docType]}` : `${DOC_TYPE_LABELS[docType]} bearbeiten`}
            </h1>
            {isNew && nextNumber && (
              <p className="text-sm text-neutral-400 mt-0.5">Nummer: {nextNumber}</p>
            )}
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-60"
        >
          {saving ? <RefreshCw size={15} className="animate-spin" /> : <Save size={15} />}
          Speichern
        </button>
      </div>

      <div className="space-y-5">
        {/* Dokumenttyp */}
        {isNew && (
          <div className="bg-white border border-neutral-200 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-neutral-700 mb-3">Dokumenttyp</h2>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(DOC_TYPE_LABELS).map(([k, v]) => (
                <button
                  key={k}
                  onClick={() => setDocType(k)}
                  className={`px-4 py-2 rounded-lg text-sm border transition-all ${
                    docType === k
                      ? 'bg-primary-600 text-white border-primary-600'
                      : 'text-neutral-700 border-neutral-200 hover:border-neutral-300'
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Stammdaten */}
        <div className="bg-white border border-neutral-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-neutral-700 mb-4">Grunddaten</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Kontakt</label>
              <ContactSearch
                value={contactId}
                label={contactLabel}
                onChange={(id, name) => { setContactId(id); setContactLabel(name) }}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Titel / Betreff</label>
              <input
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="z.B. Webentwicklung März 2026"
                className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Datum</label>
              <input type="date" value={date} onChange={e => setDate(e.target.value)}
                className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
            </div>
            {docType === 'rechnung' && (
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Zahlungsziel</label>
                <input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)}
                  className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Referenz / Ihre Bestellnummer</label>
              <input
                value={reference}
                onChange={e => setReference(e.target.value)}
                placeholder="optional"
                className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">MwSt.-Modus</label>
              <select value={taxMode} onChange={e => setTaxMode(e.target.value)}
                className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
                <option value="per_position">Pro Position wählbar</option>
                <option value="single_rate">Ein Satz für alle</option>
                <option value="kleinunternehmer">Kleinunternehmer (keine MwSt.)</option>
              </select>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Einleitungstext</label>
              <textarea value={introText} onChange={e => setIntroText(e.target.value)} rows={2}
                className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm resize-none" />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Schlusstext</label>
              <textarea value={outroText} onChange={e => setOutroText(e.target.value)} rows={2}
                className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm resize-none" />
            </div>
          </div>
        </div>

        {/* Positionen */}
        <div className="bg-white border border-neutral-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-neutral-700">Positionen</h2>
            <TimeEntryPicker contactId={contactId} onAdd={addTimeEntries} />
          </div>

          {/* Artikel-Suche */}
          <div className="mb-3">
            <ArticleSearch onSelect={(art) => addPosition(art)} />
          </div>

          {/* Positionstabelle */}
          <div className="space-y-2">
            {positions.map((pos, i) => (
              <PositionRow
                key={i}
                pos={pos}
                index={i}
                taxMode={taxMode}
                onChange={(field, val) => updatePosition(i, field, val)}
                onRemove={() => removePosition(i)}
              />
            ))}
          </div>

          <button
            type="button"
            onClick={() => addPosition()}
            className="mt-3 flex items-center gap-1.5 text-sm text-primary-600 hover:underline"
          >
            <Plus size={14} /> Position hinzufügen
          </button>

          {/* Summen */}
          <div className="mt-5 border-t pt-4 flex justify-end">
            <div className="w-64 space-y-1.5 text-sm">
              <div className="flex justify-between text-neutral-600">
                <span>Netto</span>
                <span>{fmtEuro(subtotal)}</span>
              </div>
              {taxMode !== 'kleinunternehmer' && (
                <div className="flex justify-between text-neutral-600">
                  <span>MwSt.</span>
                  <span>{fmtEuro(taxTotal)}</span>
                </div>
              )}
              <div className="flex justify-between font-semibold text-neutral-900 border-t pt-1.5">
                <span>Gesamt</span>
                <span>{fmtEuro(total)}</span>
              </div>
              {taxMode === 'kleinunternehmer' && (
                <p className="text-xs text-neutral-400 mt-1">Gemäß § 6 Abs. 1 Z 27 UStG keine USt.</p>
              )}
            </div>
          </div>
        </div>

        {/* PDF-Vorlage */}
        <div className="bg-white border border-neutral-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-neutral-700 mb-3">PDF-Vorlage</h2>
          <div className="flex gap-2 flex-wrap">
            {[1, 2, 3, 4, 5].map(n => (
              <button
                key={n}
                onClick={() => setTemplateId(n)}
                className={`w-20 h-24 rounded-lg border-2 text-sm transition-all flex flex-col items-center justify-center gap-1 ${
                  templateId === n ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-neutral-200 hover:border-neutral-300 text-neutral-600'
                }`}
              >
                <FileText size={20} />
                <span>Vorlage {n}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Interne Notiz */}
        <div className="bg-white border border-neutral-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-neutral-700 mb-3">Interne Notiz</h2>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={3}
            placeholder="Wird nicht auf dem Dokument gedruckt"
            className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm resize-none"
          />
        </div>
      </div>
    </div>
  )
}

// ── Positionszeile ────────────────────────────────────────────────────────────
function PositionRow({ pos, index, taxMode, onChange, onRemove }) {
  const lineTotal = calcLine(pos)

  return (
    <div className="border border-neutral-200 rounded-lg p-3 bg-neutral-50">
      <div className="grid grid-cols-12 gap-2 items-start">
        {/* Beschreibung */}
        <div className="col-span-12 md:col-span-5">
          <input
            value={pos.description}
            onChange={e => onChange('description', e.target.value)}
            placeholder="Beschreibung *"
            className="w-full border border-neutral-200 rounded px-2 py-1.5 text-sm bg-white"
          />
        </div>
        {/* Menge */}
        <div className="col-span-3 md:col-span-1">
          <input
            type="number"
            value={pos.quantity}
            onChange={e => onChange('quantity', e.target.value)}
            placeholder="Menge"
            className="w-full border border-neutral-200 rounded px-2 py-1.5 text-sm bg-white text-right"
          />
        </div>
        {/* Einheit */}
        <div className="col-span-3 md:col-span-1">
          <input
            value={pos.unit || ''}
            onChange={e => onChange('unit', e.target.value)}
            placeholder="Einh."
            className="w-full border border-neutral-200 rounded px-2 py-1.5 text-sm bg-white"
          />
        </div>
        {/* Preis */}
        <div className="col-span-3 md:col-span-2">
          <input
            type="number"
            step="0.01"
            value={pos.unit_price}
            onChange={e => onChange('unit_price', e.target.value)}
            placeholder="Preis"
            className="w-full border border-neutral-200 rounded px-2 py-1.5 text-sm bg-white text-right"
          />
        </div>
        {/* MwSt. */}
        {taxMode !== 'kleinunternehmer' && (
          <div className="col-span-3 md:col-span-1">
            <select
              value={pos.tax_rate}
              onChange={e => onChange('tax_rate', e.target.value)}
              className="w-full border border-neutral-200 rounded px-1 py-1.5 text-sm bg-white"
            >
              <option value="20">20%</option>
              <option value="10">10%</option>
              <option value="0">0%</option>
              <option value="">RC</option>
            </select>
          </div>
        )}
        {/* Gesamt */}
        <div className="col-span-2 md:col-span-1 flex items-center justify-end">
          <span className="text-sm font-medium text-neutral-800">{fmtEuro(lineTotal)}</span>
        </div>
        {/* Löschen */}
        <div className="col-span-1 flex items-center justify-center">
          <button onClick={onRemove} className="p-1 text-neutral-400 hover:text-red-500">
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      {/* Detail */}
      <input
        value={pos.detail || ''}
        onChange={e => onChange('detail', e.target.value)}
        placeholder="Zusatztext (optional)"
        className="mt-2 w-full border border-neutral-100 rounded px-2 py-1 text-xs bg-white text-neutral-500"
      />
    </div>
  )
}
