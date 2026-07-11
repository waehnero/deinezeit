import { useState, useEffect } from 'react'
import { posteckeApi } from '../services/api'

/**
 * Foto-Vorschau für die Postecke: lädt das Bild als Blob über die API
 * (Bearer-Token nötig, daher kein direktes <img src="/api/...">).
 * Wird in der Postliste, im Editor, im Kanban und im Kalender genutzt.
 */
export default function PosteckeFotoThumb({ fotoId, className }) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    let objectUrl = null
    posteckeApi.getFoto(fotoId)
      .then(res => { objectUrl = URL.createObjectURL(res.data); setUrl(objectUrl) })
      .catch(() => {})
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [fotoId])
  if (!url) return <div className={`bg-neutral-100 animate-pulse ${className}`} />
  return <img src={url} alt="" className={`object-cover ${className}`} />
}
