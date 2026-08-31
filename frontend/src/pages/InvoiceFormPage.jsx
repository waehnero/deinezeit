import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { getAccessToken, invoiceApi, masterdataApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import {
  Save, ArrowLeft, Plus, Trash2, Search,
  RefreshCw, FileText, Clock, Download, Eye, Repeat, Paperclip, X as XIcon,
  Lock, History, ChevronUp, ChevronDown, Image as ImageIcon, Bell, Layers, FileCode
} from 'lucide-react'

function today() { return new Date().toISOString().slice(0, 10) }
function addDays(d, n) {
  const dt = new Date(d); dt.setDate(dt.getDate() + n); return dt.toISOString().slice(0, 10)
}
function calcLine(pos) {
  const qty = parseFloat(pos.quantity) || 0
  const price = parseFloat(pos.unit_price) || 0
  const disc = parseFloat(pos.discount_pct) || 0
  return Math.round(qty * price * (1 - disc / 100) * 100) / 100
}
// Zeilen, die nur der Gliederung dienen (siehe backend/app/services/positionen.py)
const GLIEDERUNG = ['heading', 'text', 'subtotal']
// Abzug einer bereits gestellten Anzahlung. Wird serverseitig gerechnet und
// hier nur angezeigt — die Zeile trägt einen negativen Betrag.
const ANZAHLUNGSABZUG = 'advance_deduction'

/** Index, ab dem die Gruppe der Zeile bei `index` zählt. */
function gruppeAb(positions, index) {
  for (let i = index - 1; i >= 0; i--) {
    if (['heading', 'subtotal'].includes(positions[i].pos_type)) return i + 1
  }
  return 0
}

/** Nettosumme der laufenden Gruppe — Grundlage für Rabatt und Zwischensumme. */
function gruppenSumme(positions, ab, bis, mitRabatt = false) {
  let s = 0
  for (let i = ab; i < bis; i++) {
    const p = positions[i]
    if (GLIEDERUNG.includes(p.pos_type)) continue
    if (p.pos_type === 'discount') { if (mitRabatt) s += calcZeile(positions, i); continue }
    // Ein Rabatt bezieht sich auf die Leistung, nicht auf einen Abzug —
    // sonst würde er den Abzug mitrabattieren.
    if (p.pos_type === ANZAHLUNGSABZUG) continue
    s += calcLine(p)
  }
  return Math.round(s * 100) / 100
}

/** Betrag einer beliebigen Zeile — Rabatt und Zwischensumme brauchen Kontext. */
function calcZeile(positions, index) {
  const p = positions[index]
  const typ = p.pos_type || 'item'
  if (typ === 'heading' || typ === 'text') return 0
  const ab = gruppeAb(positions, index)
  if (typ === 'subtotal') return gruppenSumme(positions, ab, index, true)
  if (typ === 'discount') {
    const basis = gruppenSumme(positions, ab, index)
    const betrag = p.discount_pct
      ? Math.round(basis * parseFloat(p.discount_pct)) / 100
      : parseFloat(p.unit_price) || 0
    return -Math.min(Math.max(betrag, 0), Math.max(basis, 0))
  }
  return calcLine(p)
}

function calcTotals(positions, taxMode) {
  let subtotal = 0, taxTotal = 0
  positions.forEach((p, i) => {
    const typ = p.pos_type || 'item'
    if (GLIEDERUNG.includes(typ)) return
    const line = calcZeile(positions, i)
    subtotal += line
    if (taxMode === 'kleinunternehmer') return
    if (typ === 'discount') {
      // Anteilig auf die Sätze der Gruppe — wie im Backend
      const ab = gruppeAb(positions, i)
      const basis = gruppenSumme(positions, ab, i)
      if (basis <= 0) return
      for (let j = ab; j < i; j++) {
        const q = positions[j]
        if (GLIEDERUNG.includes(q.pos_type) || q.pos_type === 'discount') continue
        if (q.tax_rate == null || q.tax_rate === '') continue
        taxTotal += (line * calcLine(q) / basis) * parseFloat(q.tax_rate) / 100
      }
      return
    }
    if (p.tax_rate != null && p.tax_rate !== '')
      taxTotal += line * parseFloat(p.tax_rate) / 100
  })
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
  rechnung: 'Rechnung', angebot: 'Angebot',
  auftragsbestaetigung: 'Auftragsbestätigung',
  gutschrift: 'Gutschrift', lieferschein: 'Lieferschein',
}

const EMPTY_POSITION = {
  pos_type: 'item', description: '', detail: '', quantity: '1', unit: 'Stk',
  unit_price: '0', discount_pct: '', tax_rate: '20', article_id: null, time_entry_id: null,
}

function ContactSearch({ value, label, onChange }) {
  const [search, setSearch] = useState(label || '')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  // Sync wenn label von außen gesetzt wird (z.B. nach async Kontakt-Lookup beim Laden)
  useEffect(() => { if (label) setSearch(label) }, [label])
  useEffect(() => {
    if (!open) return
    const t = setTimeout(async () => {
      try { const res = await masterdataApi.listRecords('kontakte', { search: search || undefined, page_size: 20 }); setResults(res.data.items || []) }
      catch { setResults([]) }
    }, 300)
    return () => clearTimeout(t)
  }, [search, open])
  return (
    <div className="relative">
      <input value={search} onChange={e => { setSearch(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
        placeholder="Kontakt suchen…" className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300" />
      {open && results.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 bg-surface border border-neutral-200 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto">
          {results.map(r => (
            <button key={r.id} className="w-full text-left px-3 py-2 text-sm hover:bg-neutral-50 border-b last:border-0"
              onMouseDown={() => { onChange(r.id, r.display_name); setSearch(r.display_name); setOpen(false) }}>
              <p className="font-medium text-neutral-800">{r.display_name}</p>
              <p className="text-xs text-neutral-400">{r.data?.typ || ''} · {r.data?.ort || ''}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ArticleSearch({ onSelect, contactId }) {
  const [search, setSearch] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const t = setTimeout(async () => {
      try { const res = await masterdataApi.listRecords('artikel', { search: search || undefined, page_size: 20 }); setResults(res.data.items || []) }
      catch { setResults([]) }
    }, 300)
    return () => clearTimeout(t)
  }, [search, open])
  return (
    <div className="relative">
      <input value={search} onChange={e => { setSearch(e.target.value); setOpen(true) }} onFocus={() => setOpen(true)}
        placeholder="Artikel aus Stammdaten…" className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300" />
      {open && results.length > 0 && (
        <div className="absolute z-50 top-full left-0 right-0 bg-surface border border-neutral-200 rounded-lg shadow-lg mt-1 max-h-48 overflow-y-auto">
          {results.map(r => (
            <button key={r.id} className="w-full text-left px-3 py-2 text-sm hover:bg-neutral-50 border-b last:border-0"
              onMouseDown={async () => {
                // Grundwerte sofort übernehmen, damit die Position auch dann
                // entsteht, wenn die Vorgaben-Abfrage scheitert.
                const basis = {
                  article_id: r.id,
                  description: r.display_name,
                  unit_price: r.data?.preis != null ? String(r.data.preis) : '0',
                  unit: r.data?.einheit || 'Stk',
                  detail: r.data?.beschreibung || '',
                  account_nr: r.data?.erloes_konto || null,
                }
                // Konto, USt-Satz und Einheit über die Kaskade auflösen
                // (Artikel → Artikelgruppe → Standard-Erlöskonto). Die
                // Auflösung macht der Server: Läge sie hier, gäbe es zwei
                // Auslegungen davon, welches Konto gilt — und die im Browser
                // wäre die, die keiner prüft.
                try {
                  // Der Kunde bestimmt den Steuerfall und damit Konto und Satz.
                  const { data: v } = await masterdataApi.artikelVorgaben(r.id, contactId)
                  basis.account_nr = v.erloes_konto || basis.account_nr
                  basis.unit = v.einheit || basis.unit
                  // Reverse Charge heißt: gar kein Steuersatz, nicht 0 %.
                  // Eine Null erschiene in der UVA als steuerfreier Umsatz.
                  // Im Formular steht dafür der Leerstring — beim Speichern
                  // wird daraus NULL (siehe Aufbereitung der Positionen).
                  if (v.reverse_charge) basis.tax_rate = ''
                  else if (v.ust_satz != null) basis.tax_rate = String(Number(v.ust_satz))
                } catch { /* Vorgaben sind Komfort — die Position entsteht auch ohne */ }
                onSelect(basis)
                setSearch(''); setOpen(false)
              }}>
              <p className="font-medium text-neutral-800">{r.display_name}</p>
              <p className="text-xs text-neutral-400">{r.data?.artikelnummer || ''} · {r.data?.preis ? r.data.preis + ' €' : ''}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function TimeEntryPicker({ contactId, onAdd }) {
  const [entries, setEntries] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(new Set())
  const [search, setSearch] = useState('')

  async function load(searchVal = '') {
    setLoading(true)
    try {
      const params = {}
      if (contactId) params.contact_id = contactId
      if (searchVal) params.search = searchVal
      const res = await invoiceApi.unbilledEntries(params)
      setEntries(res.data)
    } catch { toast.error('Fehler beim Laden der Zeiteinträge') }
    finally { setLoading(false) }
  }

  useEffect(() => {
    if (!open) return
    const t = setTimeout(() => load(search), 350)
    return () => clearTimeout(t)
  }, [search, open]) // eslint-disable-line

  const totalHours = entries.filter(e => selected.has(e.id)).reduce((s, e) => s + Number(e.duration_hours), 0)

  return (
    <>
      <button type="button" onClick={() => { setOpen(true); setSearch(''); setSelected(new Set()); load('') }}
        className="flex items-center gap-1.5 text-sm text-blue-600 hover:underline">
        <Clock size={14} /> Zeiteinträge übernehmen
      </button>
      {open && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 sheet-safe">
          <div className="max-h-full overflow-y-auto bg-surface rounded-xl shadow-xl p-6 w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-base font-semibold">Nicht verrechnete Zeiteinträge</h2>
              {entries.length > 0 && <button onClick={() => setSelected(new Set(entries.map(e => e.id)))} className="text-xs text-primary-600 hover:underline">Alle auswählen</button>}
            </div>
            <div className="relative mb-3">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Kontakt, Projekt oder Beschreibung…"
                className="w-full pl-8 pr-3 py-2 text-sm border border-neutral-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-300" />
            </div>
            {loading ? (
              <div className="flex-1 flex items-center justify-center py-8"><RefreshCw size={20} className="animate-spin text-neutral-400" /></div>
            ) : entries.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center py-8 px-6 text-neutral-400">
                <Clock size={28} className="mb-2 opacity-30" />
                <p className="text-sm">Keine offenen Zeiteinträge gefunden</p>
                {/* Erklärt die Auswahlregeln — eine leere Liste ist sonst nicht
                    von einem Fehler zu unterscheiden. */}
                <p className="text-xs mt-3 max-w-md text-center leading-relaxed">
                  Angezeigt werden nur abgeschlossene, verrechenbare Zeiteinträge
                  mit dem Status <strong className="text-neutral-500">„Freigegeben“</strong>,
                  die noch auf keinem Beleg stehen.
                  {contactId && ' Außerdem ist nach dem Kontakt des Belegs gefiltert.'}
                </p>
                <p className="text-xs mt-1 text-neutral-300">
                  Freigeben lassen sich Einträge in der Zeiterfassung über das Status-Symbol.
                </p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto divide-y border rounded-lg">
                {entries.map(e => (
                  <label key={e.id} className="flex items-center gap-3 py-2.5 hover:bg-neutral-50 cursor-pointer px-3">
                    <input type="checkbox" checked={selected.has(e.id)} onChange={() => setSelected(s => { const n = new Set(s); n.has(e.id) ? n.delete(e.id) : n.add(e.id); return n })} className="w-4 h-4 rounded" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-neutral-800 truncate">{e.description || '(kein Titel)'}</p>
                      <p className="text-xs text-neutral-400 truncate">{[e.contact, e.project].filter(Boolean).join(' · ')}{e.started_at && ' · ' + new Date(e.started_at).toLocaleDateString('de-AT')}</p>
                    </div>
                    <span className="text-sm font-medium text-neutral-700 whitespace-nowrap">{Number(e.duration_hours).toFixed(2)} h</span>
                  </label>
                ))}
              </div>
            )}
            <div className="flex items-center justify-between mt-4 pt-4 border-t">
              <div className="text-xs text-neutral-500">
                {selected.size > 0 && <span>{selected.size} ausgewählt · <strong>{totalHours.toFixed(2)} h</strong></span>}
              </div>
              <div className="flex gap-2">
                <button onClick={() => setOpen(false)} className="px-4 py-2 text-sm border rounded-lg hover:bg-neutral-50">Abbrechen</button>
                <button onClick={() => { const toAdd = entries.filter(e => selected.has(e.id)); onAdd(toAdd); setOpen(false); setSelected(new Set()); setSearch('') }}
                  disabled={selected.size === 0} className="px-4 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
                  {selected.size > 0 ? selected.size + ' übernehmen' : 'Übernehmen'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default function InvoiceFormPage() {
  const { id } = useParams()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const isNew = !id || id === 'new'
  // Das Mahn-Panel hängt am Zusatzrecht: Ohne das Recht antworten die
  // Endpunkte mit 403, das Panel bliebe leer.
  const { hasModule } = useAuth()
  const hatBuchhaltung = hasModule('buchhaltung')

  const [docType, setDocType] = useState(searchParams.get('type') || 'rechnung')
  const [contactId, setContactId] = useState(null)
  const [contactLabel, setContactLabel] = useState('')
  // Belegstatus steuert die Sperre: Ein finalisierter Beleg (Status ≠ Entwurf)
  // darf inhaltlich nicht mehr verändert werden — das PDF wird bei jedem
  // Abruf neu erzeugt und würde sich sonst rückwirkend ändern.
  const [status, setStatus] = useState('entwurf')
  const [number, setNumber] = useState(null)
  // Nur durchgereicht, damit Speichern sie nicht verliert
  const [projectId, setProjectId] = useState(null)
  const [currency, setCurrency] = useState('EUR')
  const [title, setTitle] = useState('')
  const [date, setDate] = useState(today())
  const [dueDate, setDueDate] = useState(addDays(today(), 30))
  // Bindefrist des Angebots. Leer lassen ist erlaubt — dann gilt es unbefristet.
  const [validUntil, setValidUntil] = useState('')
  // Abrechnung in Stufen: '' = gewöhnliche Rechnung
  const [billingStage, setBillingStage] = useState('')
  const [chainId, setChainId] = useState(null)
  const [strang, setStrang] = useState(null)
  // Zahlungsbedingung: "x % Skonto binnen y Tagen". Steht auf dem Beleg und
  // ist nach dem Ausstellen gesperrt — eine Zusage ändert man nicht nachträglich.
  const [skontoPercent, setSkontoPercent] = useState('')
  const [skontoDays, setSkontoDays] = useState('')
  // Liefer-/Leistungsdatum (Pflicht bei Rechnung und Gutschrift, § 11 UStG).
  // Mit Bis-Datum wird daraus ein Leistungszeitraum.
  const [deliveryDate, setDeliveryDate] = useState(today())
  const [deliveryDateTo, setDeliveryDateTo] = useState('')
  const [istZeitraum, setIstZeitraum] = useState(false)
  // Gepflegte Steuersätze aus den Verkaufseinstellungen
  const [taxRates, setTaxRates] = useState([])
  const [reference, setReference] = useState('')
  const [introText, setIntroText] = useState('')
  const [outroText, setOutroText] = useState('')
  const [notes, setNotes] = useState('')
  const [taxMode, setTaxMode] = useState('per_position')
  // PDF-Vorlage: bei neuen Belegen aus den Belegeinstellungen (default_template),
  // bei bestehenden die am Beleg gespeicherte — vorher war hier fix die 1,
  // dadurch waren die Vorlagen 2–5 nicht erreichbar.
  const [templateId, setTemplateId] = useState(1)
  const [positions, setPositions] = useState([{ ...EMPTY_POSITION }])
  const [nextNumber, setNextNumber] = useState('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(!isNew)
  // Wiederkehrende Rechnung (nur doc_type=rechnung)
  const [isRecurring, setIsRecurring] = useState(false)
  const [recurringInterval, setRecurringInterval] = useState('monthly')
  const [recurringNext, setRecurringNext] = useState(today())
  const [recurringEnd, setRecurringEnd] = useState('')
  // Was am Stichtag geschehen soll: erinnern | Entwurf anlegen | anlegen und senden
  const [recurringAction, setRecurringAction] = useState('create')
  const [contracts, setContracts] = useState([])   // [{id, filename}, …] bereits hinterlegt
  const [contractUploading, setContractUploading] = useState(false)
  const MAX_CONTRACTS = 10

  useEffect(() => {
    invoiceApi.getSettings().then(res => {
      const s = res.data
      if (Array.isArray(s.tax_rates)) setTaxRates(s.tax_rates.filter(t => t.aktiv))
      if (isNew) {
        setIntroText(s['default_intro_' + docType] || '')
        setOutroText(s['default_outro_' + docType] || '')
        if (s.default_payment_days) setDueDate(addDays(today(), parseInt(s.default_payment_days)))
        // Vorbelegter Steuersatz: bevorzugt der als Standard markierte Satz
        // aus der gepflegten Liste, sonst der alte Einzelwert.
        const standard = (s.tax_rates || []).find(t => t.standard && t.aktiv)
        const satz = standard ? standard.satz : s.default_tax_rate
        if (satz != null) setPositions([{ ...EMPTY_POSITION, tax_rate: String(satz) }])
        if (s.default_template) setTemplateId(Number(s.default_template) || 1)
      }
    }).catch(() => {})
  }, [docType]) // eslint-disable-line

  // Vorschau der künftigen Nummer — auch für gespeicherte Entwürfe, die noch
  // keine haben (die Nummer fällt erst beim Finalisieren).
  useEffect(() => {
    if (!isNew && number) return
    invoiceApi.nextNumber(docType).then(res => setNextNumber(res.data.preview)).catch(() => {})
  }, [docType, isNew, number])

  useEffect(() => {
    if (isNew) return
    setLoading(true)
    invoiceApi.get(id).then(res => {
      const inv = res.data
      setDocType(inv.doc_type); setContactId(inv.contact_id); setTitle(inv.title || '')
      setStatus(inv.status); setNumber(inv.number)
      setProjectId(inv.project_id || null); setCurrency(inv.currency || 'EUR')
      // Kontaktname laden
      if (inv.contact_id) {
        masterdataApi.getRecord('kontakte', inv.contact_id)
          .then(r => setContactLabel(r.data.display_name || ''))
          .catch(() => {})
      }
      setDate(inv.date); setDueDate(inv.due_date || ''); setReference(inv.reference || '')
      setSkontoPercent(inv.skonto_percent ?? '')
      setSkontoDays(inv.skonto_days ?? '')
      setValidUntil(inv.valid_until || '')
      setBillingStage(inv.billing_stage || '')
      setChainId(inv.chain_id || null)
      setDeliveryDate(inv.delivery_date || inv.date)
      setDeliveryDateTo(inv.delivery_date_to || '')
      setIstZeitraum(!!inv.delivery_date_to)
      setIntroText(inv.intro_text || ''); setOutroText(inv.outro_text || ''); setNotes(inv.notes || '')
      setTaxMode(inv.tax_mode)
      setTemplateId(inv.template_id || 1)
      setIsRecurring(!!inv.is_recurring_template)
      if (inv.recurring_interval) setRecurringInterval(inv.recurring_interval)
      if (inv.recurring_next) setRecurringNext(inv.recurring_next)
      setRecurringEnd(inv.recurring_end || '')
      setRecurringAction(inv.recurring_action || 'create')
      setContracts((inv.attachments || [])
        .filter(a => a.attach_type === 'contract')
        .map(a => ({ id: a.id, filename: a.filename })))
      setPositions(inv.positions.length > 0 ? inv.positions.map(p => ({
        ...p, quantity: String(p.quantity), unit_price: String(p.unit_price),
        discount_pct: p.discount_pct != null ? String(p.discount_pct) : '',
        tax_rate: p.tax_rate != null ? String(p.tax_rate) : '',
      })) : [{ ...EMPTY_POSITION }])
    }).catch(() => toast.error('Fehler beim Laden')).finally(() => setLoading(false))
  }, [id, isNew])

  function addPosition(override = {}) { setPositions(p => [...p, { ...EMPTY_POSITION, ...override }]) }
  function removePosition(i) { setPositions(p => p.filter((_, idx) => idx !== i)) }
  /**
   * Zeile um eine Stelle verschieben.
   *
   * Reine Anzeigereihenfolge — das Backend übernimmt beim Speichern den Index
   * der Liste als sort_order. Wichtig: Zwischensumme und Rabatt rechnen nach
   * Position, ihre Beträge ändern sich beim Verschieben also mit. Das ist
   * gewollt und wird sofort sichtbar, weil die Summen aus dem Array kommen.
   */
  function movePosition(i, richtung) {
    const ziel = i + richtung
    setPositions(p => {
      if (ziel < 0 || ziel >= p.length) return p
      const neu = [...p]
      ;[neu[i], neu[ziel]] = [neu[ziel], neu[i]]
      return neu
    })
  }
  function updatePosition(i, field, value) { setPositions(p => p.map((pos, idx) => idx === i ? { ...pos, [field]: value } : pos)) }
  /**
   * Kunde wechseln — und die Positionen an seinen Steuerfall anpassen.
   *
   * Der Steuerfall (Inland, innergemeinschaftlich, Drittland, Reverse Charge)
   * hängt am Kontakt und entscheidet über Erlöskonto und Steuersatz. Wird der
   * Kunde nachträglich gewechselt, passen die schon erfassten Positionen
   * womöglich nicht mehr.
   *
   * Neu bestimmt werden nur **unberührte** Positionen: solche, deren Konto und
   * Satz noch genau dem entsprechen, was die Auflösung für den alten Kunden
   * ergeben hätte. Wer ein Konto bewusst abweichend gesetzt hat, behält es —
   * ein Sonderkonto für ein Projekt darf nicht dadurch verschwinden, dass
   * jemand den Kunden korrigiert.
   *
   * Was geändert wurde, wird anschließend gemeldet. Eine stille Umbuchung wäre
   * hier das Schlimmste: Sie beträfe die Konten, auf denen der Umsatz landet.
   */
  async function kontaktWechseln(cid, name) {
    const alterKontakt = contactId
    setContactId(cid)
    setContactLabel(name)

    const kandidaten = positions
      .map((pos, i) => ({ pos, i }))
      .filter(({ pos }) => pos.article_id)
    if (!kandidaten.length || cid === alterKontakt) return

    try {
      const geaendert = []
      const neu = [...positions]

      for (const { pos, i } of kandidaten) {
        const [alt, jetzt] = await Promise.all([
          masterdataApi.artikelVorgaben(pos.article_id, alterKontakt),
          masterdataApi.artikelVorgaben(pos.article_id, cid),
        ])
        const altSatz = alt.data.reverse_charge ? '' : (alt.data.ust_satz != null ? String(Number(alt.data.ust_satz)) : '')
        const unberuehrt = (pos.account_nr || null) === (alt.data.erloes_konto || null)
                        && String(pos.tax_rate ?? '') === altSatz
        if (!unberuehrt) continue

        const neuerSatz = jetzt.data.reverse_charge ? '' : (jetzt.data.ust_satz != null ? String(Number(jetzt.data.ust_satz)) : '')
        if ((jetzt.data.erloes_konto || null) === (pos.account_nr || null)
            && neuerSatz === String(pos.tax_rate ?? '')) continue

        neu[i] = { ...pos, account_nr: jetzt.data.erloes_konto || null, tax_rate: neuerSatz }
        geaendert.push(pos.description || `Position ${i + 1}`)
      }

      if (geaendert.length) {
        setPositions(neu)
        toast.success(
          `Steuerfall geändert — Konto und Steuersatz angepasst: ${geaendert.join(', ')}`,
          { duration: 7000 })
      }
    } catch {
      toast.error('Der Steuerfall des neuen Kunden konnte nicht geprüft werden — '
                + 'bitte Konten und Steuersätze der Positionen kontrollieren.',
                { duration: 8000 })
    }
  }

  function addTimeEntries(entries) {
    setPositions(p => [...p, ...entries.map(e => ({ ...EMPTY_POSITION, pos_type: 'time_entry', description: e.description || 'Zeitaufwand', quantity: String(e.duration_hours), unit: 'h', unit_price: '0', time_entry_id: e.id }))])
  }

  // Ausgestellter Beleg: inhaltlich gesperrt (nur die interne Notiz bleibt offen)
  const gesperrt = !isNew && status !== 'entwurf'

  const { subtotal, taxTotal, total } = calcTotals(positions, taxMode)

  async function handleSave() {
    if (positions.length === 0) { toast.error('Mindestens eine Position erforderlich'); return }
    setSaving(true)
    try {
      const payload = {
        doc_type: docType, contact_id: contactId || null, title: title || null,
        project_id: projectId || null, currency,
        date, due_date: dueDate || null, reference: reference || null,
        skonto_percent: skontoPercent === '' ? null : skontoPercent,
        skonto_days: skontoDays === '' ? null : parseInt(skontoDays),
        valid_until: (docType === 'angebot' && validUntil) ? validUntil : null,
        // Die Stufe gibt es nur an der Rechnung — sie bestimmt, ob in der
        // Schlussrechnung abgezogen wird.
        billing_stage: docType === 'rechnung' ? (billingStage || null) : null,
        chain_id: chainId,
        delivery_date: deliveryDate || null,
        delivery_date_to: (istZeitraum && deliveryDateTo) ? deliveryDateTo : null,
        intro_text: introText || null, outro_text: outroText || null, notes: notes || null,
        tax_mode: taxMode, template_id: templateId,
        // Wiederkehrend nur bei Rechnung
        is_recurring_template: docType === 'rechnung' ? isRecurring : false,
        recurring_interval: (docType === 'rechnung' && isRecurring) ? recurringInterval : null,
        recurring_next: (docType === 'rechnung' && isRecurring) ? (recurringNext || date) : null,
        recurring_end: (docType === 'rechnung' && isRecurring && recurringEnd) ? recurringEnd : null,
        recurring_action: (docType === 'rechnung' && isRecurring) ? recurringAction : null,
        positions: positions.map((p, i) => ({
          sort_order: i, pos_type: p.pos_type, description: p.description, detail: p.detail || null,
          quantity: parseFloat(p.quantity) || 1, unit: p.unit || null, unit_price: parseFloat(p.unit_price) || 0,
          discount_pct: p.discount_pct !== '' ? parseFloat(p.discount_pct) : null,
          tax_rate: p.tax_rate !== '' ? parseFloat(p.tax_rate) : null,
          account_nr: p.account_nr || null,
          // Bild reist als Feld mit — Positionen werden beim Speichern gelöscht
          // und neu angelegt, ein Anhang könnte sich sonst nirgends festhalten.
          image_key: p.image_key || null, image_size: p.image_size || null,
          image_provider: p.image_provider || null,
          article_id: p.article_id || null, time_entry_id: p.time_entry_id || null,
        })),
      }
      let res
      if (isNew) { res = await invoiceApi.create(payload); toast.success(DOC_TYPE_LABELS[docType] + ' ' + res.data.number + ' erstellt') }
      else { res = await invoiceApi.update(id, payload); toast.success('Gespeichert') }
      navigate('/invoices/' + res.data.id)
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler beim Speichern') }
    finally { setSaving(false) }
  }

  async function handleContractUpload(e) {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    const frei = MAX_CONTRACTS - contracts.length
    if (frei <= 0) { toast.error(`Maximal ${MAX_CONTRACTS} Verträge je Beleg`); e.target.value = ''; return }
    const toUpload = files.slice(0, frei)
    setContractUploading(true)
    try {
      for (const file of toUpload) {
        const res = await invoiceApi.uploadContract(id, file)
        setContracts(list => [...list, { id: res.data.id, filename: res.data.filename }])
      }
      toast.success(toUpload.length > 1 ? `${toUpload.length} Verträge hinterlegt` : 'Vertrag hinterlegt')
      if (files.length > frei) toast.error(`Nur ${frei} von ${files.length} übernommen (max. ${MAX_CONTRACTS})`)
    } catch (err) { toast.error(err.response?.data?.detail || 'Upload fehlgeschlagen') }
    finally { setContractUploading(false); e.target.value = '' }
  }
  async function handleContractDelete(attId) {
    try { await invoiceApi.deleteContract(attId); setContracts(list => list.filter(c => c.id !== attId)); toast.success('Vertrag entfernt') }
    catch { toast.error('Fehler') }
  }
  async function handleContractOpen(attId) {
    try {
      const token = getAccessToken()
      const res = await fetch('/api/invoices/contract/' + attId + '/download', { headers: { Authorization: 'Bearer ' + token } })
      if (!res.ok) throw new Error()
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
      setTimeout(() => URL.revokeObjectURL(url), 60000)
    } catch { toast.error('Vertrag konnte nicht geöffnet werden') }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><RefreshCw size={24} className="animate-spin text-neutral-400" /></div>

  return (
    <div className="">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/invoices')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500"><ArrowLeft size={18} /></button>
          <div>
            <h1 className="text-xl font-semibold text-neutral-900">{isNew ? 'Neue ' + DOC_TYPE_LABELS[docType] : DOC_TYPE_LABELS[docType] + ' bearbeiten'}</h1>
            {number
              ? <p className="text-sm text-neutral-400 mt-0.5">Nummer: {number}</p>
              : nextNumber && (
                  <p className="text-sm text-neutral-400 mt-0.5">
                    Entwurf — Nummer <span className="font-medium text-neutral-500">{nextNumber}</span> wird beim Finalisieren vergeben
                  </p>
                )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
          {!isNew && (
            <>
              <button onClick={async () => {
                try {
                  const token = getAccessToken()
                  const res = await fetch('/api/invoices/' + id + '/pdf', { headers: { Authorization: 'Bearer ' + token } })
                  const blob = new Blob([await res.arrayBuffer()], { type: 'application/pdf' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a'); a.href = url; a.download = id + '.pdf'; a.click(); URL.revokeObjectURL(url)
                } catch { toast.error('PDF-Fehler') }
              }} className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50">
                <Download size={14} /> PDF
              </button>
              <button onClick={async () => {
                try {
                  const token = getAccessToken()
                  const res = await fetch('/api/invoices/' + id + '/preview', { headers: { Authorization: 'Bearer ' + token } })
                  const html = await res.text()
                  const blob = new Blob([html], { type: 'text/html' })
                  const url = URL.createObjectURL(blob)
                  window.open(url, '_blank')
                  setTimeout(() => URL.revokeObjectURL(url), 10000)
                } catch { toast.error('Vorschau-Fehler') }
              }} className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50">
                <Eye size={14} /> Vorschau
              </button>
            </>
          )}
          <button onClick={handleSave} disabled={saving}
            title={gesperrt ? 'Speichert die interne Notiz' : undefined}
            className="flex-1 sm:flex-none flex items-center justify-center gap-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-60">
            {saving ? <RefreshCw size={15} className="animate-spin" /> : <Save size={15} />}
            {gesperrt ? 'Notiz speichern' : 'Speichern'}
          </button>
        </div>
      </div>

      <div className="space-y-5">
        {gesperrt && (
          <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
            <Lock size={16} className="text-amber-600 mt-0.5 shrink-0" />
            <div className="text-sm text-amber-900">
              <p className="font-semibold">Beleg ist ausgestellt und inhaltlich gesperrt</p>
              <p className="mt-1 text-amber-800 leading-relaxed">
                Positionen, Beträge, Empfänger, Datum und alle gedruckten Texte lassen sich
                nicht mehr ändern — das PDF wird bei jedem Abruf neu erzeugt und würde sich
                sonst rückwirkend verändern. Für eine inhaltliche Korrektur den Beleg
                <strong> stornieren</strong> und neu ausstellen.
                Änderbar bleibt die interne Notiz.
              </p>
            </div>
          </div>
        )}

        <fieldset disabled={gesperrt} className="space-y-5 min-w-0 disabled:opacity-60">
        {isNew && (
          <div className="bg-surface border border-neutral-200 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-neutral-700 mb-3">Dokumenttyp</h2>
            <div className="flex gap-2 flex-wrap">
              {Object.entries(DOC_TYPE_LABELS).map(([k, v]) => (
                <button key={k} onClick={() => setDocType(k)} className={'px-4 py-2 rounded-lg text-sm border transition-all ' + (docType === k ? 'bg-primary-600 text-white border-primary-600' : 'text-neutral-700 border-neutral-200 hover:border-neutral-300')}>{v}</button>
              ))}
            </div>
          </div>
        )}

        <div className="bg-surface border border-neutral-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-neutral-700 mb-4">Grunddaten</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Kontakt</label>
              <ContactSearch value={contactId} label={contactLabel} onChange={kontaktWechseln} />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Titel / Betreff</label>
              <input value={title} onChange={e => setTitle(e.target.value)} placeholder="z.B. Webentwicklung März 2026" className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Datum</label>
              <input type="date" value={date} onChange={e => setDate(e.target.value)} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
            </div>
            {docType === 'rechnung' && (
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Zahlungsziel</label>
                <input type="date" value={dueDate} onChange={e => setDueDate(e.target.value)} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
              </div>
            )}
            {docType === 'angebot' && (
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">Gültig bis</label>
                <input type="date" value={validUntil} onChange={e => setValidUntil(e.target.value)}
                  className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
                <p className="text-xs text-neutral-400 mt-1">
                  Steht auf dem Angebot. Leer heißt: unbefristet gültig.
                </p>
              </div>
            )}
            {docType === 'rechnung' && (
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">
                  Abrechnungsstufe
                  <span className="text-xs font-normal text-neutral-400 ml-1">optional</span>
                </label>
                <select value={billingStage} onChange={e => setBillingStage(e.target.value)}
                  disabled={status !== 'entwurf'}
                  className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm disabled:bg-neutral-50 disabled:text-neutral-400">
                  <option value="">Gewöhnliche Rechnung</option>
                  <option value="anzahlung">Anzahlungsrechnung</option>
                  <option value="teil">Teilrechnung</option>
                  <option value="schluss">Schlussrechnung</option>
                </select>
                <p className="text-xs text-neutral-400 mt-1">
                  Anzahlungen und Teilrechnungen werden in der Schlussrechnung
                  desselben Vorgangs wieder abgezogen.
                </p>
              </div>
            )}
            {docType === 'rechnung' && (
              <div>
                <label className="block text-sm font-medium text-neutral-700 mb-1">
                  Skonto
                  <span className="text-xs font-normal text-neutral-400 ml-1">optional</span>
                </label>
                <div className="flex items-center gap-2">
                  <input type="number" step="0.01" min="0" max="100" value={skontoPercent}
                    onChange={e => setSkontoPercent(e.target.value)} placeholder="2"
                    className="w-20 border border-neutral-200 rounded-lg px-3 py-2 text-sm text-right" />
                  <span className="text-sm text-neutral-500">% binnen</span>
                  <input type="number" min="0" value={skontoDays}
                    onChange={e => setSkontoDays(e.target.value)} placeholder="10"
                    className="w-20 border border-neutral-200 rounded-lg px-3 py-2 text-sm text-right" />
                  <span className="text-sm text-neutral-500">Tagen</span>
                </div>
              </div>
            )}
            {/* Pflichtangabe nach § 11 Abs. 1 Z 4 UStG — wird beim Ausstellen
                verlangt, am Entwurf noch nicht. */}
            <div className={istZeitraum ? 'md:col-span-2' : ''}>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-sm font-medium text-neutral-700">
                  {istZeitraum ? 'Leistungszeitraum' : 'Liefer-/Leistungsdatum'}
                  {['rechnung', 'gutschrift'].includes(docType) && <span className="text-red-500"> *</span>}
                </label>
                <label className="flex items-center gap-1.5 text-xs text-neutral-500 cursor-pointer">
                  <input type="checkbox" checked={istZeitraum} className="w-3.5 h-3.5 rounded"
                    onChange={e => {
                      setIstZeitraum(e.target.checked)
                      if (e.target.checked && !deliveryDateTo) setDeliveryDateTo(deliveryDate || date)
                    }} />
                  Zeitraum
                </label>
              </div>
              <div className={istZeitraum ? 'grid grid-cols-2 gap-2' : ''}>
                <input type="date" value={deliveryDate} onChange={e => setDeliveryDate(e.target.value)}
                  className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
                {istZeitraum && (
                  <input type="date" value={deliveryDateTo} onChange={e => setDeliveryDateTo(e.target.value)}
                    className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
                )}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Referenz</label>
              <input value={reference} onChange={e => setReference(e.target.value)} placeholder="optional" className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">MwSt.-Modus</label>
              <select value={taxMode}
                onChange={e => {
                  const modus = e.target.value
                  setTaxMode(modus)
                  // „Ein Satz für alle": den Satz der ersten Position auf alle
                  // übertragen, damit die Auswahl sofort wirkt statt erst beim
                  // Speichern. Das Backend erzwingt dieselbe Regel nochmals.
                  if (modus === 'single_rate') {
                    const erster = positions.find(p => p.tax_rate !== '' && p.tax_rate != null)?.tax_rate
                    if (erster != null) setPositions(l => l.map(p => ({ ...p, tax_rate: erster })))
                  }
                }}
                className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
                <option value="per_position">Pro Position wählbar</option>
                <option value="single_rate">Ein Satz für alle</option>
                <option value="kleinunternehmer">Kleinunternehmer (keine MwSt.)</option>
              </select>
              {taxMode === 'single_rate' && (
                <div className="mt-2">
                  <label className="block text-xs text-neutral-500 mb-1">Steuersatz für alle Positionen</label>
                  <select
                    value={positions.find(p => p.tax_rate !== '' && p.tax_rate != null)?.tax_rate ?? ''}
                    onChange={e => setPositions(l => l.map(p => ({ ...p, tax_rate: e.target.value })))}
                    className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
                    {taxRates.map(t => (
                      <option key={t.satz} value={String(t.satz)}>{t.satz}% — {t.bezeichnung}</option>
                    ))}
                    <option value="">Reverse Charge</option>
                  </select>
                </div>
              )}
            </div>
          </div>
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Einleitungstext</label>
              <textarea value={introText} onChange={e => setIntroText(e.target.value)} rows={2} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm resize-none" />
            </div>
            <div>
              <label className="block text-sm font-medium text-neutral-700 mb-1">Schlusstext</label>
              <textarea value={outroText} onChange={e => setOutroText(e.target.value)} rows={2} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm resize-none" />
            </div>
          </div>
        </div>

        {docType === 'rechnung' && (
          <div className="bg-surface border border-neutral-200 rounded-xl p-5">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={isRecurring} onChange={e => setIsRecurring(e.target.checked)} className="w-4 h-4 rounded" />
              <Repeat size={16} className="text-primary-600" />
              <span className="text-sm font-semibold text-neutral-700">Wiederkehrende Rechnung</span>
            </label>
            {isRecurring && (
              <>
                <p className="text-xs text-neutral-500 mt-2 mb-4">
                  Diese Rechnung dient als Vorlage. Was am Stichtag geschieht, legst du unten fest.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="md:col-span-3">
                    <label className="block text-sm font-medium text-neutral-700 mb-1">Am Stichtag</label>
                    <select value={recurringAction} onChange={e => setRecurringAction(e.target.value)}
                      className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
                      <option value="create">Entwurf anlegen — ich stelle ihn selbst aus</option>
                      <option value="remind">Nur erinnern — Aufgabe anlegen, kein Beleg</option>
                      <option value="create_and_send">Anlegen, ausstellen und per E-Mail senden</option>
                    </select>
                    <p className="text-xs text-neutral-500 mt-1">
                      {recurringAction === 'remind' &&
                        'Es entsteht kein Beleg, sondern eine Aufgabe mit dem Fälligkeitsdatum.'}
                      {recurringAction === 'create' &&
                        'Der Entwurf bekommt noch keine Belegnummer — die fällt erst beim Ausstellen.'}
                      {recurringAction === 'create_and_send' &&
                        'Der Beleg wird ausgestellt (Nummer wird vergeben) und an die E-Mail-Adresse des Kunden geschickt. Scheitert der Versand, bleibt er ausgestellt stehen und ist von Hand zu verschicken.'}
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 mb-1">Intervall</label>
                    <select value={recurringInterval} onChange={e => setRecurringInterval(e.target.value)} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm">
                      <option value="weekly">Wöchentlich</option>
                      <option value="monthly">Monatlich</option>
                      <option value="quarterly">Quartalsweise</option>
                      <option value="yearly">Jährlich</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 mb-1">Nächste Ausführung</label>
                    <input type="date" value={recurringNext} onChange={e => setRecurringNext(e.target.value)} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-neutral-700 mb-1">Laufzeit bis <span className="text-neutral-400 font-normal">(optional)</span></label>
                    <input type="date" value={recurringEnd} onChange={e => setRecurringEnd(e.target.value)} className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm" />
                  </div>
                </div>
                <div className="mt-4">
                  <label className="block text-sm font-medium text-neutral-700 mb-1">Verträge <span className="text-neutral-400 font-normal">(optional, bis {MAX_CONTRACTS})</span></label>
                  {isNew ? (
                    <p className="text-xs text-neutral-500">Bitte zuerst speichern, danach können Verträge hochgeladen werden.</p>
                  ) : (
                    <div className="space-y-2">
                      {contracts.map(c => (
                        <div key={c.id} className="flex items-center gap-2 text-sm bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 w-fit">
                          <Paperclip size={14} className="text-neutral-500" />
                          <button type="button" onClick={() => handleContractOpen(c.id)} className="text-primary-700 hover:underline" title="Vertrag öffnen">{c.filename}</button>
                          <button type="button" onClick={() => handleContractOpen(c.id)} className="text-neutral-400 hover:text-primary-600" title="Vertrag öffnen"><Eye size={14} /></button>
                          <button type="button" onClick={() => handleContractDelete(c.id)} className="text-neutral-400 hover:text-red-500" title="Vertrag entfernen"><XIcon size={14} /></button>
                        </div>
                      ))}
                      {contracts.length < MAX_CONTRACTS && (
                        <label className="inline-flex items-center gap-2 text-sm px-3 py-2 border border-neutral-200 rounded-lg cursor-pointer hover:bg-neutral-50 w-fit">
                          <Paperclip size={14} /> {contractUploading ? 'Lädt…' : (contracts.length === 0 ? 'Vertrag hochladen' : 'Weiteren Vertrag hochladen')}
                          <input type="file" multiple className="hidden" onChange={handleContractUpload} disabled={contractUploading} />
                        </label>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        <div className="bg-surface border border-neutral-200 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-neutral-700">Positionen</h2>
            <TimeEntryPicker contactId={contactId} onAdd={addTimeEntries} />
          </div>
          <div className="mb-3"><ArticleSearch contactId={contactId} onSelect={art => addPosition(art)} /></div>
          <div className="space-y-2">
            {positions.map((pos, i) => (
              <PositionRow key={i} pos={pos} index={i} taxMode={taxMode} taxRates={taxRates}
                betrag={calcZeile(positions, i)}
                istErste={i === 0} istLetzte={i === positions.length - 1}
                onMove={richtung => movePosition(i, richtung)}
                onChange={(field, val) => updatePosition(i, field, val)} onRemove={() => removePosition(i)} />
            ))}
          </div>
          <div className="mt-3 flex flex-wrap gap-4">
            <button type="button" onClick={() => addPosition()} className="flex items-center gap-1.5 text-sm text-primary-600 hover:underline">
              <Plus size={14} /> Position
            </button>
            {/* Gliederung: Überschrift eröffnet eine Gruppe, Freitext nicht —
                eine erläuternde Zeile soll eine Gruppe nicht zerreißen. */}
            <button type="button" onClick={() => addPosition({ pos_type: 'heading', description: 'Neue Gruppe', quantity: '0', unit_price: '0', tax_rate: '' })}
              className="flex items-center gap-1.5 text-sm text-neutral-600 hover:underline">
              <Plus size={14} /> Überschrift
            </button>
            <button type="button" onClick={() => addPosition({ pos_type: 'text', description: '', quantity: '0', unit_price: '0', tax_rate: '' })}
              className="flex items-center gap-1.5 text-sm text-neutral-600 hover:underline">
              <Plus size={14} /> Freitext
            </button>
            <button type="button" onClick={() => addPosition({ pos_type: 'subtotal', description: 'Zwischensumme', quantity: '0', unit_price: '0', tax_rate: '' })}
              className="flex items-center gap-1.5 text-sm text-neutral-600 hover:underline">
              <Plus size={14} /> Zwischensumme
            </button>
            <button type="button" onClick={() => addPosition({ pos_type: 'discount', description: 'Rabatt', quantity: '1', unit_price: '0', tax_rate: '' })}
              className="flex items-center gap-1.5 text-sm text-neutral-600 hover:underline">
              <Plus size={14} /> Rabatt
            </button>
          </div>
          <div className="mt-5 border-t pt-4 flex justify-end">
            <div className="w-64 space-y-1.5 text-sm">
              <div className="flex justify-between text-neutral-600"><span>Netto</span><span>{fmtEuro(subtotal)}</span></div>
              {taxMode !== 'kleinunternehmer' && <div className="flex justify-between text-neutral-600"><span>MwSt.</span><span>{fmtEuro(taxTotal)}</span></div>}
              <div className="flex justify-between font-semibold text-neutral-900 border-t pt-1.5"><span>Gesamt</span><span>{fmtEuro(total)}</span></div>
              {taxMode === 'kleinunternehmer' && <p className="text-xs text-neutral-400 mt-1">Gemäß § 6 Abs. 1 Z 27 UStG keine USt.</p>}
            </div>
          </div>
        </div>

        </fieldset>

        {/* Bewusst AUSSERHALB des fieldset: Die interne Notiz steht nicht auf
            dem Beleg und bleibt daher auch nach dem Finalisieren änderbar. */}
        <div className="bg-surface border border-neutral-200 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-neutral-700 mb-3">Interne Notiz</h2>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={3}
            placeholder="Wird nicht auf dem Dokument gedruckt"
            className="w-full border border-neutral-200 rounded-lg px-3 py-2 text-sm resize-none" />
        </div>

        {!isNew && chainId && <StrangPanel invoiceId={id} />}
        {!isNew && gesperrt && ['rechnung', 'gutschrift'].includes(docType) && (
          <ERechnungPanel invoiceId={id} nummer={number} />
        )}
        {!isNew && gesperrt && docType === 'rechnung' && hatBuchhaltung && <MahnPanel invoiceId={id} />}
        {!isNew && gesperrt && <AuditPanel invoiceId={id} />}
      </div>
    </div>
  )
}

const AUDIT_LABELS = {
  finalisiert: 'Ausgestellt',
  status:      'Status geändert',
  bezahlt:     'Als bezahlt markiert',
  storniert:   'Storniert',
  bearbeitet:  'Bearbeitet',
  archiviert:  'Archivierung',
  zahlung:     'Zahlung',
  skonto:      'Skonto',
  mahnung:     'Mahnwesen',
  hinweis:     'Hinweis',
}

/**
 * Mahnhistorie und Mahnsperre am Beleg.
 *
 * Die Stufe wird hier bewusst OHNE Wartezeit-Prüfung angeboten („force"):
 * Wer den Beleg vor sich hat, hat meist einen Grund, früher zu mahnen. Der
 * Mahnlauf hält sich dagegen strikt an die Fristen. Die Mahnsperre bleibt in
 * beiden Fällen unantastbar.
 */
function MahnPanel({ invoiceId }) {
  const [eintraege, setEintraege] = useState([])
  const [beleg, setBeleg] = useState(null)
  const [laeuft, setLaeuft] = useState(false)

  const laden = useCallback(async () => {
    try {
      const [h, b] = await Promise.all([
        invoiceApi.dunningHistory(invoiceId),
        invoiceApi.get(invoiceId),
      ])
      setEintraege(h.data)
      setBeleg(b.data)
    } catch { /* stiller Fehler: das Panel ist Beiwerk, nicht der Beleg */ }
  }, [invoiceId])

  useEffect(() => { laden() }, [laden])

  async function mahnen() {
    setLaeuft(true)
    try {
      await invoiceApi.createDunning(invoiceId, { force: true })
      toast.success('Mahnung erstellt')
      await laden()
    } catch (e) { toast.error(e.response?.data?.detail || 'Mahnung nicht möglich') }
    finally { setLaeuft(false) }
  }

  async function sperreUmschalten() {
    const sperren = !beleg?.dunning_blocked
    const grund = sperren ? window.prompt('Grund der Mahnsperre (z.B. Ratenvereinbarung):') : null
    if (sperren && grund === null) return
    try {
      const res = await invoiceApi.dunningBlock(invoiceId, { blocked: sperren, reason: grund })
      setBeleg(res.data)
      toast.success(sperren ? 'Mahnsperre gesetzt' : 'Mahnsperre aufgehoben')
    } catch { toast.error('Die Mahnsperre konnte nicht geändert werden') }
  }

  async function pdfOeffnen(dunningId) {
    try {
      const res = await invoiceApi.dunningPdf(dunningId)
      window.open(URL.createObjectURL(res.data), '_blank')
    } catch { toast.error('Das Mahnschreiben konnte nicht erzeugt werden') }
  }

  async function zuruecknehmen(dunningId) {
    if (!window.confirm('Diese Mahnung wirklich zurücknehmen? Das verschickte Schreiben holt das nicht zurück.')) return
    try {
      const res = await invoiceApi.deleteDunning(dunningId)
      setEintraege(res.data)
      await laden()
      toast.success('Mahnung zurückgenommen')
    } catch { toast.error('Fehler') }
  }

  return (
    <div className="bg-surface border border-neutral-200 rounded-xl p-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-neutral-700">
          <Bell size={15} className="text-neutral-500" /> Mahnwesen
        </h2>
        <div className="flex items-center gap-2">
          <button type="button" onClick={sperreUmschalten}
            className="text-xs px-2.5 py-1.5 border border-neutral-200 rounded-lg hover:bg-neutral-50">
            {beleg?.dunning_blocked ? 'Sperre aufheben' : 'Mahnsperre setzen'}
          </button>
          <button type="button" onClick={mahnen} disabled={laeuft || beleg?.dunning_blocked}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-neutral-800 text-white hover:bg-neutral-900 disabled:opacity-40">
            Mahnung erstellen
          </button>
        </div>
      </div>

      {beleg?.dunning_blocked && (
        <p className="mb-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          Mahngesperrt{beleg.dunning_block_reason ? ` — ${beleg.dunning_block_reason}` : ''}
        </p>
      )}

      {eintraege.length === 0 ? (
        <p className="text-sm text-neutral-400">Noch nicht gemahnt.</p>
      ) : (
        <div className="divide-y border border-neutral-200 rounded-lg">
          {eintraege.map(m => (
            <div key={m.id} className="flex items-center justify-between px-3 py-2 text-sm">
              <div>
                <span className="font-medium text-neutral-800">{m.label || `Stufe ${m.level}`}</span>
                <span className="text-neutral-400 ml-2">
                  {new Date(m.dunned_at).toLocaleDateString('de-AT')}
                  {m.due_date && ` · Frist ${new Date(m.due_date).toLocaleDateString('de-AT')}`}
                </span>
                <span className="block text-xs text-neutral-500">
                  offen {Number(m.open_amount).toFixed(2)}
                  {Number(m.fee) > 0 && ` · Gebühr ${Number(m.fee).toFixed(2)}`}
                  {Number(m.interest) > 0 && ` · Zinsen ${Number(m.interest).toFixed(2)}`}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <button type="button" onClick={() => pdfOeffnen(m.id)} title="Mahnschreiben öffnen"
                  className="p-1 text-neutral-400 hover:text-neutral-700"><FileText size={14} /></button>
                <button type="button" onClick={() => zuruecknehmen(m.id)} title="Mahnung zurücknehmen"
                  className="p-1 text-neutral-400 hover:text-red-500"><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const FELD_LABELS = {
  status: 'Status', number: 'Belegnummer', notes: 'Interne Notiz',
  project_id: 'Projekt',
}

/**
 * Überblick über den Abrechnungsvorgang.
 *
 * Zeigt alle Belege des Bauvorhabens und was in der Schlussrechnung abgezogen
 * wird. Ohne diese Ansicht müsste man sich aus der Belegliste zusammensuchen,
 * was zusammengehört — und würde eine vergessene Teilrechnung erst bemerken,
 * wenn der Kunde reklamiert.
 */
function StrangPanel({ invoiceId }) {
  const navigate = useNavigate()
  const [daten, setDaten] = useState(null)
  const [offen, setOffen] = useState(true)

  useEffect(() => {
    invoiceApi.chain(invoiceId).then(r => setDaten(r.data)).catch(() => {})
  }, [invoiceId])

  if (!daten?.belege?.length) return null

  return (
    <div className="bg-surface border border-neutral-200 rounded-xl overflow-hidden">
      <button onClick={() => setOffen(o => !o)}
        className="w-full flex items-center gap-2 px-5 py-3 text-sm font-semibold text-neutral-700 hover:bg-neutral-50">
        <Layers size={15} className="text-neutral-500" />
        Abrechnungsvorgang
        <span className="font-normal text-neutral-400">
          {daten.belege.length} {daten.belege.length === 1 ? 'Beleg' : 'Belege'}
        </span>
        {offen ? <ChevronUp size={15} className="ml-auto text-neutral-400" />
               : <ChevronDown size={15} className="ml-auto text-neutral-400" />}
      </button>

      {offen && (
        <div className="border-t border-neutral-100">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-neutral-100">
              {daten.belege.map(b => (
                <tr key={b.id} className={b.id === invoiceId ? 'bg-primary-50/50' : 'hover:bg-neutral-50'}>
                  <td className="px-5 py-2.5">
                    <button onClick={() => navigate(`/invoices/${b.id}/edit`)}
                      className="font-medium text-neutral-800 hover:text-primary-600">
                      {b.number || 'Entwurf'}
                    </button>
                    <span className="block text-xs text-neutral-400">{b.stage_label}</span>
                  </td>
                  <td className="px-3 py-2.5 text-neutral-500 hidden sm:table-cell whitespace-nowrap">
                    {new Date(b.date).toLocaleDateString('de-AT')}
                  </td>
                  <td className="px-3 py-2.5 text-right font-medium text-neutral-800 whitespace-nowrap">
                    {fmtEuro(b.total)}
                  </td>
                  <td className="px-3 py-2.5 text-xs text-neutral-500 whitespace-nowrap">
                    {b.status}
                    {Number(b.open_amount) !== 0 && (
                      <span className="block text-amber-600">offen {fmtEuro(b.open_amount)}</span>
                    )}
                  </td>
                  <td className="px-5 py-2.5 text-right">
                    {b.deducted && (
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-700">
                        wird abgezogen
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {daten.abzug?.length > 0 && (
            <div className="border-t border-neutral-100 px-5 py-3 bg-neutral-50/60">
              <p className="text-xs font-medium text-neutral-600 mb-1.5">
                Abzug in der Schlussrechnung
              </p>
              {daten.abzug.map((z, i) => (
                <div key={i} className="flex justify-between text-xs text-neutral-600">
                  <span>{z.tax_rate == null ? 'Reverse Charge' : `${Number(z.tax_rate)} % USt.`}</span>
                  <span>{fmtEuro(z.net_amount)} netto + {fmtEuro(z.tax_amount)} USt.</span>
                </div>
              ))}
              <div className="flex justify-between text-xs font-semibold text-neutral-800 mt-1.5 pt-1.5 border-t border-neutral-200">
                <span>Gesamt brutto</span>
                <span>{fmtEuro(daten.abzug_brutto)}</span>
              </div>
              {/* Der Unterschied zwischen „gestellt" und „bezahlt" ist hier
                  wesentlich — deshalb ausgeschrieben und nicht nur angedeutet. */}
              <p className="text-xs text-neutral-500 mt-2 leading-relaxed">
                Abgezogen wird, was bereits in Rechnung gestellt wurde — auch wenn
                es noch nicht bezahlt ist. Die Umsatzsteuer entsteht mit der
                Rechnung; ein offener Betrag bleibt als offener Posten stehen.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}


/**
 * E-Rechnung (ZUGFeRD 2.5 / Factur-X).
 *
 * Zeigt den Stand und benennt, was noch fehlt. Der Ton ist bewusst sachlich:
 * Eine unvollständige E-Rechnung ist kein Fehler des Anwenders, sondern eine
 * Liste von Feldern, die niemand vorher gebraucht hat.
 */
function ERechnungPanel({ invoiceId, nummer }) {
  const [stand, setStand] = useState(null)
  const [laden, setLaden] = useState(true)

  useEffect(() => {
    invoiceApi.erechnungPruefen(invoiceId)
      .then(r => setStand(r.data))
      .catch(() => {})
      .finally(() => setLaden(false))
  }, [invoiceId])

  if (laden || !stand) return null

  const vollstaendig = stand.moeglich
  return (
    <div className="bg-surface border border-neutral-200 rounded-xl p-5">
      <div className="flex items-start gap-3">
        <FileCode size={16} className={vollstaendig ? 'text-emerald-600 mt-0.5' : 'text-amber-600 mt-0.5'} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-neutral-800">
            E-Rechnung
            <span className="ml-2 text-xs font-normal text-neutral-400">{stand.format}</span>
          </p>

          {vollstaendig ? (
            <p className="text-sm text-neutral-600 mt-1 leading-relaxed">
              {stand.aktiv
                ? 'Eingeschaltet. Das PDF dieses Belegs enthält die Rechnungsdaten als eingebettete Datei — sichtbar ändert sich nichts.'
                : 'Dieser Beleg wäre vollständig, die E-Rechnung ist aber ausgeschaltet. Der Schalter steht in den Belegeinstellungen.'}
            </p>
          ) : (
            <>
              <p className="text-sm text-neutral-600 mt-1">
                Noch nicht vollständig. Es fehlt:
              </p>
              <ul className="mt-2 space-y-1">
                {stand.fehlende_angaben.map((z, i) => (
                  <li key={i} className="text-sm text-neutral-600 flex gap-2">
                    <span className="text-amber-500 shrink-0">•</span>
                    <span>{z}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          <div className="flex flex-wrap gap-2 mt-4">
            <a href={invoiceApi.erechnungXmlUrl(invoiceId, !vollstaendig)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50">
              <Download size={14} /> XML {vollstaendig ? 'herunterladen' : 'trotzdem ansehen'}
            </a>
            {nummer && (
              <a href={`/api/invoices/${invoiceId}/pdf`}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50">
                <Download size={14} /> PDF
              </a>
            )}
          </div>

          {/* Der Punkt, an dem ich mich nicht selbst bestätigen kann. */}
          <p className="text-xs text-neutral-400 mt-3 leading-relaxed">
            Ob die Datei einer Prüfung standhält, entscheidet ein Validator —
            nicht der Erzeuger. Vor dem ersten echten Versand gehört eine
            Probedatei extern geprüft.
          </p>
        </div>
      </div>
    </div>
  )
}


function AuditPanel({ invoiceId }) {
  const [eintraege, setEintraege] = useState([])
  const [offen, setOffen] = useState(false)
  const [geladen, setGeladen] = useState(false)

  useEffect(() => {
    if (!offen || geladen) return
    invoiceApi.getAudit(invoiceId)
      .then(res => { setEintraege(res.data); setGeladen(true) })
      .catch(() => toast.error('Protokoll konnte nicht geladen werden'))
  }, [offen, geladen, invoiceId])

  return (
    <div className="bg-surface border border-neutral-200 rounded-xl p-5">
      <button type="button" onClick={() => setOffen(o => !o)}
        className="flex items-center gap-2 text-sm font-semibold text-neutral-700">
        <History size={15} className="text-neutral-500" />
        Änderungsprotokoll
        <span className="text-xs font-normal text-neutral-400">
          {offen ? 'ausblenden' : 'anzeigen'}
        </span>
      </button>

      {offen && (
        <div className="mt-4">
          {eintraege.length === 0 ? (
            <p className="text-sm text-neutral-400">Noch keine Einträge.</p>
          ) : (
            <ol className="space-y-3 border-l border-neutral-200 pl-4">
              {eintraege.map(e => (
                <li key={e.id} className="relative">
                  <span className="absolute -left-[21px] top-1.5 w-2 h-2 rounded-full bg-neutral-300" />
                  <p className="text-sm text-neutral-800">
                    {AUDIT_LABELS[e.action] || e.action}
                    <span className="text-xs text-neutral-400 ml-2">
                      {new Date(e.changed_at).toLocaleString('de-AT')}
                      {e.changed_by && ' · ' + e.changed_by}
                    </span>
                  </p>
                  {e.note && <p className="text-xs text-neutral-500 mt-0.5">{e.note}</p>}
                  {e.changes && Object.entries(e.changes).map(([feld, w]) => (
                    <p key={feld} className="text-xs text-neutral-500 mt-0.5">
                      {FELD_LABELS[feld] || feld}: <span className="line-through">{w.alt ?? '—'}</span>
                      {' → '}<span className="text-neutral-700">{w.neu ?? '—'}</span>
                    </p>
                  ))}
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  )
}

// Muss zu backend/app/services/position_image.py passen
const BILDGROESSEN = [
  ['klein',  'Klein',  '3 cm'],
  ['mittel', 'Mittel', '6 cm'],
  ['gross',  'Groß',   '10 cm'],
]

/**
 * Bild einer Position.
 *
 * Ablauf wie besprochen: Datei wählen, dann eine der drei Größen — erst diese
 * Wahl löst den Upload aus. Das Bild wird dabei serverseitig auf die Größe
 * verkleinert und nur so gespeichert; eine andere Größe heißt neu hochladen.
 */
function PositionImage({ pos, onChange }) {
  const [datei, setDatei] = useState(null)
  const [laeuft, setLaeuft] = useState(false)
  const [vorschau, setVorschau] = useState(null)

  // Das Bild kann NICHT direkt als <img src="/api/..."> geladen werden: Ein
  // img-Tag schickt keinen Anmelde-Token mit, der Endpunkt antwortet dann mit
  // 401 und der Browser zeigt ein kaputtes Bild. Deshalb per fetch holen und
  // als Objekt-URL einhängen — dasselbe Muster wie bei den Verträgen.
  useEffect(() => {
    if (!pos.image_key) { setVorschau(null); return }
    let url = null
    let abgebrochen = false
    ;(async () => {
      try {
        const token = getAccessToken()
        const res = await fetch(invoiceApi.positionImageUrl(pos.image_key, pos.image_provider),
                                { headers: { Authorization: 'Bearer ' + token } })
        if (!res.ok) throw new Error(res.status)
        const blob = await res.blob()
        if (abgebrochen) return
        url = URL.createObjectURL(blob)
        setVorschau(url)
      } catch { setVorschau(null) }
    })()
    return () => { abgebrochen = true; if (url) URL.revokeObjectURL(url) }
  }, [pos.image_key, pos.image_provider])

  async function hochladen(groesse) {
    setLaeuft(true)
    try {
      const res = await invoiceApi.uploadPositionImage(datei, groesse)
      onChange('image_key', res.data.image_key)
      onChange('image_size', res.data.image_size)
      onChange('image_provider', res.data.image_provider)
      setDatei(null)
      toast.success('Bild hinterlegt')
    } catch (e) { toast.error(e.response?.data?.detail || 'Upload fehlgeschlagen') }
    finally { setLaeuft(false) }
  }

  if (pos.image_key) {
    const label = BILDGROESSEN.find(g => g[0] === pos.image_size)
    return (
      <div className="mt-2 flex items-center gap-2">
        {vorschau
          ? <img src={vorschau} alt=""
              className="h-12 w-12 object-cover rounded border border-neutral-200" />
          : <span className="h-12 w-12 rounded border border-neutral-200 bg-neutral-50 flex items-center justify-center text-neutral-300">
              <ImageIcon size={16} />
            </span>}
        <span className="text-xs text-neutral-500">
          Bild · {label ? `${label[1]} (${label[2]})` : pos.image_size}
        </span>
        <button type="button" title="Bild entfernen"
          onClick={() => { onChange('image_key', null); onChange('image_size', null); onChange('image_provider', null) }}
          className="p-1 text-neutral-400 hover:text-red-500"><XIcon size={13} /></button>
      </div>
    )
  }

  if (datei) {
    return (
      <div className="mt-2 flex items-center gap-2 flex-wrap">
        <span className="text-xs text-neutral-600 truncate max-w-[12rem]">{datei.name}</span>
        <span className="text-xs text-neutral-500">— Größe wählen:</span>
        {BILDGROESSEN.map(([wert, name, breite]) => (
          <button key={wert} type="button" disabled={laeuft} onClick={() => hochladen(wert)}
            className="px-2 py-1 text-xs border border-neutral-200 rounded hover:bg-neutral-50 disabled:opacity-50">
            {name} <span className="text-neutral-400">{breite}</span>
          </button>
        ))}
        <button type="button" onClick={() => setDatei(null)}
          className="p-1 text-neutral-400 hover:text-red-500"><XIcon size={13} /></button>
      </div>
    )
  }

  return (
    <label className="mt-2 inline-flex items-center gap-1.5 text-xs text-neutral-500 hover:text-primary-600 cursor-pointer">
      <ImageIcon size={13} /> Bild hinzufügen
      <input type="file" accept="image/*" className="hidden"
        onChange={e => { if (e.target.files?.[0]) setDatei(e.target.files[0]); e.target.value = '' }} />
    </label>
  )
}

/** Hoch/Runter zum Umsortieren — an den Enden abgeblendet statt versteckt,
 *  damit die Zeilen nicht unterschiedlich breit werden. */
function MoveButtons({ istErste, istLetzte, onMove }) {
  return (
    <span className="flex flex-col leading-none">
      <button type="button" onClick={() => onMove(-1)} disabled={istErste}
        title="Nach oben" className="p-0.5 text-neutral-400 hover:text-primary-600 disabled:opacity-20">
        <ChevronUp size={13} />
      </button>
      <button type="button" onClick={() => onMove(1)} disabled={istLetzte}
        title="Nach unten" className="p-0.5 text-neutral-400 hover:text-primary-600 disabled:opacity-20">
        <ChevronDown size={13} />
      </button>
    </span>
  )
}

function PositionRow({ pos, index, taxMode, taxRates = [], betrag,
                      istErste, istLetzte, onMove, onChange, onRemove }) {
  const typ = pos.pos_type || 'item'

  // Abzug einer bereits gestellten Anzahlung: nur lesbar. Er wird beim
  // Speichern serverseitig aus den tatsächlich gestellten Rechnungen neu
  // gerechnet — hier daran zu drehen hätte keine Wirkung und wäre deshalb
  // eine Lüge gegenüber dem Anwender.
  if (typ === ANZAHLUNGSABZUG) {
    return (
      <div className="border border-emerald-200 rounded-lg p-3 bg-emerald-50/60">
        <div className="flex items-center gap-2">
          <Lock size={13} className="text-emerald-600 shrink-0" />
          <span className="text-xs text-emerald-700 w-24 shrink-0">Anzahlungsabzug</span>
          <span className="flex-1 text-sm text-neutral-700">{pos.description}</span>
          <span className="text-sm font-medium text-neutral-800 w-28 text-right">
            {fmtEuro(calcLine(pos))}
          </span>
        </div>
        <p className="text-xs text-neutral-500 mt-1.5">
          Wird aus den gestellten Anzahlungs- und Teilrechnungen dieses Vorgangs
          berechnet und beim Speichern aktualisiert.
        </p>
      </div>
    )
  }

  // Gliederungszeilen brauchen nur ein Textfeld — Menge, Preis und Steuersatz
  // wären dort sinnlos und würden zum Ausfüllen einladen.
  if (['heading', 'text', 'subtotal', 'discount'].includes(typ)) {
    const stil = {
      heading:  { label: 'Überschrift',   klasse: 'bg-neutral-100 font-semibold', platzhalter: 'Bezeichnung der Gruppe' },
      text:     { label: 'Freitext',      klasse: 'bg-neutral-50 text-neutral-600', platzhalter: 'Erläuternder Text' },
      subtotal: { label: 'Zwischensumme', klasse: 'bg-neutral-100', platzhalter: 'Beschriftung' },
      discount: { label: 'Rabatt',        klasse: 'bg-amber-50', platzhalter: 'Bezeichnung des Rabatts' },
    }[typ]
    return (
      <div className={`border border-neutral-200 rounded-lg p-3 ${stil.klasse}`}>
        <div className="flex items-center gap-2">
          <MoveButtons istErste={istErste} istLetzte={istLetzte} onMove={onMove} />
          <span className="text-xs text-neutral-500 w-24 shrink-0">{stil.label}</span>
          <input value={pos.description} onChange={e => onChange('description', e.target.value)}
            placeholder={stil.platzhalter}
            className="flex-1 border border-neutral-200 rounded px-2 py-1.5 text-sm bg-surface" />
          {typ === 'discount' && (
            <>
              <input type="number" step="0.01" value={pos.discount_pct ?? ''}
                onChange={e => onChange('discount_pct', e.target.value)} placeholder="%"
                title="Prozent der Gruppe — leer lassen für einen festen Betrag"
                className="w-16 border border-neutral-200 rounded px-2 py-1.5 text-sm bg-surface text-right" />
              <input type="number" step="0.01" value={pos.unit_price}
                onChange={e => onChange('unit_price', e.target.value)} placeholder="Betrag"
                disabled={!!pos.discount_pct}
                className="w-24 border border-neutral-200 rounded px-2 py-1.5 text-sm bg-surface text-right disabled:opacity-40" />
            </>
          )}
          {['subtotal', 'discount'].includes(typ) && (
            <span className="text-sm font-medium text-neutral-800 w-28 text-right">{fmtEuro(betrag)}</span>
          )}
          <button onClick={onRemove} className="p-1 text-neutral-400 hover:text-red-500"><Trash2 size={14} /></button>
        </div>
        {typ === 'discount' && (
          <p className="text-xs text-neutral-500 mt-1.5 ml-26">
            Wirkt auf die Positionen seit der letzten Überschrift oder Zwischensumme
            und wird anteilig auf deren Steuersätze verteilt.
          </p>
        )}
      </div>
    )
  }

  const lineTotal = calcLine(pos)
  return (
    <div className="border border-neutral-200 rounded-lg p-3 bg-neutral-50">
      <div className="grid grid-cols-2 md:grid-cols-12 gap-2 items-start">
        <div className="col-span-2 md:col-span-5">
          <input value={pos.description} onChange={e => onChange('description', e.target.value)} placeholder="Beschreibung *"
            className="w-full border border-neutral-200 rounded px-2 py-1.5 text-sm bg-surface" />
        </div>
        <div className="col-span-1 md:col-span-1">
          <input type="number" value={pos.quantity} onChange={e => onChange('quantity', e.target.value)} placeholder="Menge"
            className="w-full border border-neutral-200 rounded px-2 py-1.5 text-sm bg-surface text-right" />
        </div>
        <div className="col-span-1 md:col-span-1">
          <input value={pos.unit || ''} onChange={e => onChange('unit', e.target.value)} placeholder="Einh."
            className="w-full border border-neutral-200 rounded px-2 py-1.5 text-sm bg-surface" />
        </div>
        <div className="col-span-1 md:col-span-2">
          <input type="number" step="0.01" value={pos.unit_price} onChange={e => onChange('unit_price', e.target.value)} placeholder="Preis"
            className="w-full border border-neutral-200 rounded px-2 py-1.5 text-sm bg-surface text-right" />
        </div>
        {/* Bei „Ein Satz für alle" steuert das Feld oben im Kopf — hier wäre es
            irreführend, weil eine Änderung je Zeile ohnehin überschrieben wird. */}
        {taxMode === 'per_position' && (
          <div className="col-span-1 md:col-span-1">
            {/* Sätze kommen aus den Verkaufseinstellungen — früher fest
                verdrahtet, dadurch war z.B. 13 % gar nicht erfassbar. */}
            <select value={pos.tax_rate} onChange={e => onChange('tax_rate', e.target.value)}
              className="w-full border border-neutral-200 rounded px-1 py-1.5 text-sm bg-surface">
              {taxRates.map(t => (
                <option key={t.satz} value={String(t.satz)} title={t.bezeichnung}>{t.satz}%</option>
              ))}
              {/* Ein am Beleg gespeicherter Satz, der nicht mehr gepflegt ist,
                  darf nicht stillschweigend verschwinden. */}
              {pos.tax_rate !== '' && pos.tax_rate != null
                && !taxRates.some(t => String(t.satz) === String(pos.tax_rate)) && (
                <option value={String(pos.tax_rate)}>{pos.tax_rate}%</option>
              )}
              <option value="">RC</option>
            </select>
          </div>
        )}
        <div className="col-span-1 md:col-span-1 flex items-center justify-end">
          <span className="text-sm font-medium text-neutral-800">{fmtEuro(lineTotal)}</span>
        </div>
        <div className="col-span-1 md:col-span-1 flex items-center justify-center gap-0.5">
          <MoveButtons istErste={istErste} istLetzte={istLetzte} onMove={onMove} />
          <button onClick={onRemove} className="p-1 text-neutral-400 hover:text-red-500"><Trash2 size={14} /></button>
        </div>
      </div>
      <div className="mt-2 flex gap-2">
        <input value={pos.detail || ''} onChange={e => onChange('detail', e.target.value)} placeholder="Zusatztext (optional)"
          className="flex-1 border border-neutral-100 rounded px-2 py-1 text-xs bg-surface text-neutral-500" />
        {/* Erlöskonto: leer = Standard-Erlöskonto aus dem Kontenplan. Wird beim
            Übernehmen eines Artikels aus dessen Stammdaten vorbelegt. */}
        <input value={pos.account_nr || ''} onChange={e => onChange('account_nr', e.target.value || null)}
          placeholder="Erlöskonto" title="Leer = Standard-Erlöskonto"
          className="w-28 border border-neutral-100 rounded px-2 py-1 text-xs bg-surface text-neutral-500 font-mono" />
      </div>
      <PositionImage pos={pos} onChange={onChange} />
    </div>
  )
}
