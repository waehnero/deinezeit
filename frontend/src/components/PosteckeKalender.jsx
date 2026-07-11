import { useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, Check, Bell } from 'lucide-react'

/**
 * Kalender-Ansicht (Monat) für die Postecke (Etappe 2) — Redaktionsplan.
 * Zeigt geplante Posts am Planungstermin und veröffentlichte am
 * Veröffentlichungsdatum. Klick auf einen Eintrag öffnet den Editor.
 *
 * Props:
 *   posts       – Postliste
 *   kanalVon    – (profilId) => Kanal-ID ('facebook_privat', ...) oder null
 *   onOpen(p)   – Post im Editor öffnen
 */

const WOCHENTAGE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

// Farbe je Kanal (Facebook blau, Instagram pink, LinkedIn violett, Rest grau)
const KANAL_FARBEN = {
  facebook_privat: 'bg-blue-50 text-blue-700',
  facebook_seite:  'bg-blue-50 text-blue-700',
  instagram:       'bg-pink-50 text-pink-700',
  linkedin:        'bg-purple-50 text-purple-700',
  sonstige:        'bg-neutral-100 text-neutral-600',
}

const tagKey = (d) => {
  const j = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const t = String(d.getDate()).padStart(2, '0')
  return `${j}-${m}-${t}`
}

export default function PosteckeKalender({ posts, kanalVon, onOpen }) {
  const [monat, setMonat] = useState(() => {
    const d = new Date()
    return new Date(d.getFullYear(), d.getMonth(), 1)
  })

  // Alle Zellen des Monatsrasters (Wochen ab Montag, inkl. Rand-Tage)
  const zellen = useMemo(() => {
    const erste = new Date(monat)
    // Montag der ersten Woche (getDay(): So=0 ... Sa=6)
    const versatz = (erste.getDay() + 6) % 7
    const start = new Date(erste)
    start.setDate(erste.getDate() - versatz)
    const liste = []
    const d = new Date(start)
    do {
      liste.push(new Date(d))
      d.setDate(d.getDate() + 1)
    } while (d.getMonth() === monat.getMonth() || liste.length % 7 !== 0)
    return liste
  }, [monat])

  // Posts je Tag: geplant -> geplant_am, veröffentlicht -> veroeffentlicht_am
  const postsProTag = useMemo(() => {
    const map = {}
    for (const p of posts) {
      const iso = p.status === 'geplant' ? p.geplant_am
        : p.status === 'veroeffentlicht' ? p.veroeffentlicht_am : null
      if (!iso) continue
      const key = tagKey(new Date(iso))
      ;(map[key] = map[key] || []).push(p)
    }
    for (const key of Object.keys(map)) {
      map[key].sort((a, b) =>
        new Date(a.geplant_am || a.veroeffentlicht_am) - new Date(b.geplant_am || b.veroeffentlicht_am))
    }
    return map
  }, [posts])

  const heute = tagKey(new Date())
  const monatsname = monat.toLocaleDateString('de-AT', { month: 'long', year: 'numeric' })
  const wechseln = (schritt) =>
    setMonat(m => new Date(m.getFullYear(), m.getMonth() + schritt, 1))

  return (
    <div>
      {/* Monatsnavigation */}
      <div className="flex items-center justify-between mb-3">
        <button onClick={() => wechseln(-1)}
          className="p-1.5 rounded-lg border border-neutral-200 bg-white text-neutral-500 hover:text-neutral-800">
          <ChevronLeft size={16} />
        </button>
        <button onClick={() => setMonat(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1) })}
          className="text-sm font-medium text-neutral-800 hover:text-primary-700" title="Zum aktuellen Monat">
          {monatsname}
        </button>
        <button onClick={() => wechseln(1)}
          className="p-1.5 rounded-lg border border-neutral-200 bg-white text-neutral-500 hover:text-neutral-800">
          <ChevronRight size={16} />
        </button>
      </div>

      {/* Raster */}
      <div className="grid grid-cols-7 gap-1">
        {WOCHENTAGE.map(w => (
          <p key={w} className="text-[11px] text-neutral-400 text-center pb-1">{w}</p>
        ))}
        {zellen.map((tag, i) => {
          const key = tagKey(tag)
          const imMonat = tag.getMonth() === monat.getMonth()
          const eintraege = postsProTag[key] || []
          return (
            <div key={i}
              className={`rounded-lg border p-1 min-h-[72px] ${
                key === heute ? 'border-primary-300 bg-primary-50/40'
                  : imMonat ? 'border-neutral-200 bg-white' : 'border-neutral-100 bg-neutral-50'
              }`}>
              <p className={`text-[11px] px-0.5 ${imMonat ? 'text-neutral-500' : 'text-neutral-300'} ${key === heute ? 'font-semibold text-primary-700' : ''}`}>
                {tag.getDate()}
              </p>
              <div className="space-y-0.5 mt-0.5">
                {eintraege.slice(0, 3).map(p => {
                  const farbe = KANAL_FARBEN[kanalVon(p.profil_id)] || KANAL_FARBEN.sonstige
                  return (
                    <button key={p.id} onClick={() => onOpen(p)}
                      className={`w-full text-left text-[10px] px-1 py-0.5 rounded truncate ${farbe} hover:opacity-80 flex items-center gap-0.5`}>
                      {p.status === 'veroeffentlicht'
                        ? <Check size={9} className="shrink-0" />
                        : <Bell size={9} className="shrink-0" />}
                      <span className="truncate">
                        {p.titel || p.text?.slice(0, 30) || 'Post'}
                      </span>
                    </button>
                  )
                })}
                {eintraege.length > 3 && (
                  <p className="text-[10px] text-neutral-400 px-1">+{eintraege.length - 3} weitere</p>
                )}
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-[11px] text-neutral-400 mt-2 flex items-center gap-3">
        <span className="flex items-center gap-1"><Bell size={11} /> geplant</span>
        <span className="flex items-center gap-1"><Check size={11} /> veröffentlicht</span>
      </p>
    </div>
  )
}
