import { useState, useEffect, useCallback, useRef } from 'react'
import {
  HardDrive, FolderOpen, Folder, File, FileText, FileImage, FileVideo,
  FileArchive, Link2, Upload, Search, Download, Trash2, Share2, Eye,
  ChevronRight, ChevronDown, Loader2, X, ExternalLink, Copy, Check,
  RefreshCw, Info, Clock, Ban, CalendarClock
} from 'lucide-react'
import { datacenterApi } from '../services/api'
import toast from 'react-hot-toast'

// ── Hilfsfunktionen ──────────────────────────────────────────────────────────

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('de-AT', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  })
}

function FileIcon({ mimetype, type, size = 18 }) {
  if (type === 'link') return <Link2 size={size} className="text-blue-500" />
  if (!mimetype) return <File size={size} className="text-gray-400" />
  if (mimetype.startsWith('image/'))       return <FileImage size={size} className="text-green-500" />
  if (mimetype.startsWith('video/'))       return <FileVideo size={size} className="text-purple-500" />
  if (mimetype.startsWith('text/') || mimetype.includes('pdf'))
                                           return <FileText size={size} className="text-orange-500" />
  if (mimetype.includes('zip') || mimetype.includes('archive') || mimetype.includes('compressed'))
                                           return <FileArchive size={size} className="text-yellow-600" />
  return <File size={size} className="text-gray-400" />
}

// Bekannte Entity-Typen mit Labels
const ENTITY_LABELS = {
  zeiterfassung: 'Zeiterfassung',
  kontakte:      'Kontakte',
  projekte:      'Projekte',
  aufgaben:      'Aufgaben',
}
function entityLabel(slug) {
  return ENTITY_LABELS[slug] || slug.charAt(0).toUpperCase() + slug.slice(1)
}

// ── ShareDialog ──────────────────────────────────────────────────────────────

function ShareDialog({ attachment, onClose }) {
  const [loading, setLoading]   = useState(false)
  const [shareUrl, setShareUrl] = useState(attachment.share_token
    ? `${window.location.origin}/share/${attachment.share_token}` : null)
  const [copied, setCopied]     = useState(false)
  const [days, setDays]         = useState(7)

  const createLink = async () => {
    setLoading(true)
    try {
      const res = await datacenterApi.createShareLink(attachment.id, days * 24)
      // Backend gibt share_url zurück (volle URL)
      setShareUrl(res.data.share_url)
      toast.success('Share-Link erstellt')
    } catch {
      toast.error('Fehler beim Erstellen des Share-Links')
    } finally {
      setLoading(false)
    }
  }

  const deleteLink = async () => {
    setLoading(true)
    try {
      await datacenterApi.deleteShareLink(attachment.id)
      setShareUrl(null)
      toast.success('Share-Link gelöscht')
    } catch {
      toast.error('Fehler beim Löschen des Share-Links')
    } finally {
      setLoading(false)
    }
  }

  const copy = () => {
    navigator.clipboard.writeText(shareUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-[70] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h3 className="font-bold text-gray-900">Share-Link</h3>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400">
            <X size={18} />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-gray-600">
            Erstelle einen öffentlichen Download-Link für <strong>{attachment.display_name || attachment.filename}</strong>.
          </p>

          {shareUrl ? (
            <div className="space-y-3">
              <div className="flex gap-2">
                <input readOnly value={shareUrl}
                  className="flex-1 text-xs border border-gray-200 rounded-lg px-3 py-2 bg-gray-50 text-gray-700 font-mono" />
                <button onClick={copy}
                  className="px-3 py-2 border border-gray-200 rounded-lg hover:bg-gray-50 text-gray-600 transition">
                  {copied ? <Check size={15} className="text-green-500" /> : <Copy size={15} />}
                </button>
              </div>
              <button onClick={deleteLink} disabled={loading}
                className="w-full py-2 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition">
                Link deaktivieren
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <label className="text-sm text-gray-600 whitespace-nowrap">Gültig für</label>
                <select value={days} onChange={e => setDays(Number(e.target.value))}
                  className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-700">
                  <option value={1}>1 Tag</option>
                  <option value={7}>7 Tage</option>
                  <option value={30}>30 Tage</option>
                  <option value={90}>90 Tage</option>
                </select>
              </div>
              <button onClick={createLink} disabled={loading}
                className="w-full py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition flex items-center justify-center gap-2">
                {loading ? <Loader2 size={15} className="animate-spin" /> : <Share2 size={15} />}
                Link erstellen
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── ExtendDialog ─────────────────────────────────────────────────────────────

function ExtendDialog({ attachment, onClose, onExtended }) {
  const [loading, setLoading] = useState(false)
  const [days, setDays]       = useState(7)

  const extend = async () => {
    setLoading(true)
    try {
      await datacenterApi.extendShareLink(attachment.id, days * 24)
      toast.success('Freigabe verlängert')
      onExtended()
      onClose()
    } catch {
      toast.error('Verlängern fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-[70] flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm">
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h3 className="font-bold text-gray-900">Freigabe verlängern</h3>
          <button onClick={onClose} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400">
            <X size={18} />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-gray-600 truncate">
            <strong>{attachment.display_name || attachment.filename}</strong>
          </p>
          <div className="flex items-center gap-3">
            <label className="text-sm text-gray-600 whitespace-nowrap">Verlängern um</label>
            <select value={days} onChange={e => setDays(Number(e.target.value))}
              className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm text-gray-700 flex-1">
              <option value={1}>1 Tag</option>
              <option value={7}>7 Tage</option>
              <option value={30}>30 Tage</option>
              <option value={90}>90 Tage</option>
              <option value={0}>Unbegrenzt</option>
            </select>
          </div>
          <button onClick={extend} disabled={loading}
            className="w-full py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg transition flex items-center justify-center gap-2">
            {loading ? <Loader2 size={15} className="animate-spin" /> : <CalendarClock size={15} />}
            Verlängern
          </button>
        </div>
      </div>
    </div>
  )
}

// ── SharedFileRow ─────────────────────────────────────────────────────────────

function SharedFileRow({ attachment, onRevoke, onExtend, onCopy }) {
  const [confirmRevoke, setConfirmRevoke] = useState(false)

  const isExpired = attachment.share_expires_at &&
    new Date(attachment.share_expires_at) < new Date()

  const expiresLabel = () => {
    if (!attachment.share_expires_at) return 'Unbegrenzt'
    const d = new Date(attachment.share_expires_at)
    const diff = d - new Date()
    if (diff < 0) return <span className="text-red-500">Abgelaufen</span>
    const days = Math.ceil(diff / (1000 * 60 * 60 * 24))
    if (days === 1) return <span className="text-orange-500">Läuft heute ab</span>
    if (days <= 3) return <span className="text-orange-400">Noch {days} Tage</span>
    return `Noch ${days} Tage`
  }

  return (
    <tr className={`hover:bg-gray-50 transition group ${isExpired ? 'opacity-60' : ''}`}>
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <FileIcon mimetype={attachment.mimetype} type={attachment.type} size={17} />
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate max-w-xs">
              {attachment.display_name || attachment.filename}
            </p>
            <p className="text-xs text-gray-400">
              <span className="px-1.5 py-0.5 rounded-full bg-gray-100">{entityLabel(attachment.entity_type)}</span>
            </p>
          </div>
        </div>
      </td>
      <td className="px-4 py-3 text-xs hidden md:table-cell">
        <div className="flex items-center gap-1.5">
          <Clock size={12} className="text-gray-400" />
          <span className="text-gray-600">{expiresLabel()}</span>
        </div>
        {attachment.share_expires_at && (
          <p className="text-gray-400 mt-0.5">
            {new Date(attachment.share_expires_at).toLocaleDateString('de-AT', {
              day: '2-digit', month: '2-digit', year: 'numeric'
            })}
          </p>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-gray-400 hidden lg:table-cell">
        {formatBytes(attachment.filesize)}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition">
          <button onClick={() => onCopy(attachment)} title="Link kopieren"
            className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition">
            <Copy size={14} />
          </button>
          <button onClick={() => onExtend(attachment)} title="Verlängern"
            className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition">
            <CalendarClock size={14} />
          </button>
          <button
            onClick={() => { if (confirmRevoke) onRevoke(attachment); else setConfirmRevoke(true) }}
            onBlur={() => setTimeout(() => setConfirmRevoke(false), 200)}
            title={confirmRevoke ? 'Nochmal klicken' : 'Freigabe widerrufen'}
            className={`p-1.5 rounded-lg transition ${
              confirmRevoke ? 'bg-red-100 text-red-600' : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
            }`}>
            <Ban size={14} />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── PreviewModal ─────────────────────────────────────────────────────────────

function PreviewModal({ attachment, onClose }) {
  const [url, setUrl]         = useState(null)
  const [loading, setLoading] = useState(true)
  const [isEml, setIsEml]     = useState(false)

  useEffect(() => {
    const fn = (attachment.filename || '').toLowerCase()
    const eml = attachment.mimetype === 'message/rfc822' ||
                attachment.mimetype === 'text/rfc822' ||
                attachment.mimetype === 'application/vnd.ms-outlook' ||
                fn.endsWith('.eml') ||
                fn.endsWith('.msg')
    setIsEml(eml)

    // Für EML/MSG liefert das Backend fertig gerendertes HTML (text) zurück
    const responseType = eml ? 'text' : 'blob'
    datacenterApi.previewRaw(attachment.id, responseType)
      .then(res => {
        const blob = eml
          ? new Blob([res.data], { type: 'text/html' })
          : new Blob([res.data], { type: attachment.mimetype || 'application/octet-stream' })
        setUrl(URL.createObjectURL(blob))
      })
      .catch(() => toast.error('Vorschau nicht verfügbar'))
      .finally(() => setLoading(false))
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [attachment.id])

  const isImage = attachment.mimetype?.startsWith('image/')
  const isPdf   = attachment.mimetype === 'application/pdf'

  return (
    <div className="fixed inset-0 bg-black/80 z-[70] flex flex-col">
      <div className="flex items-center justify-between px-5 py-3 bg-black/60 text-white">
        <span className="text-sm font-medium truncate">{attachment.display_name || attachment.filename}</span>
        <button onClick={onClose} className="p-1.5 hover:bg-white/20 rounded-lg transition">
          <X size={20} />
        </button>
      </div>
      <div className="flex-1 flex items-center justify-center p-4 overflow-hidden">
        {loading ? (
          <Loader2 size={32} className="animate-spin text-white" />
        ) : url ? (
          isImage ? (
            <img src={url} alt={attachment.filename} className="max-h-full max-w-full object-contain rounded-lg shadow-2xl" />
          ) : isPdf || isEml ? (
            <iframe src={url} className="w-full h-full rounded-lg bg-white" title={attachment.filename} />
          ) : (
            <div className="text-white text-center">
              <File size={48} className="mx-auto mb-3 text-gray-400" />
              <p>Vorschau nicht verfügbar für diesen Dateityp.</p>
              <a href={url} target="_blank" rel="noopener noreferrer"
                className="mt-3 inline-block text-primary-400 hover:underline text-sm">
                Datei herunterladen
              </a>
            </div>
          )
        ) : (
          <p className="text-white">Vorschau konnte nicht geladen werden.</p>
        )}
      </div>
    </div>
  )
}

// ── Ordnerbaum ───────────────────────────────────────────────────────────────

function FolderTree({ folders, selected, onSelect }) {
  const [expanded, setExpanded] = useState({})

  const toggle = (key) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  const isShared = selected === 'shared'

  return (
    <nav className="space-y-0.5">
      {/* Alle Dateien */}
      <button
        onClick={() => onSelect(null)}
        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition ${
          selected === null ? 'bg-primary-50 text-primary-700 font-medium' : 'text-gray-700 hover:bg-gray-100'
        }`}
      >
        <HardDrive size={15} className={selected === null ? 'text-primary-600' : 'text-gray-400'} />
        <span>Alle Dateien</span>
        <span className="ml-auto text-xs text-gray-400">{folders.total}</span>
      </button>

      {/* Freigaben */}
      <button
        onClick={() => onSelect('shared')}
        className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition ${
          isShared ? 'bg-green-50 text-green-700 font-medium' : 'text-gray-700 hover:bg-gray-100'
        }`}
      >
        <Share2 size={15} className={isShared ? 'text-green-600' : 'text-gray-400'} />
        <span>Freigaben</span>
        {folders.sharedCount > 0 && (
          <span className="ml-auto text-xs text-gray-400">{folders.sharedCount}</span>
        )}
      </button>

      {/* Entity-Typen */}
      {folders.types?.map(type => {
        const isExpanded = expanded[type.slug]
        const isTypeSelected = selected?.type === type.slug && !selected?.entityId
        return (
          <div key={type.slug}>
            <button
              onClick={() => {
                toggle(type.slug)
                onSelect({ type: type.slug })
              }}
              className={`w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition ${
                isTypeSelected ? 'bg-primary-50 text-primary-700 font-medium' : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              {isExpanded
                ? <ChevronDown size={13} className="text-gray-400 flex-shrink-0" />
                : <ChevronRight size={13} className="text-gray-400 flex-shrink-0" />
              }
              {isExpanded
                ? <FolderOpen size={15} className={isTypeSelected ? 'text-primary-600' : 'text-amber-500'} />
                : <Folder size={15} className={isTypeSelected ? 'text-primary-600' : 'text-amber-500'} />
              }
              <span className="truncate">{entityLabel(type.slug)}</span>
              <span className="ml-auto text-xs text-gray-400 flex-shrink-0">{type.count}</span>
            </button>

            {isExpanded && type.entities?.length > 0 && (
              <div className="ml-4 space-y-0.5 border-l border-gray-100 pl-2 mt-0.5 mb-1">
                {type.entities.map(entity => {
                  const isEntitySelected = selected?.type === type.slug && selected?.entityId === entity.id
                  return (
                    <button
                      key={entity.id}
                      onClick={() => onSelect({ type: type.slug, entityId: entity.id })}
                      className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition ${
                        isEntitySelected ? 'bg-primary-50 text-primary-700 font-medium' : 'text-gray-600 hover:bg-gray-100'
                      }`}
                    >
                      <Folder size={13} className={isEntitySelected ? 'text-primary-500' : 'text-gray-300'} />
                      <span className="truncate">{entity.label || entity.id}</span>
                      <span className="ml-auto text-gray-400">{entity.count}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </nav>
  )
}

// ── Datei-Zeile ──────────────────────────────────────────────────────────────

function FileRow({ attachment, onPreview, onDownload, onShare, onDelete }) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const _fn = (attachment.filename || '').toLowerCase()
  const canPreview = attachment.type === 'file' && (
    attachment.mimetype?.startsWith('image/') ||
    attachment.mimetype === 'application/pdf' ||
    attachment.mimetype?.startsWith('text/') ||
    attachment.mimetype === 'message/rfc822' ||
    attachment.mimetype === 'text/rfc822' ||
    attachment.mimetype === 'application/vnd.ms-outlook' ||
    _fn.endsWith('.eml') ||
    _fn.endsWith('.msg')
  )

  return (
    <tr className="hover:bg-gray-50 transition group">
      <td className="px-4 py-3">
        <div className="flex items-center gap-3">
          <FileIcon mimetype={attachment.mimetype} type={attachment.type} size={17} />
          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate max-w-xs">
              {attachment.display_name || attachment.filename || attachment.link_url}
            </p>
            {attachment.description && (
              <p className="text-xs text-gray-400 truncate">{attachment.description}</p>
            )}
          </div>
        </div>
      </td>
      <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap hidden md:table-cell">
        <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
          {entityLabel(attachment.entity_type)}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap hidden lg:table-cell">
        {attachment.type === 'file' ? formatBytes(attachment.filesize) : (
          <span className="flex items-center gap-1">
            <Link2 size={12} className="text-blue-400" />
            {attachment.link_provider || 'Link'}
          </span>
        )}
      </td>
      <td className="px-4 py-3 text-xs text-gray-400 whitespace-nowrap hidden xl:table-cell">
        {formatDate(attachment.created_at)}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition">
          {canPreview && (
            <button onClick={() => onPreview(attachment)} title="Vorschau"
              className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
              <Eye size={14} />
            </button>
          )}
          {attachment.type === 'file' && (
            <button onClick={() => onDownload(attachment)} title="Herunterladen"
              className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
              <Download size={14} />
            </button>
          )}
          {attachment.type === 'link' && (
            <a href={attachment.link_url} target="_blank" rel="noopener noreferrer" title="Öffnen"
              className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition">
              <ExternalLink size={14} />
            </a>
          )}
          {attachment.type === 'file' && (
            <button onClick={() => onShare(attachment)} title="Teilen"
              className="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-lg transition">
              <Share2 size={14} />
            </button>
          )}
          <button
            onClick={() => { if (confirmDelete) onDelete(attachment); else setConfirmDelete(true) }}
            onBlur={() => setTimeout(() => setConfirmDelete(false), 200)}
            title={confirmDelete ? 'Nochmal klicken' : 'Löschen'}
            className={`p-1.5 rounded-lg transition ${
              confirmDelete ? 'bg-red-100 text-red-600' : 'text-gray-400 hover:text-red-500 hover:bg-red-50'
            }`}>
            <Trash2 size={14} />
          </button>
        </div>
      </td>
    </tr>
  )
}

// ── Upload-Zone ──────────────────────────────────────────────────────────────

function UploadZone({ onUpload, disabled }) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  const handleDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    if (disabled) return
    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) onUpload(files)
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`border-2 border-dashed rounded-xl p-6 text-center transition ${
        dragging ? 'border-primary-400 bg-primary-50' : 'border-gray-200 bg-gray-50 hover:border-gray-300'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
      onClick={() => !disabled && inputRef.current?.click()}
    >
      <Upload size={24} className="mx-auto mb-2 text-gray-300" />
      <p className="text-sm text-gray-500">
        {disabled
          ? 'Bitte zuerst einen Ordner auswählen'
          : 'Dateien hierher ziehen oder klicken zum Hochladen'
        }
      </p>
      <input ref={inputRef} type="file" multiple className="hidden"
        onChange={e => { const files = Array.from(e.target.files); if (files.length) onUpload(files) }} />
    </div>
  )
}

// ── Hauptseite ────────────────────────────────────────────────────────────────

export default function DatacenterPage() {
  const [folders, setFolders]         = useState({ total: 0, types: [] })
  const [foldersLoading, setFoldersLoading] = useState(true)
  const [selected, setSelected]       = useState(null)   // null = alle, { type, entityId? }
  const [attachments, setAttachments] = useState([])
  const [listLoading, setListLoading] = useState(false)
  const [search, setSearch]           = useState('')
  const [uploading, setUploading]     = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [previewItem, setPreviewItem] = useState(null)
  const [shareItem, setShareItem]     = useState(null)
  const [extendItem, setExtendItem]   = useState(null)

  // Ordnerbaum laden
  const loadFolders = useCallback(async () => {
    setFoldersLoading(true)
    try {
      // Alle Anhänge laden und aggregieren
      const res = await datacenterApi.listAll()
      const all = res.data.attachments || []

      // Typen gruppieren
      const typeMap = {}
      all.forEach(a => {
        if (!typeMap[a.entity_type]) typeMap[a.entity_type] = { slug: a.entity_type, count: 0, entityMap: {} }
        typeMap[a.entity_type].count++
        if (!typeMap[a.entity_type].entityMap[a.entity_id]) {
          // entity_label vom Backend nutzen (sprechender Name statt UUID)
          typeMap[a.entity_type].entityMap[a.entity_id] = {
            id: a.entity_id,
            label: a.entity_label || a.entity_id,
            count: 0
          }
        }
        typeMap[a.entity_type].entityMap[a.entity_id].count++
      })

      const types = Object.values(typeMap).map(t => ({
        ...t,
        entities: Object.values(t.entityMap)
      }))

      const sharedCount = all.filter(a => a.has_share_link).length
      setFolders({ total: all.length, types, sharedCount })
    } catch {
      toast.error('Ordnerstruktur konnte nicht geladen werden')
    } finally {
      setFoldersLoading(false)
    }
  }, [])

  // Dateiliste laden
  const loadAttachments = useCallback(async () => {
    setListLoading(true)
    try {
      const entityType = (selected && selected !== 'shared') ? selected.type : null
      const entityId   = (selected && selected !== 'shared') ? selected.entityId : null
      const res = await datacenterApi.listAll(entityType, entityId)
      let items = res.data.attachments || []
      if (selected === 'shared') {
        items = items.filter(a => a.has_share_link)
      }
      if (search) {
        const q = search.toLowerCase()
        items = items.filter(a =>
          (a.display_name || '').toLowerCase().includes(q) ||
          (a.filename || '').toLowerCase().includes(q) ||
          (a.link_url || '').toLowerCase().includes(q) ||
          (a.description || '').toLowerCase().includes(q)
        )
      }
      setAttachments(items)
    } catch {
      toast.error('Dateien konnten nicht geladen werden')
    } finally {
      setListLoading(false)
    }
  }, [selected, search])

  useEffect(() => { loadFolders() }, [loadFolders])
  useEffect(() => { loadAttachments() }, [loadAttachments])

  const handleUpload = async (files) => {
    if (!selected?.type) {
      toast.error('Bitte zuerst einen Ordner (Entity-Typ) auswählen')
      return
    }
    const entityId = selected.entityId || 'global'
    setUploading(true)
    try {
      for (const file of files) {
        await datacenterApi.upload(selected.type, entityId, file, (pct) => setUploadProgress(pct))
      }
      toast.success(`${files.length} Datei${files.length > 1 ? 'en' : ''} hochgeladen`)
      await Promise.all([loadFolders(), loadAttachments()])
    } catch {
      toast.error('Upload fehlgeschlagen')
    } finally {
      setUploading(false)
      setUploadProgress(0)
    }
  }

  const handleDownload = async (attachment) => {
    try {
      const res = await datacenterApi.download(attachment.id)
      const blob = new Blob([res.data])
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url
      a.download = attachment.filename
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch {
      toast.error('Download fehlgeschlagen')
    }
  }

  const handleDelete = async (attachment) => {
    try {
      await datacenterApi.delete(attachment.id)
      toast.success('Gelöscht')
      await Promise.all([loadFolders(), loadAttachments()])
    } catch {
      toast.error('Löschen fehlgeschlagen')
    }
  }

  const handleRevokeShare = async (attachment) => {
    try {
      await datacenterApi.deleteShareLink(attachment.id)
      toast.success('Freigabe widerrufen')
      await Promise.all([loadFolders(), loadAttachments()])
    } catch {
      toast.error('Widerrufen fehlgeschlagen')
    }
  }

  const handleCopyShareLink = (attachment) => {
    const base = window.location.origin
    const url  = `${base}/api/datacenter/share/${attachment.share_token || ''}`
    navigator.clipboard.writeText(url)
    toast.success('Link kopiert')
  }

  // Statistik
  const totalSize = attachments.filter(a => a.type === 'file').reduce((s, a) => s + (a.filesize || 0), 0)
  const fileCount = attachments.filter(a => a.type === 'file').length
  const linkCount = attachments.filter(a => a.type === 'link').length

  // Titel der aktuellen Auswahl
  const currentEntityLabel = selected?.entityId
    ? folders.types?.find(t => t.slug === selected.type)
        ?.entities?.find(e => e.id === selected.entityId)?.label
      || selected.entityId
    : null

  const currentTitle = selected === null
    ? 'Alle Dateien'
    : selected === 'shared'
      ? 'Freigaben'
      : selected.entityId
        ? `${entityLabel(selected.type)} / ${currentEntityLabel}`
        : entityLabel(selected.type)

  return (
    <div className="flex h-full overflow-hidden -m-6">
      {/* ── Sidebar ───────────────────────────────────────────────────────── */}
      <aside className="w-56 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col overflow-hidden">
        <div className="px-4 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <HardDrive size={17} className="text-primary-600" />
            <h2 className="font-bold text-gray-900 text-sm">Datacenter</h2>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">Dateien & Links</p>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-3">
          {foldersLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 size={20} className="animate-spin text-gray-300" />
            </div>
          ) : (
            <FolderTree folders={folders} selected={selected} onSelect={setSelected} />
          )}
        </div>

        {/* Speicherinfo */}
        <div className="px-4 py-3 border-t border-gray-100 bg-gray-50">
          <div className="flex items-center gap-1.5 text-xs text-gray-400">
            <Info size={12} />
            <span>{folders.total} Dateien gesamt</span>
          </div>
        </div>
      </aside>

      {/* ── Hauptbereich ──────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col overflow-hidden bg-gray-50">
        {/* Toolbar */}
        <div className="bg-white border-b border-gray-200 px-5 py-3 flex items-center gap-3 flex-shrink-0">
          <div className="flex-1">
            <h3 className="font-semibold text-gray-900 text-sm">{currentTitle}</h3>
            <p className="text-xs text-gray-400">
              {fileCount} {fileCount === 1 ? 'Datei' : 'Dateien'}
              {linkCount > 0 && ` · ${linkCount} Links`}
              {fileCount > 0 && ` · ${formatBytes(totalSize)}`}
            </p>
          </div>
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text" value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Suchen…"
              className="pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 w-48"
            />
          </div>
          <button onClick={() => { loadFolders(); loadAttachments() }}
            className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition" title="Aktualisieren">
            <RefreshCw size={15} />
          </button>
        </div>

        {/* Upload-Zone (nur wenn Ordner ausgewählt, nicht in Freigaben-Ansicht) */}
        {selected?.type && selected !== 'shared' && (
          <div className="px-5 pt-4 flex-shrink-0">
            {uploading ? (
              <div className="border-2 border-dashed border-primary-300 rounded-xl p-5 bg-primary-50">
                <div className="flex items-center gap-3">
                  <Loader2 size={20} className="animate-spin text-primary-500" />
                  <div className="flex-1">
                    <p className="text-sm text-primary-700 font-medium">Wird hochgeladen…</p>
                    <div className="mt-1.5 h-1.5 bg-primary-200 rounded-full overflow-hidden">
                      <div className="h-full bg-primary-500 transition-all duration-300 rounded-full"
                        style={{ width: `${uploadProgress}%` }} />
                    </div>
                  </div>
                  <span className="text-sm font-medium text-primary-700">{uploadProgress}%</span>
                </div>
              </div>
            ) : (
              <UploadZone onUpload={handleUpload} disabled={!selected?.type} />
            )}
          </div>
        )}

        {/* Dateiliste */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {listLoading ? (
            <div className="flex items-center justify-center h-40">
              <Loader2 size={28} className="animate-spin text-gray-300" />
            </div>
          ) : attachments.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-40 text-gray-400">
              <HardDrive size={36} className="mb-3 text-gray-200" />
              <p className="text-sm font-medium">
                {search ? 'Keine Ergebnisse' : selected === 'shared' ? 'Keine aktiven Freigaben' : 'Keine Dateien vorhanden'}
              </p>
            </div>
          ) : selected === 'shared' ? (
            <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Datei</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide hidden md:table-cell">Läuft ab</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide hidden lg:table-cell">Größe</th>
                    <th className="px-4 py-2.5 w-28"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {attachments.map(a => (
                    <SharedFileRow
                      key={a.id}
                      attachment={a}
                      onRevoke={handleRevokeShare}
                      onExtend={setExtendItem}
                      onCopy={handleCopyShareLink}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-100 bg-gray-50">
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide">Name</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide hidden md:table-cell">Bereich</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide hidden lg:table-cell">Größe / Typ</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide hidden xl:table-cell">Erstellt</th>
                    <th className="px-4 py-2.5 w-28"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {attachments.map(a => (
                    <FileRow
                      key={a.id}
                      attachment={a}
                      onPreview={setPreviewItem}
                      onDownload={handleDownload}
                      onShare={setShareItem}
                      onDelete={handleDelete}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Modals */}
      {previewItem && <PreviewModal attachment={previewItem} onClose={() => setPreviewItem(null)} />}
      {shareItem   && <ShareDialog  attachment={shareItem}   onClose={() => setShareItem(null)} />}
      {extendItem  && (
        <ExtendDialog
          attachment={extendItem}
          onClose={() => setExtendItem(null)}
          onExtended={() => { loadFolders(); loadAttachments() }}
        />
      )}
    </div>
  )
}
