import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { masterdataApi, authApi } from '../services/api'
import {
  Database, ChevronRight, Loader2, Plus, ArrowRight,
} from 'lucide-react'

const ICON_MAP = {
  Users: '👥', Package: '📦', FolderOpen: '📁',
  Database: '🗄️', Settings: '⚙️',
}

// ── Stammdaten-Karte ──────────────────────────────────────────────────────────
function StatCard({ type, onClick }) {
  return (
    <button
      onClick={onClick}
      className="card p-5 text-left hover:shadow-card-hover transition-all duration-200 group w-full"
    >
      <div className="flex items-start justify-between mb-4">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-xl"
          style={{ backgroundColor: (type.color || '#f97316') + '18' }}
        >
          {ICON_MAP[type.icon] || '📋'}
        </div>
        <ChevronRight size={16} className="text-neutral-300 group-hover:text-primary-500 transition-colors mt-1" />
      </div>
      <p className="font-semibold text-neutral-900 text-sm">{type.name}</p>
      <p className="text-2xl font-bold text-neutral-900 mt-1">{type.record_count ?? 0}</p>
      <p className="text-xs text-neutral-400 mt-0.5">{type.record_count === 1 ? 'Eintrag' : 'Einträge'}</p>
    </button>
  )
}

// ── Hauptseite ────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [types,   setTypes]   = useState([])
  const [user,    setUser]    = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([masterdataApi.listTypes(), authApi.me()])
      .then(([typesRes, meRes]) => { setTypes(typesRes.data); setUser(meRes.data) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const hour      = new Date().getHours()
  const greeting  = hour < 12 ? 'Guten Morgen' : hour < 18 ? 'Guten Tag' : 'Guten Abend'
  const firstName = user?.full_name?.split(' ')[0] || ''

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <p className="text-sm font-medium text-primary-500 mb-1">
          {greeting}{firstName ? `, ${firstName}` : ''} 👋
        </p>
        <h1 className="text-2xl font-bold text-neutral-900">Dashboard</h1>
        <p className="text-neutral-500 text-sm mt-1">Übersicht deiner Stammdaten</p>
      </div>

      {/* ── Stammdaten ── */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-neutral-500 uppercase tracking-wider">Stammdaten</h2>
          <button onClick={() => navigate('/masterdata')}
            className="text-xs font-medium text-primary-600 hover:text-primary-700 flex items-center gap-1 transition-colors">
            Alle anzeigen <ArrowRight size={12} />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-neutral-400 py-8">
            <Loader2 size={18} className="animate-spin" />
            <span className="text-sm">Wird geladen…</span>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {types.map(type => (
              <StatCard key={type.id} type={type} onClick={() => navigate(`/masterdata/${type.slug}`)} />
            ))}
            <button onClick={() => navigate('/masterdata')}
              className="card p-5 text-left hover:shadow-card-hover transition-all duration-200 border-dashed group w-full flex flex-col items-center justify-center gap-2 text-neutral-400 hover:text-primary-500 hover:border-primary-300">
              <div className="w-10 h-10 rounded-xl bg-neutral-100 group-hover:bg-primary-50 flex items-center justify-center transition-colors">
                <Plus size={18} />
              </div>
              <p className="text-xs font-medium text-center">Neuer Typ</p>
            </button>
          </div>
        )}
      </div>

      {/* ── Schnellzugriff ── */}
      <div>
        <h2 className="text-sm font-semibold text-neutral-500 uppercase tracking-wider mb-4">Schnellzugriff</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button onClick={() => navigate('/masterdata')}
            className="card p-4 text-left hover:shadow-card-hover transition-all duration-200 flex items-center gap-4 group">
            <div className="w-9 h-9 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
              <Database size={16} className="text-primary-600" />
            </div>
            <div>
              <p className="text-sm font-semibold text-neutral-900">Stammdaten verwalten</p>
              <p className="text-xs text-neutral-400 mt-0.5">Typen und Felder konfigurieren</p>
            </div>
            <ChevronRight size={16} className="ml-auto text-neutral-300 group-hover:text-primary-500 transition-colors" />
          </button>
          <button onClick={() => navigate('/users')}
            className="card p-4 text-left hover:shadow-card-hover transition-all duration-200 flex items-center gap-4 group">
            <div className="w-9 h-9 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
              <span className="text-base">👤</span>
            </div>
            <div>
              <p className="text-sm font-semibold text-neutral-900">Benutzerverwaltung</p>
              <p className="text-xs text-neutral-400 mt-0.5">Benutzer und Rollen verwalten</p>
            </div>
            <ChevronRight size={16} className="ml-auto text-neutral-300 group-hover:text-primary-500 transition-colors" />
          </button>
        </div>
      </div>
    </div>
  )
}
