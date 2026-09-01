import { useState, useEffect } from 'react'
import PageHeader from '../components/PageHeader'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { masterdataApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import {
  Users, Package, FolderOpen, Database, Plus, Settings,
  ChevronRight, Hash, Loader2, Clock
} from 'lucide-react'
import { ZEITPROJEKTE_SLUG, ZEITPROJEKTE_ALTE_SLUGS, ZEITPROJEKTE_PFAD } from '../utils/zeitprojekte'

// Icon-Mapping: Backend-Name → Lucide-Komponente
export const ICONS = {
  Users, Package, FolderOpen, Database,
  Settings, Hash,
}

// Neue Stammdaten-Typ anlegen Modal
function NewTypeModal({ onClose, onCreated }) {
  const [name, setName] = useState('')
  const [icon, setIcon] = useState('Database')
  const [color, setColor] = useState('#6b7280')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)

  const ICON_OPTIONS = [
    { key: 'Users', label: 'Personen' },
    { key: 'Package', label: 'Pakete/Produkte' },
    { key: 'FolderOpen', label: 'Projekte' },
    { key: 'Database', label: 'Datenbank' },
    { key: 'Settings', label: 'Einstellungen' },
    { key: 'Hash', label: 'Allgemein' },
  ]

  const COLOR_OPTIONS = [
    '#3b82f6', '#10b981', '#8b5cf6', '#f59e0b',
    '#ef4444', '#06b6d4', '#ec4899', '#6b7280',
  ]

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setLoading(true)
    try {
      const res = await masterdataApi.createType({ name, icon, color, description })
      toast.success(`'${name}' wurde angelegt`)
      onCreated(res.data)
    } catch (err) {
      const detail = err.response?.data?.detail
      const message = Array.isArray(detail)
        ? detail.map(e => e.msg || String(e)).join('; ')
        : (typeof detail === 'string' ? detail : 'Fehler beim Anlegen')
      toast.error(message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-2xl shadow-2xl w-full max-w-md">
        <div className="p-6 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-900">Neuen Stammdaten-Typ anlegen</h2>
          <p className="text-sm text-gray-500 mt-1">z.B. Mitarbeiter, Fahrzeuge, Verträge …</p>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-5">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Bezeichnung *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="z.B. Mitarbeiter"
            />
          </div>

          {/* Icon */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Icon</label>
            <div className="flex flex-wrap gap-2">
              {ICON_OPTIONS.map(({ key, label }) => {
                const Icon = ICONS[key]
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setIcon(key)}
                    title={label}
                    className={`p-2.5 rounded-xl border-2 transition ${
                      icon === key
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <Icon size={20} className={icon === key ? 'text-primary-600' : 'text-gray-500'} />
                  </button>
                )
              })}
            </div>
          </div>

          {/* Farbe */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Farbe</label>
            <div className="flex gap-2">
              {COLOR_OPTIONS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`w-8 h-8 rounded-full border-2 transition ${
                    color === c ? 'border-gray-800 scale-110' : 'border-transparent'
                  }`}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>

          {/* Beschreibung */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Beschreibung (optional)</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="Kurze Beschreibung"
            />
          </div>

          {/* Buttons */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition"
            >
              Abbrechen
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim()}
              className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2"
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
              Anlegen
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Hauptseite ────────────────────────────────────────────────────────────────
export default function MasterDataOverview() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const [types, setTypes] = useState([])
  const [loading, setLoading] = useState(true)
  const [showNewModal, setShowNewModal] = useState(false)

  useEffect(() => {
    loadTypes()
  }, [])

  const loadTypes = async () => {
    try {
      const res = await masterdataApi.listTypes()
      // Zeitprojekte sind ins Zeiterfassungs-Modul gewandert (01.09.2026) und
      // erscheinen hier nicht mehr als Karte. Statt sie kommentarlos
      // verschwinden zu lassen, steht unten ein Hinweis mit dem neuen Weg —
      // wer sie zwei Jahre lang in den Stammdaten gesucht hat, sucht sie beim
      // ersten Mal auch dort. Die alten Slugs stehen mit in der Liste, damit
      // die Karte auch vor Migration 0059 verschwindet.
      setTypes((res.data || []).filter(
        typ => ![ZEITPROJEKTE_SLUG, ...ZEITPROJEKTE_ALTE_SLUGS].includes(typ.slug)))
    } catch (err) {
      toast.error('Stammdaten konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }

  const handleCreated = (newType) => {
    setTypes([...types, { ...newType, record_count: 0 }])
    setShowNewModal(false)
    navigate(`/masterdata/${newType.slug}`)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={32} className="animate-spin text-primary-500" />
      </div>
    )
  }

  return (
    <div>
      <PageHeader icon={Database} title="Stammdaten" subtitle="Kontakte, Artikel und eigene Datentypen verwalten">
        {isAdmin && <button
          onClick={() => setShowNewModal(true)}
          className="flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-4 py-2.5 rounded-xl font-medium transition"
        >
          <Plus size={18} />
          Neuer Typ
        </button>}
      </PageHeader>

      {/* Karten-Grid */}
      {types.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          <Database size={48} className="mx-auto mb-3 text-gray-200" />
          <p className="font-medium">Noch keine Stammdaten-Typen vorhanden</p>
          {/* Der Hinweis nennt einen Knopf, den nur Admins sehen — sonst sucht
              man vergeblich. Neue Typen anzulegen ist Admin-Sache (der Server
              verlangt dort require_admin), Datensätze darin nicht. */}
          <p className="text-sm mt-1">
            {isAdmin ? 'Klicken Sie auf „Neuer Typ" um zu beginnen'
              : 'Ein Administrator kann hier neue Stammdaten-Typen anlegen'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {types.map((type) => {
            const Icon = ICONS[type.icon] || Database
            return (
              <button
                key={type.id}
                onClick={() => navigate(`/masterdata/${type.slug}`)}
                className="bg-surface rounded-2xl border border-gray-100 p-6 text-left hover:shadow-md hover:border-gray-200 transition group"
              >
                <div className="flex items-start justify-between">
                  <div
                    className="p-3 rounded-xl text-white mb-4"
                    style={{ backgroundColor: type.color }}
                  >
                    <Icon size={22} />
                  </div>
                  <ChevronRight
                    size={18}
                    className="text-gray-300 group-hover:text-gray-500 transition mt-1"
                  />
                </div>
                <h3 className="font-bold text-gray-900 text-lg">{type.name}</h3>
                {type.description && (
                  <p className="text-sm text-gray-500 mt-1 line-clamp-2">{type.description}</p>
                )}
                <div className="flex items-center gap-1 mt-3 text-sm text-gray-400">
                  <Hash size={14} />
                  <span>
                    {type.record_count} {type.record_count === 1 ? 'Eintrag' : 'Einträge'}
                  </span>
                  <span className="mx-2">·</span>
                  <span>{type.fields?.length || 0} Felder</span>
                </div>
              </button>
            )
          })}
        </div>
      )}

      {/* Wegweiser zu den Zeitprojekten */}
      <button
        onClick={() => navigate(ZEITPROJEKTE_PFAD)}
        className="mt-4 w-full flex items-start gap-3 text-left bg-primary-50 border border-primary-200 rounded-2xl px-4 py-3 hover:bg-primary-100/70 transition"
      >
        <Clock size={17} className="text-primary-600 mt-0.5 flex-shrink-0" />
        <span className="text-sm text-primary-800">
          <b>Zeitprojekte</b> findest du jetzt unter <b>Zeiterfassung</b> — sie gehören zu den
          Projektzeiten, die darauf gebucht werden.
          <span className="block text-primary-600/80 text-xs mt-0.5">Hier klicken, um sie zu öffnen</span>
        </span>
        <ChevronRight size={16} className="text-primary-400 ml-auto mt-0.5 flex-shrink-0" />
      </button>

      {isAdmin && showNewModal && (
        <NewTypeModal
          onClose={() => setShowNewModal(false)}
          onCreated={handleCreated}
        />
      )}
    </div>
  )
}
