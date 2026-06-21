import { useMemo, useState } from 'react'
import {
  DndContext, PointerSensor, useSensor, useSensors, closestCorners,
  useDraggable, useDroppable, DragOverlay,
} from '@dnd-kit/core'
import { User as UserIcon, Calendar, Flag, Clock } from 'lucide-react'
import toast from 'react-hot-toast'
import { projektplanApi } from '../services/api'

// Aufgabenbaum flach machen (Board zeigt alle Aufgaben, auch Teilaufgaben)
function flatten(tasks, out = []) {
  for (const t of tasks) {
    out.push(t)
    if (t.children?.length) flatten(t.children, out)
  }
  return out
}

function fmtHours(min) {
  if (!min) return null
  const h = min / 60
  return `${h.toFixed(h < 10 ? 1 : 0)} h`
}
function fmtDate(d) {
  if (!d) return null
  const [, m, day] = d.split('-')
  return `${day}.${m}.`
}

const PRIO_COLOR = { hoch: '#f59e0b', kritisch: '#ef4444' }

// ── Eine Aufgabenkarte (ziehbar) ──────────────────────────────────────────────
function Card({ task, onOpen }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: task.id })
  const style = {
    transform: transform ? `translate(${transform.x}px, ${transform.y}px)` : undefined,
    opacity: isDragging ? 0.4 : 1,
  }
  const logged = task.logged_minutes || 0
  const estimate = task.estimate_minutes || 0
  return (
    <div ref={setNodeRef} style={style}
      className="bg-white border border-gray-200 rounded-lg p-3 mb-2 shadow-sm select-none">
      {/* Greifbereich + Klick zum Öffnen */}
      <div {...listeners} {...attributes} className="cursor-grab active:cursor-grabbing">
        {task.data?.task_type && task.data.task_type !== 'aufgabe' && (
          <span className="inline-block text-[10px] bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded mb-1">
            {task.data.task_type}
          </span>
        )}
        <p className="text-sm text-gray-900 leading-snug mb-1.5">{task.title}</p>
        {task.data?.tags?.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-1.5">
            {task.data.tags.map(t => (
              <span key={t} className="text-[10px] bg-primary-50 text-primary-700 px-1.5 py-0.5 rounded">{t}</span>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-gray-400">
          {task.assignee_name && <span className="flex items-center gap-1"><UserIcon size={11} /> {task.assignee_name}</span>}
          {task.due_date && <span className="flex items-center gap-1"><Calendar size={11} /> {fmtDate(task.due_date)}</span>}
          {(estimate > 0 || logged > 0) && <span className="flex items-center gap-1"><Clock size={11} /> {fmtHours(logged) || '0 h'}{estimate ? `/${fmtHours(estimate)}` : ''}</span>}
          {(task.priority === 'hoch' || task.priority === 'kritisch') && (
            <span className="flex items-center gap-1" style={{ color: PRIO_COLOR[task.priority] }}><Flag size={11} /> {task.priority}</span>
          )}
        </div>
      </div>
      <button onClick={() => onOpen(task)} className="mt-2 text-[11px] text-primary-600 hover:text-primary-700">
        Details öffnen
      </button>
    </div>
  )
}

// ── Eine Spalte (Drop-Ziel) ───────────────────────────────────────────────────
function Column({ status, tasks, onOpen }) {
  const { setNodeRef, isOver } = useDroppable({ id: status.value })
  return (
    <div className="shrink-0 w-64 md:w-auto md:shrink md:min-w-0">
      <div className="flex items-center gap-2 mb-2 px-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: status.color || '#6b7280' }} />
        <span className="text-sm font-medium text-gray-700 truncate">{status.label}</span>
        <span className="text-xs text-gray-400">{tasks.length}</span>
      </div>
      <div ref={setNodeRef}
        className={`rounded-xl p-2 min-h-[140px] md:min-h-[200px] transition-colors ${isOver ? 'bg-primary-50' : 'bg-gray-50'}`}>
        {tasks.length === 0 ? (
          <p className="text-xs text-gray-300 text-center py-6">leer</p>
        ) : (
          tasks.map(t => <Card key={t.id} task={t} onOpen={onOpen} />)
        )}
      </div>
    </div>
  )
}

export default function KanbanBoard({ project, settings, onOpenTask, onChanged }) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))
  const [activeTask, setActiveTask] = useState(null)
  // Lokaler Status-Override für sofortiges UI-Feedback beim Verschieben
  const [override, setOverride] = useState({})  // taskId -> statusValue

  const allTasks = useMemo(() => flatten(project.tasks || []), [project.tasks])

  const statusOf = (t) => override[t.id] ?? t.status

  // Spalten aus konfigurierten Status + dynamisch alle tatsächlich vorkommenden
  // Status, die (noch) nicht konfiguriert sind -> so geht keine Aufgabe verloren.
  const columns = useMemo(() => {
    const configured = settings?.statuses?.length ? settings.statuses : [
      { value: 'offen', label: 'Offen', color: '#6b7280' },
      { value: 'in_arbeit', label: 'In Arbeit', color: '#3b82f6' },
      { value: 'erledigt', label: 'Erledigt', color: '#22c55e' },
    ]
    const known = new Set(configured.map(s => s.value))
    // Status, die an Aufgaben vorkommen, aber nicht konfiguriert sind
    const extra = []
    const seen = new Set()
    for (const t of allTasks) {
      const sv = statusOf(t)
      if (sv && !known.has(sv) && !seen.has(sv)) {
        seen.add(sv)
        extra.push({ value: sv, label: sv, color: '#9ca3af' })  // grau = unkonfiguriert
      }
    }
    return [...configured, ...extra]
  }, [settings, allTasks, override])

  const tasksByStatus = (statusValue) => allTasks.filter(t => statusOf(t) === statusValue)

  const onDragStart = (e) => {
    setActiveTask(allTasks.find(t => t.id === e.active.id) || null)
  }

  const onDragEnd = async (e) => {
    setActiveTask(null)
    const { active, over } = e
    if (!over) return
    const task = allTasks.find(t => t.id === active.id)
    const newStatus = over.id
    if (!task || statusOf(task) === newStatus) return

    // sofortiges UI-Feedback
    setOverride(o => ({ ...o, [task.id]: newStatus }))
    try {
      await projektplanApi.updateTask(task.id, {
        status: newStatus,
        progress: newStatus === 'erledigt' ? 100 : (task.progress || 0),
      })
      onChanged?.()   // lädt Projekt neu -> Override wird durch echte Daten ersetzt
    } catch {
      toast.error('Status konnte nicht geändert werden')
      setOverride(o => { const n = { ...o }; delete n[task.id]; return n })
    }
  }

  if (allTasks.length === 0) {
    return <p className="text-center text-gray-400 text-sm py-8">Noch keine Aufgaben für das Board.</p>
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCorners}
      onDragStart={onDragStart} onDragEnd={onDragEnd}>
      {/* Mobil: horizontal scrollbar (flex). Desktop: alle Spalten als Grid nebeneinander. */}
      <div className="flex gap-3 overflow-x-auto pb-2 md:grid md:overflow-visible"
        style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}>
        {columns.map(col => (
          <Column key={col.value} status={col} tasks={tasksByStatus(col.value)} onOpen={onOpenTask} />
        ))}
      </div>
      <DragOverlay>
        {activeTask ? (
          <div className="bg-white border border-primary-300 rounded-lg p-3 shadow-lg w-60">
            <p className="text-sm text-gray-900">{activeTask.title}</p>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  )
}
