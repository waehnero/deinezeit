import { useState, useEffect, useCallback } from 'react'
import { Paperclip, FolderOpen, Loader2 } from 'lucide-react'
import { datacenterApi } from '../services/api'
import AttachmentExplorer from './AttachmentExplorer'

// Kompakte Anzeige im Datensatz-Dialog:
// Zeigt nur Badge mit Anzahl + Button zum Öffnen des Explorers
export default function AttachmentPanel({ entityType, entityId }) {
  const [count, setCount]       = useState(null)   // null = noch nicht geladen
  const [loading, setLoading]   = useState(true)
  const [showExplorer, setShowExplorer] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await datacenterApi.list(entityType, entityId)
      setCount((r.data.attachments || []).length)
    } catch {
      setCount(0)
    } finally {
      setLoading(false)
    }
  }, [entityType, entityId])

  useEffect(() => { load() }, [load])

  return (
    <>
      <div className="flex items-center justify-between py-3 border-t border-gray-100 mt-4">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <Paperclip size={15} className="text-primary-500" />
          <span className="font-medium">Anhänge</span>
          {loading ? (
            <Loader2 size={13} className="animate-spin text-gray-400" />
          ) : (
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
              count > 0 ? 'bg-primary-100 text-primary-700' : 'bg-gray-100 text-gray-400'
            }`}>
              {count === 0 ? 'Keine' : count}
            </span>
          )}
        </div>
        <button
          onClick={() => setShowExplorer(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 hover:border-primary-300 hover:text-primary-600 transition-colors"
        >
          <FolderOpen size={13} />
          Öffnen
        </button>
      </div>

      {showExplorer && (
        <AttachmentExplorer
          entityType={entityType}
          entityId={entityId}
          onClose={() => { setShowExplorer(false); load() }}
        />
      )}
    </>
  )
}
