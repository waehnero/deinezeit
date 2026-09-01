/**
 * Projektzeit nachtragen / bearbeiten.
 *
 * Aus ZeiterfassungPage.jsx herausgelöst, damit der Bericht „Projektzeiten"
 * denselben Dialog öffnet: Ein zweiter, eigener Bearbeiten-Dialog würde mit
 * jeder Änderung weiter vom ersten abweichen — und der Unterschied fiele erst
 * auf, wenn ein Feld nur an einer der beiden Stellen gespeichert wird.
 *
 * `initial`: optionale Vorbefüllung (z.B. KI-Vorschlag aus dem Sprach-Nachtragen)
 */
import { useState } from 'react'
import { X, Check, Loader2, Sparkles, AlertTriangle } from 'lucide-react'
import toast from 'react-hot-toast'
import { zeiterfassungApi, datacenterApi } from '../services/api'
import ZeitprojektSuche from './ZeitprojektSuche'
import AttachmentPanel from './AttachmentPanel'
import AttachmentQuickBar from './AttachmentQuickBar'
import {
  isoToDateLocal, isoToTimeLocal, localToIso, calcDuration, apiErrorText, fmtMinutes,
} from '../utils/zeit'

export default function ProjektzeitModal({ entry, initial = null, onClose, onSaved }) {
  const isEdit = !!entry
  const now = new Date()
  const init = initial || {}
  const [project, setProject] = useState(entry ? {
    projectId: entry.project_id, projectName: entry.project_name || '',
    contactName: entry.contact_name || '',
  } : (init.project || { projectId: null, projectName: '', contactName: '' }))
  const [startDate, setStartDate] = useState(entry ? isoToDateLocal(entry.started_at) : (init.startDate || isoToDateLocal(now.toISOString())))
  const [startTime, setStartTime] = useState(entry ? isoToTimeLocal(entry.started_at) : (init.startTime || isoToTimeLocal(now.toISOString())))
  const [endDate, setEndDate] = useState(entry?.ended_at ? isoToDateLocal(entry.ended_at) : (init.endDate || init.startDate || isoToDateLocal(now.toISOString())))
  const [endTime, setEndTime] = useState(entry?.ended_at ? isoToTimeLocal(entry.ended_at) : (init.endTime || isoToTimeLocal(now.toISOString())))
  const [pause, setPause] = useState(entry?.pause_minutes ?? init.pause ?? 0)
  const [note, setNote] = useState(entry?.note ?? init.note ?? '')
  const [billable, setBillable] = useState(entry?.billable ?? init.billable ?? true)
  const [loading, setLoading] = useState(false)
  const [createAnother, setCreateAnother] = useState(false)
  const [createdEntry, setCreatedEntry] = useState(null)
  const [attachmentsRefresh, setAttachmentsRefresh] = useState(0)

  const startedAt = localToIso(startDate, startTime)
  const endedAt = localToIso(endDate, endTime)
  const durationMin = calcDuration(startedAt, endedAt, pause)

  const buildPayload = () => ({
    project_id: project.projectId || null,
    project_name: project.projectName || null,
    contact_id: null, contact_name: project.contactName || null,
    started_at: startedAt, ended_at: endedAt || null,
    pause_minutes: Number(pause) || 0,
    note: note || null, billable, data: {},
  })

  // Für Anhänge ohne gespeicherten Eintrag: Projekt + Startzeit sind Pflicht,
  // dann sofort speichern, um eine entityId zu erhalten.
  // Wenn `files` übergeben werden (Upload-Button), wird direkt hochgeladen und
  // true/false zurückgegeben (das Modal bleibt offen, kein Unmount).
  const ensureEntity = async (files = null) => {
    const uploadTo = async (id) => {
      if (!files || !files.length) return true
      try {
        for (const file of Array.from(files)) {
          await datacenterApi.upload('zeiterfassung', id, file)
        }
        toast.success(files.length > 1 ? 'Dateien hochgeladen' : 'Datei hochgeladen')
        setAttachmentsRefresh(n => n + 1)
        return true
      } catch {
        toast.error('Datei konnte nicht hochgeladen werden')
        return false
      }
    }

    if (createdEntry) return files ? await uploadTo(createdEntry.id) : createdEntry.id
    if (isEdit)       return files ? await uploadTo(entry.id)        : entry.id
    if (!project.projectId) {
      toast.error('Bitte zuerst ein Zeitprojekt wählen')
      return files ? false : null
    }
    if (!startedAt) {
      toast.error('Bitte Startzeit angeben')
      return files ? false : null
    }
    setLoading(true)
    try {
      const res = await zeiterfassungApi.createEntry(buildPayload())
      setCreatedEntry(res.data)
      toast.success('Zeiteintrag gespeichert')
      return files ? await uploadTo(res.data.id) : res.data.id
    } catch (err) {
      toast.error(apiErrorText(err, 'Fehler beim Speichern'), { duration: 6000 })
      return files ? false : null
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!startedAt) return toast.error('Bitte gültige Startzeit (Datum + Uhrzeit) angeben')
    setLoading(true)
    try {
      const payload = buildPayload()
      if (isEdit || createdEntry) {
        await zeiterfassungApi.updateEntry((entry || createdEntry).id, payload)
        toast.success('Zeiteintrag aktualisiert')
      } else {
        await zeiterfassungApi.createEntry(payload)
        toast.success('Zeiteintrag gespeichert')
      }
      if (createAnother && !isEdit && !createdEntry) {
        setNote(''); setPause(0)
        setStartTime(endTime); setStartDate(endDate)
        setEndTime(isoToTimeLocal(new Date().toISOString()))
      } else { onSaved() }
    } catch (err) {
      console.error('Zeiteintrag speichern fehlgeschlagen:', err)
      toast.error(apiErrorText(err, 'Fehler beim Speichern'), { duration: 6000 })
    } finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center p-4 overflow-y-auto sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-2xl shadow-2xl w-full max-w-2xl my-8">
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            {isEdit ? 'Zeiteintrag bearbeiten' : 'Projektzeit nachtragen'}
            {initial && <Sparkles size={16} className="text-primary-500" title="Per KI aus Sprachaufnahme vorbefüllt" />}
          </h2>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition">
            <X size={20} />
          </button>
        </div>

        {/* Hinweise aus der KI-Auswertung (Sprach-Nachtragen) */}
        {init.warnings?.length > 0 && (
          <div className="mx-5 mt-4 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl">
            {init.warnings.map((w, i) => (
              <p key={i} className="flex items-start gap-2 text-sm text-amber-700">
                <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" /> {w}
              </p>
            ))}
          </div>
        )}

        <div className="p-5 grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Zeitprojekt</label>
            <ZeitprojektSuche value={project} onChange={setProject}
              initialSearch={!project.projectId ? (init.project?.projectName || '') : ''} />
          </div>
          <div className="sm:col-span-2">
            <label className="block text-sm font-medium text-gray-700 mb-1">Notiz</label>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2}
              placeholder="Was wurde gemacht?"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Startzeit</label>
            <div className="flex gap-2">
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
                className="flex-1 px-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
              <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)}
                className="w-24 px-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Endzeit</label>
            <div className="flex gap-2">
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
                className="flex-1 px-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
              <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)}
                className="w-24 px-3 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pause (Minuten)</label>
            <input type="number" value={pause} onChange={(e) => setPause(e.target.value)} min={0}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Dauer</label>
            <div className="px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl text-sm text-gray-600 font-medium">
              {fmtMinutes(durationMin)} h
            </div>
          </div>
          <div className="sm:col-span-2 flex items-center gap-3">
            <input type="checkbox" id="modal-billable" checked={billable} onChange={(e) => setBillable(e.target.checked)}
              className="w-5 h-5 rounded accent-primary-600" />
            <label htmlFor="modal-billable" className="text-sm font-medium text-gray-700 cursor-pointer">Verrechenbar</label>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 p-5 border-t border-gray-100">
          {/* Quick-Upload: beim Bearbeiten direkt an entry.id (stabil),
              beim Nachtragen via onEnsureEntity (legt Eintrag an). */}
          <AttachmentQuickBar entityType="zeiterfassung"
            entityId={isEdit ? entry.id : createdEntry?.id || null}
            onEnsureEntity={ensureEntity}
            onUploaded={() => setAttachmentsRefresh(n => n + 1)}
            className="mr-auto" />
          {!isEdit && !createdEntry && (
            <label className="flex items-center gap-2 text-sm text-gray-500 cursor-pointer">
              <input type="checkbox" checked={createAnother} onChange={(e) => setCreateAnother(e.target.checked)}
                className="w-4 h-4 rounded accent-primary-600" />
              Weiteren erstellen
            </label>
          )}
          <button onClick={onClose} className={`px-5 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition ${isEdit ? 'ml-auto' : ''}`}>
            Abbrechen
          </button>
          <button onClick={handleSave} disabled={loading}
            className="px-6 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center gap-2">
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />}
            Speichern
          </button>
        </div>

        {/* Anhänge – Dateiliste bei bestehenden oder bereits gespeicherten Einträgen */}
        {(isEdit || createdEntry) && (
          <div className="px-5 pb-5 border-t border-gray-100">
            <AttachmentPanel entityType="zeiterfassung" entityId={(entry || createdEntry).id}
              refreshTrigger={attachmentsRefresh} />
          </div>
        )}
      </div>
    </div>
  )
}
