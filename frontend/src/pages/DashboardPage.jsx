import { useState, useEffect, useRef, useCallback } from 'react'
import PageHeader from '../components/PageHeader'
import { LayoutDashboard } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import {
  masterdataApi, authApi, zeiterfassungApi, usersApi, systemApi, dashboardApi,
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
  Mic, Sparkles, X, Pencil, RotateCcw, Copy, Trash2, LayoutGrid,
  AlertTriangle, Megaphone, TrendingUp, Receipt,
} from 'lucide-react'
import toast from 'react-hot-toast'
import VoiceEntryDialog from '../components/VoiceEntryDialog'
import { WIDGET_REGISTRY, widgetDef, widgetErlaubt } from '../data/dashboardWidgets'
import {
  normalisiereConfig, aktivesLayout, setzeWidgets, wechsleLayout,
  fuegeLayoutHinzu, benenneLayoutUm, loescheLayout, setzeLayoutZurueck,
  neuesWidget, STANDARD_LAYOUT_ID, MAX_LAYOUTS,
} from '../utils/dashboardConfig'

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

// Das Raster hat auf dem Handy zwei Spalten und ab „sm" vier (siehe unten).
// Deshalb muss die Breite auf dem Handy bei zwei Spalten gedeckelt werden:
// ein `col-span-4` in einem zweispaltigen Raster erzwingt zusätzliche Spalten,
// das Raster wächst über den Bildschirm hinaus und alle Kacheln rutschen
// ineinander. Die vollständigen Klassennamen stehen bewusst ausgeschrieben da,
// sonst findet Tailwind sie beim Erzeugen der CSS-Datei nicht.
function colSpanClass(size) {
  return {
    1: 'col-span-1',
    2: 'col-span-2 sm:col-span-2',
    3: 'col-span-2 sm:col-span-3',
    4: 'col-span-2 sm:col-span-4',
  }[size] || 'col-span-1'
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

// Der Widget-Katalog liegt jetzt zentral in ../data/dashboardWidgets.js.
// Ein neues Widget wird dort eingetragen und unten im Render-Zweig dargestellt.

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
function SortableWidget({
  id, size, editMode, onSizeChange, onRemove, onTitelChange,
  titel, standardTitel, children,
}) {
  const {
    attributes, listeners, setNodeRef, transform, transition, isDragging,
  } = useSortable({ id })
  const [umbenennen, setUmbenennen] = useState(false)
  const [entwurf, setEntwurf] = useState(titel || '')

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  function titelSpeichern() {
    onTitelChange(entwurf.trim())
    setUmbenennen(false)
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`${colSpanClass(size)} min-w-0 ${editMode ? 'relative' : ''}`}
    >
      {editMode && (
        <div className="absolute top-0 inset-x-0 bg-primary-500 rounded-t-xl z-10">
          <div className="flex items-center justify-between gap-1 px-2 py-1">
            <div
              {...attributes}
              {...listeners}
              className="cursor-grab active:cursor-grabbing text-white flex items-center gap-1 text-xs font-medium select-none min-w-0"
            >
              <GripVertical size={14} className="flex-shrink-0" />
              <span className="hidden sm:inline">Verschieben</span>
            </div>
            <div className="flex items-center gap-1 flex-shrink-0">
              <SizeButtons size={size} onChange={onSizeChange} />
              <button
                onClick={() => { setEntwurf(titel || ''); setUmbenennen(o => !o) }}
                title="Überschrift ändern"
                className="p-0.5 rounded text-white/80 hover:text-white hover:bg-white/20 transition-colors"
              >
                <Pencil size={13} />
              </button>
              <button
                onClick={onRemove}
                title="Baustein entfernen"
                className="p-0.5 rounded text-white/80 hover:text-white hover:bg-red-500 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Eigene Überschrift — leer lassen für die Standardbezeichnung */}
          {umbenennen && (
            <div className="flex items-center gap-1 px-2 pb-1.5">
              <input
                autoFocus
                value={entwurf}
                maxLength={40}
                placeholder={standardTitel}
                onChange={e => setEntwurf(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') titelSpeichern()
                  if (e.key === 'Escape') setUmbenennen(false)
                }}
                className="flex-1 min-w-0 text-xs px-2 py-1 rounded border-0 focus:ring-2 focus:ring-white/60"
              />
              <button
                onClick={titelSpeichern}
                className="text-[11px] font-medium px-2 py-1 rounded bg-white text-primary-600 hover:bg-primary-50"
              >
                OK
              </button>
            </div>
          )}
        </div>
      )}
      <div className={editMode ? (umbenennen ? 'pt-16' : 'pt-7') : ''}>
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
function EntityTypeWidget({ type, titel, editMode, onClick }) {
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
      <p className="font-semibold text-neutral-900 text-sm">{titel || type.name}</p>
      <p className="text-2xl font-bold text-neutral-900 mt-1">{type.record_count ?? 0}</p>
      <p className="text-xs text-neutral-400 mt-0.5">{type.record_count === 1 ? 'Eintrag' : 'Einträge'}</p>
    </button>
  )
}

// ── Widget: Aufgaben (heute & überfällig + Mail-Vorschläge) ───────────────────
function AufgabenWidget({ stats, mailCount, titel, editMode, navigate }) {
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
      <WidgetHead icon={CheckSquare} title={titel || 'Aufgaben'} sub={stats ? `${stats.heute_faellig} heute fällig` : 'Übersicht'} badge={badge} editMode={editMode} />
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
function ZeiterfassungWidget({ stats, running, elapsedSec, onStop, titel, editMode, navigate }) {
  const [voiceOpen, setVoiceOpen] = useState(false)

  // KI-Vorschlag → weiter zur Zeiterfassung, dort öffnet der vorbefüllte
  // Nachtragen-Dialog (Übergabe über den Router-State)
  const handleVoiceResult = (v) => {
    setVoiceOpen(false)
    navigate('/zeiterfassung', { state: { kiVorschlag: v } })
  }

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
        <WidgetHead icon={Clock} title={titel || 'Zeiterfassung'} sub="Übersicht" editMode={editMode} />
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
            <>
              <button
                onClick={(e) => { e.stopPropagation(); setVoiceOpen(true) }}
                title="Projektzeit per Sprache nachtragen (KI)"
                className="relative flex items-center bg-primary-500 hover:bg-primary-600 text-white rounded-lg px-2 py-1 transition-colors flex-shrink-0"
              >
                <Mic size={12} />
                <Sparkles size={8} className="absolute top-0.5 right-0.5" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onStop() }}
                className="flex items-center gap-1 bg-surface text-neutral-900 rounded-lg px-2.5 py-1 text-xs font-semibold hover:bg-neutral-200 transition-colors flex-shrink-0"
              >
                <Square size={11} fill="currentColor" />
                Stopp
              </button>
            </>
          )}
        </div>
      ) : (
        !editMode && (
          <div className="flex items-stretch gap-2 mb-4">
            <button
              onClick={() => navigate('/zeiterfassung')}
              className="flex items-center justify-center gap-1.5 flex-1 bg-primary-500 hover:bg-primary-600 text-white rounded-xl px-3 py-2 text-sm font-semibold transition-colors"
            >
              <Play size={14} fill="currentColor" />
              Timer starten
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); setVoiceOpen(true) }}
              title="Projektzeit per Sprache nachtragen (KI)"
              className="relative flex items-center justify-center bg-primary-500 hover:bg-primary-600 text-white rounded-xl px-3 transition-colors flex-shrink-0"
            >
              <Mic size={15} />
              <Sparkles size={9} className="absolute top-1 right-1" />
            </button>
          </div>
        )
      )}

      {/* Sprach-Nachtragen (KI) */}
      {voiceOpen && (
        <div onClick={(e) => e.stopPropagation()}>
          <VoiceEntryDialog onClose={() => setVoiceOpen(false)} onResult={handleVoiceResult} />
        </div>
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
function FinanzWidget({ invoiceStats, titel, editMode, onClick }) {
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
      <WidgetHead icon={FileText} title={titel || 'Finanzen'} sub="Rechnungen & Umsatz" editMode={editMode} />
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
function ProjekteWidget({ projects, titel, editMode, navigate }) {
  return (
    <div className={`card p-5 h-full ${editMode ? 'rounded-tl-none rounded-tr-none' : ''}`}>
      <button
        disabled={editMode}
        onClick={editMode ? undefined : () => navigate('/projekte')}
        className={`w-full text-left ${editMode ? '' : 'group'}`}
      >
        <WidgetHead icon={GanttChartSquare} title={titel || 'Projekte'} sub="Zuletzt bearbeitet" editMode={editMode} />
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

function QuickAccessWidget({ titel, editMode, navigate }) {
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
            <p className="font-semibold text-neutral-900 text-sm">{titel || 'Schnellzugriff'}</p>
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
function DatacenterWidget({ dcStats, titel, editMode, onClick }) {
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
      <p className="font-semibold text-neutral-900 text-sm">{titel || 'Datacenter'}</p>
      <p className="text-2xl font-bold text-neutral-900 mt-1">{dcStats?.gesamt ?? '—'}</p>
      <p className="text-xs text-neutral-400 mt-0.5">
        Dateien{dcStats?.neu_7_tage > 0 ? ` · ${dcStats.neu_7_tage} neu (7 Tage)` : ''}
      </p>
    </button>
  )
}

// ── Widget: Berichte ──────────────────────────────────────────────────────────
function BerichteWidget({ titel, editMode, onClick }) {
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
      <p className="font-semibold text-neutral-900 text-sm">{titel || 'Berichte'}</p>
      <p className="text-xs text-neutral-400 mt-1">Zeiten auswerten und exportieren</p>
    </button>
  )
}

// ── Widget: Buchhaltung (nur Admin) ──────────────────────────────────────────
function BuchhaltungWidget({ accountCount, titel, editMode, navigate }) {
  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/buchhaltung')}
    >
      <WidgetHead
        icon={Landmark} title={titel || 'Buchhaltung'} sub="Konten & BMD-Export"
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
function SystemWidget({ userStats, versionInfo, titel, editMode, navigate }) {
  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/users')}
    >
      <WidgetHead
        icon={ShieldCheck} title={titel || 'Benutzer & System'} sub="Verwaltung"
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
            {versionInfo?.update_available ? ' · neuere Version auf GitHub' : ''}
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Widget: Offene Posten & Mahnwesen ─────────────────────────────────────────
function OffenePostenWidget({ daten, titel, editMode, navigate }) {
  const staffel = daten?.staffel
  const zeilen = [
    { key: 'bis_30',   label: 'bis 30 Tage',  farbe: 'text-amber-600',  bg: 'bg-amber-50' },
    { key: 'bis_60',   label: '31–60 Tage',   farbe: 'text-orange-600', bg: 'bg-orange-50' },
    { key: 'ueber_60', label: 'über 60 Tage', farbe: 'text-red-600',    bg: 'bg-red-50' },
  ]
  const badge = daten?.gesamt?.count > 0
    ? <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-600">
        {fmtEuro(daten.gesamt.sum)}
      </span>
    : null

  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/buchhaltung/offene-posten')}
    >
      <WidgetHead
        icon={AlertTriangle} title={titel || 'Offene Posten'}
        sub={daten ? `${daten.gesamt.count} überfällige Forderungen` : 'Außenstände'}
        badge={badge} editMode={editMode}
      />
      {!daten ? (
        <p className="text-sm text-neutral-400">—</p>
      ) : daten.gesamt.count === 0 ? (
        <p className="text-sm text-neutral-400 py-2">Keine überfälligen Forderungen.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {zeilen.map(z => {
            const w = staffel[z.key]
            return (
              <div key={z.key} className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg ${w.count ? z.bg : ''}`}>
                <span className="text-sm text-neutral-700">{z.label}</span>
                <span className="flex items-baseline gap-2">
                  <span className="text-xs text-neutral-400">{w.count}</span>
                  <span className={`text-sm font-bold ${w.count ? z.farbe : 'text-neutral-300'}`}>
                    {fmtEuro(w.sum)}
                  </span>
                </span>
              </div>
            )
          })}
          {daten.mahnstufen?.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1 mt-1 border-t border-neutral-100">
              {daten.mahnstufen.map(m => (
                <span key={m.stufe} className="text-[11px] px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-600">
                  Stufe {m.stufe}: {m.belege}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Widget: Postecke ──────────────────────────────────────────────────────────
function PosteckeWidget({ daten, titel, editMode, navigate }) {
  const spalten = [
    { key: 'entwurf',   label: 'Entwurf' },
    { key: 'kontrolle', label: 'Kontrolle' },
    { key: 'geplant',   label: 'Geplant' },
  ]
  const badge = daten?.fehler > 0
    ? <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-red-50 text-red-600">
        {daten.fehler} fehlgeschlagen
      </span>
    : null

  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/postecke')}
    >
      <WidgetHead
        icon={Megaphone} title={titel || 'Postecke'}
        sub="Beiträge und Veröffentlichungen" badge={badge} editMode={editMode}
      />
      {!daten ? (
        <p className="text-sm text-neutral-400">—</p>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2 mb-3">
            {spalten.map(s => (
              <div key={s.key} className="text-center px-2 py-2 rounded-lg bg-neutral-50">
                <p className="text-lg font-bold text-neutral-900">{daten.je_status[s.key] ?? 0}</p>
                <p className="text-[11px] text-neutral-400">{s.label}</p>
              </div>
            ))}
          </div>
          {daten.naechste?.length > 0 ? (
            <div className="flex flex-col gap-1">
              <p className="text-[11px] text-neutral-400 uppercase tracking-wide">Als Nächstes</p>
              {daten.naechste.map(p => (
                <div key={p.id} className="flex items-center justify-between gap-2 px-2 py-1 rounded hover:bg-neutral-50">
                  <span className="text-sm text-neutral-800 truncate">{p.titel}</span>
                  <span className="text-xs text-neutral-400 flex-shrink-0">
                    {p.geplant_am
                      ? new Date(p.geplant_am).toLocaleDateString('de-AT', { day: '2-digit', month: '2-digit' })
                      : ''}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-neutral-400">Nichts geplant.</p>
          )}
        </>
      )}
    </div>
  )
}

// ── Widget: Umsatz-Verlauf ────────────────────────────────────────────────────
// Balkendiagramm als reines SVG — für zwölf Werte lohnt keine Bibliothek, und
// das Bundle bleibt schlank.
function UmsatzWidget({ daten, titel, editMode, navigate }) {
  const MONATE = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
  const monate = daten?.monate || []
  // Maßstab über beide Jahre, sonst wären die Balken nicht vergleichbar
  const max = Math.max(1, ...monate.map(m => Math.max(m.netto, m.vorjahr)))

  const B = 26          // Abstand je Monat
  const H = 90          // Höhe der Zeichenfläche
  const hoehe = (wert) => Math.max(wert > 0 ? 2 : 0, (wert / max) * H)

  const diff = daten && daten.vorjahr_gesamt > 0
    ? ((daten.netto_gesamt - daten.vorjahr_gesamt) / daten.vorjahr_gesamt) * 100
    : null

  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/buchhaltung/auswertungen')}
    >
      <WidgetHead
        icon={TrendingUp} title={titel || 'Umsatz-Verlauf'}
        sub={daten ? `${daten.jahr} — netto ${fmtEuro(daten.netto_gesamt)}` : 'Monatsumsätze'}
        badge={diff !== null ? (
          <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
            diff >= 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'
          }`}>
            {diff >= 0 ? '+' : ''}{diff.toFixed(0)} % ggü. Vorjahr
          </span>
        ) : null}
        editMode={editMode}
      />
      {!daten ? (
        <p className="text-sm text-neutral-400">—</p>
      ) : (
        <>
          <svg viewBox={`0 0 ${B * 12} ${H + 18}`} className="w-full" style={{ maxHeight: 130 }}>
            {monate.map((m, i) => {
              const x = i * B
              return (
                <g key={m.monat}>
                  {/* Vorjahr im Hintergrund, heuer davor.
                      `fill-current` + Textfarbe statt `fill-primary-500`: die
                      Farben dieses Projekts sind CSS-Variablen, und fill-current
                      funktioniert damit garantiert. */}
                  <rect x={x + 4}  y={H - hoehe(m.vorjahr)} width={9} height={hoehe(m.vorjahr)}
                        rx="2" className="fill-current text-neutral-200" />
                  <rect x={x + 13} y={H - hoehe(m.netto)}   width={9} height={hoehe(m.netto)}
                        rx="2" className="fill-current text-primary-500" />
                  <text x={x + 13} y={H + 13} textAnchor="middle"
                        className="fill-current text-neutral-400" style={{ fontSize: 9 }}>
                    {MONATE[i]}
                  </text>
                </g>
              )
            })}
          </svg>
          <div className="flex items-center gap-4 mt-1 text-[11px] text-neutral-400">
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-primary-500" />
              {daten.jahr}
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2.5 h-2.5 rounded-sm bg-neutral-200" />
              {daten.jahr - 1} ({fmtEuro(daten.vorjahr_gesamt)})
            </span>
          </div>
        </>
      )}
    </div>
  )
}

// ── Widget: Eingangsrechnungen & Monatsabschluss ──────────────────────────────
function EingangsrechnungenWidget({ daten, titel, editMode, navigate }) {
  const vormonat = daten?.vormonat
  const monatsName = vormonat
    ? new Date(vormonat.jahr, vormonat.monat - 1, 1)
        .toLocaleDateString('de-AT', { month: 'long', year: 'numeric' })
    : ''

  return (
    <div
      className={`card p-5 h-full ${!editMode ? 'cursor-pointer hover:shadow-card-hover transition-all duration-200 group' : 'rounded-tl-none rounded-tr-none'}`}
      onClick={editMode ? undefined : () => navigate('/buchhaltung/eingangsrechnungen')}
    >
      <WidgetHead
        icon={Receipt} title={titel || 'Eingangsrechnungen'}
        sub="Lieferanten & Vorsteuer"
        badge={daten?.offen?.count > 0
          ? <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-50 text-amber-700">
              {daten.offen.count} zu zahlen
            </span>
          : null}
        editMode={editMode}
      />
      {!daten ? (
        <p className="text-sm text-neutral-400">—</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-neutral-50">
            <span className="text-sm text-neutral-800">Offen</span>
            <span className="text-sm font-bold text-neutral-900">{fmtEuro(daten.offen.sum)}</span>
          </div>
          <div className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-neutral-50">
            <span className="text-sm text-neutral-800">Vorsteuer laufender Monat</span>
            <span className="text-sm font-bold text-neutral-900">{fmtEuro(daten.vorsteuer_monat)}</span>
          </div>
          {vormonat && (
            <div className="flex items-center justify-between px-2 py-1.5 rounded-lg hover:bg-neutral-50">
              <span className="text-sm text-neutral-800 truncate">Abschluss {monatsName}</span>
              <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full flex-shrink-0 ${
                vormonat.abgeschlossen
                  ? 'bg-emerald-50 text-emerald-600'
                  : 'bg-amber-50 text-amber-700'
              }`}>
                {vormonat.abgeschlossen ? 'erledigt' : 'offen'}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Katalog-Dialog: Baustein hinzufügen ───────────────────────────────────────
// Zeigt alles, was die Registry hergibt und der Benutzer sehen darf. Bereits
// verwendete Bausteine sind ausgegraut (Stammdaten-Typen einzeln je Typ).
function KatalogDialog({ offen, onClose, vorhandeneTypen, vorhandeneSlugs, types, ctx, onAdd }) {
  if (!offen) return null

  const eintraege = []
  for (const def of WIDGET_REGISTRY) {
    if (!widgetErlaubt(def.type, ctx)) continue
    if (def.mehrfach) {
      // Stammdaten-Typen: ein Eintrag je vorhandenem Typ
      for (const t of types) {
        eintraege.push({
          key: `${def.type}:${t.slug}`,
          def,
          slug: t.slug,
          label: t.name,
          beschreibung: 'Stammdaten-Typ',
          drin: vorhandeneSlugs.has(t.slug),
        })
      }
    } else {
      eintraege.push({
        key: def.type,
        def,
        slug: undefined,
        label: def.label,
        beschreibung: def.beschreibung,
        drin: vorhandeneTypen.has(def.type),
      })
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100">
          <div>
            <p className="font-semibold text-neutral-900">Baustein hinzufügen</p>
            <p className="text-xs text-neutral-400">Wird unten an die Ansicht angehängt</p>
          </div>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-700">
            <X size={20} />
          </button>
        </div>

        <div className="overflow-y-auto p-3 flex flex-col gap-1.5">
          {eintraege.map(e => {
            const Icon = e.def.icon
            return (
              <button
                key={e.key}
                disabled={e.drin}
                onClick={() => { onAdd(e.def.type, e.slug); onClose() }}
                className={`flex items-center gap-3 p-3 rounded-xl text-left transition-colors ${
                  e.drin
                    ? 'opacity-40 cursor-default'
                    : 'hover:bg-primary-50 cursor-pointer'
                }`}
              >
                <div className="w-9 h-9 rounded-lg bg-primary-50 flex items-center justify-center flex-shrink-0">
                  <Icon size={17} className="text-primary-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-neutral-900 truncate">
                    {e.label}
                    {e.def.adminOnly && (
                      <span className="ml-1.5 text-[9px] font-bold px-1.5 py-0.5 rounded-full bg-neutral-800 text-white align-middle">Admin</span>
                    )}
                  </p>
                  <p className="text-xs text-neutral-400 truncate">{e.beschreibung}</p>
                </div>
                {e.drin
                  ? <span className="text-[11px] text-neutral-400 flex-shrink-0">bereits drin</span>
                  : <Plus size={16} className="text-neutral-300 flex-shrink-0" />}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

// ── Ansichten-Leiste (mehrere Layouts je Benutzer) ────────────────────────────
function LayoutLeiste({ config, editMode, onWechsel, onNeu, onKopie, onUmbenennen, onLoeschen }) {
  const [umbenennen, setUmbenennen] = useState(false)
  const [entwurf, setEntwurf] = useState('')
  const aktiv = aktivesLayout(config)

  // Außerhalb des Bearbeiten-Modus nur zeigen, wenn es überhaupt etwas zu
  // wechseln gibt — bei einer einzigen Ansicht wäre die Leiste nur Ballast.
  if (!editMode && config.layouts.length < 2) return null

  return (
    <div className="flex items-center gap-2 mb-4 flex-wrap">
      <LayoutGrid size={15} className="text-neutral-400 flex-shrink-0" />

      {config.layouts.map(l => (
        <button
          key={l.id}
          onClick={() => onWechsel(l.id)}
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            l.id === aktiv?.id
              ? 'bg-primary-500 text-white'
              : 'bg-neutral-100 text-neutral-600 hover:bg-neutral-200'
          }`}
        >
          {l.name}
        </button>
      ))}

      {editMode && (
        <>
          {config.layouts.length < MAX_LAYOUTS && (
            <>
              <button
                onClick={onNeu}
                title="Leere Ansicht anlegen"
                className="p-1.5 rounded-lg bg-neutral-100 text-neutral-500 hover:bg-neutral-200"
              >
                <Plus size={15} />
              </button>
              <button
                onClick={onKopie}
                title="Aktuelle Ansicht duplizieren"
                className="p-1.5 rounded-lg bg-neutral-100 text-neutral-500 hover:bg-neutral-200"
              >
                <Copy size={14} />
              </button>
            </>
          )}
          <button
            onClick={() => { setEntwurf(aktiv?.name || ''); setUmbenennen(o => !o) }}
            title="Ansicht umbenennen"
            className="p-1.5 rounded-lg bg-neutral-100 text-neutral-500 hover:bg-neutral-200"
          >
            <Pencil size={14} />
          </button>
          {aktiv?.id !== STANDARD_LAYOUT_ID && (
            <button
              onClick={() => onLoeschen(aktiv.id)}
              title="Ansicht löschen"
              className="p-1.5 rounded-lg bg-neutral-100 text-neutral-500 hover:bg-red-50 hover:text-red-600"
            >
              <Trash2 size={14} />
            </button>
          )}

          {umbenennen && (
            <div className="flex items-center gap-1 w-full sm:w-auto">
              <input
                autoFocus
                value={entwurf}
                maxLength={30}
                onChange={e => setEntwurf(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter') { onUmbenennen(aktiv.id, entwurf); setUmbenennen(false) }
                  if (e.key === 'Escape') setUmbenennen(false)
                }}
                className="text-sm px-2 py-1.5 rounded-lg border border-neutral-200 focus:ring-2 focus:ring-primary-200 focus:border-primary-400"
              />
              <button
                onClick={() => { onUmbenennen(aktiv.id, entwurf); setUmbenennen(false) }}
                className="text-xs font-medium px-2.5 py-1.5 rounded-lg bg-primary-500 text-white hover:bg-primary-600"
              >
                OK
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
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
  // Kennzahlen der vier Bausteine aus Etappe 2 — jeweils null, solange nicht geladen
  const [offenePosten,   setOffenePosten]   = useState(null)
  const [postecke,       setPostecke]       = useState(null)
  const [umsatz,         setUmsatz]         = useState(null)
  const [eingangsRe,     setEingangsRe]     = useState(null)
  const [config,   setConfig]   = useState(null)
  const [editMode, setEditMode] = useState(false)
  const [katalogOffen, setKatalogOffen] = useState(false)
  const [loading,  setLoading]  = useState(true)
  const configLoaded = useRef(false)
  const saveTimer = useRef(null)

  const isAdmin = user?.role === 'admin'

  // ── Daten laden ──────────────────────────────────────────────────────────
  // Zwei Wellen statt der früheren dreizehn Einzelanfragen:
  //   1. Wer bin ich, welche Stammdaten-Typen gibt es, wie sieht mein
  //      Dashboard aus? Erst daraus ergibt sich, welche Kacheln sichtbar sind.
  //   2. Ein Aufruf holt die Kennzahlen — und zwar nur für genau diese Kacheln.
  useEffect(() => {
    Promise.all([
      masterdataApi.listTypes(),
      authApi.me(),
      usersApi.getDashboard().catch(() => ({ data: { config: null } })),
    ]).then(async ([typesRes, meRes, cfgRes]) => {
      const loadedTypes = typesRes.data
      const me = meRes.data
      setTypes(loadedTypes)
      setUser(me)

      // ── Dashboard-Konfiguration: Server → localStorage-Altbestand → Standard ─
      // normalisiereConfig kümmert sich um das alte Format v1, um entfernte
      // Stammdaten-Typen und um neu ausgelieferte Bausteine.
      const ctx = { isAdmin: me?.role === 'admin', modules: me?.modules ?? null }
      let roh = cfgRes.data?.config
      if (!roh) {
        try { roh = JSON.parse(localStorage.getItem(LS_KEY)) } catch { /* ignorieren */ }
      }
      const cfg = normalisiereConfig(roh, loadedTypes, ctx)
      setConfig(cfg)
      configLoaded.current = true

      // ── Welle 2: Kennzahlen nur für die sichtbaren Kacheln ────────────────
      const sichtbar = aktivesLayout(cfg)?.widgets || []
      const gebraucht = [...new Set(
        sichtbar.map(w => w.type).filter(t => widgetErlaubt(t, ctx)),
      )]

      if (gebraucht.length) {
        const { data } = await dashboardApi.kennzahlen(gebraucht)
        const k = data?.kennzahlen || {}

        if (k.aufgaben) {
          setAufgabenStats(k.aufgaben.stats)
          setMailCount(k.aufgaben.mail_vorschlaege || 0)
        }
        if (k.zeiterfassung) {
          setStats(k.zeiterfassung.stats)
          setRunning(k.zeiterfassung.laufend || null)
        }
        if (k.rechnungen) {
          setInvoiceStats({
            offen:        k.rechnungen.offen,
            ueberfaellig: k.rechnungen.ueberfaellig,
            bezahltMonat: k.rechnungen.bezahlt_monat,
          })
        }
        if (k.projekte)   setRecentProjects(k.projekte || [])
        if (k.datacenter) setDcStats(k.datacenter)
        if (k.buchhaltung) setAccountCount(k.buchhaltung.konten)
        if (k.offene_posten)      setOffenePosten(k.offene_posten)
        if (k.postecke)           setPostecke(k.postecke)
        if (k.umsatz)             setUmsatz(k.umsatz)
        if (k.eingangsrechnungen) setEingangsRe(k.eingangsrechnungen)
        if (k.benutzer_system) {
          setUserStats({
            gesamt: k.benutzer_system.benutzer_gesamt,
            aktiv:  k.benutzer_system.benutzer_aktiv,
          })
          setVersionInfo({ current: k.benutzer_system.version })
        }

        // Update-Prüfung bewusst getrennt und nicht blockierend: sie fragt bei
        // GitHub nach (5 s Timeout, notfalls git fetch mit 10 s). Im
        // Sammelaufruf hinge das ganze Dashboard daran.
        if (k.benutzer_system) {
          systemApi.getVersion()
            .then(res => setVersionInfo(res.data))
            .catch(() => { /* lokale Version steht bereits */ })
        }
      }
    }).catch(err => {
      console.error('Dashboard laden fehlgeschlagen:', err?.response?.data || err)
    }).finally(() => setLoading(false))
  }, [])

  // ── Config speichern (serverseitig, entprellt) ───────────────────────────
  // Fehler NICHT verschlucken: sonst arbeitet der Benutzer weiter und wundert
  // sich später, warum seine Anordnung verschwunden ist.
  useEffect(() => {
    if (!configLoaded.current || !config) return
    clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      usersApi.saveDashboard(config).catch(err => {
        console.error('Dashboard speichern fehlgeschlagen:', err?.response?.data || err)
        toast.error('Dashboard konnte nicht gespeichert werden.')
      })
    }, 800)
    return () => clearTimeout(saveTimer.current)
  }, [config])

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

  // ── Bearbeiten: alle Änderungen betreffen die gerade aktive Ansicht ───────
  function aendereWidgets(fn) {
    setConfig(prev => setzeWidgets(prev, fn(aktivesLayout(prev)?.widgets || [])))
  }

  function handleDragEnd(event) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    aendereWidgets(liste => {
      const alt = liste.findIndex(w => w.id === active.id)
      const neu = liste.findIndex(w => w.id === over.id)
      return (alt < 0 || neu < 0) ? liste : arrayMove(liste, alt, neu)
    })
  }

  const updateSize   = (id, size)  => aendereWidgets(l => l.map(w => w.id === id ? { ...w, size } : w))
  const entferne     = (id)        => aendereWidgets(l => l.filter(w => w.id !== id))
  const setzeTitel   = (id, titel) => aendereWidgets(l => l.map(w => {
    if (w.id !== id) return w
    const rest = { ...w }
    if (titel) rest.titel = titel.slice(0, 40)
    else delete rest.titel                       // leer = wieder Standardbezeichnung
    return rest
  }))
  const fuegeHinzu   = (type, slug) => aendereWidgets(l => [...l, neuesWidget(type, slug)])

  // ── Render ───────────────────────────────────────────────────────────────
  const hour      = new Date().getHours()
  const greeting  = hour < 12 ? 'Guten Morgen' : hour < 18 ? 'Guten Tag' : 'Guten Abend'
  const firstName = user?.full_name?.split(' ')[0] || ''

  if (loading || !config) {
    return (
      <div className="flex items-center justify-center py-24 text-neutral-400">
        <span className="text-sm">Wird geladen…</span>
      </div>
    )
  }

  const typeMap = Object.fromEntries(types.map(t => [t.slug, t]))

  // Rechte-Kontext: Modulrechte stehen in der Registry (Beschluss 2026-07-12),
  // die Prüfung selbst in data/dashboardWidgets.js.
  const ctx = { isAdmin, modules: user?.modules ?? null }

  const layout = aktivesLayout(config)
  // normalisiereConfig hat bereits aussortiert; hier nur noch der Sicherheitsgurt
  // für Rechte, die sich seit dem Laden geändert haben könnten.
  const sichtbareWidgets = (layout?.widgets || []).filter(w =>
    widgetErlaubt(w.type, ctx) && (w.type !== 'entity_type' || typeMap[w.slug])
  )

  // Was schon in der Ansicht steckt — für die Ausgrauung im Katalog
  const vorhandeneTypen = new Set(sichtbareWidgets.filter(w => w.type !== 'entity_type').map(w => w.type))
  const vorhandeneSlugs = new Set(sichtbareWidgets.filter(w => w.type === 'entity_type').map(w => w.slug))

  // Standardbezeichnung eines Bausteins (Platzhalter beim Umbenennen)
  const standardTitel = (w) => w.type === 'entity_type'
    ? (typeMap[w.slug]?.name || w.slug)
    : (widgetDef(w.type)?.label || w.type)

  return (
    <div>
      {/* Header */}
      <PageHeader icon={LayoutDashboard} title="Dashboard" subtitle={`${greeting}${firstName ? `, ${firstName}` : ''} — Übersicht deiner Daten`}>
        <div className="flex items-center gap-2">
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
      </PageHeader>

      {/* Ansichten-Umschalter */}
      <LayoutLeiste
        config={config}
        editMode={editMode}
        onWechsel={(id) => setConfig(prev => wechsleLayout(prev, id))}
        onNeu={() => setConfig(prev => fuegeLayoutHinzu(prev, 'Neue Ansicht'))}
        onKopie={() => setConfig(prev => fuegeLayoutHinzu(prev, `${aktivesLayout(prev)?.name} (Kopie)`, { kopieren: true }))}
        onUmbenennen={(id, name) => setConfig(prev => benenneLayoutUm(prev, id, name))}
        onLoeschen={(id) => setConfig(prev => loescheLayout(prev, id))}
      />

      {/* Bearbeiten-Modus: Hinweis + Aktionen */}
      {editMode && (
        <div className="mb-4 p-4 bg-primary-50 border border-primary-200 rounded-xl text-sm text-primary-700">
          <div className="flex items-start gap-2 mb-3">
            <Settings2 size={15} className="mt-0.5 flex-shrink-0" />
            <span>
              Ziehe die Bausteine, um sie neu anzuordnen. Mit ¼ / ½ / ↔ die Breite anpassen,
              mit dem Stift die Überschrift ändern, mit ✕ den Baustein entfernen.
              Alles wird automatisch gespeichert und gilt auf allen deinen Geräten.
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setKatalogOffen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-500 text-white rounded-lg text-sm font-medium hover:bg-primary-600 transition-colors"
            >
              <Plus size={14} />
              Baustein hinzufügen
            </button>
            <button
              onClick={() => {
                if (window.confirm('Diese Ansicht auf die Standardbelegung zurücksetzen?')) {
                  setConfig(prev => setzeLayoutZurueck(prev, types, ctx))
                }
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-primary-200 text-primary-700 rounded-lg text-sm font-medium hover:bg-primary-100 transition-colors"
            >
              <RotateCcw size={14} />
              Auf Standard zurücksetzen
            </button>
          </div>
        </div>
      )}

      <KatalogDialog
        offen={katalogOffen}
        onClose={() => setKatalogOffen(false)}
        vorhandeneTypen={vorhandeneTypen}
        vorhandeneSlugs={vorhandeneSlugs}
        types={types}
        ctx={ctx}
        onAdd={fuegeHinzu}
      />

      {/* Leere Ansicht */}
      {sichtbareWidgets.length === 0 && (
        <div className="card p-10 flex flex-col items-center justify-center gap-3 text-center text-neutral-400">
          <LayoutGrid size={28} />
          <p className="text-sm">Diese Ansicht ist noch leer.</p>
          {editMode ? (
            <button
              onClick={() => setKatalogOffen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-primary-500 text-white rounded-lg text-sm font-medium hover:bg-primary-600 transition-colors"
            >
              <Plus size={14} />
              Ersten Baustein hinzufügen
            </button>
          ) : (
            <p className="text-xs">Über „Anpassen" kannst du Bausteine hinzufügen.</p>
          )}
        </div>
      )}

      {/* Widget-Grid */}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={sichtbareWidgets.map(w => w.id)} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 auto-rows-auto">
            {sichtbareWidgets.map(widget => (
              <SortableWidget
                key={widget.id}
                id={widget.id}
                size={Math.min(widget.size, 4)}
                editMode={editMode}
                titel={widget.titel}
                standardTitel={standardTitel(widget)}
                onSizeChange={(s) => updateSize(widget.id, s)}
                onTitelChange={(t) => setzeTitel(widget.id, t)}
                onRemove={() => entferne(widget.id)}
              >
                {widget.type === 'entity_type' && typeMap[widget.slug] && (
                  <EntityTypeWidget
                    type={typeMap[widget.slug]}
                    titel={widget.titel}
                    editMode={editMode}
                    onClick={() => navigate(`/masterdata/${widget.slug}`)}
                  />
                )}
                {widget.type === 'aufgaben' && (
                  <AufgabenWidget
                    stats={aufgabenStats}
                    mailCount={mailCount}
                    titel={widget.titel}
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
                    titel={widget.titel}
                    editMode={editMode}
                    navigate={navigate}
                  />
                )}
                {widget.type === 'rechnungen' && (
                  <FinanzWidget
                    invoiceStats={invoiceStats}
                    titel={widget.titel}
                    editMode={editMode}
                    onClick={() => navigate('/invoices')}
                  />
                )}
                {widget.type === 'projekte' && (
                  <ProjekteWidget projects={recentProjects} titel={widget.titel} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'quick_access' && (
                  <QuickAccessWidget titel={widget.titel} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'datacenter' && (
                  <DatacenterWidget dcStats={dcStats} titel={widget.titel} editMode={editMode} onClick={() => navigate('/datacenter')} />
                )}
                {widget.type === 'berichte' && (
                  <BerichteWidget titel={widget.titel} editMode={editMode} onClick={() => navigate('/zeiterfassung')} />
                )}
                {widget.type === 'buchhaltung' && isAdmin && (
                  <BuchhaltungWidget accountCount={accountCount} titel={widget.titel} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'benutzer_system' && isAdmin && (
                  <SystemWidget userStats={userStats} versionInfo={versionInfo} titel={widget.titel} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'offene_posten' && (
                  <OffenePostenWidget daten={offenePosten} titel={widget.titel} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'postecke' && (
                  <PosteckeWidget daten={postecke} titel={widget.titel} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'umsatz' && (
                  <UmsatzWidget daten={umsatz} titel={widget.titel} editMode={editMode} navigate={navigate} />
                )}
                {widget.type === 'eingangsrechnungen' && (
                  <EingangsrechnungenWidget daten={eingangsRe} titel={widget.titel} editMode={editMode} navigate={navigate} />
                )}
              </SortableWidget>
            ))}

            {/* Neuer Stammdaten-Typ Button (nur außerhalb Bearbeiten-Modus) */}
            {!editMode && sichtbareWidgets.length > 0 && (
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
