import { describe, it, expect } from 'vitest'
import { mitCacheBuster } from './SettingsContext'

describe('mitCacheBuster', () => {
  it('lässt eine Adresse mit Versionsparameter unverändert (kein doppeltes ?v=)', () => {
    const url = '/api/static/logo/logo_header.png?v=1785821496'
    expect(mitCacheBuster(url)).toBe(url)
  })
  it('hängt an eine Adresse ohne Parameter genau einen Zeitstempel an', () => {
    expect(mitCacheBuster('/api/static/logo/alt.png')).toMatch(/^\/api\/static\/logo\/alt\.png\?v=\d+$/)
  })
  it('gibt leere Werte unverändert zurück', () => {
    expect(mitCacheBuster('')).toBe('')
    expect(mitCacheBuster(null)).toBeNull()
  })
})
