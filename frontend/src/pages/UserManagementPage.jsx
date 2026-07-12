import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { usersApi, authApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import {
  Users, Plus, Trash2, UserCheck, UserX,
  Loader2, X, Pencil, ShieldOff, KeyRound
} from 'lucide-react'

const ROLE_LABELS = { admin: 'Administrator', employee: 'Mitarbeiter' }
const ROLE_COLORS = {
  admin: 'bg-primary-50 text-primary-700 border-primary-200',
  employee: 'bg-neutral-100 text-neutral-600 border-neutral-200',
}

function Modal({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4 sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-neutral-100">
          <h2 className="text-base font-semibold text-neutral-900">{title}</h2>
          <button onClick={onClose} className="p-1.5 text-neutral-400 hover:text-neutral-600 hover:bg-neutral-100 rounded-lg transition">
            <X size={18} />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  )
}

function NewUserModal({ onClose, onCreated }) {
  const [form, setForm] = useState({ email: '', full_name: '', password: '', role: 'employee', language: 'de' })
  const [loading, setLoading] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await usersApi.create(form)
      toast.success(`${form.full_name} wurde angelegt`)
      onCreated(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Anlegen')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title="Neuen Benutzer anlegen" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="label">Name *</label>
          <input className="input" type="text" value={form.full_name} onChange={e => set('full_name', e.target.value)} required autoFocus placeholder="Vor- und Nachname" />
        </div>
        <div>
          <label className="label">E-Mail *</label>
          <input className="input" type="email" value={form.email} onChange={e => set('email', e.target.value)} required placeholder="name@firma.at" />
        </div>
        <div>
          <label className="label">Passwort *</label>
          <input className="input" type="password" value={form.password} onChange={e => set('password', e.target.value)} required minLength={8} placeholder="Mindestens 8 Zeichen" />
        </div>
        <div>
          <label className="label">Rolle</label>
          <div className="flex gap-2">
            {['employee', 'admin'].map(r => (
              <button key={r} type="button" onClick={() => set('role', r)}
                className={`flex-1 py-2 text-sm rounded-lg border-2 transition font-medium ${form.role === r ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-neutral-200 text-neutral-600 hover:border-neutral-300'}`}>
                {ROLE_LABELS[r]}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="label">Sprache</label>
          <div className="flex gap-2">
            {[{ code: 'de', label: 'Deutsch' }, { code: 'en', label: 'English' }].map(l => (
              <button key={l.code} type="button" onClick={() => set('language', l.code)}
                className={`flex-1 py-2 text-sm rounded-lg border-2 transition ${form.language === l.code ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-neutral-200 text-neutral-600 hover:border-neutral-300'}`}>
                {l.label}
              </button>
            ))}
          </div>
        </div>
        <div className="flex gap-3 pt-1">
          <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Abbrechen</button>
          <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
            Anlegen
          </button>
        </div>
      </form>
    </Modal>
  )
}

// Modul-Liste — muss zu backend/app/core/modules.py passen
const ALL_MODULES = [
  { key: 'dashboard',     label: 'Dashboard' },
  { key: 'zeiterfassung', label: 'Zeiterfassung' },
  { key: 'aufgaben',      label: 'Aufgaben' },
  { key: 'projekte',      label: 'Projekte' },
  { key: 'verkauf',       label: 'Verkauf' },
  { key: 'postecke',      label: 'Postecke' },
  { key: 'stammdaten',    label: 'Stammdaten' },
  { key: 'datacenter',    label: 'Datacenter' },
]

function EditUserModal({ user, onClose, onUpdated }) {
  const [form, setForm] = useState({
    full_name: user.full_name,
    role: user.role,
    language: user.language,
    password: '',
    disable_totp: false,
    // null (= alle erlaubt) → volle Liste vorauswählen
    modules: user.allowed_modules ?? ALL_MODULES.map(m => m.key),
  })
  const [loading, setLoading] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const toggleModule = (key) => {
    setForm(f => ({
      ...f,
      modules: f.modules.includes(key)
        ? f.modules.filter(m => m !== key)
        : [...f.modules, key],
    }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const payload = {
        full_name: form.full_name,
        role: form.role,
        language: form.language,
        disable_totp: form.disable_totp || undefined,
        allowed_modules: form.modules,
      }
      if (form.password) payload.password = form.password
      const res = await usersApi.updateByAdmin(user.id, payload)
      toast.success(`${form.full_name} wurde aktualisiert`)
      onUpdated(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal title={`${user.full_name} bearbeiten`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="label">Name</label>
          <input className="input" type="text" value={form.full_name} onChange={e => set('full_name', e.target.value)} required />
        </div>
        <div>
          <label className="label">Neues Passwort <span className="text-neutral-400 font-normal">(leer lassen = unverändert)</span></label>
          <input className="input" type="password" value={form.password} onChange={e => set('password', e.target.value)} placeholder="Neues Passwort vergeben" minLength={8} />
        </div>
        <div>
          <label className="label">Rolle</label>
          <div className="flex gap-2">
            {['employee', 'admin'].map(r => (
              <button key={r} type="button" onClick={() => set('role', r)}
                className={`flex-1 py-2 text-sm rounded-lg border-2 transition font-medium ${form.role === r ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-neutral-200 text-neutral-600 hover:border-neutral-300'}`}>
                {ROLE_LABELS[r]}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="label">Sprache</label>
          <div className="flex gap-2">
            {[{ code: 'de', label: 'Deutsch' }, { code: 'en', label: 'English' }].map(l => (
              <button key={l.code} type="button" onClick={() => set('language', l.code)}
                className={`flex-1 py-2 text-sm rounded-lg border-2 transition ${form.language === l.code ? 'border-primary-500 bg-primary-50 text-primary-700' : 'border-neutral-200 text-neutral-600 hover:border-neutral-300'}`}>
                {l.label}
              </button>
            ))}
          </div>
        </div>
        {/* Modulrechte: nur relevant für Mitarbeiter — Admins sehen immer alles */}
        {form.role !== 'admin' && (
          <div>
            <label className="label">Module <span className="text-neutral-400 font-normal">(was dieser Benutzer verwenden darf)</span></label>
            <div className="grid grid-cols-2 gap-2">
              {ALL_MODULES.map(({ key, label }) => {
                const active = form.modules.includes(key)
                return (
                  <button key={key} type="button" onClick={() => toggleModule(key)}
                    className={`flex items-center gap-2 px-3 py-2 text-sm rounded-lg border-2 transition text-left font-medium ${
                      active
                        ? 'border-primary-500 bg-primary-50 text-primary-700'
                        : 'border-neutral-200 text-neutral-400 hover:border-neutral-300'
                    }`}>
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${active ? 'bg-primary-500' : 'bg-neutral-300'}`} />
                    {label}
                  </button>
                )
              })}
            </div>
            {form.modules.length === 0 && (
              <p className="text-xs text-amber-600 mt-1.5">
                Ohne Module sieht der Benutzer nach dem Login nur sein Profil.
              </p>
            )}
          </div>
        )}
        {user.totp_enabled && (
          <div className="flex items-center gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg">
            <ShieldOff size={16} className="text-amber-600 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-800">2-Faktor-Authentifizierung aktiv</p>
              <p className="text-xs text-amber-600">Deaktivieren wenn Benutzer keinen Zugriff mehr hat</p>
            </div>
            <button type="button" onClick={() => set('disable_totp', !form.disable_totp)}
              className={`px-3 py-1 text-xs font-medium rounded-lg border transition ${form.disable_totp ? 'bg-red-100 border-red-300 text-red-700' : 'bg-surface border-amber-300 text-amber-700 hover:bg-amber-100'}`}>
              {form.disable_totp ? '✓ Wird deaktiviert' : '2FA deaktivieren'}
            </button>
          </div>
        )}
        <div className="flex gap-3 pt-1">
          <button type="button" onClick={onClose} className="btn-secondary flex-1 justify-center">Abbrechen</button>
          <button type="submit" disabled={loading} className="btn-primary flex-1 justify-center">
            {loading ? <Loader2 size={15} className="animate-spin" /> : null}
            Speichern
          </button>
        </div>
      </form>
    </Modal>
  )
}

export default function UserManagementPage() {
  const { t } = useTranslation()
  const { isAdmin } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [currentUser, setCurrentUser] = useState(null)
  const [showNewModal, setShowNewModal] = useState(false)
  const [editUser, setEditUser] = useState(null)

  useEffect(() => {
    Promise.all([usersApi.list(), authApi.me()])
      .then(([usersRes, meRes]) => {
        setUsers(usersRes.data)
        setCurrentUser(meRes.data)
      })
      .catch(() => toast.error('Benutzer konnten nicht geladen werden'))
      .finally(() => setLoading(false))
  }, [])

  const handleDelete = async (user) => {
    if (!confirm(`„${user.full_name}" wirklich endgültig löschen?\n\nDieser Vorgang kann nicht rückgängig gemacht werden.`)) return
    try {
      await usersApi.delete(user.id)
      setUsers(prev => prev.filter(u => u.id !== user.id))
      toast.success(`${user.full_name} wurde gelöscht`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Löschen')
    }
  }

  const handleUpdated = (updatedUser) => {
    setUsers(users.map(u => u.id === updatedUser.id ? updatedUser : u))
    setEditUser(null)
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64">
      <Loader2 size={28} className="animate-spin text-primary-500" />
    </div>
  )

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-neutral-900">{t('nav.users')}</h1>
          <p className="text-neutral-400 text-sm mt-0.5">{users.length} Benutzer</p>
        </div>
        {isAdmin && (
          <button onClick={() => setShowNewModal(true)} className="btn-primary">
            <Plus size={16} /> Neuer Benutzer
          </button>
        )}
      </div>

      <div className="card overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-neutral-100 bg-neutral-50">
              <th className="px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">Name</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide hidden sm:table-cell">E-Mail</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">Rolle</th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide hidden md:table-cell">Status</th>
              <th className="px-4 py-3 w-24"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-50">
            {users.map(user => (
              <tr key={user.id} className="hover:bg-neutral-50 transition-colors">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-sm font-semibold flex-shrink-0">
                      {user.full_name?.charAt(0)?.toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-neutral-900">{user.full_name}</p>
                      <p className="text-xs text-neutral-400 sm:hidden">{user.email}</p>
                      {user.totp_enabled && (
                        <span className="text-xs text-green-600 font-medium">2FA aktiv</span>
                      )}
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-neutral-500 hidden sm:table-cell">{user.email}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-medium px-2 py-1 rounded-full border ${ROLE_COLORS[user.role]}`}>
                    {ROLE_LABELS[user.role]}
                  </span>
                </td>
                <td className="px-4 py-3 hidden md:table-cell">
                  <span className={`flex items-center gap-1.5 text-xs font-medium ${user.is_active ? 'text-green-600' : 'text-neutral-400'}`}>
                    {user.is_active ? <UserCheck size={13} /> : <UserX size={13} />}
                    {user.is_active ? 'Aktiv' : 'Deaktiviert'}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1">
                    {isAdmin && (
                      <>
                        <button
                          onClick={() => setEditUser(user)}
                          className="p-1.5 text-neutral-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition"
                          title="Benutzer bearbeiten"
                        >
                          <Pencil size={14} />
                        </button>
                        {currentUser?.id !== user.id && (
                          <button
                            onClick={() => handleDelete(user)}
                            className="p-1.5 text-neutral-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                            title="Benutzer löschen"
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {isAdmin && showNewModal && <NewUserModal onClose={() => setShowNewModal(false)} onCreated={u => { setUsers([...users, u]); setShowNewModal(false) }} />}
      {isAdmin && editUser && <EditUserModal user={editUser} onClose={() => setEditUser(null)} onUpdated={handleUpdated} />}
    </div>
  )
}
