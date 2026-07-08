import { useState, useEffect, useCallback } from 'react'
import { zeiterfassungApi } from '../services/api'
import toast from 'react-hot-toast'
import { Plus, Trash2, Loader2, Wallet, AlertTriangle } from 'lucide-react'

// Minuten als h:mm formatieren (negativ möglich, z.B. -1:30)
export function fmtBudgetMinutes(min) {
  if (min === null || min === undefined) return '—'
  const sign = min < 0 ? '-' : ''
  const abs = Math.abs(min)
  const h = Math.floor(abs / 60)
  const m = abs % 60
  return `${sign}${h}:${String(m).padStart(2, '0')}`
}

/**
 * Verwaltung der Stundenkonten einer Projektzeit.
 *
 * Stundenkonten sind vom Kunden im Voraus erworbene Stundenpakete.
 * Das Budget der Projektzeit = Summe der Konten; verbraucht wird es
 * durch verrechenbare Zeiteinträge. Ist es aufgebraucht, wird darauf
 * hingewiesen, dem Kunden ein neues Stundenkonto anzubieten.
 *
 * Zwei Betriebsarten:
 * - projectId gesetzt (Bearbeiten): Konten werden direkt über die API
 *   gespeichert/gelöscht.
 * - projectId null (Neuanlegen): Konten werden lokal in `pending` /
 *   `onPendingChange` gesammelt und vom Aufrufer (RecordModal) nach dem
 *   Anlegen des Datensatzes gespeichert — der Dialog ist damit beim
 *   Anlegen und Bearbeiten gleich aufgebaut.
 */
export default function StundenkontenPanel({ projectId = null, pending = [], onPendingChange = null }) {
  const isLocal = !projectId
  const [konten, setKonten] = useState([])
  const [budget, setBudget] = useState(null)
  const [loading, setLoading] = useState(!isLocal)
  const [showForm, setShowForm] = useState(false)
  const [saving, setSaving] = useState(false)

  const today = new Date().toISOString().slice(0, 10)
  const [form, setForm] = useState({ bezeichnung: '', stunden: '', preis: '', erworben_am: today })

  const load = useCallback(async () => {
    if (isLocal) return
    try {
      const [kontenRes, budgetRes] = await Promise.all([
        zeiterfassungApi.listStundenkonten(projectId),
        zeiterfassungApi.getBudgets([projectId]),
      ])
      setKonten(kontenRes.data)
      setBudget(budgetRes.data[0] || null)
    } catch {
      toast.error('Stundenkonten konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }, [projectId, isLocal])

  useEffect(() => { load() }, [load])

  // Beim Neuanlegen: lokale Liste + lokal berechnetes Budget (noch kein Verbrauch)
  const items = isLocal ? pending : konten
  const localBudgetMinutes = pending.reduce((sum, k) => sum + Math.round(Number(k.stunden) * 60), 0)
  const shownBudget = isLocal
    ? (pending.length
        ? { has_budget: true, budget_minutes: localBudgetMinutes, consumed_minutes: 0,
            remaining_minutes: localBudgetMinutes, exhausted: false }
        : null)
    : budget

  const handleAdd = async () => {
    const stunden = parseFloat(String(form.stunden).replace(',', '.'))
    if (!stunden || stunden <= 0) return toast.error('Bitte gültige Stundenanzahl angeben')
    if (!form.erworben_am) return toast.error('Bitte Kaufdatum angeben')
    const payload = {
      bezeichnung: form.bezeichnung || null,
      stunden,
      preis: form.preis ? parseFloat(String(form.preis).replace(',', '.')) : null,
      erworben_am: form.erworben_am,
    }

    if (isLocal) {
      onPendingChange?.([...pending, { ...payload, id: `tmp-${Date.now()}` }])
      setForm({ bezeichnung: '', stunden: '', preis: '', erworben_am: today })
      setShowForm(false)
      return
    }

    setSaving(true)
    try {
      await zeiterfassungApi.createStundenkonto(projectId, payload)
      toast.success('Stundenkonto erfasst')
      setForm({ bezeichnung: '', stunden: '', preis: '', erworben_am: today })
      setShowForm(false)
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (konto) => {
    if (isLocal) {
      onPendingChange?.(pending.filter(k => k.id !== konto.id))
      return
    }
    try {
      await zeiterfassungApi.deleteStundenkonto(konto.id)
      toast.success('Stundenkonto gelöscht')
      load()
    } catch {
      toast.error('Löschen fehlgeschlagen')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-6">
        <Loader2 size={20} className="animate-spin text-primary-400" />
      </div>
    )
  }

  const inputCls = "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"

  return (
    <div className="pt-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Wallet size={15} className="text-primary-600" />
          <h3 className="text-sm font-semibold text-gray-800">Stundenkonten (Budget)</h3>
        </div>
        <button type="button" onClick={() => setShowForm(v => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-primary-600 border border-primary-200 rounded-lg hover:bg-primary-50 transition">
          <Plus size={13} /> Stundenkonto
        </button>
      </div>

      {/* Budget-Übersicht */}
      {shownBudget?.has_budget && (
        <div className={`flex flex-wrap items-center gap-x-5 gap-y-1 px-4 py-3 rounded-xl mb-3 text-sm ${
          shownBudget.exhausted ? 'bg-red-50 border border-red-200' : 'bg-gray-50 border border-gray-200'}`}>
          <span className="text-gray-500">Budget <b className="text-gray-800">{fmtBudgetMinutes(shownBudget.budget_minutes)} h</b></span>
          <span className="text-gray-500">Verbraucht <b className="text-gray-800">{fmtBudgetMinutes(shownBudget.consumed_minutes)} h</b></span>
          <span className="text-gray-500">Rest <b className={shownBudget.exhausted ? 'text-red-600' : 'text-green-700'}>{fmtBudgetMinutes(shownBudget.remaining_minutes)} h</b></span>
          {shownBudget.exhausted && (
            <span className="flex items-center gap-1.5 text-red-600 font-medium">
              <AlertTriangle size={13} /> Budget verbraucht – dem Kunden ein neues Stundenkonto anbieten
            </span>
          )}
        </div>
      )}

      {/* Formular: neues Stundenkonto */}
      {showForm && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 border border-gray-200 rounded-xl mb-3 bg-gray-50">
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-xs font-medium text-gray-500 mb-1">Bezeichnung</label>
            <input type="text" value={form.bezeichnung} placeholder="z.B. Stundenpaket 10h"
              onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Stunden *</label>
            <input type="number" min="0" step="0.25" value={form.stunden}
              onChange={(e) => setForm({ ...form, stunden: e.target.value })} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Preis (netto)</label>
            <input type="number" min="0" step="0.01" value={form.preis}
              onChange={(e) => setForm({ ...form, preis: e.target.value })} className={inputCls} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Erworben am *</label>
            <input type="date" value={form.erworben_am}
              onChange={(e) => setForm({ ...form, erworben_am: e.target.value })} className={inputCls} />
          </div>
          <div className="col-span-2 sm:col-span-4 flex justify-end gap-2">
            <button type="button" onClick={() => setShowForm(false)}
              className="px-4 py-2 text-sm border border-gray-300 rounded-lg text-gray-600 hover:bg-white transition">
              Abbrechen
            </button>
            <button type="button" onClick={handleAdd} disabled={saving}
              className="px-4 py-2 text-sm font-medium bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white rounded-lg transition flex items-center gap-2">
              {saving && <Loader2 size={13} className="animate-spin" />} Erfassen
            </button>
          </div>
        </div>
      )}

      {/* Liste der Konten */}
      {items.length === 0 ? (
        <p className="text-sm text-gray-400 py-2">
          Noch keine Stundenkonten erfasst. Ohne Stundenkonto wird für diese Projektzeit kein Budget geführt.
        </p>
      ) : (
        <ul className="divide-y divide-gray-100 border border-gray-200 rounded-xl overflow-hidden">
          {items.map(k => (
            <li key={k.id} className="flex items-center gap-3 px-4 py-2.5 text-sm bg-white">
              <div className="flex-1 min-w-0">
                <span className="font-medium text-gray-800">{k.bezeichnung || 'Stundenkonto'}</span>
                <span className="text-gray-400 ml-2 text-xs">
                  erworben am {new Date(k.erworben_am).toLocaleDateString('de-AT')}
                  {k.preis != null && <> · {Number(k.preis).toLocaleString('de-AT', { minimumFractionDigits: 2 })} €</>}
                </span>
              </div>
              <span className="font-semibold text-gray-800 tabular-nums">
                {Number(k.stunden).toLocaleString('de-AT')} h
              </span>
              <button type="button" onClick={() => handleDelete(k)} title="Löschen"
                className="p-1.5 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition">
                <Trash2 size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
