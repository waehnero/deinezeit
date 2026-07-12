import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  masterdataApi, authApi, zeiterfassungApi, invoiceApi, projektplanApi,
  aufgabenApi, mailImportApi, datacenterApi, usersApi, systemApi, accountingApi,
} from '../services/api'
import {
  DndContext, closestCenter, PointerSensor, KeyboardSensor, useSensor, useSensors,
} from '@dnd-kit/core'
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates,
  rectSortingStrategy, useSortable,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import {
  GripVertical, Settings2, ChevronRight, Plus, Play, Square,
  Database, Clock, Check, FileText, GanttChartSquare, CheckSquare,
  FolderOpen, BarChart3, Landmark, ShieldCheck, Mail, Zap,
} from 'lucide-react'

// ── Hilfsfunktionen ───────────────────────────────────────────────────────────
const ICON_MAP = { Users: '👥', Package: '📦', FolderOpen: '📁', Database: '🗄️', Settings: '⚙️' }
const LS_KEY = 'dz_dashboard_config' // alte lokale Speicherung → wird zum Server migriert

function fmtMin(m) {
  if (!m) return '0:00'
  return `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}`
}

function fmtEuro(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}

function fmtElapsed(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function colSpanClass(size) {
  return { 1: 'col-span-1', 2: 'col-span-2', 3: 'col-span-3', 4: 'col-span-4' }[size] || 'col-span-1'
}

// Fälligkeits-Label für Aufgaben ("seit 2 Tg.", "heute", "in 3 Tg.", Datum)
function dueLabel(dueDate) {
  if (!dueDate) return ''
  const heute = new Date(); heute.setHours(0, 0, 0, 0)
  const due = new Date(dueDate); due.setHours(0, 0, 0, 0)
  const diff = Math.round((due - heute) / 86400000)
  if (diff === 0) return 'heute'
  if (diff === 1) return 'morgen'
  if (diff < 0) return `seit ${-diff} Tg.`
  if (diff <= 7) return `in ${diff} Tg.`
  return due.toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit' })
}

// ── Widget-Katalog ────────────────────────────────────────────────────────────
// Feste Widgets; adminOnly-Widgets erscheinen nur für Admins.
const FIXED_WIDGETS = [
  { id: 'widget_aufgaben',   type: 'aufgaben',        size: 2 },
  { id: 'widget_zeit',       type: 'zeiterfassung',   size: 2 },
  { id: 'widget_rechnungen', type: 'rechnungen',      size: 2 },
  { id: 'widget_projekte',   type: 'projekte',        size: 2 },
  { id: 'widget_quick',      type: 'quick_access',    size: 2 },
  { id: 'widget_datacenter', type: 'datacenter',      size: 1 },
  { id: 'widget_berichte',   type: 'berichte',        size: 1 },
  { id: 'widget_buha',       type: 'buchhaltung',     size: 2, adminOnly: true },
  { id: 'widget_system',     type: 'benutzer_system', size: 2, adminOnly: true },
]

const WIDGET_LABELS = {
  aufgaben: 'Aufgaben', zeiterfassung: 'Zeiterfassung', rechnungen: 'Finanzen',
  projekte: 'Projekte', quick_access: 'Schnellzugriff', datacenter: 'Datacenter',
  berichte: 'Berichte', buchhaltung: 'Buchhaltung', benutzer_system: 'Benutzer & System',
}

const ADMIN_TYPES = new Set(
  FIXED_WIDGETS.filter(w => w.adminOnly).map(w => w.type)
)

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

// ── Gemeinsamer Widget-Kopf ───────────────────────────────────────────────────
function WidgetHead({ icon: Icon, title, sub, badge, editMode }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div className="flex items-center gap-2 min-w-0">
        <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center flex-shrink-0">
          <Icon size={18} className="text-primary-600" />
        </div>
        <div className="min-w-0">
          <p className="font-semibold text-neutral-900 text-sm truncate">{title}</p>
          {sub && <p className="text-xs text-neutral-400 truncate">{sub}</p>}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {badge}
        {!editMode && (
          <ChevronRight size={16} className="text-neutral-300 group-hover:text-primary-500 transition-colors" />
        )}
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

// ── Widget: Aufgaben (heute & überfällig + Mail-Vorschläge) ───────────────────
function AufgabenWidget({ stats, mailCount, editMode, navigate }) {
  const badge = stats && stats.ueberfaellig > 0
    ? <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-600">{stats.ueberfaellig} überfällig</span>
    : stats
      ? <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-500">{stats.offen_gesamt} offen</span>
      : null

  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/aufgaben')}
    >
      <WidgetHead icon={CheckSquare} title="Aufgaben" sub={stats ? `${stats.heute_faellig} heute fällig` : 'Übersicht'} badge={badge} editMode={editMode} />
      {stats ? (
        <div className="flex flex-col gap-1.5">
          {stats.naechste.length === 0 && (
            <p className="text-sm text-neutral-400 py-1">Keine offenen Aufgaben. 🎉</p>
          )}
          {stats.naechste.map(a => (
            <div key={a.id} className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg hover:bg-neutral-50">
              <span className={`text-sm truncate ${a.ueberfaellig ? 'text-red-600 font-medium' : 'text-neutral-800'}`}>
                {a.ueberfaellig ? '🔴 ' : ''}{a.title}
              </span>
              <span className={`text-xs flex-shrink-0 ${a.ueberfaellig ? 'text-red-500 font-semibold' : 'text-neutral-400'}`}>
                {dueLabel(a.due_date)}
              </span>
            </div>
          ))}
          {mailCount > 0 && (
            <div className="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg bg-primary-50 mt-1">
              <span className="text-sm text-neutral-800 flex items-center gap-1.5">
                <Mail size={14} className="text-primary-600" />
                <b>{mailCount} Mail-{mailCount === 1 ? 'Vorschlag' : 'Vorschläge'}</b> aus dem Import
              </span>
              <span className="text-xs text-primary-600 font-medium flex-shrink-0">prüfen →</span>
            </div>
          )}
        </div>
      ) : (
        <p className="text-sm text-neutral-400">Wird geladen…</p>
      )}
    </div>
  )
}

// ── Widget: Zeiterfassung (inkl. aktivem Zeitgeber) ───────────────────────────
function ZeiterfassungWidget({ stats, running, elapsedSec, onStop, editMode, navigate }) {
  const rows = [
    { label: 'Heute',  total: stats?.today_minutes,  billable: stats?.today_billable_minutes,  target: stats?.today_target_minutes },
    { label: 'Woche',  total: stats?.week_minutes,   billable: stats?.week_billable_minutes,   target: stats?.week_target_minutes  },
    { label: 'Monat',  total: stats?.month_minutes,  billable: stats?.month_billable_minutes,  target: stats?.month_target_minutes },
  ]
  return (
    <div className={`card p-5 h-full ${editMode ? 'rounded-tl-none rounded-tr-none' : ''}`}>
      <div
        className={!editMode ? 'cursor-pointer group' : ''}
        onClick={editMode ? undefined : () => navigate('/zeiterfassung')}
      >
        <WidgetHead icon={Clock} title="Zeiterfassung" sub="Übersicht" editMode={editMode} />
      </div>

      {/* Aktiver Zeitgeber — erscheint nur, wenn ein Timer läuft */}
      {running ? (
        <div className="flex items-center gap-2.5 bg-neutral-900 text-white rounded-xl px-3.5 py-2.5 mb-4">
          <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse flex-shrink-0" />
          <span className="font-bold tabular-nums text-sm">{fmtElapsed(elapsedSec)}</span>
          <span className="text-xs text-neutral-300 truncate flex-1 min-w-0">
            {running.project_name || running.contact_name || running.note || 'Zeit läuft'}
          </span>
          {!editMode && (
            <button
              onClick={(e) => { e.stopPropagation(); onStop() }}
              className="flex items-center gap-1 bg-surface text-neutral-900 rounded-lg px-2.5 py-1 text-xs font-semibold hover:bg-neutral-200 transition-colors flex-shrink-0"
            >
              <Square size={11} fill="currentColor" />
              Stopp
            </button>
          )}
        </div>
      ) : (
        !editMode && (
          <button
            onClick={() => navigate('/zeiterfassung')}
            className="flex items-center justify-center gap-1.5 w-full bg-primary-500 hover:bg-primary-600 text-white rounded-xl px-3 py-2 mb-4 text-sm font-semibold transition-colors"
          >
            <Play size={14} fill="currentColor" />
            Timer starten
          </button>
        )
      )}

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

// ── Widget: Finanzen (Rechnungsübersicht) ─────────────────────────────────────
function FinanzWidget({ invoiceStats, editMode, onClick }) {
  const { offen, ueberfaellig, bezahltMonat } = invoiceStats || {}
  const rows = [
    { label: 'Offen',           count: offen?.count,        sum: offen?.sum,        color: 'text-amber-600', bg: 'bg-amber-50' },
    { label: 'Überfällig',      count: ueberfaellig?.count, sum: ueberfaellig?.sum, color: 'text-red-600',   bg: 'bg-red-50' },
    { label: 'Bezahlt (Monat)', count: bezahltMonat?.count, sum: bezahltMonat?.sum, color: 'text-green-600', bg: 'bg-green-50' },
  ]
  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : onClick}
    >
      <WidgetHead icon={FileText} title="Finanzen" sub="Rechnungen & Umsatz" editMode={editMode} />
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

// ── Widget: Projekte (5 zuletzt bearbeitete) ──────────────────────────────────
function ProjekteWidget({ projects, editMode, navigate }) {
  return (
    <div className={`card p-5 h-full ${editMode ? 'rounded-tl-none rounded-tr-none' : ''}`}>
      <button
        disabled={editMode}
        onClick={editMode ? undefined : () => navigate('/projekte')}
        className={`w-full text-left ${editMode ? '' : 'group'}`}
      >
        <WidgetHead icon={GanttChartSquare} title="Projekte" sub="Zuletzt bearbeitet" editMode={editMode} />
      </button>

      {(!projects || projects.length === 0) ? (
        <p className="text-sm text-neutral-400 py-2">Noch keine Projekte.</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {projects.map(p => (
            <button key={p.id} disabled={editMode}
              onClick={editMode ? undefined : () => navigate(`/projekte/${p.id}`)}
              className={`flex items-center gap-2.5 p-2 rounded-lg transition-all ${editMode ? 'bg-neutral-50 cursor-default' : 'hover:bg-primary-50 group cursor-pointer'}`}>
              <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: p.color || '#9ca3af' }} />
              <span className="text-sm text-neutral-800 truncate flex-1 min-w-0 text-left">{p.name}</span>
              <span className="text-xs text-neutral-400 flex-shrink-0">{p.progress_percent}%</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Widget: Schnellzugriff (Aktionen + konfigurierbare Modul-Links) ──────────
const QUICK_ACTIONS = [
  { key: 'zeit',     label: 'Zeit erfassen',   path: '/zeiterfassung', icon: Clock },
  { key: 'rechnung', label: 'Neue Rechnung',   path: '/invoices/new',  icon: FileText },
  { key: 'aufgabe',  label: 'Neue Aufgabe',    path: '/aufgaben',      icon: CheckSquare },
  { key: 'datei',    label: 'Datei hochladen', path: '/datacenter',    icon: FolderOpen },
]

const QUICK_LINKS = [
  { key: 'zeiterfassung', label: 'Zeiterfassung',        sub: 'Zeiten erfassen und auswerten',  path: '/zeiterfassung', icon: Clock },
  { key: 'aufgaben',      label: 'Aufgaben',             sub: 'Zentrale To-do-Liste',           path: '/aufgaben',      icon: CheckSquare },
  { key: 'projekte',      label: 'Projekte',             sub: 'Projektplanung und Aufgaben',    path: '/projekte',      icon: GanttChartSquare },
  { key: 'invoices',      label: 'Verkauf',              sub: 'Rechnungen, Angebote, Belege',   path: '/invoices',      icon: FileText },
  { key: 'masterdata',    label: 'Stammdaten verwalten', sub: 'Typen und Felder konfigurieren', path: '/masterdata',    icon: Database },
  { key: 'datacenter',    label: 'Datacenter',           sub: 'Dateien und Anhänge',            path: '/datacenter',    icon: FolderOpen },
  { key: 'users',         label: 'Benutzer',             sub: 'Benutzer verwalten',             path: '/users',         icon: Database },
]
const QUICK_LS_KEY = 'dashboard_quickaccess_v1'
const QUICK_DEFAULT = ['masterdata', 'zeiterfassung']

function QuickAccessWidget({ editMode, navigate }) {
  const [selected, setSelected] = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(QUICK_LS_KEY))
      return Array.isArray(saved) ? saved : QUICK_DEFAULT
    } catch { return QUICK_DEFAULT }
  })
  const [configOpen, setConfigOpen] = useState(false)

  const toggle = (key) => {
    setSelected(prev => {
      const next = prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
      localStorage.setItem(QUICK_LS_KEY, JSON.stringify(next))
      return next
    })
  }

  const links = QUICK_LINKS.filter(l => selected.includes(l.key))

  return (
    <div className={`card p-5 h-full ${editMode ? 'rounded-tl-none rounded-tr-none' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center">
            <Zap size={18} className="text-primary-600" />
          </div>
          <div>
            <p className="font-semibold text-neutral-900 text-sm">Schnellzugriff</p>
            <p className="text-xs text-neutral-400">Häufige Aktionen</p>
          </div>
        </div>
        {!editMode && (
          <button onClick={() => setConfigOpen(o => !o)}
            className="text-neutral-400 hover:text-primary-600" title="Schnellzugriff anpassen">
            <Settings2 size={16} />
          </button>
        )}
      </div>

      {/* Aktions-Kacheln */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        {QUICK_ACTIONS.map(a => (
          <button key={a.key} disabled={editMode}
            onClick={editMode ? undefined : () => navigate(a.path)}
            className={`flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all ${
              editMode ? 'bg-neutral-50 text-neutral-400 cursor-default' : 'bg-primary-50 text-primary-700 hover:bg-primary-100'
            }`}>
            <a.icon size={15} className="flex-shrink-0" />
            <span className="truncate">{a.label}</span>
          </button>
        ))}
      </div>

      {configOpen && !editMode ? (
        <div className="space-y-1.5">
          <p className="text-xs text-neutral-400 mb-2">Welche Module sollen erscheinen?</p>
          {QUICK_LINKS.map(l => (
            <label key={l.key} className="flex items-center gap-2.5 p-2 rounded-lg hover:bg-neutral-50 cursor-pointer">
              <input type="checkbox" checked={selected.includes(l.key)} onChange={() => toggle(l.key)} />
              <l.icon size={15} className="text-primary-600" />
              <span className="text-sm text-neutral-800">{l.label}</span>
            </label>
          ))}
          <button onClick={() => setConfigOpen(false)}
            className="mt-2 w-full text-sm text-primary-600 hover:text-primary-700 py-1.5">Fertig</button>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {links.map(l => (
            <button key={l.key} disabled={editMode}
              onClick={editMode ? undefined : () => navigate(l.path)}
              className={`flex items-center gap-3 p-2.5 rounded-xl transition-all ${editMode ? 'bg-neutral-50 cursor-default' : 'hover:bg-primary-50 group cursor-pointer'}`}>
              <div className="w-8 h-8 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
                <l.icon size={16} className="text-primary-600" />
              </div>
              <div className="text-left flex-1 min-w-0">
                <p className="text-sm font-semibold text-neutral-900 truncate">{l.label}</p>
                <p className="text-xs text-neutral-400 truncate">{l.sub}</p>
              </div>
              {!editMode && <ChevronRight size={14} className="text-neutral-300 group-hover:text-primary-500 flex-shrink-0" />}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Widget: Datacenter ────────────────────────────────────────────────────────
function DatacenterWidget({ dcStats, editMode, onClick }) {
  return (
    <button
      onClick={editMode ? undefined : onClick}
      disabled={editMode}
      className={`card p-5 text-left transition-all duration-200 group w-full h-full ${
        editMode ? 'cursor-default rounded-tl-none rounded-tr-none' : 'hover:shadow-card-hover'
      }`}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center">
          <FolderOpen size={18} className="text-primary-600" />
        </div>
        {!editMode && (
          <ChevronRight size={16} className="text-neutral-300 group-hover:text-primary-500 transition-colors mt-1" />
        )}
      </div>
      <p className="font-semibold text-neutral-900 text-sm">Datacenter</p>
      <p className="text-2xl font-bold text-neutral-900 mt-1">{dcStats?.gesamt ?? '—'}</p>
      <p className="text-xs text-neutral-400 mt-0.5">
        Dateien{dcStats?.neu_7_tage > 0 ? ` · ${dcStats.neu_7_tage} neu (7 Tage)` : ''}
      </p>
    </button>
  )
}

// ── Widget: Berichte ──────────────────────────────────────────────────────────
function BerichteWidget({ editMode, onClick }) {
  return (
    <button
      onClick={editMode ? undefined : onClick}
      disabled={editMode}
      className={`card p-5 text-left transition-all duration-200 group w-full h-full ${
        editMode ? 'cursor-default rounded-tl-none rounded-tr-none' : 'hover:shadow-card-hover'
      }`}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="w-10 h-10 rounded-xl bg-primary-50 flex items-center justify-center">
          <BarChart3 size={18} className="text-primary-600" />
        </div>
        {!editMode && (
          <ChevronRight size={16} className="text-neutral-300 group-hover:text-primary-500 transition-colors mt-1" />
        )}
      </div>
      <p className="font-semibold text-neutral-900 text-sm">Berichte</p>
      <p className="text-xs text-neutral-400 mt-1">Zeiten auswerten und exportieren</p>
    </button>
  )
}

// ── Widget: Buchhaltung (nur Admin) ──────────────────────────────────────────
function BuchhaltungWidget({ accountCount, editMode, navigate }) {
  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/invoices/book')}
    >
      <WidgetHead
        icon={Landmark} title="Buchhaltung" sub="Konten & BMD-Export"
        badge={<span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-neutral-800 text-white">Admin</span>}
        editMode={editMode}
      />
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-neutral-50">
          <span className="text-sm text-neutral-800">Buchungskonten</span>
          <span className="text-sm font-bold text-neutral-900">{accountCount ?? '—'}</span>
        </div>
        <div className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-neutral-50">
          <span className="text-sm text-neutral-800">Rechnungsbuch öffnen</span>
          <ChevronRight size={14} className="text-neutral-300" />
        </div>
      </div>
    </div>
  )
}

// ── Widget: Benutzer & System (nur Admin) ─────────────────────────────────────
function SystemWidget({ userStats, versionInfo, editMode, navigate }) {
  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/users')}
    >
      <WidgetHead
        icon={ShieldCheck} title="Benutzer & System" sub="Verwaltung"
        badge={<span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-neutral-800 text-white">Admin</span>}
        editMode={editMode}
      />
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-neutral-50">
          <span className="text-sm text-neutral-800">Aktive Benutzer</span>
          <span className="text-sm font-bold text-neutral-900">
            {userStats ? `${userStats.aktiv} / ${userStats.gesamt}` : '—'}
          </span>
        </div>
        <div className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-neutral-50">
          <span className="text-sm text-neutral-800">Version</span>
          <span className="text-xs text-neutral-400">
            {versionInfo?.current || '—'}
            {versionInfo?.update_available ? ' · Update verfügbar' : ''}
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Konfiguration: Standard & Migration ───────────────────────────────────────
function normalizeWidget(w) {
  return { id: w.id, type: w.type, slug: w.slug, size: w.size || 1, hidden: !!w.hidden }
}

function buildDefaultConfig(types) {
  return [
    ...FIXED_WIDGETS.map(normalizeWidget),
    ...types.map(t => normalizeWidget({ id: `widget_et_${t.slug}`, type: 'entity_type', slug: t.slug, size: 1 })),
  ]
}

function mergeConfig(saved, types) {
  const normalized = saved.map(normalizeWidget)
  const savedIds = normalized.map(w => w.id)

  // Neue feste Widgets hinzufügen falls noch nicht vorhanden
  const newFixed = FIXED_WIDGETS.filter(w => !savedIds.includes(w.id)).map(normalizeWidget)

  // Neue Entity-Typen die noch nicht in der Config sind hinzufügen
  const existingSlugs = normalized.filter(w => w.type === 'entity_type').map(w => w.slug)
  const newEntityWidgets = types
    .filter(t => !existingSlugs.includes(t.slug))
    .map(t => normalizeWidget({ id: `widget_et_${t.slug}`, type: 'entity_type', slug: t.slug, size: 1 }))

  // Gelöschte Entity-Typen entfernen
  const validSlugs = types.map(t => t.slug)
  const filtered = normalized.filter(w => w.type !== 'entity_type' || validSlugs.includes(w.slug))

  return [...filtered, ...newFixed, ...newEntityWidgets]
}

// ── Hauptseite ────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  const navigate = useNavigate()
  const [types,    setTypes]    = useState([])
  const [user,     setUser]     = useState(null)
  const [stats,    setStats]    = useState(null)
  const [invoiceStats,   setInvoiceStats]   = useState(null)
  const [recentProjects, setRecentProjects] = useState([])
  const [aufgabenStats,  setAufgabenStats]  = useState(null)
  const [mailCount,      setMailCount]      = useState(0)
  const [dcStats,        setDcStats]        = useState(null)
  const [running,        setRunning]        = useState(null)
  const [nowSec,         setNowSec]         = useState(Date.now())
  const [userStats,      setUserStats]      = useState(null)
  const [versionInfo,    setVersionInfo]    = useState(null)
  const [accountCount,   setAccountCount]   = useState(null)
  const [widgets,  setWidgets]  = useState([])
  const [editMode, setEditMode] = useState(false)
  const [loading,  setLoading]  = useState(true)
  const configLoaded = useRef(false)
  const saveTimer = useRef(null)

  const isAdmin = user?.role === 'admin'

  // ── Daten laden ──────────────────────────────────────────────────────────
  useEffect(() => {
    Promise.all([
      masterdataApi.listTypes(),
      authApi.me(),
      zeiterfassungApi.getStats().catch(() => ({ data: null })),
      invoiceApi.list({ doc_type: 'rechnung' }).catch(() => ({ data: [] })),
      projektplanApi.recentProjects(5).catch(() => ({ data: [] })),
      aufgabenApi.stats({ limit: 4 }).catch(() => ({ data: null })),
      mailImportApi.listSuggestions('offen').catch(() => ({ data: [] })),
      datacenterApi.stats(3).catch(() => ({ data: null })),
      zeiterfassungApi.getRunning().catch(() => ({ data: null })),
      usersApi.getDashboard().catch(() => ({ data: { config: null } })),
    ]).then(([typesRes, meRes, statsRes, invRes, recentRes,
              aufgRes, mailRes, dcRes, runningRes, cfgRes]) => {
      const loadedTypes = typesRes.data
      const me = meRes.data
      setTypes(loadedTypes)
      setUser(me)
      setStats(statsRes.data)
      setRecentProjects(recentRes.data || [])
      setAufgabenStats(aufgRes.data)
      setMailCount((mailRes.data || []).length)
      setDcStats(dcRes.data)
      setRunning(runningRes.data || null)

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

      // Admin-Daten nachladen
      if (me?.role === 'admin') {
        usersApi.list().then(res => {
          const list = res.data || []
          setUserStats({ gesamt: list.length, aktiv: list.filter(u => u.is_active).length })
        }).catch(() => {})
        systemApi.getVersion().then(res => setVersionInfo(res.data)).catch(() => {})
        accountingApi.listAccounts().then(res => setAccountCount((res.data || []).length)).catch(() => {})
      }

      // ── Dashboard-Konfiguration: Server → localStorage-Migration → Standard ──
      const serverCfg = cfgRes.data?.config
      if (serverCfg && Array.isArray(serverCfg.widgets)) {
        setWidgets(mergeConfig(serverCfg.widgets, loadedTypes))
      } else {
        // Migration: alte Browser-Konfiguration übernehmen, falls vorhanden
        let migrated = null
        try {
          const old = JSON.parse(localStorage.getItem(LS_KEY))
          if (Array.isArray(old)) migrated = mergeConfig(old, loadedTypes)
        } catch { /* ignorieren */ }
        setWidgets(migrated || buildDefaultConfig(loadedTypes))
      }
      configLoaded.current = true
    }).catch(() => {}).finally(() => setLoading(false))
  }, [])

  // ── Config speichern (serverseitig, entprellt) ───────────────────────────
  useEffect(() => {
    if (!configLoaded.current || widgets.length === 0) return
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      usersApi.saveDashboard({ widgets }).catch(() => {})
    }, 800)
    return () => clearTimeout(saveTimer.current)
  }, [widgets])

  // ── Timer-Sekundentakt (nur bei laufendem Timer) ─────────────────────────
  useEffect(() => {
    if (!running) return
    const iv = setInterval(() => setNowSec(Date.now()), 1000)
    return () => clearInterval(iv)
  }, [running])

  const elapsedSec = running
    ? Math.max(0, Math.floor((nowSec - new Date(running.started_at).getTime()) / 1000))
    : 0

  const stopTimer = useCallback(async () => {
    if (!running) return
    try {
      await zeiterfassungApi.stopTimer(running.id, {
        ended_at: new Date().toISOString(),
        pause_minutes: 0,
      })
      setRunning(null)
      // Statistik aktualisieren (Heute-Wert ändert sich)
      zeiterfassungApi.getStats().then(res => setStats(res.data)).catch(() => {})
    } catch { /* Fehler still ignorieren; Seite zeigt weiterhin laufenden Timer */ }
  }, [running])

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

  function toggleHidden(id) {
    setWidgets(prev => prev.map(w => w.id === id ? { ...w, hidden: !w.hidden } : w))
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

  // Modulrechte: Widget-Typ → benötigtes Modul (Beschluss 2026-07-12).
  // Widgets nicht freigeschalteter Module werden ausgeblendet.
  const WIDGET_MODULE = {
    aufgaben: 'aufgaben', zeiterfassung: 'zeiterfassung', berichte: 'zeiterfassung',
    rechnungen: 'verkauf', projekte: 'projekte', datacenter: 'datacenter',
    entity_type: 'stammdaten',
  }
  const userModules = user?.modules ?? null
  const widgetAllowed = (w) => {
    const mod = WIDGET_MODULE[w.type]
    if (!mod || userModules === null) return true
    return userModules.includes(mod)
  }

  // Sichtbare Widgets: Admin-Widgets nur für Admins, Modul-Widgets nur mit
  // freigeschaltetem Modul, versteckte nie
  const visibleWidgets = widgets.filter(w => {
    if (ADMIN_TYPES.has(w.type) && !isAdmin) return false
    if (!widgetAllowed(w)) return false
    if (w.type === 'entity_type' && !typeMap[w.slug]) return false
    return !w.hidden
  })

  // Katalog für den Bearbeiten-Modus (inkl. versteckter Widgets)
  const catalogWidgets = widgets.filter(w => {
    if (ADMIN_TYPES.has(w.type) && !isAdmin) return false
    if (!widgetAllowed(w)) return false
    if (w.type === 'entity_type' && !typeMap[w.slug]) return false
    return true
  })

  function widgetLabel(w) {
    if (w.type === 'entity_type') return typeMap[w.slug]?.name || w.slug
    return WIDGET_LABELS[w.type] || w.type
  }

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
              Anpassen
            </button>
          )}
        </div>
      </div>

      {/* Bearbeiten-Modus: Hinweis + Widget-Katalog */}
      {editMode && (
        <div className="mb-4 p-4 bg-primary-50 border border-primary-200 rounded-xl text-sm text-primary-700">
          <div className="flex items-center gap-2 mb-3">
            <Settings2 size={15} />
            Ziehe die Bausteine um sie neu anzuordnen. Mit ¼ / ½ / ↔ die Breite anpassen.
            Dein Dashboard wird automatisch gespeichert und ist auf allen Geräten gleich.
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-1.5">
            {catalogWidgets.map(w => (
              <label key={w.id} className="flex items-center gap-1.5 cursor-pointer text-neutral-700 text-[13px]">
                <input
                  type="checkbox"
                  checked={!w.hidden}
                  onChange={() => toggleHidden(w.id)}
                />
                {widgetLabel(w)}
                {ADMIN_TYPES.has(w.type) && (
                  <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-neutral-800 text-white">Admin</span>
                )}
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Widget-Grid */}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={visibleWidgets.map(w => w.id)} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 auto-rows-auto">
            {visibleWidgets.map(widget => (
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
                {widget.type === 'aufgaben' && (
                  <AufgabenWidget
                    stats={aufgabenStats}
                    mailCount={mailCount}
                    editMode={editMode}
                    navigate={navigate}
                  />
                )}
                {widget.type === 'zeiterfassung' && (
                  <ZeiterfassungWidget
                    stats={stats}
                    running={running}
                    elapsedSec={elapsedSec}
                    onStop={stopTimer}
                    editMode={editMode}
                    navigate={navigate}
                  />
                )}
                {widget.type === 'rechnungen' && (
                  <FinanzWidget
                    invoiceStats={invoiceStats}
                    editMode={editMode}
                    onClick={() => navigate('/invoices')}
                  />
                )}
                {widget.type === 'projekte' && (
                  <ProjekteWidget projects={recentProjects} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'quick_access' && (
                  <QuickAccessWidget editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'datacenter' && (
                  <DatacenterWidget dcStats={dcStats} editMode={editMode} onClick={() => navigate('/datacenter')} />
                )}
                {widget.type === 'berichte' && (
                  <BerichteWidget editMode={editMode} onClick={() => navigate('/zeiterfassung')} />
                )}
                {widget.type === 'buchhaltung' && isAdmin && (
                  <BuchhaltungWidget accountCount={accountCount} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'benutzer_system' && isAdmin && (
                  <SystemWidget userStats={userStats} versionInfo={versionInfo} editMode={editMode} navigate={navigate} />
                )}
              </SortableWidget>
            ))}

            {/* Neuer Stammdaten-Typ Button (nur außerhalb Bearbeiten-Modus) */}
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
