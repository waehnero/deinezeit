import { useState } from 'react'
import {
  DndContext, PointerSensor, useSensor, useSensors, closestCorners,
  useDraggable, useDroppable, DragOverlay,
} from '@dnd-kit/core'
import { Camera, Bell, Check, X, Archive, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { posteckeApi } from '../services/api'
import PosteckeFotoThumb from './PosteckeFotoThumb'

/**
 * Kanban-Board für die Postecke (Etappe 2).
 * Spalten = Post-Status; Drag&Drop ändert den Status.
 * Besonderheit: Beim Ziehen nach „Geplant" wird nach Datum/Uhrzeit gefragt.
 * Gleiche Bedienlogik wie AufgabenKanban.jsx — bewusst eigene Komponente,
 * die Postecke ist eine eigene Domäne.
 *
 * Props:
 *   posts        – Postliste
 *   profilName   – (profilId) => Anzeigename
 *   kanalLabel   – (profilId) => Kanal-Bezeichnung oder null
 *   onOpen(p)    – Post im Editor öffnen
 *   onChanged    – nach erfolgreicher Statusänderung (Liste neu laden)
 */

const SPALTEN = [
  { value: 'entwurf',         label: 'Entwürfe',       color: '#9ca3af' },
  { value: 'kontrolle',       label: 'Zur Kontrolle',  color: '#f59e0b' },
  { value: 'geplant',         label: 'Geplant',        color: '#3b82f6' },
  { value: 'veroeffentlicht', label: 'Veröffentlicht', color: '#22c55e' },
]

function zeit(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('de-AT', { weekday: 'short', day: '2-digit', month: '2-digit' }) +
    ' ' + d.toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' })
}

// ── Eine Postkarte (ziehbar) ──────────────────────────────────────────────────
function Card({ post, profilName, kanalLabel, onOpen, onArchivieren, onLoeschen }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: post.id })
  const style = {
    transform: transform ? `translate(${transform.x}px, ${transform.y}px)` : undefined,
    opacity: isDragging ? 0.4 : 1,
  }
  return (
    <div ref={setNodeRef} style={style}
      className="bg-surface border border-neutral-200 rounded-lg p-3 mb-2 shadow-sm select-none">
      <div {...listeners} {...attributes} className="cursor-grab active:cursor-grabbing">
        {post.fotos?.length > 0 ? (
          <PosteckeFotoThumb fotoId={post.fotos[0].id} className="w-full h-28 rounded-md mb-2" />
        ) : (
          <div className="w-full h-14 rounded-md bg-neutral-50 flex items-center justify-center mb-2">
            <Camera size={16} className="text-neutral-300" />
          </div>
        )}
        <p className="text-sm text-neutral-900 leading-snug mb-1 line-clamp-2">
          {post.titel || post.text?.slice(0, 60) || post.beschreibung?.slice(0, 60) || 'Ohne Titel'}
        </p>
        {post.text && (
          <p className="text-xs text-neutral-500 leading-snug mb-1.5 line-clamp-2">{post.text}</p>
        )}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-neutral-400 mb-1">
          {post.profil_id && (
            <span className="px-1.5 py-0.5 rounded-full bg-primary-50 text-primary-700">
              {kanalLabel(post.profil_id) || profilName(post.profil_id)}
            </span>
          )}
          {post.fotos?.length > 1 && <span>{post.fotos.length} Fotos</span>}
          {post.status === 'geplant' && post.geplant_am && (
            <span className="flex items-center gap-1 text-primary-600">
              <Bell size={11} /> {zeit(post.geplant_am)}
            </span>
          )}
          {post.status === 'veroeffentlicht' && post.veroeffentlicht_am && (
            <span className="flex items-center gap-1 text-green-600">
              <Check size={11} /> {zeit(post.veroeffentlicht_am)}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center justify-between pt-1 border-t border-neutral-100">
        <button onClick={() => onOpen(post)} className="text-[11px] text-primary-600 hover:text-primary-700">
          Öffnen
        </button>
        <div className="flex gap-0.5">
          <button onClick={() => onArchivieren(post)} title="Archivieren"
            className="p-1 rounded text-neutral-300 hover:text-amber-600 hover:bg-amber-50">
            <Archive size={13} />
          </button>
          <button onClick={() => onLoeschen(post)} title="Löschen"
            className="p-1 rounded text-neutral-300 hover:text-red-600 hover:bg-red-50">
            <Trash2 size={13} />
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Eine Spalte (Drop-Ziel) ───────────────────────────────────────────────────
function Column({ spalte, posts, profilName, kanalLabel, onOpen, onArchivieren, onLoeschen }) {
  const { setNodeRef, isOver } = useDroppable({ id: spalte.value })
  return (
    <div className="shrink-0 w-64 md:w-auto md:shrink md:min-w-0">
      <div className="flex items-center gap-2 mb-2 px-1">
        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: spalte.color }} />
        <span className="text-sm font-medium text-neutral-700 truncate">{spalte.label}</span>
        <span className="text-xs text-neutral-400">{posts.length}</span>
      </div>
      <div ref={setNodeRef}
        className={`rounded-xl p-2 min-h-[140px] md:min-h-[200px] transition-colors ${isOver ? 'bg-primary-50' : 'bg-neutral-50'}`}>
        {posts.length === 0 ? (
          <p className="text-xs text-neutral-300 text-center py-6">leer</p>
        ) : (
          posts.map(p => (
            <Card key={p.id} post={p} profilName={profilName} kanalLabel={kanalLabel}
              onOpen={onOpen} onArchivieren={onArchivieren} onLoeschen={onLoeschen} />
          ))
        )}
      </div>
    </div>
  )
}

// ── Termin-Dialog beim Ziehen nach „Geplant" ─────────────────────────────────
function PlanenDialog({ post, onBestaetigen, onAbbrechen }) {
  const [wert, setWert] = useState('')
  return (
    <div className="fixed inset-0 z-50 bg-neutral-900/40 flex items-center justify-center p-4 sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-2xl p-4 w-full max-w-xs space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-neutral-900">Wann soll gepostet werden?</p>
          <button onClick={onAbbrechen} className="p-1 rounded-lg hover:bg-neutral-100 text-neutral-500">
            <X size={16} />
          </button>
        </div>
        <p className="text-xs text-neutral-500 truncate">
          {post.titel || post.text?.slice(0, 50) || 'Post'}
        </p>
        <input type="datetime-local" value={wert} onChange={e => setWert(e.target.value)} autoFocus
          className="w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm bg-surface focus:outline-none focus:ring-2 focus:ring-primary-200" />
        <div className="flex gap-2 justify-end">
          <button onClick={onAbbrechen}
            className="px-3 py-2 rounded-lg text-sm text-neutral-600 hover:bg-neutral-100">Abbrechen</button>
          <button onClick={() => wert && onBestaetigen(wert)} disabled={!wert}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50">
            Planen
          </button>
        </div>
      </div>
    </div>
  )
}

export default function PosteckeKanban({ posts, profilName, kanalLabel, onOpen, onChanged,
                                          onArchivieren, onLoeschen }) {
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))
  const [activePost, setActivePost] = useState(null)
  const [planenFuer, setPlanenFuer] = useState(null)   // Post, der nach „geplant" gezogen wurde
  // Lokaler Status-Override für sofortiges UI-Feedback beim Verschieben
  const [override, setOverride] = useState({})          // postId -> status

  const statusOf = (p) => override[p.id] ?? p.status
  const postsInSpalte = (status) => posts.filter(p => statusOf(p) === status)

  const statusSetzen = async (post, status, geplantAm = null) => {
    setOverride(o => ({ ...o, [post.id]: status }))
    try {
      await posteckeApi.setStatus(post.id, status, geplantAm)
      onChanged?.()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Status konnte nicht geändert werden')
      setOverride(o => { const n = { ...o }; delete n[post.id]; return n })
    }
  }

  const onDragStart = (e) => setActivePost(posts.find(p => p.id === e.active.id) || null)

  const onDragEnd = (e) => {
    setActivePost(null)
    const { active, over } = e
    if (!over) return
    const post = posts.find(p => p.id === active.id)
    const neu = over.id
    if (!post || statusOf(post) === neu) return
    if (neu === 'geplant') {
      setPlanenFuer(post)   // Termin abfragen, erst dann Status setzen
      return
    }
    statusSetzen(post, neu)
  }

  if (posts.length === 0) {
    return <p className="text-center text-neutral-400 text-sm py-8">Keine Posts für das Board.</p>
  }

  return (
    <>
      <DndContext sensors={sensors} collisionDetection={closestCorners}
        onDragStart={onDragStart} onDragEnd={onDragEnd}>
        {/* Mobil: horizontal scrollbar (flex). Desktop: Spalten als Grid nebeneinander. */}
        <div className="flex gap-3 overflow-x-auto pb-2 md:grid md:overflow-visible"
          style={{ gridTemplateColumns: `repeat(${SPALTEN.length}, minmax(0, 1fr))` }}>
          {SPALTEN.map(sp => (
            <Column key={sp.value} spalte={sp} posts={postsInSpalte(sp.value)}
              profilName={profilName} kanalLabel={kanalLabel} onOpen={onOpen}
              onArchivieren={onArchivieren} onLoeschen={onLoeschen} />
          ))}
        </div>
        <DragOverlay>
          {activePost ? (
            <div className="bg-surface border border-primary-300 rounded-lg p-3 shadow-lg w-60">
              <p className="text-sm text-neutral-900">
                {activePost.titel || activePost.text?.slice(0, 50) || 'Post'}
              </p>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      {planenFuer && (
        <PlanenDialog post={planenFuer}
          onBestaetigen={(wert) => {
            statusSetzen(planenFuer, 'geplant', new Date(wert).toISOString())
            setPlanenFuer(null)
          }}
          onAbbrechen={() => setPlanenFuer(null)} />
      )}
    </>
  )
}
