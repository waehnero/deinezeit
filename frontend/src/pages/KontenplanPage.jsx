import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { accountingApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import { BookText, ArrowLeft, Loader2, Star, Plus, Save, Eye, Trash2, Lock } from 'lucide-react'

/**
 * Kontenplan (EKR).
 *
 * Lag bisher als Reiter in den Einstellungen und war damit nur für Admins
 * erreichbar. Der Kontenplan ist aber Arbeitsmittel der Buchhaltung, nicht
 * Konfiguration der Anwendung — deshalb steht er jetzt im Bereich Buchhaltung.
 *
 * **Ändern** darf ihn weiterhin nur ein Admin; das prüft auch das Backend
 * (require_admin an den Schreib-Endpunkten). Alle anderen mit dem Recht
 * „Buchhaltung" sehen ihn nur — was beim Zuordnen von Erlöskonten reicht.
 */
const TYP_LABELS = { aktiv: 'Aktiv', passiv: 'Passiv', ertrag: 'Ertrag', aufwand: 'Aufwand', neutral: 'Neutral' }
const TYP_COLORS = {
  aktiv: 'bg-blue-50 text-blue-700', passiv: 'bg-purple-50 text-purple-700',
  ertrag: 'bg-green-50 text-green-700', aufwand: 'bg-red-50 text-red-700',
  neutral: 'bg-neutral-100 text-neutral-600',
}

export default function KontenplanPage() {
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)
  const [editRow, setEditRow] = useState(null)
  const [editData, setEditData] = useState({})
  const [showNew, setShowNew] = useState(false)
  const [newData, setNewData] = useState({ nr: '', name: '', typ: 'ertrag', ust_code: '', beschreibung: '' })
  const [typFilter, setTypFilter] = useState('')
  const [search, setSearch] = useState('')

  async function load() {
    setLoading(true)
    try { const res = await accountingApi.listAccounts({ active_only: false }); setAccounts(res.data) }
    catch { toast.error('Fehler beim Laden') }
    finally { setLoading(false) }
  }
  useEffect(() => { load() }, [])

  const filtered = accounts.filter(a => {
    if (typFilter && a.typ !== typFilter) return false
    if (search) { const s = search.toLowerCase(); return a.nr.includes(s) || a.name.toLowerCase().includes(s) }
    return true
  })

  async function handleSave(id) {
    try { await accountingApi.updateAccount(id, editData); toast.success('Gespeichert'); setEditRow(null); load() }
    catch { toast.error('Fehler') }
  }
  async function handleCreate() {
    try {
      await accountingApi.createAccount(newData)
      toast.success(`Konto ${newData.nr} angelegt`)
      setShowNew(false)
      setNewData({ nr: '', name: '', typ: 'ertrag', ust_code: '', beschreibung: '' })
      load()
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler') }
  }
  async function handleDelete(id, nr) {
    if (!window.confirm(`Konto ${nr} wirklich löschen?`)) return
    try { await accountingApi.deleteAccount(id); toast.success('Gelöscht'); load() }
    catch { toast.error('Fehler') }
  }
  async function handleSetDefault(id) {
    try { await accountingApi.setDefaultErloes(id); toast.success('Standard-Erlöskonto gesetzt'); load() }
    catch { toast.error('Fehler') }
  }

  if (loading) return <div className="flex justify-center py-16"><Loader2 size={24} className="animate-spin text-neutral-400" /></div>

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/buchhaltung')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
          <ArrowLeft size={18} />
        </button>
        <PageHeader icon={BookText} title="Kontenplan"
          subtitle="Vorbefüllt mit dem österreichischen EKR" />
      </div>

      {!isAdmin && (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-neutral-200 bg-neutral-50 px-4 py-3 text-sm text-neutral-600">
          <Lock size={15} className="mt-0.5 shrink-0" />
          <span>Nur zur Ansicht — Konten anlegen, ändern oder löschen darf ein Administrator.</span>
        </div>
      )}

      <p className="text-xs text-neutral-400 mb-4">
        <Star size={11} className="inline mb-0.5" />-Konto = Standard-Erlöskonto für neue Positionen.
      </p>

      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Nr. oder Name…"
          className="flex-1 max-w-xs border border-neutral-200 rounded-lg px-3 py-1.5 text-sm" />
        <select value={typFilter} onChange={e => setTypFilter(e.target.value)}
          className="text-sm border border-neutral-200 rounded-lg px-3 py-1.5">
          <option value="">Alle Typen</option>
          {Object.entries(TYP_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        {isAdmin && (
          <button onClick={() => setShowNew(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700">
            <Plus size={14} /> Konto hinzufügen
          </button>
        )}
      </div>

      {showNew && (
        <div className="border border-primary-200 bg-primary-50 rounded-xl p-4 mb-3 grid grid-cols-12 gap-2 items-center">
          <input value={newData.nr} onChange={e => setNewData({ ...newData, nr: e.target.value })} placeholder="Nr." className="col-span-2 border border-neutral-200 rounded px-2 py-1.5 text-sm" />
          <input value={newData.name} onChange={e => setNewData({ ...newData, name: e.target.value })} placeholder="Bezeichnung" className="col-span-4 border border-neutral-200 rounded px-2 py-1.5 text-sm" />
          <select value={newData.typ} onChange={e => setNewData({ ...newData, typ: e.target.value })} className="col-span-2 border border-neutral-200 rounded px-2 py-1.5 text-sm">
            {Object.entries(TYP_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <input value={newData.ust_code} onChange={e => setNewData({ ...newData, ust_code: e.target.value })} placeholder="USt-Code" className="col-span-2 border border-neutral-200 rounded px-2 py-1.5 text-sm" />
          <div className="col-span-2 flex gap-1">
            <button onClick={handleCreate} className="flex-1 px-2 py-1.5 text-xs bg-primary-600 text-white rounded hover:bg-primary-700">Anlegen</button>
            <button onClick={() => setShowNew(false)} className="px-2 py-1.5 text-xs border rounded hover:bg-neutral-50">✕</button>
          </div>
        </div>
      )}

      <div className="border border-neutral-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="bg-neutral-50 border-b border-neutral-100">
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-20">Nr.</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500">Bezeichnung</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-24">Typ</th>
            <th className="text-left px-3 py-2.5 font-medium text-neutral-500 w-20">USt-Code</th>
            <th className="px-3 py-2.5 w-28"></th>
          </tr></thead>
          <tbody className="divide-y divide-neutral-50">
            {filtered.map(a => (
              <tr key={a.id} className={`hover:bg-neutral-50 ${!a.is_active ? 'opacity-40' : ''}`}>
                {editRow === a.id ? (
                  <>
                    <td className="px-2 py-1.5"><input value={editData.nr} onChange={e => setEditData({ ...editData, nr: e.target.value })} className="w-full border border-neutral-200 rounded px-2 py-1 text-sm font-mono" /></td>
                    <td className="px-2 py-1.5"><input value={editData.name} onChange={e => setEditData({ ...editData, name: e.target.value })} className="w-full border border-neutral-200 rounded px-2 py-1 text-sm" /></td>
                    <td className="px-2 py-1.5"><select value={editData.typ} onChange={e => setEditData({ ...editData, typ: e.target.value })} className="w-full border border-neutral-200 rounded px-1 py-1 text-xs">{Object.entries(TYP_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></td>
                    <td className="px-2 py-1.5"><input value={editData.ust_code || ''} onChange={e => setEditData({ ...editData, ust_code: e.target.value })} className="w-full border border-neutral-200 rounded px-2 py-1 text-xs" /></td>
                    <td className="px-2 py-1.5"><div className="flex gap-1">
                      <button onClick={() => handleSave(a.id)} className="px-2 py-1 text-xs bg-primary-600 text-white rounded hover:bg-primary-700"><Save size={12} /></button>
                      <button onClick={() => setEditRow(null)} className="px-2 py-1 text-xs border rounded hover:bg-neutral-50">✕</button>
                    </div></td>
                  </>
                ) : (
                  <>
                    <td className="px-3 py-2.5 font-mono font-medium text-neutral-800">{a.nr}{a.is_default_erloes && <Star size={11} className="inline ml-1 text-amber-500 mb-0.5" fill="currentColor" />}</td>
                    <td className="px-3 py-2.5 text-neutral-700">{a.name}</td>
                    <td className="px-3 py-2.5"><span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYP_COLORS[a.typ] || 'bg-neutral-100 text-neutral-600'}`}>{TYP_LABELS[a.typ] || a.typ}</span></td>
                    <td className="px-3 py-2.5 text-xs text-neutral-500 font-mono">{a.ust_code || '—'}</td>
                    <td className="px-3 py-2.5"><div className="flex gap-1 justify-end">
                      {isAdmin && !a.is_default_erloes && a.typ === 'ertrag' && (
                        <button onClick={() => handleSetDefault(a.id)} title="Standard-Erlöskonto" className="p-1 text-neutral-400 hover:text-amber-500"><Star size={13} /></button>
                      )}
                      {isAdmin && (
                        <>
                          <button onClick={() => { setEditRow(a.id); setEditData({ nr: a.nr, name: a.name, typ: a.typ, ust_code: a.ust_code || '', beschreibung: a.beschreibung || '', is_active: a.is_active, is_default_erloes: a.is_default_erloes }) }} className="p-1 text-neutral-400 hover:text-neutral-700"><Eye size={13} /></button>
                          <button onClick={() => handleDelete(a.id, a.nr)} className="p-1 text-neutral-400 hover:text-red-500"><Trash2 size={13} /></button>
                        </>
                      )}
                    </div></td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && <div className="text-center py-8 text-sm text-neutral-400">Keine Konten gefunden</div>}
      </div>
      <p className="text-xs text-neutral-400 mt-2">{filtered.length} von {accounts.length} Konten</p>
    </div>
  )
}
