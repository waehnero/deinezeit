/**
 * Zeit-Hilfsfunktionen der Zeiterfassung.
 *
 * Aus ZeiterfassungPage.jsx herausgelöst, als die Berichtsseite dieselben
 * Formate brauchte. Zwei Kopien derselben Umrechnung sind in einem Modul, das
 * mit Zeitzonen und Rundung zu tun hat, ein sicherer Weg zu zwei verschiedenen
 * Ergebnissen für denselben Eintrag.
 */
export function fmtMinutes(min) {
  if (min === null || min === undefined) return '—'
  const h = Math.floor(min / 60)
  const m = min % 60
  return `${h}:${String(m).padStart(2, '0')}`
}

export function fmtElapsed(startedAt) {
  const sec = Math.floor((Date.now() - new Date(startedAt)) / 1000)
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

export function fmtTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' })
}

export function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('de-AT', { weekday: 'short', day: '2-digit', month: '2-digit', year: 'numeric' })
}

export function nowIso() { return new Date().toISOString() }
export function isoToDateLocal(iso) { return iso ? new Date(iso).toISOString().slice(0, 10) : '' }
export function isoToTimeLocal(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
export function localToIso(date, time) {
  if (!date || !time) return null
  const d = new Date(`${date}T${time}:00`)
  return isNaN(d.getTime()) ? null : d.toISOString()   // ungültige Werte nie durchreichen
}
// Fehlerdetail aus API-Antworten immer als lesbaren Text liefern
// (FastAPI-Validierungsfehler kommen als Array — ohne das zeigt der Toast nichts an)
export function apiErrorText(err, fallback) {
  const d = err?.response?.data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map(x => x?.msg || JSON.stringify(x)).join('; ')
  return fallback
}
export function calcDuration(startedAt, endedAt, pauseMin) {
  if (!startedAt || !endedAt) return 0
  const delta = (new Date(endedAt) - new Date(startedAt)) / 60000
  return Math.max(0, Math.round(delta) - (pauseMin || 0))
}
// Lokales Datum (YYYY-MM-DD) — bewusst NICHT über toISOString (UTC-Verschiebung)
export function isoToLocalDateStr(iso) {
  const d = iso ? new Date(iso) : new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
export function nowTimeLocal() { return isoToTimeLocal(new Date().toISOString()) }
