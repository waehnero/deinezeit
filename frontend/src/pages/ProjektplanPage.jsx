import { useState, useEffect, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, GanttChartSquare, Loader2, Archive, X, Settings2, MoreVertical,
  Search, Users, ChevronDown, ChevronRight,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { projektplanApi } from '../services/api'
import {
  EditProjectDialog, DuplicateProjectDialog, DeleteProjectDialog, ProjectActionsMenu,
} from '../components/ProjektDialoge'

export default function ProjektplanPage() {
  const navigate = useNavigate()
  const [projects, setProjects] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [newName, setNewName] = useState('')
  const [saving, setSaving] = useState(false)
  const [statuses, setStatuses] = useState([])
  const [showArchived, setShowArchived] = useState(false)

  // Filter
  const [tab, setTab] = useState('alle')
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [grouped, setGrouped] = useState(true)
  const [collapsed, setCollapsed] = useState({})  // contactName -> true

  // Menü / Dialoge
  const [menuFor, setMenuFor] = useState(null)
  const [editProj, setEditProj] = useState(null)
  const [dupProj, setDupProj] = useState(null)
  const [delProj, setDelProj] = useState(null)

  const statusLabel = (val) => statuses.find(s => s.value === val)?.label || val
  const statusColor = (val) => statuses.find(s => s.value === val)?.color || '#6b7280'

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await projektplanApi.listProjects({ include_archived: showArchived })
      setProjects(data)
    } catch {
      toast.error('Projekte konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [showArchived])
  useEffect(() => { projektplanApi.getSettings().then(r => setStatuses(r.data.statuses || [])).catch(() => {}) }, [])

  const createProject = async () => {
    const name = newName.trim()
    if (!name) return toast.error('Bitte einen Projektnamen eingeben')
    setSaving(true)
    try {
      const { data } = await projektplanApi.createProject({ name })
      toast.success('Projekt angelegt')
      setShowCreate(false)
      setNewName('')
      navigate(`/projekte/${data.id}`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Anlegen')
    } finally {
      setSaving(false)
    }
  }

  // ── Dynamische Tabs aus tatsächlich vorkommenden Kontakt-Typen ─────────────
  // "Alle" + je ein Tab pro Kontakt-Typ, der an mindestens einem Projekt hängt.
  // So erscheint jeder neue Kontakt-Typ automatisch, ohne Konfiguration.
  const typeTabs = useMemo(() => {
    const counts = new Map()   // typLabel (Original) -> Anzahl
    for (const p of projects) {
      const t = (p.contact_type || '').trim()
      if (t) counts.set(t, (counts.get(t) || 0) + 1)
    }
    const dyn = Array.from(counts.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([label, n]) => ({ id: label.toLowerCase(), label, value: label.toLowerCase(), count: n }))
    return [{ id: 'alle', label: 'Alle', value: null, count: projects.length }, ...dyn]
  }, [projects])

  // ── Filtern ───────────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const tabDef = typeTabs.find(t => t.id === tab) || typeTabs[0]
    const s = search.trim().toLowerCase()
    return projects.filter(p => {
      if (tabDef?.value) {
        if ((p.contact_type || '').toLowerCase() !== tabDef.value) return false
      }
      if (statusFilter && p.status !== statusFilter) return false
      if (s) {
        const hay = `${p.name} ${p.contact_name || ''}`.toLowerCase()
        if (!hay.includes(s)) return false
      }
      return true
    })
  }, [projects, tab, search, statusFilter, typeTabs])

  // ── Nach Kontakt gruppieren ───────────────────────────────────────────────
  const groups = useMemo(() => {
    const map = new Map()
    for (const p of filtered) {
      const key = p.contact_name || '— ohne Kontakt —'
      if (!map.has(key)) map.set(key, { name: key, type: p.contact_type, items: [] })
      map.get(key).items.push(p)
    }
    return Array.from(map.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [filtered])

  const initials = (name) => (name || '?').split(/\s+/).slice(0, 2).map(w => w[0]).join('').toUpperCase()

  return (
    <div className="max-w-6xl mx-auto px-4 md:px-6 py-6 pb-28">
      {/* Kopf */}
      <div className="flex items-center gap-3 mb-1">
        <GanttChartSquare className="text-primary-600" size={26} />
        <div className="flex-1">
          <h1 className="text-xl md:text-2xl font-medium text-gray-900">Projekte</h1>
          <p className="text-xs text-gray-400 hidden sm:block">Kunden · Lieferanten · Interessenten</p>
        </div>
        <button onClick={() => setShowArchived(v => !v)}
          className={`transition ${showArchived ? 'text-primary-600' : 'text-gray-400 hover:text-primary-600'}`}
          title={showArchived ? 'Archivierte ausblenden' : 'Archivierte anzeigen'}>
          <Archive size={20} />
        </button>
        <button onClick={() => navigate('/projekte/einstellungen')}
          className="text-gray-400 hover:text-primary-600 transition" title="Projekt-Einstellungen">
          <Settings2 size={20} />
        </button>
        <button onClick={() => setShowCreate(true)}
          className="hidden sm:flex items-center gap-1.5 bg-primary-600 hover:bg-primary-700 text-white px-4 py-2 rounded-lg text-sm font-medium">
          <Plus size={16} /> Neues Projekt
        </button>
      </div>

      {/* Tabs nach Kontakt-Typ */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg overflow-x-auto flex-nowrap sm:w-fit -mx-4 px-4 sm:mx-0 sm:px-1 mt-4 mb-3">
        {typeTabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`text-sm px-3 py-1.5 rounded-md whitespace-nowrap transition ${
              tab === t.id ? 'bg-surface text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}>
            {t.label} <span className="text-gray-400">{t.count}</span>
          </button>
        ))}
      </div>

      {/* Suche + Status + Gruppieren */}
      <div className="flex gap-2 items-center mb-4">
        <div className="flex-1 flex items-center gap-2 border border-gray-300 rounded-lg px-3 h-9">
          <Search size={15} className="text-gray-400 shrink-0" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Projekt oder Kontakt suchen…"
            className="w-full text-sm bg-transparent focus:outline-none" />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-gray-300 rounded-lg px-2 h-9 text-sm text-gray-600">
          <option value="">Alle Status</option>
          {statuses.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <button onClick={() => setGrouped(g => !g)}
          className={`hidden sm:flex items-center gap-1.5 border rounded-lg px-3 h-9 text-sm transition ${
            grouped ? 'border-primary-300 bg-primary-50 text-primary-700' : 'border-gray-300 text-gray-600'
          }`} title="Nach Kontakt gruppieren">
          <Users size={15} /> nach Kontakt
        </button>
      </div>

      {/* Inhalt */}
      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin text-primary-400" size={28} /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <GanttChartSquare size={40} className="mx-auto mb-3 text-gray-300" />
          <p>{projects.length === 0 ? 'Noch keine Projekte. Lege dein erstes Projekt an.' : 'Keine Projekte für diesen Filter.'}</p>
        </div>
      ) : grouped ? (
        // ── Gruppierte Tabelle ──
        <div className="border border-gray-200 rounded-xl overflow-hidden bg-surface">
          <div className="hidden md:grid bg-gray-50 border-b border-gray-200 px-4 py-2 text-[11px] text-gray-400"
            style={{ gridTemplateColumns: '1.6fr 110px 90px 90px 40px' }}>
            <span>Projekt</span><span className="text-center">Status</span>
            <span className="text-center">Aufgaben</span><span className="text-right">% erledigt</span><span></span>
          </div>
          {groups.map(g => (
            <div key={g.name}>
              <button onClick={() => setCollapsed(c => ({ ...c, [g.name]: !c[g.name] }))}
                className="w-full flex items-center gap-2 px-4 py-2 bg-gray-50/70 border-b border-gray-100 text-left">
                {collapsed[g.name] ? <ChevronRight size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
                <span className="w-6 h-6 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-[10px] shrink-0">{initials(g.name)}</span>
                <span className="text-sm font-medium text-gray-800 truncate">{g.name}</span>
                <span className="text-[11px] text-gray-400 shrink-0">{g.type ? `${g.type} · ` : ''}{g.items.length} Projekt{g.items.length > 1 ? 'e' : ''}</span>
              </button>
              {!collapsed[g.name] && g.items.map(p => (
                <ProjectRow key={p.id} p={p} statusLabel={statusLabel} statusColor={statusColor}
                  onOpen={() => navigate(`/projekte/${p.id}`)}
                  menuOpen={menuFor === p.id} onMenu={() => setMenuFor(menuFor === p.id ? null : p.id)}
                  onCloseMenu={() => setMenuFor(null)}
                  onEdit={() => { setEditProj(p); setMenuFor(null) }}
                  onDuplicate={() => { setDupProj(p); setMenuFor(null) }}
                  onDelete={() => { setDelProj(p); setMenuFor(null) }} />
              ))}
            </div>
          ))}
        </div>
      ) : (
        // ── Flache Tabelle ──
        <div className="border border-gray-200 rounded-xl overflow-hidden bg-surface">
          <div className="hidden md:grid bg-gray-50 border-b border-gray-200 px-4 py-2 text-[11px] text-gray-400"
            style={{ gridTemplateColumns: '1.4fr 1.1fr 110px 80px 80px 40px' }}>
            <span>Projekt</span><span>Kontakt</span><span className="text-center">Status</span>
            <span className="text-center">Aufg.</span><span className="text-right">%</span><span></span>
          </div>
          {filtered.map(p => (
            <ProjectRow key={p.id} p={p} flat statusLabel={statusLabel} statusColor={statusColor}
              onOpen={() => navigate(`/projekte/${p.id}`)}
              menuOpen={menuFor === p.id} onMenu={() => setMenuFor(menuFor === p.id ? null : p.id)}
              onCloseMenu={() => setMenuFor(null)}
              onEdit={() => { setEditProj(p); setMenuFor(null) }}
              onDuplicate={() => { setDupProj(p); setMenuFor(null) }}
              onDelete={() => { setDelProj(p); setMenuFor(null) }} />
          ))}
        </div>
      )}

      {/* Dialoge */}
      {editProj && <EditProjectDialog project={editProj} statuses={statuses} onClose={() => setEditProj(null)} onSaved={load} />}
      {dupProj && <DuplicateProjectDialog project={dupProj} onClose={() => setDupProj(null)} onDuplicated={(np) => navigate(`/projekte/${np.id}`)} />}
      {delProj && <DeleteProjectDialog project={delProj} onClose={() => setDelProj(null)} onArchived={load} onDeleted={load} />}

      {/* FAB (nur Handy) */}
      <button onClick={() => setShowCreate(true)}
        className="sm:hidden fixed bottom-6 right-6 flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-5 py-3 rounded-full shadow-lg">
        <Plus size={20} /> <span className="font-medium">Neu</span>
      </button>

      {/* Anlegen-Sheet */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/40" onClick={() => setShowCreate(false)}>
          <div className="bg-surface w-full md:max-w-md rounded-t-2xl md:rounded-2xl p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-gray-900">Neues Projekt</h2>
              <button onClick={() => setShowCreate(false)}><X size={20} className="text-gray-400" /></button>
            </div>
            <input autoFocus value={newName} onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createProject()}
              placeholder="Projektname, z. B. Wohnhaus Mariahilf"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-base focus:outline-none focus:border-primary-400" />
            <button onClick={createProject} disabled={saving}
              className="w-full mt-4 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-3 rounded-lg font-medium transition">
              {saving ? 'Anlegen…' : 'Anlegen & öffnen'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Eine Projektzeile – Desktop als Tabellengrid, Mobile als Karte */
function ProjectRow({ p, flat, statusLabel, statusColor, onOpen, menuOpen, onMenu, onCloseMenu, onEdit, onDuplicate, onDelete }) {
  const cols = flat ? '1.4fr 1.1fr 110px 80px 80px 40px' : '1.6fr 110px 90px 90px 40px'
  const menuBtnDesktop = useRef(null)
  const menuBtnMobile = useRef(null)
  return (
    <div className={`border-b border-gray-100 last:border-0 ${p.is_archived ? 'opacity-60' : 'hover:bg-gray-50'}`}>
      {/* Desktop */}
      <div className="hidden md:grid items-center px-4 py-2.5 text-sm" style={{ gridTemplateColumns: cols }}>
        <button onClick={onOpen} className="flex items-center gap-2 min-w-0 text-left">
          {p.color && <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: p.color }} />}
          <span className="truncate text-gray-900">{p.name}</span>
          {p.is_archived && <Archive size={13} className="text-gray-400 shrink-0" />}
        </button>
        {flat && <span className="text-gray-500 truncate">{p.contact_name || '—'}</span>}
        <span className="text-center">
          <span className="text-[11px] px-2 py-0.5 rounded-md" style={{ backgroundColor: statusColor(p.status) + '22', color: statusColor(p.status) }}>{statusLabel(p.status)}</span>
        </span>
        <span className="text-center text-gray-500">{p.task_count}</span>
        <span className="text-right text-gray-500">{p.progress_percent}%</span>
        <span className="relative flex justify-end">
          <button ref={menuBtnDesktop} onClick={onMenu} className="text-gray-400 hover:text-gray-700 p-1"><MoreVertical size={16} /></button>
          {menuOpen && (<><div className="fixed inset-0 z-[65]" onClick={onCloseMenu} /><ProjectActionsMenu anchorRef={menuBtnDesktop} onEdit={onEdit} onDuplicate={onDuplicate} onDelete={onDelete} /></>)}
        </span>
      </div>

      {/* Mobile (Karte) */}
      <div className="md:hidden flex items-center gap-3 px-3 py-3">
        <button onClick={onOpen} className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-2 mb-1">
            {p.color && <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: p.color }} />}
            <span className="font-medium text-gray-900 truncate text-sm">{p.name}</span>
          </div>
          <div className="text-xs text-gray-500 mb-1.5">
            {flat && p.contact_name ? `${p.contact_name} · ` : ''}{p.task_count} Aufgaben · {p.progress_percent}% · {statusLabel(p.status)}
          </div>
          <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div className="h-full bg-primary-500 rounded-full" style={{ width: `${p.progress_percent}%` }} />
          </div>
        </button>
        <div className="relative shrink-0">
          <button ref={menuBtnMobile} onClick={onMenu} className="text-gray-400 hover:text-gray-700 p-1"><MoreVertical size={18} /></button>
          {menuOpen && (<><div className="fixed inset-0 z-[65]" onClick={onCloseMenu} /><ProjectActionsMenu anchorRef={menuBtnMobile} onEdit={onEdit} onDuplicate={onDuplicate} onDelete={onDelete} /></>)}
        </div>
      </div>
    </div>
  )
}
