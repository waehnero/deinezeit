import { useState, useEffect } from 'react'
import { Play, Film } from 'lucide-react'
import { posteckeApi } from '../services/api'

/**
 * Kleines Vorschaubild eines Video-Posts (Liste/Board/Kalender): zeigt das
 * serverseitig erzeugte Standbild (Poster) mit einem Play-Badge. Fällt bei
 * fehlendem Poster auf ein Film-Symbol zurück.
 */
export default function PosteckeVideoThumb({ videoId, hasPoster = true, className = '' }) {
  const [url, setUrl] = useState(null)
  useEffect(() => {
    let objectUrl = null
    let aktiv = true
    setUrl(null)
    if (videoId && hasPoster) {
      posteckeApi.getVideoPoster(videoId)
        .then(res => { if (aktiv) { objectUrl = URL.createObjectURL(res.data); setUrl(objectUrl) } })
        .catch(() => {})
    }
    return () => { aktiv = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [videoId, hasPoster])

  return (
    <div className={`relative bg-neutral-900 overflow-hidden flex items-center justify-center ${className}`}>
      {url
        ? <img src={url} alt="" className="w-full h-full object-cover" />
        : <Film size={18} className="text-neutral-400" />}
      <span className="absolute inset-0 flex items-center justify-center">
        <span className="rounded-full bg-neutral-900/60 p-1">
          <Play size={12} className="text-white" fill="currentColor" />
        </span>
      </span>
    </div>
  )
}
