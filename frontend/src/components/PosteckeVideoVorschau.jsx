import { useState, useEffect } from 'react'
import { Play, Film } from 'lucide-react'
import { posteckeApi } from '../services/api'

/**
 * Video-Vorschau für die Postecke (bereits gespeichertes Video, per videoId).
 *
 * Standardmäßig wird das serverseitig (ffmpeg) erzeugte Standbild als Bild
 * angezeigt — das funktioniert in jedem Browser und bei jedem Format (auch
 * iPhone-.mov/HEVC). Erst auf Klick wird das eigentliche Video geladen und
 * abgespielt, damit große Dateien nicht ungefragt heruntergeladen werden.
 */
export default function PosteckeVideoVorschau({ videoId, hasPoster = true, className }) {
  const [posterUrl, setPosterUrl] = useState(null)
  const [videoUrl, setVideoUrl] = useState(null)
  const [laedt, setLaedt] = useState(false)

  // Poster laden
  useEffect(() => {
    let objectUrl = null
    let aktiv = true
    setPosterUrl(null)
    if (videoId && hasPoster) {
      posteckeApi.getVideoPoster(videoId)
        .then(res => { if (aktiv) { objectUrl = URL.createObjectURL(res.data); setPosterUrl(objectUrl) } })
        .catch(() => {})
    }
    return () => { aktiv = false; if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [videoId, hasPoster])

  // Video-Objekt-URL wieder freigeben
  useEffect(() => () => { if (videoUrl) URL.revokeObjectURL(videoUrl) }, [videoUrl])

  const abspielen = async () => {
    if (videoUrl || laedt) return
    setLaedt(true)
    try {
      const res = await posteckeApi.getVideo(videoId)
      setVideoUrl(URL.createObjectURL(res.data))
    } catch { /* still nur Poster zeigen */ }
    finally { setLaedt(false) }
  }

  if (videoUrl) {
    return (
      <video src={videoUrl} poster={posterUrl || undefined} controls autoPlay playsInline
        className={`object-contain bg-black ${className}`} />
    )
  }

  return (
    <button type="button" onClick={abspielen}
      className={`relative flex items-center justify-center bg-black overflow-hidden ${className}`}>
      {posterUrl
        ? <img src={posterUrl} alt="Video-Vorschau" className="w-full h-full object-contain" />
        : <Film size={28} className="text-neutral-500" />}
      <span className="absolute inset-0 flex items-center justify-center">
        <span className="rounded-full bg-neutral-900/60 p-3">
          <Play size={22} className="text-white" fill="currentColor" />
        </span>
      </span>
    </button>
  )
}
