import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import {
  Plus, Loader2, X, Megaphone, Sparkles, Camera, Trash2, Pencil,
  Send, CalendarClock, Inbox, Copy, Check, Settings2,
  ChevronLeft, RefreshCw, MapPin, Smile, Bell,
  List, Columns, CalendarDays, Search, Archive, ArchiveRestore,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { posteckeApi } from '../services/api'
import FotoThumb from '../components/PosteckeFotoThumb'
import PosteckeKanban from '../components/PosteckeKanban'
import PosteckeKalender from '../components/PosteckeKalender'
import ContactSearch from '../components/ContactSearch'

/* ─────────────────────────────────────────────────────────────────────────────
 * Postecke – Etappe 1: Mobile Erfassung, KI-Vorschlag, assistiertes Posten
 * Kanban-/Kalenderansicht folgt in Etappe 2 (gleiche Datenbasis).
 * ──────────────────────────────────────────────────────────────────────────── */

const KANAELE = [
  { id: 'facebook_privat', label: 'Facebook privat', url: 'https://www.facebook.com/' },
  { id: 'facebook_seite',  label: 'Facebook-Seite',  url: 'https://www.facebook.com/' },
  { id: 'instagram',       label: 'Instagram',       url: 'https://www.instagram.com/' },
  { id: 'linkedin',        label: 'LinkedIn',        url: 'https://www.linkedin.com/feed/' },
  { id: 'sonstige',        label: 'Sonstige',        url: '' },
]
const kanalInfo = (id) => KANAELE.find(k => k.id === id) || KANAELE[4]

const STATUS_META = {
  entwurf:         { label: 'Entwurf',        badge: 'bg-neutral-100 text-neutral-600' },
  kontrolle:       { label: 'Zur Kontrolle',  badge: 'bg-amber-100 text-amber-700' },
  geplant:         { label: 'Geplant',        badge: 'bg-primary-50 text-primary-700' },
  veroeffentlicht: { label: 'Veröffentlicht', badge: 'bg-green-100 text-green-700' },
  archiviert:      { label: 'Archiv',         badge: 'bg-neutral-100 text-neutral-400' },
}

function datumZeit(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('de-AT', { weekday: 'short', day: '2-digit', month: '2-digit' }) +
    ' ' + d.toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' })
}

/** Kompletten Posttext (Text + Hashtags) zusammensetzen */
function postText(post) {
  return [post.text || '', post.hashtags || ''].filter(Boolean).join('\n\n')
}

/* ── Profilverwaltung ────────────────────────────────────────────────────────── */
function ProfilForm({ profil, onSave, onCancel }) {
  const [name, setName] = useState(profil?.name || '')
  const [kanal, setKanal] = useState(profil?.kanal || 'facebook_privat')
  const [stil, setStil] = useState(profil?.stil_prompt || '')
  const [saving, setSaving] = useState(false)

  const speichern = async () => {
    if (!name.trim()) { toast.error('Bitte einen Namen angeben'); return }
    setSaving(true)
    try {
      await onSave({ name: name.trim(), kanal, stil_prompt: stil.trim() || null })
    } finally { setSaving(false) }
  }

  return (
    <div className="bg-white rounded-xl border border-neutral-200 p-4 space-y-3">
      <div>
        <label className="text-xs font-medium text-neutral-500">Name</label>
        <input value={name} onChange={e => setName(e.target.value)}
          placeholder="z.B. Facebook privat Oliver"
          className="mt-1 w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200" />
      </div>
      <div>
        <label className="text-xs font-medium text-neutral-500">Kanal</label>
        <select value={kanal} onChange={e => setKanal(e.target.value)}
          className="mt-1 w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-200">
          {KANAELE.map(k => <option key={k.id} value={k.id}>{k.label}</option>)}
        </select>
      </div>
      <div>
        <label className="text-xs font-medium text-neutral-500">
          Stil &amp; Redensart (Vorgabe für die KI)
        </label>
        <textarea value={stil} onChange={e => setStil(e.target.value)} rows={4}
          placeholder="z.B. Locker und persönlich, per Du, gerne Emojis, kurze Sätze, regionaler Bezug zu Ebreichsdorf …"
          className="mt-1 w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200" />
      </div>
      <div className="flex gap-2 justify-end">
        <button onClick={onCancel}
          className="px-3 py-2 rounded-lg text-sm text-neutral-600 hover:bg-neutral-100">Abbrechen</button>
        <button onClick={speichern} disabled={saving}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2">
          {saving && <Loader2 size={14} className="animate-spin" />} Speichern
        </button>
      </div>
    </div>
  )
}

function ProfilVerwaltung({ profile, onReload, onClose }) {
  const [bearbeite, setBearbeite] = useState(null)   // null | 'neu' | profil
  const speichern = async (data) => {
    try {
      if (bearbeite === 'neu') await posteckeApi.createProfil(data)
      else await posteckeApi.updateProfil(bearbeite.id, data)
      toast.success('Profil gespeichert')
      setBearbeite(null)
      onReload()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen')
    }
  }
  const loeschen = async (p) => {
    if (!window.confirm(`Profil „${p.name}" löschen? Vorhandene Posts bleiben erhalten.`)) return
    try {
      await posteckeApi.deleteProfil(p.id)
      toast.success('Profil gelöscht')
      onReload()
    } catch { toast.error('Löschen fehlgeschlagen') }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <button onClick={onClose} className="flex items-center gap-1 text-sm text-neutral-500 hover:text-neutral-800">
          <ChevronLeft size={16} /> Zurück zu den Posts
        </button>
        {bearbeite === null && (
          <button onClick={() => setBearbeite('neu')}
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700">
            <Plus size={15} /> Neues Profil
          </button>
        )}
      </div>

      {bearbeite !== null && (
        <ProfilForm profil={bearbeite === 'neu' ? null : bearbeite}
          onSave={speichern} onCancel={() => setBearbeite(null)} />
      )}

      {profile.length === 0 && bearbeite === null && (
        <div className="text-center py-10 text-neutral-400 text-sm">
          Noch keine Profile. Lege je Social-Media-Konto ein Profil mit Stil-Vorgaben an —
          die KI nutzt sie für passende Vorschläge.
        </div>
      )}

      {profile.map(p => (
        <div key={p.id} className="bg-white rounded-xl border border-neutral-200 p-4 flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm text-neutral-900">{p.name}</span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-primary-50 text-primary-700">
                {kanalInfo(p.kanal).label}
              </span>
              {!p.is_active && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-neutral-100 text-neutral-500">inaktiv</span>
              )}
            </div>
            {p.stil_prompt && (
              <p className="text-xs text-neutral-500 mt-1 line-clamp-2">{p.stil_prompt}</p>
            )}
          </div>
          <button onClick={() => setBearbeite(p)} title="Bearbeiten"
            className="p-1.5 rounded-lg text-neutral-400 hover:text-primary-600 hover:bg-primary-50">
            <Pencil size={15} />
          </button>
          <button onClick={() => loeschen(p)} title="Löschen"
            className="p-1.5 rounded-lg text-neutral-400 hover:text-red-600 hover:bg-red-50">
            <Trash2 size={15} />
          </button>
        </div>
      ))}
    </div>
  )
}

/* ── Erfassung / Bearbeitung eines Posts (Vollbild, mobile-first) ───────────── */
function PostEditor({ post, profile, onClose, onSaved }) {
  const istNeu = !post
  const [aktuell, setAktuell] = useState(post || null)   // Post-Objekt vom Server
  const [profilId, setProfilId] = useState(post?.profil_id || (profile[0]?.id ?? null))
  const [kontaktId, setKontaktId] = useState(post?.kontakt_id || null)
  const [kontaktName, setKontaktName] = useState(post?.kontakt_name || null)
  const [beschreibung, setBeschreibung] = useState(post?.beschreibung || '')
  const [text, setText] = useState(post?.text || '')
  const [hashtags, setHashtags] = useState(post?.hashtags || '')
  const [ort, setOrt] = useState(post?.ort || '')
  const [gefuehl, setGefuehl] = useState(post?.gefuehl || '')
  const [neueFotos, setNeueFotos] = useState([])          // File-Objekte vor dem Upload
  const [generiert, setGeneriert] = useState(!!post?.text)
  const [laufend, setLaufend] = useState(false)
  const [planenOffen, setPlanenOffen] = useState(false)
  const [geplantAm, setGeplantAm] = useState('')
  const fileRef = useRef(null)

  // Fotos für die Web Share API vorladen (muss VOR dem Klick passieren,
  // damit navigator.share synchron im Klick-Kontext aufgerufen werden kann)
  const [shareDateien, setShareDateien] = useState([])
  useEffect(() => {
    let aktiv = true
    setShareDateien([])
    const fotos = aktuell?.fotos || []
    if (!navigator.canShare || fotos.length === 0) return
    Promise.all(fotos.map(async f => {
      const res = await posteckeApi.getFoto(f.id)
      return new File([res.data], f.filename, { type: f.mimetype })
    })).then(dateien => { if (aktiv) setShareDateien(dateien) }).catch(() => {})
    return () => { aktiv = false }
  }, [aktuell?.fotos])

  // Natives Teilen mit Dateien möglich? (iPhone/iPad: ja; Desktop: meist nein)
  const kannTeilen = shareDateien.length > 0 &&
    navigator.canShare && navigator.canShare({ files: shareDateien })

  const profil = profile.find(p => p.id === profilId) || null
  const kanal = profil ? kanalInfo(profil.kanal) : null

  /** Post am Server anlegen/aktualisieren + neue Fotos hochladen; liefert Post */
  const sicherstellen = useCallback(async () => {
    let p = aktuell
    const daten = {
      profil_id: profilId, beschreibung: beschreibung || null,
      text: text || null, hashtags: hashtags || null,
      ort: ort || null, gefuehl: gefuehl || null,
      kontakt_id: kontaktId, kontakt_name: kontaktName,
    }
    if (!p) {
      const res = await posteckeApi.createPost({
        profil_id: profilId, beschreibung: beschreibung || null,
        kontakt_id: kontaktId, kontakt_name: kontaktName,
      })
      p = res.data
    } else {
      const res = await posteckeApi.updatePost(p.id, daten)
      p = res.data
    }
    if (neueFotos.length > 0) {
      const res = await posteckeApi.uploadFotos(p.id, neueFotos)
      p = res.data
      setNeueFotos([])
    }
    setAktuell(p)
    return p
  }, [aktuell, profilId, beschreibung, text, hashtags, ort, gefuehl, neueFotos, kontaktId, kontaktName])

  const kiVorschlag = async () => {
    if (!profilId) { toast.error('Bitte zuerst ein Profil wählen'); return }
    if (!beschreibung.trim() && neueFotos.length === 0 && !(aktuell?.fotos?.length)) {
      toast.error('Bitte Fotos hinzufügen oder kurz beschreiben, worum es geht')
      return
    }
    setLaufend(true)
    try {
      const p = await sicherstellen()
      const res = await posteckeApi.generieren(p.id, beschreibung || null)
      setText(res.data.text || '')
      setHashtags(res.data.hashtags || '')
      if (res.data.ort) setOrt(res.data.ort)
      if (res.data.gefuehl) setGefuehl(res.data.gefuehl)
      setGeneriert(true)
      const neu = await posteckeApi.getPost(p.id)
      setAktuell(neu.data)
      toast.success('Vorschlag erstellt — bitte kontrollieren')
    } catch (e) {
      toast.error(e.response?.data?.detail || 'KI-Vorschlag fehlgeschlagen')
    } finally { setLaufend(false) }
  }

  const speichern = async (nachricht = 'Gespeichert') => {
    setLaufend(true)
    try {
      const p = await sicherstellen()
      toast.success(nachricht)
      onSaved()
      return p
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Speichern fehlgeschlagen')
      return null
    } finally { setLaufend(false) }
  }

  /** Nach dem Übergeben: speichern + nachfragen, ob veröffentlicht wurde */
  const nachVeroeffentlichungFragen = async () => {
    const p = await speichern('Post gespeichert')
    if (!p) return
    if (window.confirm('Wurde der Post veröffentlicht? Dann verschiebe ich ihn zu „Veröffentlicht".')) {
      await posteckeApi.setStatus(p.id, 'veroeffentlicht')
      onSaved()
      onClose()
    }
  }

  /**
   * Assistiertes Posten.
   * Variante 1 (iPhone/iPad u.a.): Web Share API — natives Teilen-Menü mit
   *   FOTOS + Text, kein erneutes Hochladen. Facebook übernimmt die Fotos;
   *   den Text verwirft die FB-App absichtlich, darum liegt er zusätzlich
   *   in der Zwischenablage (nur einfügen).
   * Variante 2 (Desktop-Fallback): Text in die Zwischenablage + Kanal öffnen.
   * WICHTIG: share/open/clipboard müssen SYNCHRON im Klick-Kontext starten —
   * nach einem await blockiert sie der Popup-Blocker (v.a. Safari/iOS).
   */
  const assistiertPosten = async () => {
    const voll = postText({ text, hashtags })

    if (kannTeilen) {
      try { navigator.clipboard.writeText(voll) } catch { /* optional */ }
      try {
        await navigator.share({ files: shareDateien, text: voll })
      } catch (e) {
        if (e?.name === 'AbortError') return   // Nutzer hat abgebrochen
        toast.error('Teilen fehlgeschlagen — nutze den Zwischenablage-Weg')
      }
      await nachVeroeffentlichungFragen()
      return
    }

    if (kanal?.url) window.open(kanal.url, '_blank', 'noopener')
    try {
      await navigator.clipboard.writeText(voll)
      toast.success('Text in der Zwischenablage — beim Kanal nur noch einfügen')
    } catch {
      toast.error('Zwischenablage nicht verfügbar — Text bitte manuell kopieren')
    }
    await nachVeroeffentlichungFragen()
  }

  /** Desktop-Fallback: alle Fotos herunterladen (fürs Hochladen beim Kanal) */
  const fotosHerunterladen = async () => {
    for (const f of (aktuell?.fotos || [])) {
      try {
        const res = await posteckeApi.getFoto(f.id)
        const url = URL.createObjectURL(res.data)
        const a = document.createElement('a')
        a.href = url
        a.download = f.filename
        document.body.appendChild(a)
        a.click()
        a.remove()
        URL.revokeObjectURL(url)
      } catch { toast.error(`Download fehlgeschlagen: ${f.filename}`) }
    }
  }

  const planen = async () => {
    if (!geplantAm) { toast.error('Bitte Datum und Uhrzeit wählen'); return }
    const p = await speichern('Post gespeichert')
    if (!p) return
    try {
      await posteckeApi.setStatus(p.id, 'geplant', new Date(geplantAm).toISOString())
      toast.success('Geplant — der Post wartet im Redaktionsplan')
      onSaved()
      onClose()
    } catch (e) {
      toast.error(e.response?.data?.detail || 'Planen fehlgeschlagen')
    }
  }

  const ablegen = async () => {
    const p = await speichern('In der Postecke abgelegt')
    if (p) onClose()
  }

  const fotoWaehlen = (e) => {
    const dateien = Array.from(e.target.files || [])
    if (dateien.length) setNeueFotos(prev => [...prev, ...dateien])
    e.target.value = ''
  }

  const fotoLoeschen = async (fotoId) => {
    try {
      await posteckeApi.deleteFoto(fotoId)
      const neu = await posteckeApi.getPost(aktuell.id)
      setAktuell(neu.data)
    } catch { toast.error('Foto konnte nicht gelöscht werden') }
  }

  return (
    <div className="fixed inset-0 z-50 bg-neutral-900/40 flex items-end sm:items-center justify-center"
      style={{ paddingTop: 'env(safe-area-inset-top)' }}>
      <div className="bg-neutral-50 w-full sm:max-w-lg sm:rounded-2xl rounded-t-2xl max-h-[92vh] overflow-y-auto"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>

        {/* Kopf */}
        <div className="sticky top-0 bg-neutral-50 border-b border-neutral-200 px-4 py-3 flex items-center justify-between z-10">
          <h2 className="font-semibold text-neutral-900 text-sm flex items-center gap-2">
            <Megaphone size={16} className="text-primary-600" />
            {istNeu ? 'Neuer Post' : 'Post bearbeiten'}
          </h2>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-neutral-100 text-neutral-500">
            <X size={18} />
          </button>
        </div>

        <div className="p-4 space-y-4">
          {/* Fotos */}
          <div>
            <label className="text-xs font-medium text-neutral-500">Fotos</label>
            <div className="mt-1 grid grid-cols-4 gap-2">
              {(aktuell?.fotos || []).map(f => (
                <div key={f.id} className="relative aspect-square rounded-lg overflow-hidden group">
                  <FotoThumb fotoId={f.id} className="w-full h-full" />
                  <button onClick={() => fotoLoeschen(f.id)}
                    className="absolute top-1 right-1 p-1 rounded-full bg-neutral-900/60 text-white opacity-70 hover:opacity-100">
                    <X size={12} />
                  </button>
                </div>
              ))}
              {neueFotos.map((f, i) => (
                <div key={i} className="relative aspect-square rounded-lg overflow-hidden">
                  <img src={URL.createObjectURL(f)} alt="" className="w-full h-full object-cover" />
                  <button onClick={() => setNeueFotos(prev => prev.filter((_, j) => j !== i))}
                    className="absolute top-1 right-1 p-1 rounded-full bg-neutral-900/60 text-white opacity-70 hover:opacity-100">
                    <X size={12} />
                  </button>
                </div>
              ))}
              <button onClick={() => fileRef.current?.click()}
                className="aspect-square rounded-lg border-2 border-dashed border-neutral-300 flex flex-col items-center justify-center text-neutral-400 hover:border-primary-400 hover:text-primary-500">
                <Camera size={20} />
                <span className="text-[10px] mt-0.5">Hinzufügen</span>
              </button>
            </div>
            <input ref={fileRef} type="file" accept="image/*" multiple className="hidden" onChange={fotoWaehlen} />
          </div>

          {/* Profil */}
          <div>
            <label className="text-xs font-medium text-neutral-500">Profil</label>
            <div className="mt-1 flex flex-wrap gap-2">
              {profile.filter(p => p.is_active).map(p => (
                <button key={p.id} onClick={() => setProfilId(p.id)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                    profilId === p.id
                      ? 'bg-primary-50 border-primary-300 text-primary-700'
                      : 'bg-white border-neutral-200 text-neutral-600 hover:border-neutral-300'
                  }`}>
                  {p.name}
                </button>
              ))}
              {profile.length === 0 && (
                <span className="text-xs text-neutral-400">
                  Noch kein Profil angelegt — über das Zahnrad oben Profile verwalten.
                </span>
              )}
            </div>
          </div>

          {/* Kontakt (optional) — archivierte Posts landen im Datacenter beim Kontakt */}
          <div>
            <label className="text-xs font-medium text-neutral-500">
              Kontakt (optional — fürs Postsarchiv im Datacenter)
            </label>
            <div className="mt-1">
              <ContactSearch contactId={kontaktId} contactName={kontaktName}
                onChange={(id, name) => { setKontaktId(id); setKontaktName(name) }} />
            </div>
          </div>

          {/* Beschreibung */}
          <div>
            <label className="text-xs font-medium text-neutral-500">
              Was ist los? (Tipp: iOS-Tastatur-Mikrofon zum Diktieren)
            </label>
            <textarea value={beschreibung} onChange={e => setBeschreibung(e.target.value)} rows={3}
              placeholder="Kurz beschreiben: was, wo, mit wem — die KI macht den Rest …"
              className="mt-1 w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200" />
          </div>

          {/* KI-Vorschlag */}
          <button onClick={kiVorschlag} disabled={laufend}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50">
            {laufend ? <Loader2 size={16} className="animate-spin" /> :
              generiert ? <RefreshCw size={16} /> : <Sparkles size={16} />}
            {generiert ? 'Neuen Vorschlag erstellen' : 'KI-Vorschlag erstellen'}
          </button>

          {/* Ergebnis (editierbar) */}
          {(generiert || text) && (
            <div className="space-y-3 bg-white rounded-xl border border-neutral-200 p-3">
              <div>
                <label className="text-xs font-medium text-neutral-500">Posttext</label>
                <textarea value={text} onChange={e => setText(e.target.value)} rows={6}
                  className="mt-1 w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200" />
              </div>
              <div>
                <label className="text-xs font-medium text-neutral-500">Hashtags</label>
                <input value={hashtags} onChange={e => setHashtags(e.target.value)}
                  className="mt-1 w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm text-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-200" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs font-medium text-neutral-500 flex items-center gap-1">
                    <MapPin size={11} /> Ort
                  </label>
                  <input value={ort} onChange={e => setOrt(e.target.value)}
                    className="mt-1 w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200" />
                </div>
                <div>
                  <label className="text-xs font-medium text-neutral-500 flex items-center gap-1">
                    <Smile size={11} /> Gefühl
                  </label>
                  <input value={gefuehl} onChange={e => setGefuehl(e.target.value)}
                    className="mt-1 w-full px-3 py-2 rounded-lg border border-neutral-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200" />
                </div>
              </div>
              {aktuell?.ki_model && (
                <p className="text-[10px] text-neutral-400">Vorschlag von {aktuell.ki_model}</p>
              )}
            </div>
          )}

          {/* Aktionen */}
          {(text || generiert) && (
            <div className="space-y-2">
              <button onClick={assistiertPosten} disabled={laufend}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-neutral-200 bg-white hover:border-primary-300 text-left">
                <Send size={18} className="text-primary-600 flex-shrink-0" />
                <span>
                  <span className="block text-sm font-medium text-neutral-900">
                    {kannTeilen ? 'Jetzt teilen (Fotos + Text)' : 'Jetzt assistiert posten'}
                  </span>
                  <span className="block text-xs text-neutral-500">
                    {kannTeilen
                      ? `Teilen-Menü öffnet sich — ${kanal?.label || 'App'} wählen, Fotos sind dabei, Text nur einfügen`
                      : `Text in die Zwischenablage, ${kanal?.label || 'Kanal'} öffnet sich — Du machst den letzten Klick`}
                  </span>
                </span>
              </button>
              {!kannTeilen && (aktuell?.fotos?.length > 0) && (
                <button onClick={fotosHerunterladen} disabled={laufend}
                  className="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl border border-neutral-200 bg-white hover:border-primary-300 text-left">
                  <Camera size={16} className="text-neutral-500 flex-shrink-0" />
                  <span className="text-xs text-neutral-600">
                    Fotos herunterladen ({aktuell.fotos.length}) — fürs Hochladen beim Kanal
                  </span>
                </button>
              )}

              <button onClick={() => setPlanenOffen(v => !v)} disabled={laufend}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-neutral-200 bg-white hover:border-primary-300 text-left">
                <CalendarClock size={18} className="text-primary-600 flex-shrink-0" />
                <span>
                  <span className="block text-sm font-medium text-neutral-900">Planen</span>
                  <span className="block text-xs text-neutral-500">In den Redaktionsplan mit Termin</span>
                </span>
              </button>
              {planenOffen && (
                <div className="flex gap-2 px-1">
                  <input type="datetime-local" value={geplantAm} onChange={e => setGeplantAm(e.target.value)}
                    className="flex-1 px-3 py-2 rounded-lg border border-neutral-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-200" />
                  <button onClick={planen} disabled={laufend}
                    className="px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50">
                    <Check size={16} />
                  </button>
                </div>
              )}

              <button onClick={ablegen} disabled={laufend}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-neutral-200 bg-white hover:border-primary-300 text-left">
                <Inbox size={18} className="text-neutral-500 flex-shrink-0" />
                <span>
                  <span className="block text-sm font-medium text-neutral-900">In die Postecke legen</span>
                  <span className="block text-xs text-neutral-500">Als Entwurf für später aufheben</span>
                </span>
              </button>
            </div>
          )}

          {/* Ohne KI-Text nur speichern */}
          {!text && !generiert && (
            <button onClick={ablegen} disabled={laufend}
              className="w-full px-4 py-2.5 rounded-lg text-sm font-medium border border-neutral-200 bg-white text-neutral-600 hover:border-neutral-300">
              Als Entwurf ablegen
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── Hauptseite ─────────────────────────────────────────────────────────────── */
export default function PosteckePage() {
  const [posts, setPosts] = useState([])
  const [profile, setProfile] = useState([])
  const [laden, setLaden] = useState(true)
  const [ansicht, setAnsicht] = useState('posts')       // posts | profile
  const [editor, setEditor] = useState(null)            // null | 'neu' | post
  // Darstellung der Posts: Liste (mobil) | Kanban-Board | Kalender (Redaktionsplan)
  const [darstellung, setDarstellung] = useState(() => {
    try { return localStorage.getItem('postecke_ansicht') || 'liste' } catch { return 'liste' }
  })
  const darstellungWaehlen = (d) => {
    setDarstellung(d)
    try { localStorage.setItem('postecke_ansicht', d) } catch {}
  }

  const laden_ = useCallback(async () => {
    try {
      const [p1, p2] = await Promise.all([posteckeApi.listPosts(), posteckeApi.listProfile()])
      setPosts(p1.data)
      setProfile(p2.data)
    } catch {
      toast.error('Postecke konnte nicht geladen werden')
    } finally { setLaden(false) }
  }, [])
  useEffect(() => { laden_() }, [laden_])

  const profilName = (id) => profile.find(p => p.id === id)?.name || '—'
  const profilKanal = (id) => {
    const p = profile.find(x => x.id === id)
    return p ? kanalInfo(p.kanal).label : null
  }
  // Kanal-ID eines Profils (für Farben im Kalender)
  const profilKanalId = (id) => profile.find(x => x.id === id)?.kanal || null

  const loeschen = async (post) => {
    if (!window.confirm('Diesen Post endgültig löschen (inkl. Fotos)?')) return
    try {
      await posteckeApi.deletePost(post.id)
      toast.success('Post gelöscht')
      laden_()
    } catch { toast.error('Löschen fehlgeschlagen') }
  }

  const archivieren = async (post) => {
    try {
      await posteckeApi.setStatus(post.id, 'archiviert')
      toast.success('Post archiviert')
      laden_()
    } catch { toast.error('Archivieren fehlgeschlagen') }
  }

  const wiederherstellen = async (post) => {
    try {
      await posteckeApi.setStatus(post.id, 'entwurf')
      toast.success('Post wiederhergestellt (Entwurf)')
      laden_()
    } catch { toast.error('Wiederherstellen fehlgeschlagen') }
  }

  const kopieren = async (post) => {
    try {
      await navigator.clipboard.writeText(postText(post))
      toast.success('Text in der Zwischenablage')
    } catch { toast.error('Zwischenablage nicht verfügbar') }
  }

  // Volltextsuche über Titel, Posttext, Beschreibung, Hashtags, Ort und Profil
  const [suche, setSuche] = useState('')
  const gefiltert = useMemo(() => {
    const q = suche.trim().toLowerCase()
    if (!q) return posts
    return posts.filter(p =>
      [p.titel, p.text, p.beschreibung, p.hashtags, p.ort, p.kontakt_name,
       profilName(p.profil_id), profilKanal(p.profil_id)]
        .filter(Boolean).join(' ').toLowerCase().includes(q))
  }, [posts, suche, profile])

  // Archivierte Posts nur in der Liste (eigene Gruppe unten), nicht im Board/Kalender
  const aktivePosts = gefiltert.filter(p => p.status !== 'archiviert')

  const gruppen = ['kontrolle', 'geplant', 'entwurf', 'veroeffentlicht', 'archiviert']
    .map(s => ({ status: s, eintraege: gefiltert.filter(p => p.status === s) }))
    .filter(g => g.eintraege.length > 0)

  if (laden) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 size={28} className="animate-spin text-primary-400" />
      </div>
    )
  }

  // Breite: alle Post-Ansichten volle Breite, nur die Profilverwaltung kompakt
  const breite = ansicht === 'profile' ? 'max-w-3xl' : 'max-w-full'

  return (
    <div className={`${breite} mx-auto`}>
      {/* Kopfzeile */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-neutral-900 flex items-center gap-2">
            <Megaphone size={20} className="text-primary-600" /> Postecke
          </h1>
          <p className="text-sm text-neutral-500 mt-0.5">
            Posts mit KI vorbereiten und gezielt veröffentlichen
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setAnsicht(a => a === 'profile' ? 'posts' : 'profile')}
            title="Profile verwalten"
            className={`p-2 rounded-lg border ${ansicht === 'profile'
              ? 'bg-primary-50 border-primary-300 text-primary-700'
              : 'bg-white border-neutral-200 text-neutral-500 hover:text-neutral-800'}`}>
            <Settings2 size={17} />
          </button>
          {ansicht === 'posts' && (
            <button onClick={() => setEditor('neu')}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700">
              <Plus size={15} /> Neuer Post
            </button>
          )}
        </div>
      </div>

      {ansicht === 'profile' ? (
        <ProfilVerwaltung profile={profile} onReload={laden_} onClose={() => setAnsicht('posts')} />
      ) : (
        <>
          {/* Ansichtsumschalter + Suche */}
          {posts.length > 0 && (
            <div className="flex flex-wrap items-center gap-3 mb-4">
              <div className="flex items-center gap-1 bg-neutral-100 rounded-lg p-1 w-fit">
                {[
                  { id: 'liste',    icon: List,         label: 'Liste' },
                  { id: 'board',    icon: Columns,      label: 'Board' },
                  { id: 'kalender', icon: CalendarDays, label: 'Kalender' },
                ].map(({ id, icon: Icon, label }) => (
                  <button key={id} onClick={() => darstellungWaehlen(id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                      darstellung === id
                        ? 'bg-white text-neutral-900 shadow-sm'
                        : 'text-neutral-500 hover:text-neutral-800'
                    }`}>
                    <Icon size={13} /> {label}
                  </button>
                ))}
              </div>
              <div className="relative flex-1 min-w-[200px] max-w-sm">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
                <input value={suche} onChange={e => setSuche(e.target.value)}
                  placeholder="Suchen (Text, Hashtags, Ort, Profil) …"
                  className="w-full pl-8 pr-8 py-2 rounded-lg border border-neutral-200 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-200" />
                {suche && (
                  <button onClick={() => setSuche('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded text-neutral-400 hover:text-neutral-700">
                    <X size={14} />
                  </button>
                )}
              </div>
            </div>
          )}

          {posts.length > 0 && gefiltert.length === 0 && (
            <p className="text-center text-neutral-400 text-sm py-10">
              Keine Treffer für „{suche}".
            </p>
          )}

          {posts.length === 0 && (
            <div className="text-center py-14">
              <Megaphone size={36} className="mx-auto text-neutral-300 mb-3" />
              <p className="text-neutral-500 text-sm mb-1">Noch keine Posts in der Postecke.</p>
              <p className="text-neutral-400 text-xs mb-4">
                {profile.length === 0
                  ? 'Lege zuerst über das Zahnrad ein Profil an (z.B. „Facebook privat").'
                  : 'Fotos rein, kurz beschreiben — die KI macht den Vorschlag.'}
              </p>
              {profile.length > 0 && (
                <button onClick={() => setEditor('neu')}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-primary-600 text-white hover:bg-primary-700">
                  <Plus size={15} /> Ersten Post erstellen
                </button>
              )}
            </div>
          )}

          {darstellung === 'board' && aktivePosts.length > 0 && (
            <PosteckeKanban posts={aktivePosts} profilName={profilName}
              kanalLabel={profilKanal} onOpen={setEditor} onChanged={laden_}
              onArchivieren={archivieren} onLoeschen={loeschen} />
          )}

          {darstellung === 'kalender' && aktivePosts.length > 0 && (
            <PosteckeKalender posts={aktivePosts} kanalVon={profilKanalId} onOpen={setEditor} />
          )}

          {darstellung === 'liste' && (
          <div className="space-y-6">
            {gruppen.map(g => (
              <div key={g.status}>
                <h2 className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-2">
                  {STATUS_META[g.status].label} · {g.eintraege.length}
                </h2>
                <div className="space-y-2">
                  {g.eintraege.map(post => (
                    <div key={post.id}
                      className="bg-white rounded-xl border border-neutral-200 p-3 flex gap-3 items-start hover:border-neutral-300 cursor-pointer"
                      onClick={() => setEditor(post)}>
                      {post.fotos?.length > 0 ? (
                        <FotoThumb fotoId={post.fotos[0].id} className="w-14 h-14 rounded-lg flex-shrink-0" />
                      ) : (
                        <div className="w-14 h-14 rounded-lg bg-neutral-100 flex items-center justify-center flex-shrink-0">
                          <Camera size={18} className="text-neutral-300" />
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-neutral-900 truncate">
                            {post.titel || post.text?.slice(0, 60) || post.beschreibung?.slice(0, 60) || 'Ohne Titel'}
                          </span>
                          <span className={`text-[10px] px-2 py-0.5 rounded-full ${STATUS_META[post.status].badge}`}>
                            {STATUS_META[post.status].label}
                          </span>
                        </div>
                        <div className="flex items-center gap-3 mt-1 text-xs text-neutral-500 flex-wrap">
                          {post.profil_id && (
                            <span>{profilName(post.profil_id)}
                              {profilKanal(post.profil_id) && ` · ${profilKanal(post.profil_id)}`}</span>
                          )}
                          {post.kontakt_name && (
                            <span className="text-neutral-400">@ {post.kontakt_name}</span>
                          )}
                          {post.status === 'geplant' && post.geplant_am && (
                            <span className="flex items-center gap-1 text-primary-600">
                              <Bell size={11} /> {datumZeit(post.geplant_am)}
                            </span>
                          )}
                          {post.status === 'veroeffentlicht' && post.veroeffentlicht_am && (
                            <span className="flex items-center gap-1 text-green-600">
                              <Check size={11} /> {datumZeit(post.veroeffentlicht_am)}
                            </span>
                          )}
                          {post.fotos?.length > 0 && <span>{post.fotos.length} Foto{post.fotos.length > 1 ? 's' : ''}</span>}
                        </div>
                      </div>
                      <div className="flex gap-1" onClick={e => e.stopPropagation()}>
                        {post.text && (
                          <button onClick={() => kopieren(post)} title="Text kopieren"
                            className="p-1.5 rounded-lg text-neutral-400 hover:text-primary-600 hover:bg-primary-50">
                            <Copy size={14} />
                          </button>
                        )}
                        {post.status === 'archiviert' ? (
                          <button onClick={() => wiederherstellen(post)} title="Wiederherstellen"
                            className="p-1.5 rounded-lg text-neutral-400 hover:text-primary-600 hover:bg-primary-50">
                            <ArchiveRestore size={14} />
                          </button>
                        ) : (
                          <button onClick={() => archivieren(post)} title="Archivieren"
                            className="p-1.5 rounded-lg text-neutral-400 hover:text-amber-600 hover:bg-amber-50">
                            <Archive size={14} />
                          </button>
                        )}
                        <button onClick={() => loeschen(post)} title="Löschen"
                          className="p-1.5 rounded-lg text-neutral-400 hover:text-red-600 hover:bg-red-50">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          )}
        </>
      )}

      {editor !== null && (
        <PostEditor
          post={editor === 'neu' ? null : editor}
          profile={profile}
          onClose={() => setEditor(null)}
          onSaved={laden_}
        />
      )}
    </div>
  )
}
