import { useState } from 'react'
import { masterdataApi, zeiterfassungApi } from '../services/api'
import toast from 'react-hot-toast'
import DynamicForm from './DynamicForm'
import AttachmentPanel from './AttachmentPanel'
import StundenkontenPanel from './StundenkontenPanel'
import { X, Loader2, Database } from 'lucide-react'

/**
 * Generisches Anlege-/Bearbeiten-Modal für Stammdaten-Datensätze.
 * Aus MasterDataDetail ausgelagert, damit es auch aus anderen Modulen
 * (z.B. Zeiterfassung: unbekannte Projektzeit direkt anlegen) nutzbar ist.
 *
 * initialValues: Vorbefüllung beim Neuanlegen (z.B. eingegebener Projektzeitname).
 */
export default function RecordModal({ entityType, record, onClose, onSaved, initialValues = null }) {
  const isEdit = !!record
  const isProjektzeit = entityType.slug === 'projektzeiten'
  const [values, setValues] = useState(record?.data || initialValues || {})
  const [loading, setLoading] = useState(false)
  // Beim Neuanlegen einer Projektzeit: hier erfasste Stundenkonten werden
  // nach dem Anlegen des Datensatzes gespeichert (brauchen die Datensatz-ID).
  const [pendingKonten, setPendingKonten] = useState([])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      let res
      if (isEdit) {
        res = await masterdataApi.updateRecord(entityType.slug, record.id, values)
        toast.success('Datensatz aktualisiert')
      } else {
        res = await masterdataApi.createRecord(entityType.slug, values)
        // Vorerfasste Stundenkonten jetzt zur neuen Projektzeit speichern
        let kontenFehler = 0
        for (const k of pendingKonten) {
          try {
            await zeiterfassungApi.createStundenkonto(res.data.id, {
              bezeichnung: k.bezeichnung, stunden: k.stunden,
              preis: k.preis, erworben_am: k.erworben_am,
            })
          } catch { kontenFehler += 1 }
        }
        if (kontenFehler > 0) {
          toast.error(`${kontenFehler} Stundenkonto/-konten konnten nicht gespeichert werden`)
        }
        toast.success('Datensatz angelegt')
      }
      onSaved(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center p-4 overflow-y-auto">
      <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-2xl my-4">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-900">
            {isEdit ? 'Datensatz bearbeiten' : `Neuen ${entityType.name.replace(/en$/, '').replace(/s$/, '')} anlegen`}
          </h2>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition">
            <X size={20} />
          </button>
        </div>

        {/* Formular */}
        <form onSubmit={handleSubmit}>
          <div className="p-5">
            {entityType.fields.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <Database size={32} className="mx-auto mb-2 text-gray-200" />
                <p className="text-sm">Noch keine Felder definiert.</p>
                <p className="text-sm">Klicken Sie auf „Felder verwalten" um Felder hinzuzufügen.</p>
              </div>
            ) : (
              <DynamicForm
                fields={entityType.fields}
                tabs={entityType.tabs || []}
                values={values}
                onChange={setValues}
              />
            )}
          </div>

          <div className="flex gap-3 p-5 border-t border-gray-100">
            <button type="button" onClick={onClose}
              className="flex-1 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition">
              Abbrechen
            </button>
            <button type="submit" disabled={loading || entityType.fields.length === 0}
              className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2">
              {loading ? <Loader2 size={16} className="animate-spin" /> : null}
              {isEdit ? 'Speichern' : 'Anlegen'}
            </button>
          </div>
        </form>

        {/* Stundenkonten (Budget) – bei Projektzeiten in beiden Modi:
            beim Bearbeiten direkt über die API, beim Neuanlegen lokal
            gesammelt und mit dem Datensatz gespeichert. */}
        {isProjektzeit && (
          <div className="px-5 pb-2 border-t border-gray-100">
            {isEdit ? (
              <StundenkontenPanel projectId={record.id} />
            ) : (
              <StundenkontenPanel pending={pendingKonten} onPendingChange={setPendingKonten} />
            )}
          </div>
        )}

        {/* Anhänge – nur bei bestehenden Datensätzen */}
        {isEdit && (
          <div className="px-5 pb-5 border-t border-gray-100 mt-4">
            <AttachmentPanel entityType={entityType.slug} entityId={record.id} />
          </div>
        )}
      </div>
    </div>
  )
}
