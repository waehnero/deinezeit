import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus, GanttChartSquare, Loader2, ChevronRight, Archive, X, Settings2, MoreVertical,
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

  // Menü / Dialoge
  const [menuFor, setMenuFor] = useState(null)      // Projekt-ID, dessen Menü offen ist
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

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 pb-28">
      <div className="flex items-center gap-3 mb-6">
        <GanttChartSquare className="text-primary-600" size={28} />
        <h1 className="text-2xl font-medium text-gray-900 flex-1">Projekte</h1>
        <button
          onClick={() => setShowArchived(v => !v)}
          className={`transition ${showArchived ? 'text-primary-600' : 'text-gray-400 hover:text-primary-600'}`}
          title={showArchived ? 'Archivierte ausblenden' : 'Archivierte anzeigen'}
        >
          <Archive size={20} />
        </button>
        <button
          onClick={() => navigate('/projekte/einstellungen')}
          className="text-gray-400 hover:text-primary-600 transition"
          title="Projekt-Einstellungen"
        >
          <Settings2 size={20} />
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="animate-spin text-primary-400" size={28} />
        </div>
      ) : projects.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <GanttChartSquare size={40} className="mx-auto mb-3 text-gray-300" />
          <p>Noch keine Projekte. Lege dein erstes Planungsprojekt an.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {projects.map((p) => (
            <div
              key={p.id}
              className={`relative bg-white border rounded-xl p-4 transition flex items-center gap-3 ${
                p.is_archived ? 'border-gray-200 opacity-70' : 'border-gray-200 hover:border-primary-300'
              }`}
            >
              <button onClick={() => navigate(`/projekte/${p.id}`)} className="flex-1 min-w-0 text-left">
                <div className="flex items-center gap-2 mb-1">
                  {p.color && (
                    <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: p.color }} title="Projektfarbe" />
                  )}
                  <span className="font-medium text-gray-900 truncate">{p.name}</span>
                  {p.is_archived && <Archive size={14} className="text-gray-400 shrink-0" />}
                  <span
                    className="text-xs px-2 py-0.5 rounded-md shrink-0"
                    style={{ backgroundColor: statusColor(p.status) + '22', color: statusColor(p.status) }}
                  >
                    {statusLabel(p.status)}
                  </span>
                </div>
                <div className="text-xs text-gray-500 mb-2">
                  {p.task_count} Aufgaben · {p.progress_percent}% erledigt
                  {p.masterdata_project_name ? ` · ${p.masterdata_project_name}` : ''}
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                  <div className="h-full bg-primary-500 rounded-full transition-all" style={{ width: `${p.progress_percent}%` }} />
                </div>
              </button>

              <div className="relative shrink-0">
                <button
                  onClick={() => setMenuFor(menuFor === p.id ? null : p.id)}
                  className="text-gray-400 hover:text-gray-700 p-1"
                  title="Aktionen"
                >
                  <MoreVertical size={18} />
                </button>
                {menuFor === p.id && (
                  <>
                    <div className="fixed inset-0 z-10" onClick={() => setMenuFor(null)} />
                    <ProjectActionsMenu
                      onEdit={() => { setEditProj(p); setMenuFor(null) }}
                      onDuplicate={() => { setDupProj(p); setMenuFor(null) }}
                      onDelete={() => { setDelProj(p); setMenuFor(null) }}
                    />
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Dialoge */}
      {editProj && (
        <EditProjectDialog project={editProj} statuses={statuses}
          onClose={() => setEditProj(null)} onSaved={load} />
      )}
      {dupProj && (
        <DuplicateProjectDialog project={dupProj}
          onClose={() => setDupProj(null)}
          onDuplicated={(np) => navigate(`/projekte/${np.id}`)} />
      )}
      {delProj && (
        <DeleteProjectDialog project={delProj}
          onClose={() => setDelProj(null)} onArchived={load} onDeleted={load} />
      )}

      {/* Floating Action Button – schnelles Anlegen */}
      <button
        onClick={() => setShowCreate(true)}
        className="fixed bottom-6 right-6 md:right-auto md:left-1/2 md:-translate-x-1/2 md:max-w-3xl flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-5 py-3 rounded-full shadow-lg transition"
      >
        <Plus size={20} />
        <span className="font-medium">Neues Projekt</span>
      </button>

      {/* Bottom-Sheet zum Anlegen */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/40" onClick={() => setShowCreate(false)}>
          <div
            className="bg-white w-full md:max-w-md rounded-t-2xl md:rounded-2xl p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium text-gray-900">Neues Projekt</h2>
              <button onClick={() => setShowCreate(false)}><X size={20} className="text-gray-400" /></button>
            </div>
            <input
              autoFocus
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createProject()}
              placeholder="Projektname, z. B. Wohnhaus Mariahilf"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-base focus:outline-none focus:border-primary-400"
            />
            <button
              onClick={createProject}
              disabled={saving}
              className="w-full mt-4 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-3 rounded-lg font-medium transition"
            >
              {saving ? 'Anlegen…' : 'Anlegen & öffnen'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
