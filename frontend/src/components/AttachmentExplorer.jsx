import { useState, useEffect, useRef, useCallback } from 'react'
import {
  X, Upload, Link, Download, Eye, Share2, Trash2,
  ExternalLink, File, FileText, Image, Film, Archive,
  Plus, Copy, Check, Clock, Cloud, Loader2, FolderOpen,
  Search, HardDrive, Camera
} from 'lucide-react'
import { datacenterApi } from '../services/api'

// ── Konstanten ────────────────────────────────────────────────────────────────
const PROVIDER_COLORS = {
  nextcloud:   'bg-blue-100 text-blue-700',
  onedrive:    'bg-blue-100 text-blue-800',
  googledrive: 'bg-yellow-100 text-yellow-700',
  icloud:      'bg-gray-100 text-gray-700',
  seadrive:    'bg-teal-100 text-teal-700',
  dropbox:     'bg-blue-100 text-blue-600',
  sharepoint:  'bg-orange-100 text-orange-700',
  custom:      'bg-gray-100 text-gray-600',
}

const PROVIDER_LABELS = {
  nextcloud: 'NextCloud', onedrive: 'OneDrive', googledrive: 'Google Drive',
  icloud: 'iCloud', seadrive: 'SeaDrive', dropbox: 'Dropbox',
  sharepoint: 'SharePoint', custom: 'Link',
}

function FileIcon({ mimetype, size = 18 }) {
  const cls = 'flex-shrink-0'
  if (!mimetype) return <File size={size} className={`${cls} text-gray-400`} />
  if (mimetype.startsWith('image/'))  return <Image   size={size} className={`${cls} text-green-500`} />
  if (mimetype.startsWith('video/'))  return <Film    size={size} className={`${cls} text-purple-500`} />
  if (mimetype === 'application/pdf') return <FileText size={size} className={`${cls} text-red-500`} />
  if (mimetype.includes('zip') || mimetype.includes('rar')) return <Archive size={size} className={`${cls} text-yellow-500`} />
  if (mimetype.includes('word') || mimetype.includes('document')) return <FileText size={size} className={`${cls} text-blue-500`} />
  if (mimetype.includes('sheet') || mimetype.includes('excel'))   return <FileText size={size} className={`${cls} text-green-600`} />
  return <File size={size} className={`${cls} text-gray-400`} />
}

function formatBytes(b) {
  if (!b) return ''
  if (b < 1024) return `${b} B`
  if (b < 1048576) return `${(b/1024).toFixed(1)} KB`
  return `${(b/1048576).toFixed(1)} MB`
}

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('de-AT', { day:'2-digit', month:'2-digit', year:'numeric' })
}

// ── Share-Link Dialog ─────────────────────────────────────────────────────────
function ShareDialog({ attachment, onClose }) {
  const [hours, setHours]     = useState(24)
  const [shareUrl, setShareUrl] = useState(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied]   = useState(false)

  const OPTS = [
    { label: '1 Stunde', value: 1 },
    { label: '8 Stunden', value: 8 },
    { label: '24 Stunden', value: 24 },
    { label: '7 Tage', value: 168 },
    { label: 'Unbegrenzt', value: 0 },
  ]

  const generate = async () => {
    setLoading(true)
    try {
      const r = await datacenterApi.createShareLink(attachment.id, hours)
      setShareUrl(r.data.share_url)
    } catch { alert('Fehler beim Erstellen des Links') }
    finally { setLoading(false) }
  }

  const copy = () => {
    navigator.clipboard.writeText(shareUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <Share2 size={16} className="text-primary-500" /> Download-Link erstellen
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <div className="p-4 space-y-4">
          <p className="text-sm text-gray-500">Datei: <span className="font-medium text-gray-800">{attachment.display_name}</span></p>
          {!shareUrl ? (
            <>
              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">Link gültig für</p>
                <div className="grid grid-cols-3 gap-2">
                  {OPTS.map(o => (
                    <button key={o.value} onClick={() => setHours(o.value)}
                      className={`px-3 py-2 rounded-lg text-sm border transition-colors ${hours === o.value ? 'bg-primary-500 text-white border-primary-500' : 'border-gray-200 text-gray-600 hover:border-primary-300'}`}>
                      {o.label}
                    </button>
                  ))}
                </div>
              </div>
              <button onClick={generate} disabled={loading}
                className="w-full bg-primary-500 hover:bg-primary-600 text-white rounded-lg px-4 py-2.5 font-medium flex items-center justify-center gap-2 transition-colors">
                {loading ? <Loader2 size={15} className="animate-spin" /> : <Share2 size={15} />}
                Link generieren
              </button>
            </>
          ) : (
            <>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-400 mb-1">Öffentlicher Download-Link:</p>
                <p className="text-sm text-gray-800 break-all font-mono text-xs">{shareUrl}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={copy}
                  className="flex-1 bg-primary-500 hover:bg-primary-600 text-white rounded-lg px-4 py-2.5 font-medium flex items-center justify-center gap-2 transition-colors">
                  {copied ? <Check size={15} /> : <Copy size={15} />}
                  {copied ? 'Kopiert!' : 'Link kopieren'}
                </button>
                <button onClick={() => setShareUrl(null)}
                  className="px-4 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50">
                  Neu
                </button>
              </div>
              {hours > 0 && (
                <p className="text-xs text-gray-400 flex items-center gap-1">
                  <Clock size={11} /> Läuft nach {hours < 24 ? `${hours}h` : `${hours/24} Tag(en)`} ab
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Link hinzufügen Dialog ────────────────────────────────────────────────────
export function AddLinkDialog({ entityType, entityId, providers, onClose, onAdded }) {
  const [form, setForm] = useState({ display_name: '', link_url: '', link_provider: 'custom', description: '' })
  const [loading, setLoading] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      const r = await datacenterApi.addLink({ ...form, entity_type: entityType, entity_id: entityId })
      onAdded(r.data)
    } catch { alert('Fehler beim Hinzufügen') }
    finally { setLoading(false) }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4">
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b border-gray-100">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <Link size={16} className="text-primary-500" /> Cloud-Link hinzufügen
          </h3>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={18} /></button>
        </div>
        <form onSubmit={submit} className="p-4 space-y-3">
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Anbieter</p>
            <div className="flex flex-wrap gap-2">
              {providers.map(p => (
                <button key={p.key} type="button" onClick={() => setForm(f => ({ ...f, link_provider: p.key }))}
                  className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${form.link_provider === p.key ? 'bg-primary-500 text-white border-primary-500' : 'border-gray-200 text-gray-600 hover:border-primary-300'}`}>
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Anzeigename *</label>
            <input required value={form.display_name} onChange={e => setForm(f => ({...f, display_name: e.target.value}))}
              placeholder="z.B. Projektdokumentation"
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-400" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">URL *</label>
            <input type="url" required value={form.link_url} onChange={e => setForm(f => ({...f, link_url: e.target.value}))}
              placeholder="https://..."
              className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-400" />
          </div>
          <div className="flex gap-2 pt-1">
            <button type="submit" disabled={loading}
              className="flex-1 bg-primary-500 hover:bg-primary-600 text-white rounded-lg px-4 py-2.5 font-medium flex items-center justify-center gap-2 transition-colors">
              {loading ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />}
              Hinzufügen
            </button>
            <button type="button" onClick={onClose}
              className="px-4 py-2.5 border border-gray-200 rounded-lg text-sm text-gray-600 hover:bg-gray-50">
              Abbrechen
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Vorschau Modal ────────────────────────────────────────────────────────────
function PreviewModal({ attachment, onClose }) {
  const [url, setUrl] = useState(null)
  const [textInhalt, setTextInhalt] = useState(null)

  // Textdateien (text/plain, text/markdown, …) direkt als Text anzeigen —
  // ein iframe mit unbekanntem Texttyp bleibt in den meisten Browsern leer.
  const istText = attachment.mimetype?.startsWith('text/')

  useEffect(() => {
    if (istText) {
      datacenterApi.previewRaw(attachment.id, 'text').then(r => {
        setTextInhalt(typeof r.data === 'string' ? r.data : String(r.data))
      }).catch(onClose)
      return
    }
    datacenterApi.preview(attachment.id).then(r => {
      setUrl(URL.createObjectURL(new Blob([r.data], { type: attachment.mimetype })))
    }).catch(onClose)
    return () => { if (url) URL.revokeObjectURL(url) }
  }, [attachment.id])

  return (
    // Safe-Area-Insets: am iPhone bleibt der Schließen-Button erreichbar
    <div className="fixed inset-x-0 top-0 bg-black/80 flex items-center justify-center z-[60] p-4"
      style={{
        height: '100dvh',
        paddingTop: 'calc(1rem + env(safe-area-inset-top))',
        paddingBottom: 'calc(1rem + env(safe-area-inset-bottom))',
      }}
      onClick={onClose}>
      <div className="bg-surface rounded-xl shadow-xl max-w-4xl w-full max-h-full overflow-hidden" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between p-3 border-b border-gray-100">
          <span className="font-medium text-gray-800 text-sm">{attachment.display_name}</span>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X size={20} /></button>
        </div>
        <div className="overflow-auto" style={{ maxHeight: 'calc(100dvh - 140px)' }}>
          {istText ? (
            textInhalt === null ? (
              <div className="flex items-center justify-center h-64"><Loader2 size={28} className="animate-spin text-primary-400" /></div>
            ) : (
              <pre className="whitespace-pre-wrap p-5 text-sm text-gray-800 font-sans leading-relaxed">{textInhalt}</pre>
            )
          ) : !url ? (
            <div className="flex items-center justify-center h-64"><Loader2 size={28} className="animate-spin text-primary-400" /></div>
          ) : attachment.mimetype?.startsWith('image/') ? (
            <img src={url} alt={attachment.display_name} className="max-w-full mx-auto block p-4" />
          ) : (
            <iframe src={url} className="w-full h-[80vh]" title={attachment.display_name} />
          )}
        </div>
      </div>
    </div>
  )
}

// ── Haupt-Explorer Komponente ─────────────────────────────────────────────────
// Kann als Modal (mit onClose) oder als Vollseite (ohne onClose) verwendet werden
export default function AttachmentExplorer({ entityType, entityId, onClose, fullPage = false }) {
  const [attachments, setAttachments]   = useState([])
  const [loading, setLoading]           = useState(true)
  const [providers, setProviders]       = useState([])
  const [search, setSearch]             = useState('')
  const [uploading, setUploading]       = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dragOver, setDragOver]         = useState(false)
  const [shareTarget, setShareTarget]   = useState(null)
  const [previewTarget, setPreviewTarget] = useState(null)
  const [showAddLink, setShowAddLink]   = useState(false)
  const fileInputRef = useRef(null)
  const cameraInputRef = useRef(null)

  const load = useCallback(async () => {
    if (!entityType || !entityId) return
    setLoading(true)
    try {
      const r = await datacenterApi.list(entityType, entityId)
      setAttachments(r.data.attachments || [])
    } catch { setAttachments([]) }
    finally { setLoading(false) }
  }, [entityType, entityId])

  useEffect(() => {
    load()
    datacenterApi.getProviders().then(r => setProviders(r.data.providers || []))
  }, [load])

  const filtered = attachments.filter(a =>
    !search || a.display_name.toLowerCase().includes(search.toLowerCase())
  )

  const handleUpload = async (files) => {
    for (const file of Array.from(files)) {
      setUploading(true)
      setUploadProgress(0)
      try {
        await datacenterApi.upload(entityType, entityId, file, e => {
          if (e.total) setUploadProgress(Math.round(e.loaded / e.total * 100))
        })
      } catch { alert(`Fehler beim Hochladen: ${file.name}`) }
    }
    setUploading(false)
    load()
  }

  const handleDownload = async (att) => {
    try {
      const r = await datacenterApi.download(att.id)
      const url = URL.createObjectURL(new Blob([r.data]))
      const a = document.createElement('a')
      a.href = url; a.download = att.filename || att.display_name; a.click()
      URL.revokeObjectURL(url)
    } catch { alert('Download fehlgeschlagen') }
  }

  const handleDelete = async (att) => {
    if (!confirm(`"${att.display_name}" wirklich löschen?`)) return
    await datacenterApi.delete(att.id)
    setAttachments(prev => prev.filter(a => a.id !== att.id))
  }

  const canPreview = (att) => att.type === 'file' && att.mimetype &&
    (att.mimetype.startsWith('image/') || att.mimetype === 'application/pdf' || att.mimetype.startsWith('text/'))

  const content = (
    <div className={`flex flex-col h-full ${fullPage ? '' : ''}`}>
      {/* Toolbar */}
      <div className="flex items-center gap-2 p-4 border-b border-gray-100 flex-shrink-0">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Dateien suchen…"
            className="w-full pl-8 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-400"
          />
        </div>
        <button onClick={() => setShowAddLink(true)}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
          <Link size={14} /> Cloud-Link
        </button>
        <button onClick={() => cameraInputRef.current?.click()}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
          <Camera size={14} /> Foto aufnehmen
        </button>
        <button onClick={() => fileInputRef.current?.click()}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-white bg-primary-500 hover:bg-primary-600 rounded-lg transition-colors">
          <Upload size={14} /> Hochladen
        </button>
      </div>

      {/* Drag & Drop + Liste */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">

        {/* Upload-Zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={e => { e.preventDefault(); setDragOver(false); handleUpload(e.dataTransfer.files) }}
          onClick={() => !uploading && fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
            dragOver ? 'border-primary-400 bg-primary-50' : 'border-gray-200 hover:border-gray-300 bg-gray-50'
          } ${uploading ? 'pointer-events-none' : ''}`}
        >
          {uploading ? (
            <div className="flex flex-col items-center py-5 gap-2">
              <Loader2 size={22} className="animate-spin text-primary-500" />
              <p className="text-sm text-gray-500">Wird hochgeladen… {uploadProgress}%</p>
              <div className="w-40 bg-gray-200 rounded-full h-1.5">
                <div className="bg-primary-500 h-1.5 rounded-full transition-all" style={{ width: `${uploadProgress}%` }} />
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center gap-3 py-4">
              <FolderOpen size={20} className={dragOver ? 'text-primary-500' : 'text-gray-300'} />
              <p className="text-sm text-gray-400">Dateien hierher ziehen oder klicken · max. 100 MB</p>
            </div>
          )}
        </div>

        <input ref={fileInputRef} type="file" multiple className="hidden" onChange={e => handleUpload(e.target.files)} />
        <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" className="hidden"
          onChange={e => handleUpload(e.target.files)} />

        {/* Dateiliste */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="animate-spin text-primary-400" />
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-300 gap-2">
            <HardDrive size={36} />
            <p className="text-sm">{search ? 'Keine Treffer' : 'Noch keine Anhänge'}</p>
          </div>
        ) : (
          <div className="space-y-1.5">
            {filtered.map(att => (
              <div key={att.id}
                className="flex items-center gap-3 p-3 rounded-xl border border-gray-100 hover:border-gray-200 hover:bg-gray-50 transition-colors group">

                {/* Icon */}
                {att.type === 'link'
                  ? <Cloud size={18} className="flex-shrink-0 text-gray-400" />
                  : <FileIcon mimetype={att.mimetype} size={18} />
                }

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-800 truncate max-w-xs">
                      {att.display_name}
                    </span>
                    {att.type === 'link' && (
                      <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${PROVIDER_COLORS[att.link_provider] || 'bg-gray-100 text-gray-500'}`}>
                        {PROVIDER_LABELS[att.link_provider] || att.link_provider}
                      </span>
                    )}
                    {att.has_share_link && (
                      <span className="text-xs px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 font-medium flex items-center gap-0.5">
                        <Share2 size={9} /> Geteilt
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {att.type === 'file' ? formatBytes(att.filesize) : att.link_url?.slice(0, 50)}
                    {' · '}{formatDate(att.created_at)}
                  </p>
                </div>

                {/* Aktionen */}
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  {att.type === 'link' && (
                    <a href={att.link_url} target="_blank" rel="noopener noreferrer"
                      className="p-2 text-gray-400 hover:text-primary-500 hover:bg-primary-50 rounded-lg transition-colors" title="Öffnen">
                      <ExternalLink size={14} />
                    </a>
                  )}
                  {att.type === 'file' && canPreview(att) && (
                    <button onClick={() => setPreviewTarget(att)}
                      className="p-2 text-gray-400 hover:text-primary-500 hover:bg-primary-50 rounded-lg transition-colors" title="Vorschau">
                      <Eye size={14} />
                    </button>
                  )}
                  {att.type === 'file' && (
                    <>
                      <button onClick={() => handleDownload(att)}
                        className="p-2 text-gray-400 hover:text-primary-500 hover:bg-primary-50 rounded-lg transition-colors" title="Herunterladen">
                        <Download size={14} />
                      </button>
                      <button onClick={() => setShareTarget(att)}
                        className="p-2 text-gray-400 hover:text-green-500 hover:bg-green-50 rounded-lg transition-colors" title="Download-Link">
                        <Share2 size={14} />
                      </button>
                    </>
                  )}
                  <button onClick={() => handleDelete(att)}
                    className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors" title="Löschen">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Statuszeile */}
      {!loading && attachments.length > 0 && (
        <div className="flex items-center justify-between px-4 py-2 border-t border-gray-100 text-xs text-gray-400 flex-shrink-0">
          <span>{attachments.filter(a => a.type === 'file').length} Datei(en) · {attachments.filter(a => a.type === 'link').length} Link(s)</span>
          <span>{attachments.filter(a => a.type === 'file').reduce((s, a) => s + (a.filesize || 0), 0) > 0
            ? formatBytes(attachments.filter(a => a.type === 'file').reduce((s, a) => s + (a.filesize || 0), 0)) + ' gesamt'
            : ''}</span>
        </div>
      )}
    </div>
  )

  // Als Modal anzeigen (wenn onClose übergeben wird)
  if (!fullPage) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
        <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-2xl flex flex-col" style={{ maxHeight: '85vh' }}>
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-gray-100 flex-shrink-0">
            <h2 className="font-semibold text-gray-900 flex items-center gap-2">
              <HardDrive size={18} className="text-primary-500" />
              Anhänge & Dateien
            </h2>
            <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
              <X size={20} />
            </button>
          </div>
          {content}
        </div>

        {/* Sub-Dialoge */}
        {showAddLink && (
          <AddLinkDialog entityType={entityType} entityId={entityId} providers={providers}
            onClose={() => setShowAddLink(false)}
            onAdded={att => { setAttachments(prev => [att, ...prev]); setShowAddLink(false) }} />
        )}
        {shareTarget && <ShareDialog attachment={shareTarget} onClose={() => setShareTarget(null)} />}
        {previewTarget && <PreviewModal attachment={previewTarget} onClose={() => setPreviewTarget(null)} />}
      </div>
    )
  }

  // Als Vollseite
  return (
    <div className="h-full flex flex-col">
      {content}
      {showAddLink && (
        <AddLinkDialog entityType={entityType} entityId={entityId} providers={providers}
          onClose={() => setShowAddLink(false)}
          onAdded={att => { setAttachments(prev => [att, ...prev]); setShowAddLink(false) }} />
      )}
      {shareTarget && <ShareDialog attachment={shareTarget} onClose={() => setShareTarget(null)} />}
      {previewTarget && <PreviewModal attachment={previewTarget} onClose={() => setPreviewTarget(null)} />}
    </div>
  )
}
