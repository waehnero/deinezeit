import { useMemo, useState } from 'react'
import {
  DndContext, PointerSensor, useSensor, useSensors, closestCorners,
  useDraggable, useDroppable, DragOverlay,
} from '@dnd-kit/core'
import { User as UserIcon, Calendar, Flag, GanttChartSquare, Database } from 'lucide-react'
import toast from 'react-hot-toast'
import { aufgabenApi } from '../services/api'

/**
 * Kanban-Board für das Aufgabenmodul.
 * Spalten = konfigurierte Status (aufgaben_settings); Drag&Drop ändert den Status.
 * Gleiche Bedienlogik wie das Projektplan-Board (KanbanBoard.jsx), aber
 * bewusst eigene Komponente — das Aufgabenmodul ist eine eigene Domäne.
 *
 * Props:
 *   todos      – gefilterte Aufgabenliste
 *   statuses   – [{value,label,color}] aus den Aufgaben-Einstellungen
 *   priorities – [{value,label,color}]
 *   onOpen(t)  – Aufgabe im Dialog öffnen
 *   onChanged  – nach erfolgreicher Statusänderung (Liste neu laden)
 */

function fmtDate(d) {
  if (!d) return null
  const [, m, day] = d.split('-')
  return `${day}.${m}.`
}

// ── Eine Aufgabenkarte (ziehbar) ──────────────────────────────────────────────
function Card({ todo, prioColor, onOpen }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: todo.id })
  const style = {
    transform: transform ? `translate(${transform.x}px, ${transform.y}px)` : undefined,
    opacity: isDragging ? 0.4 : 1,
  }
  const wichtig = todo.priority === 'hoch' || todo.priority === 'kritisch'
  return (
    <div ref={setNodeRef} style={style}
      className="bg-surface border border-gray-200 rounded-lg p-3 mb-2 shadow-sm select-none">
      <div {...listeners} {...attributes} className="cursor-grab active:cursor-grabbing">
        <p className="text-sm text-gray-900 leading-snug mb-1.5">{todo.title}</p>
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-gray-400">
          {todo.assignee_name && <span className="flex items-center gap-1"><UserIcon size={11} /> {todo.assignee_name}</span>}
          {todo.due_date && (
            <span className="flex items-center gap-1">
              <Calendar size={11} /> {fmtDate(todo.due_date)}{todo.due_time ? ` ${todo.due_time.slice(0, 5)}` : ''}
            </span>
          )}
          {wichtig && (
            <span className="flex items-center gap-1" style={{ color: prioColor(todo.priority) }}>
              <Flag size={11} /> {todo.priority}
            </span>
          )}
          {todo.planning_project_name && (
            <span className="flex items-center gap-1 truncate"><GanttChartSquare size={11} /> {todo.planning_project_name}</span>
          )}
          {todo.record_name && (
            <span className="flex items-center gap-1 truncate"><Database size={11} /> {todo.record_name}</span>
          )}
        </div>
      </div>
      <button onClick={() => onOpen(todo)} className="mt-2 text-[11px] text-primary-600 hover:text-primary-700">
        Details öffnen
      </button>
    </div>
  )
}

// ── Eine Spalte (Drop-Ziel) ───────────────────────────────────────────────────
function Column({ status, todos, prioColor, onOpen }) {
  const { setNodeRef, isOver } = useDroppable({ id: status.value })
  return (
    <div className="shrink-0 w-64 md:w-auto md:shrink md:min-w-0">
      <div className="flex items-center gap-2 mb-2 px-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: status.color || '#6b7280' }} />
        <span className="text-sm font-medium text-gray-700 truncate">{status.label}</span>
        <span className="text-xs text-gray-400">{todos.length}</span>
      </div>
      <div ref={setNodeRef}
        className={`rounded-xl p-2 min-h-[140px] md:min-h-[200px] transition-colors ${isOver ? 'bg-primary-50' : 'bg-gray-50'}`}>
        {todos.length === 0 ? (
          <p className="text-xs text-gray-300 text-center py-6">leer</p>
        ) : (
          todos.map(t => <Card key={t.id} todo={t} prioColor={prioColor} onOpen={onOpen} />)
        )}
      </div>
    </div>
  )
}

export default function AufgabenKanban({ todos, statuses, priorities, onOpen, onChanged }) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))
  const [activeTodo, setActiveTodo] = useState(null)
  // Lokaler Status-Override für sofortiges UI-Feedback beim Verschieben
  const [override, setOverride] = useState({})  // todoId -> statusValue

  const statusOf = (t) => override[t.id] ?? t.status
  const prioColor = (v) => priorities.find(p => p.value === v)?.color || '#6b7280'

  // Spalten aus konfigurierten Status + dynamisch alle tatsächlich vorkommenden
  // Status, die (noch) nicht konfiguriert sind -> so geht keine Aufgabe verloren.
  const columns = useMemo(() => {
    const configured = statuses?.length ? statuses : [
      { value: 'offen', label: 'Offen', color: '#6b7280' },
      { value: 'in_arbeit', label: 'In Arbeit', color: '#3b82f6' },
      { value: 'erledigt', label: 'Erledigt', color: '#22c55e' },
    ]
    const known = new Set(configured.map(s => s.value))
    const extra = []
    const seen = new Set()
    for (const t of todos) {
      const sv = statusOf(t)
      if (sv && !known.has(sv) && !seen.has(sv)) {
        seen.add(sv)
        extra.push({ value: sv, label: sv, color: '#9ca3af' })
      }
    }
    return [...configured, ...extra]
  }, [statuses, todos, override])

  const todosByStatus = (statusValue) => todos.filter(t => statusOf(t) === statusValue)

  const onDragStart = (e) => {
    setActiveTodo(todos.find(t => t.id === e.active.id) || null)
  }

  const onDragEnd = async (e) => {
    setActiveTodo(null)
    const { active, over } = e
    if (!over) return
    const todo = todos.find(t => t.id === active.id)
    const newStatus = over.id
    if (!todo || statusOf(todo) === newStatus) return

    setOverride(o => ({ ...o, [todo.id]: newStatus }))
    try {
      await aufgabenApi.update(todo.id, { status: newStatus })
      onChanged?.()
    } catch {
      toast.error('Status konnte nicht geändert werden')
      setOverride(o => { const n = { ...o }; delete n[todo.id]; return n })
    }
  }

  if (todos.length === 0) {
    return <p className="text-center text-gray-400 text-sm py-8">Keine Aufgaben für das Board.</p>
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCorners}
      onDragStart={onDragStart} onDragEnd={onDragEnd}>
      {/* Mobil: horizontal scrollbar (flex). Desktop: Spalten als Grid nebeneinander. */}
      <div className="flex gap-3 overflow-x-auto pb-2 md:grid md:overflow-visible"
        style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(0, 1fr))` }}>
        {columns.map(col => (
          <Column key={col.value} status={col} todos={todosByStatus(col.value)}
            prioColor={prioColor} onOpen={onOpen} />
        ))}
      </div>
      <DragOverlay>
        {activeTodo ? (
          <div className="bg-surface border border-primary-300 rounded-lg p-3 shadow-lg w-60">
            <p className="text-sm text-gray-900">{activeTodo.title}</p>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  )
}
