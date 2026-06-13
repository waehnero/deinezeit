import { useState, useEffect, useRef } from 'react'
import { Link, Camera, Upload, Loader2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { datacenterApi } from '../services/api'
import { AddLinkDialog } from './AttachmentExplorer'

// Schnellzugriff-Leiste für Anhänge: Cloud-Link, Foto aufnehmen, Hochladen.
// Kann auch verwendet werden, bevor ein Eintrag gespeichert wurde:
// dazu `onEnsureEntity` übergeben - eine async Funktion, die bei Bedarf
// validiert, speichert und die entityId zurückgibt (oder null bei Abbruch).
export default function AttachmentQuickBar({ entityType, entityId, onEnsureEntity, onUploaded, className = '' }) {
  const [providers, setProviders] = useState([])
  const [showAddLink, setShowAddLink] = useState(false)
  const [linkEntityId, setLinkEntityId] = useState(null)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)

  useEffect(() => {
    datacenterApi.getProviders().then(r => setProviders(r.data.providers || [])).catch(() => {})
  }, [])

  const ensureId = async () => {
    if (entityId) return entityId
    if (!onEnsureEntity) return null
    return await onEnsureEntity()
  }

  const handleUpload = async (files) => {
    if (!files || files.length === 0) return
    const id = await ensureId()
    if (!id) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        await datacenterApi.upload(entityType, id, file)
      }
      toast.success(files.length > 1 ? 'Dateien hochgeladen' : 'Datei hochgeladen')
      onUploaded?.(id)
    } catch {
      toast.error('Fehler beim Hochladen')
    } finally {
      setUploading(false)
    }
  }

  const openCloudLink = async () => {
    const id = await ensureId()
    if (!id) return
    setLinkEntityId(id)
    setShowAddLink(true)
  }

  return (
    <>
      <div className={`flex items-center flex-wrap gap-2 ${className}`}>
        <button type="button" onClick={openCloudLink} disabled={uploading} title="Cloud-Link"
          className="flex items-center gap-1.5 px-2.5 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50">
          <Link size={14} /> <span className="hidden sm:inline">Cloud-Link</span>
        </button>
        <button type="button" onClick={() => cameraInputRef.current?.click()} disabled={uploading} title="Foto aufnehmen"
          className="flex items-center gap-1.5 px-2.5 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50">
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />} <span className="hidden sm:inline">Foto aufnehmen</span>
        </button>
        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading} title="Hochladen"
          className="flex items-center gap-1.5 px-2.5 py-2 text-sm text-white bg-primary-500 hover:bg-primary-600 rounded-lg transition-colors disabled:opacity-50">
          {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />} <span className="hidden sm:inline">Hochladen</span>
        </button>
      </div>

      <input ref={fileInputRef} type="file" multiple className="hidden"
        onChange={e => { handleUpload(e.target.files); e.target.value = '' }} />
      <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" className="hidden"
        onChange={e => { handleUpload(e.target.files); e.target.value = '' }} />

      {showAddLink && (
        <AddLinkDialog entityType={entityType} entityId={linkEntityId} providers={providers}
          onClose={() => setShowAddLink(false)}
          onAdded={() => { setShowAddLink(false); toast.success('Link hinzugefügt'); onUploaded?.(linkEntityId) }} />
      )}
    </>
  )
}
