import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Plus, Loader2, CheckCircle2, Circle, Clock, User as UserIcon,
  Calendar, Flag, X, ChevronRight, ArrowUpRight, Trash2, Diamond, Tag as TagIcon, MoreVertical,
  GanttChartSquare, List as ListIcon,
} from 'lucide-react'
import toast from 'react-hot-toast'
import errMsg from '../utils/errMsg'
import { projektplanApi } from '../services/api'
import TaskDetailSheet from '../components/TaskDetailSheet'
import Checklist from '../components/Checklist'
import GanttChart from '../components/GanttChart'
import {
  EditProjectDialog, DuplicateProjectDialog, DeleteProjectDialog, ProjectActionsMenu,
} from '../components/ProjektDialoge'

const PRIORITY_STYLE = {
  niedrig:  'text-gray-400',
  mittel:   'text-gray-500',
  hoch:     'text-amber-600',
  kritisch: 'text-red-600',
}
const PRIORITY_NEXT = { niedrig: 'mittel', mittel: 'hoch', hoch: 'kritisch', kritisch: 'niedrig' }

function fmtHours(min) {
  if (!min) return '0 h'
  const h = min / 60
  return `${h.toFixed(h < 10 ? 1 : 0)} h`
}

function fmtDate(d) {
  if (!d) return null
  const [y, m, day] = d.split('-')
  return `${day}.${m}.`
}

/** Rekursive Aufgaben-Zeile – beliebig tief verschachtelbar */
function TaskRow({ task, depth, onToggle, onAddSub, onOpen }) {
  const done = task.status === 'erledigt'
  const estimate = task.estimate_minutes || 0
  const logged = task.logged_minutes || 0
  const pct = estimate ? Math.min(100, Math.round((logged / estimate) * 100)) : task.progress

  return (
    <>
      <div
        className="flex items-start gap-2.5 px-3 py-2.5 hover:bg-gray-50 rounded-lg group"
        style={{ paddingLeft: `${12 + depth * 18}px` }}
      >
        <button onClick={() => onToggle(task)} className="mt-0.5 shrink-0">
          {task.is_milestone ? (
            <Diamond size={18} className="text-primary-600" />
          ) : done ? (
            <CheckCircle2 size={20} className="text-green-600" />
          ) : (
            <Circle size={20} className="text-gray-300 group-hover:text-primary-400" />
          )}
        </button>

        <button onClick={() => onOpen(task)} className="flex-1 min-w-0 text-left">
          <p className={`text-sm ${done ? 'line-through text-gray-400' : 'text-gray-900'}`}>
            {task.title}
          </p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1 text-[11px] text-gray-400">
            {(estimate > 0 || logged > 0) && (
              <span className="flex items-center gap-1">
                <Clock size={11} /> {fmtHours(logged)}{estimate ? ` / ${fmtHours(estimate)}` : ''}
              </span>
            )}
            {task.assignee_name && (
              <span className="flex items-center gap-1"><UserIcon size={11} /> {task.assignee_name}</span>
            )}
            {task.contact_name && (
              <span className="flex items-center gap-1 text-primary-400">{task.contact_name}</span>
            )}
            {task.due_date && (
              <span className="flex items-center gap-1"><Calendar size={11} /> bis {fmtDate(task.due_date)}</span>
            )}
            {task.priority !== 'mittel' && task.priority !== 'niedrig' && (
              <span className={`flex items-center gap-1 ${PRIORITY_STYLE[task.priority] || 'text-gray-500'}`}>
                <Flag size={11} /> {task.priority}
              </span>
            )}
          </div>
          {task.data?.tags?.length > 0 && (
            <div className="flex flex-wrap gap-1 mt-1">
              {task.data.tags.map((t) => (
                <span key={t} className="text-[10px] bg-primary-50 text-primary-700 px-1.5 py-0.5 rounded">
                  {t}
                </span>
              ))}
            </div>
          )}
          {estimate > 0 && !done && (
            <div className="h-1 bg-gray-100 rounded-full mt-1.5 max-w-[200px] overflow-hidden">
              <div className="h-full bg-primary-500 rounded-full" style={{ width: `${pct}%` }} />
            </div>
          )}
        </button>

        <button
          onClick={() => onAddSub(task)}
          className="opacity-0 group-hover:opacity-100 transition shrink-0 mt-0.5 text-gray-400 hover:text-primary-600"
          title="Teilaufgabe hinzufügen"
        >
          <Plus size={16} />
        </button>
      </div>

      {task.children?.map((c) => (
        <TaskRow key={c.id} task={c} depth={depth + 1}
          onToggle={onToggle} onAddSub={onAddSub} onOpen={onOpen} />
      ))}
    </>
  )
}

export default function ProjektplanDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [project, setProject] = useState(null)
  const [loading, setLoading] = useState(true)

  const [quickAdd, setQuickAdd] = useState(false)
  const [quickTitle, setQuickTitle] = useState('')
  const [quickParent, setQuickParent] = useState(null)
  const [saving, setSaving] = useState(false)

  const [detailTask, setDetailTask] = useState(null)
  const [settings, setSettings] = useState({ statuses: [], priorities: [], tags: [] })
  const [fields, setFields] = useState([])
  const [view, setView] = useState('liste')   // 'liste' | 'gantt'

  // Projekt-Aktionen
  const [headerMenu, setHeaderMenu] = useState(false)
  const [editProj, setEditProj] = useState(null)
  const [dupProj, setDupProj] = useState(null)
  const [delProj, setDelProj] = useState(null)

  const load = useCallback(async () => {
    try {
      const { data } = await projektplanApi.getProject(id)
      setProject(data)
    } catch {
      toast.error('Projekt konnte nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  // Konfiguration (Status/Prioritäten/Tags + eigene Felder) einmalig laden
  useEffect(() => {
    projektplanApi.getSettings().then(r => setSettings(r.data)).catch(() => {})
    projektplanApi.listFields().then(r => setFields(r.data)).catch(() => {})
  }, [])

  const openQuickAdd = (parent = null) => {
    setQuickParent(parent)
    setQuickTitle('')
    setQuickAdd(true)
  }

  const saveQuick = async (keepOpen) => {
    const title = quickTitle.trim()
    if (!title) return
    setSaving(true)
    try {
      await projektplanApi.createTask(id, {
        title,
        parent_task_id: quickParent?.id || null,
      })
      setQuickTitle('')
      await load()
      if (!keepOpen) setQuickAdd(false)
    } catch (err) {
      toast.error(errMsg(err, 'Fehler beim Speichern'))
    } finally {
      setSaving(false)
    }
  }

  const toggleDone = async (task) => {
    const next = task.status === 'erledigt' ? 'offen' : 'erledigt'
    try {
      await projektplanApi.updateTask(task.id, {
        status: next,
        progress: next === 'erledigt' ? 100 : 0,
      })
      await load()
    } catch {
      toast.error('Status konnte nicht geändert werden')
    }
  }

  const promote = async (task) => {
    try {
      const { data } = await projektplanApi.promoteTask(task.id, { move_subtasks: true, link_back: true })
      toast.success('Detailprojekt erstellt')
      setDetailTask(null)
      navigate(`/projekte/${data.id}`)
    } catch (err) {
      toast.error(errMsg(err, 'Fehler beim Erstellen'))
    }
  }

  const deleteTask = async (task) => {
    try {
      await projektplanApi.deleteTask(task.id)
      setDetailTask(null)
      await load()
    } catch {
      toast.error('Aufgabe konnte nicht gelöscht werden')
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="animate-spin text-primary-400" size={28} />
      </div>
    )
  }
  if (!project) return null

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 pb-28">
      {/* Kopf */}
      <div className="flex items-center gap-3 mb-1">
        <button onClick={() => navigate('/projekte')} className="text-gray-400 hover:text-gray-700">
          <ArrowLeft size={20} />
        </button>
        {project.color && (
          <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: project.color }} title="Projektfarbe" />
        )}
        <h1 className="text-xl font-medium text-gray-900 flex-1 truncate">{project.name}</h1>
        <div className="relative shrink-0">
          <button onClick={() => setHeaderMenu(v => !v)} className="text-gray-400 hover:text-gray-700 p-1" title="Aktionen">
            <MoreVertical size={20} />
          </button>
          {headerMenu && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setHeaderMenu(false)} />
              <ProjectActionsMenu
                onEdit={() => { setEditProj(project); setHeaderMenu(false) }}
                onDuplicate={() => { setDupProj(project); setHeaderMenu(false) }}
                onDelete={() => { setDelProj(project); setHeaderMenu(false) }}
              />
            </>
          )}
        </div>
      </div>
      <p className="text-sm text-gray-500 mb-3 ml-8">
        {project.task_count} Aufgaben · {project.progress_percent}% erledigt
      </p>

      {/* Ansichtsumschalter */}
      <div className="flex gap-1 mb-4 ml-8">
        {[
          { id: 'liste', label: 'Liste', icon: ListIcon },
          { id: 'gantt', label: 'Zeitschiene', icon: GanttChartSquare },
        ].map(v => (
          <button key={v.id} onClick={() => setView(v.id)}
            className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg transition ${
              view === v.id ? 'bg-primary-50 text-primary-700' : 'text-gray-500 hover:bg-gray-50'
            }`}>
            <v.icon size={15} /> {v.label}
          </button>
        ))}
      </div>

      {view === 'gantt' ? (
        <GanttChart project={project} onChanged={load} />
      ) : (
        /* Aufgabenliste (rekursiv) */
        <div className="bg-white border border-gray-200 rounded-xl py-1.5">
          {project.tasks.length === 0 ? (
            <p className="text-center text-gray-400 text-sm py-8">
              Noch keine Aufgaben. Tippe unten auf „Aufgabe".
            </p>
          ) : (
            project.tasks.map((t) => (
              <TaskRow key={t.id} task={t} depth={0}
                onToggle={toggleDone} onAddSub={openQuickAdd} onOpen={setDetailTask} />
            ))
          )}
        </div>
      )}

      {/* Meilensteine */}
      {project.milestones.length > 0 && (
        <div className="mt-5">
          <h3 className="text-sm font-medium text-gray-700 mb-2">Meilensteine</h3>
          <div className="space-y-1.5">
            {project.milestones.map((m) => (
              <div key={m.id} className="flex items-center gap-2 text-sm text-primary-700">
                <Diamond size={15} />
                <span className="font-medium">{m.title}</span>
                {m.due_date && <span className="text-gray-400">· {fmtDate(m.due_date)}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Checkliste auf Projektebene */}
      <div className="mt-5 bg-white border border-gray-200 rounded-xl p-4">
        <Checklist parentType="project" parentId={project.id} onItemPromoted={load} />
      </div>

      {/* FAB Quick-Add */}
      <button
        onClick={() => openQuickAdd(null)}
        className="fixed bottom-6 right-6 md:right-auto md:left-1/2 md:-translate-x-1/2 md:max-w-3xl flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-5 py-3 rounded-full shadow-lg transition"
      >
        <Plus size={20} />
        <span className="font-medium">Aufgabe</span>
      </button>

      {/* Quick-Add Bottom-Sheet */}
      {quickAdd && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center bg-black/40" onClick={() => setQuickAdd(false)}>
          <div className="bg-white w-full md:max-w-md rounded-t-2xl md:rounded-2xl p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-1">
              <h2 className="text-sm text-gray-500">
                {quickParent ? `Teilaufgabe zu „${quickParent.title}"` : 'Neue Aufgabe'}
              </h2>
              <button onClick={() => setQuickAdd(false)}><X size={20} className="text-gray-400" /></button>
            </div>
            <input
              autoFocus
              value={quickTitle}
              onChange={(e) => setQuickTitle(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && saveQuick(true)}
              placeholder="Was ist zu tun?"
              className="w-full border border-gray-300 rounded-lg px-3 py-2.5 text-base focus:outline-none focus:border-primary-400 mt-2"
            />
            <div className="flex gap-2 mt-4">
              <button
                onClick={() => saveQuick(false)}
                disabled={saving}
                className="flex-1 border border-gray-300 hover:bg-gray-50 disabled:opacity-50 text-gray-700 py-2.5 rounded-lg font-medium transition"
              >
                Speichern
              </button>
              <button
                onClick={() => saveQuick(true)}
                disabled={saving}
                className="flex-1 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-2.5 rounded-lg font-medium transition"
              >
                Speichern & weiter
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Aufgaben-Detail Bottom-Sheet (umfangreich) */}
      {detailTask && (
        <TaskDetailSheet
          task={detailTask}
          settings={settings}
          fields={fields}
          projectContact={{ contact_id: project.contact_id, contact_name: project.contact_name }}
          onClose={() => setDetailTask(null)}
          onPromote={(t) => promote(t)}
          onChanged={(action, t) => {
            if (action === 'delete') { deleteTask(t || detailTask); setDetailTask(null) }
            else load()
          }}
        />
      )}

      {/* Projekt-Dialoge */}
      {editProj && (
        <EditProjectDialog project={editProj} statuses={settings.statuses}
          onClose={() => setEditProj(null)} onSaved={load} />
      )}
      {dupProj && (
        <DuplicateProjectDialog project={dupProj}
          onClose={() => setDupProj(null)}
          onDuplicated={(np) => navigate(`/projekte/${np.id}`)} />
      )}
      {delProj && (
        <DeleteProjectDialog project={delProj}
          onClose={() => setDelProj(null)}
          onArchived={() => navigate('/projekte')}
          onDeleted={() => navigate('/projekte')} />
      )}
    </div>
  )
}
