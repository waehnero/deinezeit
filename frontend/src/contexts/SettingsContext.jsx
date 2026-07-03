import { createContext, useContext, useEffect, useState } from 'react'
import { settingsApi } from '../services/api'

const SettingsContext = createContext(null)

const THEMES = ['orange', 'blue', 'green', 'purple', 'teal', 'red']

function applyTheme(theme) {
  const root = document.documentElement
  // Standard-Thema (orange) ist in :root definiert, alle anderen über data-theme
  if (!theme || theme === 'orange') {
    root.removeAttribute('data-theme')
  } else if (THEMES.includes(theme)) {
    root.setAttribute('data-theme', theme)
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
