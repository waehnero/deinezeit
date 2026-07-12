import { useState, useLayoutEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X, Copy, Trash2, Archive, Save, AlertTriangle, User } from 'lucide-react'
import toast from 'react-hot-toast'
import errMsg from '../utils/errMsg'
import { projektplanApi } from '../services/api'
import ContactSearch from './ContactSearch'

function Overlay({ children, onClose }) {
  return (
    <div className="fixed inset-0 z-[60] flex items-end md:items-center justify-center bg-black/40" onClick={onClose}>
      <div className="bg-surface w-full md:max-w-md rounded-t-2xl md:rounded-2xl max-h-[92vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        {children}
      </div>
    </div>
  )
}

function Header({ title, onClose }) {
  return (
    <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
      <h2 className="text-base font-medium text-gray-900">{title}</h2>
      <button onClick={onClose}><X size={20} className="text-gray-400" /></button>
    </div>
  )
}

/** Projekt bearbeiten */
export function EditProjectDialog({ project, statuses = [], onClose, onSaved }) {
  const [form, setForm] = useState({
    name: project.name || '',
    description: project.description || '',
    status: project.status || 'offen',
    color: project.color || '#3b82f6',
    start_date: project.start_date || '',
    end_date: project.end_date || '',
    contact_id: project.contact_id || null,
    contact_name: project.contact_name || '',
  })
  const [saving, setSaving] = useState(false)
  const set = (p) => setForm(f => ({ ...f, ...p }))

  const save = async () => {
    if (!form.name.trim()) return toast.error('Bitte einen Projektnamen eingeben')
    setSaving(true)
    try {
      await projektplanApi.updateProject(project.id, {
        name: form.name.trim(),
        description: form.description || null,
        status: form.status,
        color: form.color,
        start_date: form.start_date || null,
        end_date: form.end_date || null,
        contact_id: form.contact_id || null,
        contact_name: form.contact_name || null,
      })
      toast.success('Projekt aktualisiert')
      onSaved?.()
      onClose()
    } catch (err) {
      toast.error(errMsg(err, 'Fehler beim Speichern'))
    } finally {
      setSaving(false)
    }
  }

  const cls = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400'
  const sts = statuses.length ? statuses : [{ value: 'offen', label: 'Offen' }]

  return (
    <Overlay onClose={onClose}>
      <Header title="Projekt bearbeiten" onClose={onClose} />
      <div className="p-5 space-y-4">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Name</label>
          <input value={form.name} onChange={(e) => set({ name: e.target.value })} className={cls} />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Beschreibung</label>
          <textarea rows={2} value={form.description} onChange={(e) => set({ description: e.target.value })} className={cls} />
        </div>
        <div>
          <label className="text-xs text-gray-500 mb-1 block flex items-center gap-1"><User size={12} /> Kontakt</label>
          <ContactSearch
            contactId={form.contact_id}
            contactName={form.contact_name}
            onChange={(id, name) => set({ contact_id: id, contact_name: name })}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Status</label>
            <select value={form.status} onChange={(e) => set({ status: e.target.value })} className={cls}>
              {sts.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Farbe</label>
            <input type="color" value={form.color} onChange={(e) => set({ color: e.target.value })}
              className="w-full h-[38px] rounded-lg border border-gray-300 cursor-pointer" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Start</label>
            <input type="date" value={form.start_date || ''} onChange={(e) => set({ start_date: e.target.value })} className={cls} />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Ende</label>
            <input type="date" value={form.end_date || ''} onChange={(e) => set({ end_date: e.target.value })} className={cls} />
          </div>
        </div>
      </div>
      <div className="px-5 py-3 border-t border-gray-100">
        <button onClick={save} disabled={saving}
          className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-2.5 rounded-lg font-medium">
          <Save size={18} /> {saving ? 'Speichern…' : 'Speichern'}
        </button>
      </div>
    </Overlay>
  )
}

/** Projekt duplizieren – mit Auswahl, wie viel mitkopiert wird */
export function DuplicateProjectDialog({ project, onClose, onDuplicated }) {
  const [name, setName] = useState(`${project.name} (Kopie)`)
  const [opts, setOpts] = useState({
    include_tasks: true,
    include_milestones: true,
    include_field_values: true,
    include_assignees: true,
    include_dates: true,
    reset_status: false,
  })
  const [busy, setBusy] = useState(false)
  const toggle = (k) => setOpts(o => ({ ...o, [k]: !o[k] }))

  const run = async () => {
    setBusy(true)
    try {
      const { data } = await projektplanApi.duplicateProject(project.id, { name: name.trim() || undefined, ...opts })
      toast.success('Projekt dupliziert')
      onDuplicated?.(data)
      onClose()
    } catch (err) {
      toast.error(errMsg(err, 'Fehler beim Duplizieren'))
    } finally {
      setBusy(false)
    }
  }

  const Row = ({ k, label, hint, disabled }) => (
    <label className={`flex items-start gap-3 py-2 ${disabled ? 'opacity-40' : ''}`}>
      <input type="checkbox" checked={opts[k]} disabled={disabled} onChange={() => toggle(k)} className="mt-0.5" />
      <span>
        <span className="text-sm text-gray-900 block">{label}</span>
        {hint && <span className="text-xs text-gray-500">{hint}</span>}
      </span>
    </label>
  )

  return (
    <Overlay onClose={onClose}>
      <Header title="Projekt duplizieren" onClose={onClose} />
      <div className="p-5">
        <label className="text-xs text-gray-500 mb-1 block">Name der Kopie</label>
        <input value={name} onChange={(e) => setName(e.target.value)}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400 mb-3" />

        <p className="text-xs text-gray-500 mb-1">Was soll mitkopiert werden?</p>
        <div className="divide-y divide-gray-100">
          <Row k="include_tasks" label="Aufgaben & Teilaufgaben" hint="Komplette Aufgabenstruktur" />
          <Row k="include_milestones" label="Meilensteine" />
          <Row k="include_field_values" label="Feldwerte & Tags" hint="Eigene Felder und Schlagwörter der Aufgaben" disabled={!opts.include_tasks} />
          <Row k="include_assignees" label="Verantwortliche" disabled={!opts.include_tasks} />
          <Row k="include_dates" label="Termine (Start/Fällig)" />
          <Row k="reset_status" label="Status zurücksetzen" hint="Alle Aufgaben auf „offen“ / 0 % – ideal für Vorlagen" disabled={!opts.include_tasks} />
        </div>
        <p className="text-[11px] text-gray-400 mt-3">
          Hinweis: Erfasste Ist-Stunden und Anlagen werden nicht mitkopiert.
        </p>
      </div>
      <div className="px-5 py-3 border-t border-gray-100">
        <button onClick={run} disabled={busy}
          className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white py-2.5 rounded-lg font-medium">
          <Copy size={18} /> {busy ? 'Dupliziere…' : 'Duplizieren'}
        </button>
      </div>
    </Overlay>
  )
}

/** Löschen / Archivieren bestätigen */
export function DeleteProjectDialog({ project, onClose, onArchived, onDeleted }) {
  const [busy, setBusy] = useState(false)

  const archive = async () => {
    setBusy(true)
    try {
      await projektplanApi.updateProject(project.id, { is_archived: !project.is_archived })
      toast.success(project.is_archived ? 'Projekt wiederhergestellt' : 'Projekt archiviert')
      onArchived?.()
      onClose()
    } catch (err) {
      toast.error(errMsg(err, 'Fehler'))
    } finally { setBusy(false) }
  }

  const del = async () => {
    setBusy(true)
    try {
      await projektplanApi.deleteProject(project.id)
      toast.success('Projekt gelöscht')
      onDeleted?.()
      onClose()
    } catch (err) {
      toast.error(errMsg(err, 'Fehler beim Löschen'))
    } finally { setBusy(false) }
  }

  return (
    <Overlay onClose={onClose}>
      <Header title="Projekt entfernen" onClose={onClose} />
      <div className="p-5">
        <div className="flex gap-3 bg-amber-50 text-amber-800 rounded-lg p-3 mb-4">
          <AlertTriangle size={18} className="shrink-0 mt-0.5" />
          <p className="text-sm">
            „{project.name}“ entfernen. <strong>Archivieren</strong> blendet es nur aus (wiederherstellbar).
            <strong> Löschen</strong> entfernt das Projekt mit allen Aufgaben endgültig.
          </p>
        </div>
        <button onClick={archive} disabled={busy}
          className="w-full flex items-center justify-center gap-2 border border-gray-300 hover:bg-gray-50 text-gray-700 py-2.5 rounded-lg font-medium mb-2">
          <Archive size={18} /> {project.is_archived ? 'Wiederherstellen' : 'Archivieren (ausblenden)'}
        </button>
        <button onClick={del} disabled={busy}
          className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white py-2.5 rounded-lg font-medium">
          <Trash2 size={18} /> Endgültig löschen
        </button>
      </div>
    </Overlay>
  )
}

/**
 * Drei-Punkte-Aktionsmenü (Dropdown).
 *
 * Wird per Portal an document.body gerendert und mit `fixed` an der Position
 * des auslösenden Buttons (`anchorRef`) platziert. Dadurch wird es nie vom
 * `overflow-hidden` der Tabellen-/Karten-Container abgeschnitten und kann
 * frei über die Liste hinausragen. Klappt automatisch nach oben auf, wenn
 * nach unten zu wenig Platz ist.
 *
 * `anchorRef` ist die ref des Auslöse-Buttons (bzw. dessen Wrapper).
 * Ohne `anchorRef` fällt die Komponente auf das alte absolute Verhalten zurück
 * (Abwärtskompatibilität).
 */
export function ProjectActionsMenu({ onEdit, onDuplicate, onDelete, align = 'right', anchorRef }) {
  const menuRef = useRef(null)
  const [pos, setPos] = useState(null)
  const MENU_W = 176 // entspricht w-44 (11rem)

  useLayoutEffect(() => {
    if (!anchorRef?.current) return
    const place = () => {
      const r = anchorRef.current.getBoundingClientRect()
      // Anchor unsichtbar (z.B. der per CSS ausgeblendete Mobile-/Desktop-Button
      // der jeweils anderen Ansicht) → rect ist 0/0/0/0. Dann NICHT positionieren,
      // sonst erscheint eine zweite Menü-Kopie oben links im Eck.
      if (r.width === 0 && r.height === 0) { setPos(null); return }
      const menuH = menuRef.current?.offsetHeight || 120
      const gap = 4
      // Nach unten, sonst nach oben klappen, wenn unten kein Platz ist
      const openUp = r.bottom + gap + menuH > window.innerHeight && r.top - gap - menuH > 0
      const top = openUp ? r.top - gap - menuH : r.bottom + gap
      // Rechtsbündig zum Button, am Viewport-Rand clampen
      let left = align === 'right' ? r.right - MENU_W : r.left
      left = Math.max(8, Math.min(left, window.innerWidth - MENU_W - 8))
      setPos({ top, left })
    }
    place()
    window.addEventListener('scroll', place, true)
    window.addEventListener('resize', place)
    return () => {
      window.removeEventListener('scroll', place, true)
      window.removeEventListener('resize', place)
    }
  }, [anchorRef, align])

  const items = (
    <>
      <button onClick={onEdit} className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2">
        <Save size={15} className="text-gray-400" /> Bearbeiten
      </button>
      <button onClick={onDuplicate} className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2">
        <Copy size={15} className="text-gray-400" /> Duplizieren
      </button>
      <button onClick={onDelete} className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2 text-red-600">
        <Trash2 size={15} /> Archivieren / Löschen
      </button>
    </>
  )

  // Fallback: altes absolutes Verhalten, wenn kein anchorRef übergeben wurde
  if (!anchorRef) {
    return (
      <div className={`absolute ${align === 'right' ? 'right-0' : 'left-0'} top-8 z-20 bg-surface border border-gray-200 rounded-lg shadow-lg py-1 w-44`}>
        {items}
      </div>
    )
  }

  // Erst rendern, wenn die Position berechnet ist – sonst würde kurzzeitig
  // eine zweite, fehlplatzierte Menü-Kopie (oben links) erscheinen.
  if (!pos) return null

  return createPortal(
    <div
      ref={menuRef}
      className="fixed z-[70] bg-surface border border-gray-200 rounded-lg shadow-lg py-1 w-44"
      style={{ top: pos.top, left: pos.left }}
    >
      {items}
    </div>,
    document.body
  )
}
