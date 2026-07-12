import { useState, useEffect, useRef } from 'react'
import {
  CheckCircle2, Circle, Plus, UserPlus, Trash2, ChevronDown, ChevronRight,
  X, User, Users, Loader2, Mail,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { projektplanApi, usersApi, masterdataApi } from '../services/api'
import errMsg from '../utils/errMsg'

/**
 * Checkliste an Projekt oder Aufgabe.
 *  - immer eine leere "Element hinzufügen"-Zeile
 *  - erledigte Einträge werden durchgestrichen
 *  - je Element: Plus (als Aufgabe), Männchen (zuweisen + E-Mail), Mistkübel (löschen)
 *
 * Props: parentType ('project'|'task'), parentId, onItemPromoted (optional callback)
 */
export default function Checklist({ parentType, parentId, onItemPromoted }) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [collapsed, setCollapsed] = useState(false)
  const [newText, setNewText] = useState('')
  const [assignFor, setAssignFor] = useState(null)   // Element, das zugewiesen wird

  const load = async () => {
    try {
      const { data } = await projektplanApi.listChecklist(parentType, parentId)
      setItems(data)
    } catch {
      // still – Checkliste ist optional
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [parentType, parentId])

  const add = async () => {
    const text = newText.trim()
    if (!text) return
    try {
      const { data } = await projektplanApi.addChecklist(parentType, parentId, { text, sort_order: items.length })
      setItems(list => [...list, data])
      setNewText('')
    } catch (err) {
      toast.error(errMsg(err, 'Konnte nicht hinzugefügt werden'))
    }
  }

  const toggle = async (it) => {
    try {
      const { data } = await projektplanApi.updateChecklist(it.id, { is_done: !it.is_done })
      setItems(list => list.map(x => x.id === it.id ? data : x))
    } catch {
      toast.error('Status konnte nicht geändert werden')
    }
  }

  const remove = async (it) => {
    try {
      await projektplanApi.deleteChecklist(it.id)
      setItems(list => list.filter(x => x.id !== it.id))
    } catch {
      toast.error('Konnte nicht gelöscht werden')
    }
  }

  const promote = async (it) => {
    try {
      await projektplanApi.checklistToTask(it.id)
      toast.success('Als Aufgabe angelegt')
      await load()
      onItemPromoted?.()
    } catch (err) {
      toast.error(errMsg(err, 'Konnte nicht als Aufgabe angelegt werden'))
    }
  }

  const doneCount = items.filter(i => i.is_done).length

  return (
    <div>
      <button onClick={() => setCollapsed(c => !c)} className="flex items-center gap-2 mb-2 text-sm font-medium text-gray-700">
        {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
        Checkliste <span className="text-gray-400 font-normal">{doneCount} / {items.length}</span>
      </button>

      {!collapsed && (
        <div className="space-y-0.5">
          {loading ? (
            <div className="text-xs text-gray-400 px-2 py-1">Lade…</div>
          ) : (
            items.map((it) => (
              <div key={it.id} className="group flex items-center gap-2 px-1 py-1.5 rounded-lg hover:bg-gray-50">
                <button onClick={() => toggle(it)} className="shrink-0">
                  {it.is_done
                    ? <CheckCircle2 size={18} className="text-green-600" />
                    : <Circle size={18} className="text-gray-300 hover:text-primary-400" />}
                </button>
                <span className={`flex-1 text-sm ${it.is_done ? 'line-through text-gray-400' : 'text-gray-800'}`}>
                  {it.text}
                </span>
                {it.assignee_name && (
                  <span className="text-[11px] text-primary-500 shrink-0 hidden sm:inline">{it.assignee_name}</span>
                )}
                {it.linked_task_id && (
                  <span className="text-[10px] text-gray-400 shrink-0">↗ Aufgabe</span>
                )}

                {/* Aktions-Symbole – auf Hover sichtbar */}
                <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition">
                  {!it.linked_task_id && (
                    <button onClick={() => promote(it)} title="Als Aufgabe anlegen"
                      className="text-gray-400 hover:text-primary-600 p-0.5">
                      <Plus size={16} />
                    </button>
                  )}
                  <button onClick={() => setAssignFor(it)} title="Zuweisen (Benutzer/Kontakt)"
                    className="text-gray-400 hover:text-primary-600 p-0.5">
                    <UserPlus size={16} />
                  </button>
                  <button onClick={() => remove(it)} title="Löschen"
                    className="text-gray-400 hover:text-red-600 p-0.5">
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))
          )}

          {/* Immer eine leere Eingabezeile */}
          <div className="flex items-center gap-2 px-1 py-1.5">
            <Circle size={18} className="text-gray-200 shrink-0" />
            <input
              value={newText}
              onChange={(e) => setNewText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && add()}
              onBlur={() => newText.trim() && add()}
              placeholder="Element hinzufügen"
              className="flex-1 text-sm bg-transparent focus:outline-none placeholder-gray-400"
            />
          </div>
        </div>
      )}

      {assignFor && (
        <AssignDialog
          item={assignFor}
          onClose={() => setAssignFor(null)}
          onAssigned={(updated) => { setItems(list => list.map(x => x.id === updated.id ? updated : x)); setAssignFor(null) }}
        />
      )}
    </div>
  )
}

/** Zuweisungs-Dialog: Benutzer oder Kontakt + E-Mail-Versand */
function AssignDialog({ item, onClose, onAssigned }) {
  const [mode, setMode] = useState('user')     // 'user' | 'contact'
  const [users, setUsers] = useState([])
  const [userId, setUserId] = useState('')
  const [contactSearch, setContactSearch] = useState('')
  const [contactResults, setContactResults] = useState([])
  const [contact, setContact] = useState(null)   // {id, name, email}
  const [email, setEmail] = useState('')
  const [sendMail, setSendMail] = useState(true)
  const [busy, setBusy] = useState(false)

  useEffect(() => { usersApi.list().then(r => setUsers(r.data)).catch(() => {}) }, [])

  useEffect(() => {
    if (mode !== 'contact') return
    const t = setTimeout(async () => {
      try {
        const res = await masterdataApi.listRecords('kontakte', { search: contactSearch || undefined, page_size: 20 })
        setContactResults(res.data.items || [])
      } catch { setContactResults([]) }
    }, 300)
    return () => clearTimeout(t)
  }, [contactSearch, mode])

  const selUser = users.find(u => u.id === userId)
  const autoEmail = mode === 'user' ? (selUser?.email || '') : (contact?.email || '')
  const targetEmail = email || autoEmail   // manuelle Eingabe hat Vorrang
  const targetName = mode === 'user' ? (selUser?.full_name || selUser?.name || selUser?.email || '') : (contact?.name || '')

  const assign = async () => {
    if (mode === 'user' && !userId) return toast.error('Bitte einen Benutzer wählen')
    if (mode === 'contact' && !contact) return toast.error('Bitte einen Kontakt wählen')
    if (sendMail && !targetEmail) return toast.error('Keine E-Mail-Adresse – bitte eingeben')
    setBusy(true)
    try {
      const { data } = await projektplanApi.assignChecklist(item.id, {
        assignee_user_id: mode === 'user' ? userId : null,
        assignee_contact_id: mode === 'contact' ? contact.id : null,
        assignee_name: targetName,
        email: targetEmail || null,
        send_email: sendMail,
      })
      toast.success(sendMail ? 'Zugewiesen & E-Mail versendet' : 'Zugewiesen')
      onAssigned(data)
    } catch (err) {
      toast.error(errMsg(err, 'Zuweisung fehlgeschlagen'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[70] sheet-safe flex items-end md:items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-surface w-full md:max-w-md rounded-2xl p-5 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-base font-medium text-gray-900">Element zuweisen</h2>
          <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
        </div>
        <p className="text-sm text-gray-500 mb-4 truncate">„{item.text}"</p>

        <div className="flex gap-2 mb-4">
          <button onClick={() => setMode('user')}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm border ${mode === 'user' ? 'border-primary-300 bg-primary-50 text-primary-700' : 'border-gray-200 text-gray-600'}`}>
            <User size={15} /> Benutzer
          </button>
          <button onClick={() => setMode('contact')}
            className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm border ${mode === 'contact' ? 'border-primary-300 bg-primary-50 text-primary-700' : 'border-gray-200 text-gray-600'}`}>
            <Users size={15} /> Kontakt
          </button>
        </div>

        {mode === 'user' ? (
          <select value={userId} onChange={(e) => setUserId(e.target.value)}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mb-3">
            <option value="">– Benutzer wählen –</option>
            {users.map(u => <option key={u.id} value={u.id}>{u.full_name || u.name || u.email}</option>)}
          </select>
        ) : (
          <div className="mb-3">
            {contact ? (
              <div className="flex items-center gap-2 border border-gray-300 rounded-lg px-3 py-2">
                <Users size={15} className="text-primary-500" />
                <span className="flex-1 text-sm truncate">{contact.name}</span>
                <button onClick={() => setContact(null)}><X size={15} className="text-gray-400" /></button>
              </div>
            ) : (
              <div className="relative">
                <input value={contactSearch} onChange={(e) => setContactSearch(e.target.value)}
                  placeholder="Kontakt suchen…"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400" />
                {contactResults.length > 0 && (
                  <div className="absolute z-50 top-full left-0 right-0 bg-surface border border-gray-200 rounded-lg shadow-lg mt-1 max-h-44 overflow-y-auto">
                    {contactResults.map(r => (
                      <button key={r.id} type="button"
                        onMouseDown={() => {
                          setContact({ id: r.id, name: r.display_name, email: r.data?.email || r.data?.e_mail || r.data?.mail || '' })
                          setContactResults([])
                        }}
                        className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 border-b border-gray-100 last:border-0">
                        {r.display_name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <label className="flex items-center gap-2 text-sm text-gray-700 mb-2">
          <input type="checkbox" checked={sendMail} onChange={(e) => setSendMail(e.target.checked)} />
          <Mail size={14} /> E-Mail-Benachrichtigung senden
        </label>

        {sendMail && (
          <div className="mb-4">
            <label className="text-xs text-gray-500 mb-1 block">
              E-Mail-Adresse {autoEmail ? '(automatisch erkannt, überschreibbar)' : '(bitte eingeben)'}
            </label>
            <input
              value={targetEmail}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="name@firma.at"
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400" />
          </div>
        )}

        <button onClick={assign} disabled={busy}
          className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-2.5 rounded-lg font-medium">
          {busy ? <Loader2 size={18} className="animate-spin" /> : <UserPlus size={18} />} Zuweisen
        </button>
      </div>
    </div>
  )
}
