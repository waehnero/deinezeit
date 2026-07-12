// Anzeige-Präferenzen PRO BENUTZER/GERÄT (Layout-Redesign Etappe 4).
// Gespeichert im localStorage (wie die eingeklappte Sidebar), wirken sofort
// und unabhängig von der globalen Designvorlage des Admins:
//   dark     'auto' | 'hell' | 'dunkel'   → data-dark am <html>
//   contrast true/false (hoher Kontrast)  → data-contrast
//   bigtext  true/false (größere Schrift) → data-bigtext
//   calm     true/false (weniger Animation) → data-calm
// Die zugehörigen Token-Overrides liegen in index.css.

const KEYS = {
  dark:     'dz_pref_dark',
  contrast: 'dz_pref_contrast',
  bigtext:  'dz_pref_bigtext',
  calm:     'dz_pref_calm',
}

export function getPrefs() {
  let dark = 'auto'
  const prefs = { dark: 'auto', contrast: false, bigtext: false, calm: false }
  try {
    dark = localStorage.getItem(KEYS.dark) || 'auto'
    prefs.dark = ['auto', 'hell', 'dunkel'].includes(dark) ? dark : 'auto'
    prefs.contrast = localStorage.getItem(KEYS.contrast) === '1'
    prefs.bigtext  = localStorage.getItem(KEYS.bigtext) === '1'
    prefs.calm     = localStorage.getItem(KEYS.calm) === '1'
  } catch { /* localStorage gesperrt → Standardwerte */ }
  return prefs
}

export function setPref(name, value) {
  try {
    if (name === 'dark') localStorage.setItem(KEYS.dark, value)
    else localStorage.setItem(KEYS[name], value ? '1' : '0')
  } catch { /* ignorieren */ }
  applyPrefs()
}

// Ist der Dunkelmodus aktuell wirksam? (direkt gewählt oder via Systemeinstellung)
export function istDunkel() {
  const p = getPrefs()
  if (p.dark === 'dunkel') return true
  if (p.dark === 'hell') return false
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ?? false
}

export function toggleDark() {
  setPref('dark', istDunkel() ? 'hell' : 'dunkel')
}

function setAttr(name, on) {
  const root = document.documentElement
  if (on) root.setAttribute(name, 'true')
  else root.removeAttribute(name)
}

export function applyPrefs() {
  const p = getPrefs()
  setAttr('data-dark', istDunkel())
  setAttr('data-contrast', p.contrast)
  setAttr('data-bigtext', p.bigtext)
  setAttr('data-calm', p.calm)
}

// Beim App-Start aufrufen: Präferenzen anwenden und bei „Auto" auf
// Systemwechsel (hell/dunkel) reagieren
export function initPrefs() {
  applyPrefs()
  try {
    window.matchMedia('(prefers-color-scheme: dark)')
      .addEventListener('change', () => applyPrefs())
  } catch { /* ältere Browser */ }
}
