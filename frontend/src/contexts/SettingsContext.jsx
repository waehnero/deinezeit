import { createContext, useContext, useEffect, useState } from 'react'
import { settingsApi } from '../services/api'

const SettingsContext = createContext(null)

const THEMES = ['orange', 'blue', 'green', 'purple', 'teal', 'red']

// Designvorlagen (Layout-Redesign Etappe 2) — Token-Presets in index.css
const DESIGNS = ['standard', 'aurora', 'bento', 'business', 'kontor', 'nordic', 'midnight', 'kontrast']

function applyTheme(theme) {
  const root = document.documentElement
  // Standard-Thema (orange) ist in :root definiert, alle anderen über data-theme
  if (!theme || theme === 'orange') {
    root.removeAttribute('data-theme')
  } else if (THEMES.includes(theme)) {
    root.setAttribute('data-theme', theme)
  }
}

// Designvorlage per data-design am <html> setzen (Presets in index.css)
function applyDesign(design) {
  const root = document.documentElement
  if (!design || design === 'standard' || !DESIGNS.includes(design)) {
    root.removeAttribute('data-design')
  } else {
    root.setAttribute('data-design', design)
  }
}

// ── Freie Markenfarbe (Whitelabel): aus einem Hex-Wert die --p-Skala rechnen ─
function hexToRgb(hex) {
  const h = (hex || '').replace('#', '')
  if (!/^[0-9a-fA-F]{6}$/.test(h)) return null
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

// Mischt eine Farbe anteilig Richtung Weiß (Tint) bzw. Schwarz (Shade)
function mix(rgb, target, anteil) {
  return rgb.map((c, i) => Math.round(c + (target[i] - c) * anteil))
}

const WEISS = [255, 255, 255]
const SCHWARZ = [0, 0, 0]

// Stufen wie bei Tailwind-Paletten: 500 = Basiston
const BRAND_STUFEN = [
  [50, WEISS, 0.95], [100, WEISS, 0.90], [200, WEISS, 0.75], [300, WEISS, 0.60],
  [400, WEISS, 0.30], [500, null, 0], [600, SCHWARZ, 0.10], [700, SCHWARZ, 0.25],
  [800, SCHWARZ, 0.40], [900, SCHWARZ, 0.50],
]

function applyBrandColor(hex) {
  const root = document.documentElement
  const rgb = hexToRgb(hex)
  for (const [stufe, target, anteil] of BRAND_STUFEN) {
    if (!rgb) {
      root.style.removeProperty(`--p-${stufe}`)
    } else {
      const [r, g, b] = target ? mix(rgb, target, anteil) : rgb
      root.style.setProperty(`--p-${stufe}`, `${r} ${g} ${b}`)
    }
  }
}

// ── Farb-Overrides (Text / Hintergrund / Flächen) als Inline-Variablen ──────
// Leerer Wert = Override entfernen, der Vorlagenwert gilt wieder.
const OVERRIDE_VARS = {
  custom_text_color:    ['--n-900'],
  custom_bg_color:      ['--page-bg'],
  custom_surface_color: ['--surface'],
}

function applyColorOverrides(settings) {
  const root = document.documentElement
  for (const [key, vars] of Object.entries(OVERRIDE_VARS)) {
    const rgb = hexToRgb(settings[key])
    for (const v of vars) {
      if (rgb) root.style.setProperty(v, `${rgb[0]} ${rgb[1]} ${rgb[2]}`)
      else root.style.removeProperty(v)
    }
  }
}

// MIME-Typ anhand der Dateiendung bestimmen (Favicon kann PNG, ICO, SVG oder JPG sein)
const FAVICON_TYPES = {
  svg:  'image/svg+xml',
  png:  'image/png',
  ico:  'image/x-icon',
  jpg:  'image/jpeg',
  jpeg: 'image/jpeg',
}

function applyFavicon(faviconUrl) {
  // Ohne eigenes Favicon auf den Standard zurückfallen (wichtig nach "Entfernen")
  const url = faviconUrl || '/favicon.svg'
  // Bestehende Favicon-Links komplett entfernen: index.html liefert
  // <link rel="icon" type="image/svg+xml" href="/favicon.svg"> — würde man nur
  // das href umschreiben, bliebe der falsche type stehen und der Browser
  // ignoriert das hochgeladene PNG/ICO-Favicon.
  document.querySelectorAll("link[rel~='icon']").forEach((el) => el.remove())

  const link = document.createElement('link')
  link.rel = 'icon'
  const ext = url.split('?')[0].split('.').pop().toLowerCase()
  if (FAVICON_TYPES[ext]) link.type = FAVICON_TYPES[ext]
  // Cache-Buster damit der Browser das neue Favicon sofort lädt
  link.href = `${url}?v=${Date.now()}`
  document.head.appendChild(link)
}

export function SettingsProvider({ children }) {
  const [settings, setSettings] = useState({
    company_name:    'DeineZeit',
    app_subtitle:    'Zeiterfassung & Stammdaten',
    color_theme:     'orange',
    logo_url:        '',
    smtp_host:       '',
    smtp_port:       '587',
    smtp_user:       '',
    smtp_password:   '',
    smtp_from_name:  '',
    smtp_from_email: '',
    smtp_tls:        'true',
    backup_keep_days:'30',
    backup_last_at:  '',
  })
  const [loading, setLoading] = useState(true)

  const loadSettings = async () => {
    try {
      const res = await settingsApi.get()
      setSettings(res.data)
      applyTheme(res.data.color_theme)
      applyDesign(res.data.design_template)
      applyBrandColor(res.data.brand_color)
      applyColorOverrides(res.data)
      applyFavicon(res.data.logo_favicon_url)
    } catch {
      // Bei Fehler Standard-Werte behalten
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadSettings()
  }, [])

  // Thema sofort anwenden wenn es sich ändert
  useEffect(() => {
    applyTheme(settings.color_theme)
  }, [settings.color_theme])

  // Designvorlage sofort anwenden wenn sie sich ändert (Live-Vorschau)
  useEffect(() => {
    applyDesign(settings.design_template)
  }, [settings.design_template])

  // Freie Markenfarbe + Farb-Overrides sofort anwenden (Live-Vorschau)
  useEffect(() => {
    applyBrandColor(settings.brand_color)
    applyColorOverrides(settings)
  }, [settings.brand_color, settings.custom_text_color, settings.custom_bg_color, settings.custom_surface_color])

  // Favicon sofort aktualisieren wenn es sich ändert
  useEffect(() => {
    applyFavicon(settings.logo_favicon_url)
  }, [settings.logo_favicon_url])

  const updateSettings = (partial) => {
    setSettings(prev => ({ ...prev, ...partial }))
  }

  return (
    <SettingsContext.Provider value={{ settings, loading, loadSettings, updateSettings }}>
      {children}
    </SettingsContext.Provider>
  )
}

export function useSettings() {
  const ctx = useContext(SettingsContext)
  if (!ctx) throw new Error('useSettings muss innerhalb von SettingsProvider verwendet werden')
  return ctx
}
