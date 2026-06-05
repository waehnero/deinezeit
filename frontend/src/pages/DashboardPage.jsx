import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { masterdataApi, authApi, zeiterfassungApi, invoiceApi } from '../services/api'
import {
  DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates,
  rectSortingStrategy, useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  GripVertical, Settings2, ChevronRight, Plus,
  Database, Clock, Check, FileText,
} from 'lucide-react'

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────
const ICON_MAP = { Users: '👥', Package: '📦', FolderOpen: '📁', Database: '🗄️', Settings: '⚙️' }
const LS_KEY = 'dz_dashboard_config'

function fmtMin(m) {
  if (!m) return '0:00'
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
}

function colSpanClass(size) {
  return { 1: 'col-span-1', 2: 'col-span-2', 3: 'col-span-3', 4: 'col-span-4' }[size] || 'col-span-1'
}

// ── Größen-Auswahl ────────────────────────────────────────────────────────────
function SizeButtons({ size, onChange }) {
  return (
    <div className="flex gap-1">
      {[1, 2, 4].map(s => (
        <button
          key={s}
          onClick={() => onChange(s)}
          className={`text-[10px] font-bold px-1.5 py-0.5 rounded transition-colors ${
            size === s
              ? 'bg-primary-500 text-white'
              : 'bg-neutral-100 text-neutral-500 hover:bg-neutral-200'
          }`}
        >
          {s === 4 ? '↔' : s === 2 ? '½' : '¼'}
        </button>
      ))}
    </div>
  )
}

// ── Sortierbarer Wrapper ──────────────────────────────────────────────────────
function SortableWidget({ id, size, editMode, onSizeChange, children }) {
  const {
    attributes, listeners, setNodeRef, transform, transition, isDragging,
  } = useSortable({ id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`${colSpanClass(size)} min-w-0 ${editMode ? 'relative' : ''}`}
    >
      {editMode && (
        <div className="absolute top-0 inset-x-0 flex items-center justify-between px-2 py-1 bg-primary-500 rounded-t-xl z-10">
          <div
            {...attributes}
            {...listeners}
            className="cursor-grab active:cursor-grabbing text-white flex items-center gap-1 text-xs font-medium select-none"
          >
            <GripVertical size={14} />
            <span>Verschieben</span>
          </div>
          <SizeButtons size={size} onChange={onSizeChange} />
        </div>
      )}
      <div className={editMode ? 'pt-7' : ''}>
        {children}
      </div>
    </div>
  )
}

// ── Widget: Stammdaten-Typ ────────────────────────────────────────────────────
function EntityTypeWidget({ type, editMode, onClick }) {
  return (
    <button
      onClick={editMode ? undefined : onClick}
      disabled={editMode}
      className={`card p-5 text-left transition-all duration-200 group w-full h-full ${
        editMode
          ? 'cursor-default rounded-tl-none rounded-tr-none'
          : 'hover:shadow-card-hover'
      }`}
    >
      <div className="flex items-start justify-between mb-4">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center text-xl"
          style={{ backgroundColor: (type.color || '#f97316') + '18' }}
        >
          {ICON_MAP[type.icon] || '📋'}
        </div>
        {!editMode && (
          <ChevronRight size={16} className="text-neutral-300 group-hover:text-primary-500 transition-colors mt-1" />
        )}
      </div>
      <p className="font-semibold text-neutral-900 text-sm">{type.name}</p>
      <p className="text-2xl font-bold text-neutral-900 mt-1">{type.record_count ?? 0}</p>
      <p className="text-xs text-neutral-400 mt-0.5">{type.record_count === 1 ? 'Eintrag' : 'Einträge'}</p>
    </button>
  )
}

// ── Widget: Zeiterfassung ─────────────────────────────────────────────────────
function ZeiterfassungWidget({ stats, editMode, onClick }) {
  const rows = [
    { label: 'Heute',  total: stats?.today_minutes,  billable: stats?.today_billable_minutes,  target: stats?.today_target_minutes },
    { label: 'Woche',  total: stats?.week_minutes,   billable: stats?.week_billable_minutes,   target: stats?.week_target_minutes  },
    { label: 'Monat',  total: stats?.month_minutes,  billable: stats?.month_billable_minutes,  target: stats?.month_target_minutes },
  ]
  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : onClick}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center">
            <Clock size={18} className="text-primary-600" />
          </div>
          <div>
            <p className="font-semibold text-neutral-900 text-sm">Zeiterfassung</p>
            <p className="text-xs text-neutral-400">Übersicht</p>
          </div>
        </div>
        {!editMode && (
          <ChevronRight size={16} className="text-neutral-300 group-hover:text-primary-500 transition-colors" />
        )}
      </div>
      {stats ? (
        <div className="grid grid-cols-3 gap-3">
          {rows.map(({ label, total, billable, target }) => {
            const pct = target > 0 ? Math.min(1, total / target) : 0
            const billablePct = target > 0 ? Math.min(1, billable / target) : 0
            return (
              <div key={label} className="text-center">
                <p className="text-[10px] font-semibold text-neutral-400 uppercase tracking-wide mb-1">{label}</p>
                <p className="text-lg font-bold text-neutral-900">{fmtMin(total)}</p>
                <div className="w-full bg-neutral-100 rounded-full h-1.5 mt-1 overflow-hidden">
                  <div className="h-full rounded-full flex">
                    <div className="h-full bg-green-500 rounded-full" style={{ width: `${billablePct * 100}%` }} />
                    <div className="h-full bg-orange-400 rounded-full" style={{ width: `${Math.max(0, pct - billablePct) * 100}%` }} />
                  </div>
                </div>
                <p className="text-[10px] text-neutral-400 mt-0.5">{Math.round(pct * 100)}%</p>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="text-sm text-neutral-400">Wird geladen…</p>
      )}
    </div>
  )
}

// ── Widget: Rechnungsübersicht ────────────────────────────────────────────────
function fmtEuro(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

function RechnungWidget({ invoiceStats, editMode, onClick }) {
  const { offen, ueberfaellig, bezahltMonat } = invoiceStats || {}
  const rows = [
    { label: 'Offen',      count: offen?.count,      sum: offen?.sum,      color: 'text-amber-600',  bg: 'bg-amber-50'  },
    { label: 'Überfällig', count: ueberfaellig?.count, sum: ueberfaellig?.sum, color: 'text-red-600', bg: 'bg-red-50'    },
    { label: 'Bezahlt (Monat)', count: bezahltMonat?.count, sum: bezahltMonat?.sum, color: 'text-green-600', bg: 'bg-green-50' },
  ]
  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : onClick}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center">
            <FileText size={18} className="text-primary-600" />
          </div>
          <div>
            <p className="font-semibold text-neutral-900 text-sm">Rechnungen</p>
            <p className="text-xs text-neutral-400">Übersicht</p>
          </div>
        </div>
        {!editMode && (
          <ChevronRight size={16} className="text-neutral-300 group-hover:text-primary-500 transition-colors" />
        )}
      </div>
      {invoiceStats ? (
        <div className="flex flex-col gap-2">
          {rows.map(({ label, count, sum, color, bg }) => (
            <div key={label} className={`flex items-center justify-between px-3 py-2 rounded-lg ${bg}`}>
              <div>
                <p className={`text-xs font-semibold ${color}`}>{label}</p>
                <p className="text-[11px] text-neutral-500">{count ?? 0} {count === 1 ? 'Rechnung' : 'Rechnungen'}</p>
              </div>
              <p className={`text-sm font-bold ${color}`}>{fmtEuro(sum ?? 0)}</p>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-sm text-neutral-400">Wird geladen…</p>
      )}
    </div>
  )
}

// ── Widget: Schnellzugriff ────────────────────────────────────────────────────
function QuickAccessWidget({ editMode, navigate }) {
  const links = [
    { label: 'Stammdaten verwalten',  sub: 'Typen und Felder konfigurieren', path: '/masterdata', icon: <Database size={16} className="text-primary-600" /> },
    { label: 'Zeiterfassung',          sub: 'Zeiten erfassen und auswerten',  path: '/zeiterfassung', icon: <Clock size={16} className="text-primary-600" /> },
  ]
  return (
    <div className={`card p-5 h-full ${editMode ? 'rounded-tl-none rounded-tr-none' : ''}`}>
      <h3 className="text-sm font-semibold text-neutral-500 uppercase tracking-wider mb-3">Schnellzugriff</h3>
      <div className="flex flex-col gap-2">
        {links.map(l => (
          <button
            key={l.path}
            disabled={editMode}
            onClick={editMode ? undefined : () => navigate(l.path)}
            className={`flex items-center gap-3 p-3 rounded-xl transition-all ${
              editMode
                ? 'bg-neutral-50 cursor-default'
                : 'hover:bg-primary-50 group cursor-pointer'
            }`}
          >
            <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
              {l.icon}
            </div>
            <div className="text-left flex-1 min-w-0">
              <p className="text-sm font-semibold text-neutral-900 truncate">{l.label}</p>
              <p className="text-xs text-neutral-400 truncate">{l.sub}</p>
            </div>
            {!editMode && <ChevronRight size={14} className="text-neutral-300 group-hover:text-primary-500 flex-shrink-0" />}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Standard-Konfiguration ────────────────────────────────────────────────────
function buildDefaultConfig(types) {
  return [
    { id: 'widget_zeit',      type: 'zeiterfassung',    size: 2 },
    { id: 'widget_rechnungen', type: 'rechnungen',      size: 2 },
    { id: 'widget_quick',     type: 'quick_access',     size: 2 },
    ...types.map(t => ({ id: `widget_et_${t.slug}`, type: 'entity_type', slug: t.slug, size: 1 })),
  ]
}

function mergeConfig(saved, types) {
  // Neue Entity-Typen die noch nicht in der Config sind hinzufügen
  const existingSlugs = saved
    .filter(w => w.type === 'entity_type')
    .map(w => w.slug)
  const newWidgets = types
    .filter(t => !existingSlugs.includes(t.slug))
    .map(t => ({ id: `widget_et_${t.slug}`, type: 'entity_type', slug: t.slug, size: 1 }))
  // Gelöschte Entity-Typen entfernen
  const validSlugs = types.map(t => t.slug)
  const filtered = saved.filter(w => w.type !== 'entity_type' || validSlugs.includes(w.slug))
  return [...filtered, ...newWidgets]
}

// ── Hauptseite ────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const navigate  = useNavigate()
  const [types,    setTypes]    = useState([])
  const [user,     setUser]     = useState(null)
  const [stats,    setStats]    = useState(null)
  const [invoiceStats, setInvoiceStats] = useState(null)
  const [widgets,  setWidgets]  = useState([])
  const [editMode, setEditMode] = useState(false)
  const [loading,  setLoading]  = useState(true)

  // ── Daten laden ──────────────────────────────────────────────────────────
  useEffect(() => {
    Promise.all([
      masterdataApi.listTypes(),
      authApi.me(),
      zeiterfassungApi.getStats().catch(() => ({ data: null })),
      invoiceApi.list({ doc_type: 'rechnung' }).catch(() => ({ data: [] })),
    ]).then(([typesRes, meRes, statsRes, invRes]) => {
      const loadedTypes = typesRes.data
      setTypes(loadedTypes)
      setUser(meRes.data)
      setStats(statsRes.data)

      // Rechnungs-Statistiken berechnen
      const invList = invRes.data || []
      const nowMonth = new Date().getMonth()
      const nowYear  = new Date().getFullYear()
      function sumGroup(list) {
        return { count: list.length, sum: list.reduce((a, i) => a + (parseFloat(i.total_gross) || 0), 0) }
      }
      setInvoiceStats({
        offen:        sumGroup(invList.filter(i => i.status === 'offen')),
        ueberfaellig: sumGroup(invList.filter(i => i.status === 'ueberfaellig')),
        bezahltMonat: sumGroup(invList.filter(i => {
          if (i.status !== 'bezahlt') return false
          const d = new Date(i.paid_at || i.updated_at)
          return d.getMonth() === nowMonth && d.getFullYear() === nowYear
        })),
      })

      // Config aus localStorage laden oder Standard generieren
      try {
        const saved = JSON.parse(localStorage.getItem(LS_KEY))
        if (saved && Array.isArray(saved)) {
          setWidgets(mergeConfig(saved, loadedTypes))
        } else {
          setWidgets(buildDefaultConfig(loadedTypes))
        }
      } catch {
        setWidgets(buildDefaultConfig(loadedTypes))
      }
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  // ── Config speichern ─────────────────────────────────────────────────────
  useEffect(() => {
    if (widgets.length > 0) {
      localStorage.setItem(LS_KEY, JSON.stringify(widgets))
    }
  }, [widgets])

  // ── Drag & Drop ──────────────────────────────────────────────────────────
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  )

  function handleDragEnd(event) {
    const { active, over } = event
    if (over && active.id !== over.id) {
      setWidgets(prev => {
        const oldIdx = prev.findIndex(w => w.id === active.id)
        const newIdx = prev.findIndex(w => w.id === over.id)
        return arrayMove(prev, oldIdx, newIdx)
      })
    }
  }

  function updateSize(id, size) {
    setWidgets(prev => prev.map(w => w.id === id ? { ...w, size } : w))
  }

  // ── Render ───────────────────────────────────────────────────────────────
  const hour      = new Date().getHours()
  const greeting  = hour < 12 ? 'Guten Morgen' : hour < 18 ? 'Guten Tag' : 'Guten Abend'
  const firstName = user?.full_name?.split(' ')[0] || ''

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-neutral-400">
        <span className="text-sm">Wird geladen…</span>
      </div>
    )
  }

  const typeMap = Object.fromEntries(types.map(t => [t.slug, t]))

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-primary-500 mb-1">
            {greeting}{firstName ? `, ${firstName}` : ''} 👋
          </p>
          <h1 className="text-2xl font-bold text-neutral-900">Dashboard</h1>
          <p className="text-neutral-500 text-sm mt-1">Übersicht deiner Daten</p>
        </div>
        <div className="flex items-center gap-2 mt-1">
          {editMode ? (
            <>
              <span className="text-xs text-primary-600 font-medium hidden sm:block">Layout bearbeiten</span>
              <button
                onClick={() => setEditMode(false)}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-500 text-white rounded-lg text-sm font-medium hover:bg-primary-600 transition-colors"
              >
                <Check size={14} />
                Fertig
              </button>
            </>
          ) : (
            <button
              onClick={() => setEditMode(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-neutral-100 text-neutral-600 rounded-lg text-sm font-medium hover:bg-neutral-200 transition-colors"
            >
              <Settings2 size={14} />
              Layout
            </button>
          )}
        </div>
      </div>

      {/* Edit-Modus Hinweis */}
      {editMode && (
        <div className="mb-4 p-3 bg-primary-50 border border-primary-200 rounded-xl text-sm text-primary-700 flex items-center gap-2">
          <Settings2 size={15} />
          Ziehe die Bausteine um sie neu anzuordnen. Mit ¼ / ½ / ↔ die Breite anpassen.
        </div>
      )}

      {/* Widget-Grid */}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={widgets.map(w => w.id)} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 auto-rows-auto">
            {widgets.map(widget => (
              <SortableWidget
                key={widget.id}
                id={widget.id}
                size={Math.min(widget.size, 4)}
                editMode={editMode}
                onSizeChange={(s) => updateSize(widget.id, s)}
              >
                {widget.type === 'entity_type' && typeMap[widget.slug] && (
                  <EntityTypeWidget
                    type={typeMap[widget.slug]}
                    editMode={editMode}
                    onClick={() => navigate(`/masterdata/${widget.slug}`)}
                  />
                )}
                {widget.type === 'zeiterfassung' && (
                  <ZeiterfassungWidget
                    stats={stats}
                    editMode={editMode}
                    onClick={() => navigate('/zeiterfassung')}
                  />
                )}
                {widget.type === 'rechnungen' && (
                  <RechnungWidget
                    invoiceStats={invoiceStats}
                    editMode={editMode}
                    onClick={() => navigate('/invoices')}
                  />
                )}
                {widget.type === 'quick_access' && (
                  <QuickAccessWidget editMode={editMode} navigate={navigate} />
                )}
              </SortableWidget>
            ))}

            {/* Neuer Stammdaten-Typ Button (nur außerhalb Edit-Modus) */}
            {!editMode && (
              <div className="col-span-1">
                <button
                  onClick={() => navigate('/masterdata')}
                  className="card p-5 text-left hover:shadow-card-hover transition-all duration-200 border-dashed group w-full h-full flex flex-col items-center justify-center gap-2 text-neutral-400 hover:text-primary-500 hover:border-primary-300 min-h-[120px]"
                >
                  <div className="w-10 h-10 rounded-xl bg-neutral-100 group-hover:bg-primary-50 flex items-center justify-center transition-colors">
                    <Plus size={18} />
                  </div>
                  <p className="text-xs font-medium text-center">Neuer Typ</p>
                </button>
              </div>
            )}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  )
}
