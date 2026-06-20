/**
 * Wandelt jeden API-Fehler in eine lesbare Zeichenkette um.
 * Wichtig: FastAPI liefert bei 422 das `detail` als Array von Objekten —
 * das darf NICHT direkt an toast.error()/JSX übergeben werden (sonst Render-Crash
 * und weiße Seite). Diese Funktion normalisiert alles zu einem String.
 */
export default function errMsg(err, fallback = 'Ein Fehler ist aufgetreten') {
  const d = err?.response?.data?.detail
  if (!d) return err?.message || fallback
  if (typeof d === 'string') return d
  if (Array.isArray(d)) return d.map(e => e?.msg || (typeof e === 'string' ? e : JSON.stringify(e))).join('; ')
  if (typeof d === 'object') return d.msg || JSON.stringify(d)
  return String(d)
}
