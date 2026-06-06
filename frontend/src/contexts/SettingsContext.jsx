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

function applyFavicon(faviconUrl) {
  if (!faviconUrl) return
  let link = document.querySelector("link[rel~='icon']")
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  // Cache-Buster damit der Browser das neue Favicon sofort lädt
  link.href = `${faviconUrl}?v=${Date.now()}`
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
