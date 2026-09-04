/**
 * Token-Verwaltung und stiller Refresh in services/api.js.
 *
 * Geprüft wird das Verhalten, das im Audit als sicherheitsrelevant galt:
 * Der Access-Token darf nie in localStorage landen, ein 401 wird genau EINMAL
 * über /auth/refresh erneuert und die Anfrage wiederholt, mehrere parallele
 * 401 lösen nur EINE Erneuerung aus (sonst entwertet der Server die
 * Sitzungskette), und scheitert die Erneuerung, wird abgemeldet.
 *
 * Der Netzverkehr wird über den axios-Adapter abgefangen — kein Server nötig.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import axios from 'axios'
import api, {
  setAccessToken, getAccessToken, tokenVerwerfen, warAngemeldet, setAbmeldeHandler,
} from './api'

/** Baut einen Adapter, der pro URL eine feste Antwortfolge liefert. */
function adapterMit(antworten) {
  const aufrufe = []
  return {
    aufrufe,
    adapter: async (config) => {
      aufrufe.push({ url: config.url, auth: config.headers?.Authorization })
      const pfad = Object.keys(antworten).find((k) => config.url.includes(k))
      const naechste = antworten[pfad].shift()
      const antwort = { status: naechste.status, data: naechste.data ?? {}, headers: {}, config }
      if (naechste.status >= 400) {
        const fehler = new Error(`HTTP ${naechste.status}`)
        fehler.config = config
        fehler.response = antwort
        throw fehler
      }
      return antwort
    },
  }
}

beforeEach(() => {
  tokenVerwerfen()
  localStorage.clear()
  setAbmeldeHandler(null)
})

describe('Token-Ablage', () => {
  it('hält den Access-Token nur im Arbeitsspeicher, nie in localStorage', () => {
    setAccessToken('geheim.jwt')
    expect(getAccessToken()).toBe('geheim.jwt')
    expect(warAngemeldet()).toBe(true)
    expect(Object.values(localStorage)).not.toContain('geheim.jwt')
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('räumt beim Verwerfen auch Altlasten früherer Versionen weg', () => {
    localStorage.setItem('access_token', 'alt')
    localStorage.setItem('refresh_token', 'alt')
    setAccessToken('x')
    tokenVerwerfen()
    expect(getAccessToken()).toBeNull()
    expect(warAngemeldet()).toBe(false)
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('schickt den Token als Bearer-Header mit', async () => {
    const { adapter, aufrufe } = adapterMit({ '/auth/me': [{ status: 200, data: { id: 1 } }] })
    api.defaults.adapter = adapter
    setAccessToken('abc')
    await api.get('/auth/me')
    expect(aufrufe[0].auth).toBe('Bearer abc')
  })
})

describe('Stiller Refresh bei 401', () => {
  it('erneuert einmal und wiederholt die Anfrage mit dem neuen Token', async () => {
    const { adapter, aufrufe } = adapterMit({
      '/auth/refresh': [{ status: 200, data: { access_token: 'neu' } }],
      '/auth/me': [{ status: 401 }, { status: 200, data: { ok: true } }],
    })
    api.defaults.adapter = adapter
    axios.defaults.adapter = adapter
    setAccessToken('alt')

    const res = await api.get('/auth/me')
    expect(res.data).toEqual({ ok: true })
    expect(getAccessToken()).toBe('neu')
    expect(aufrufe.map((a) => a.url)).toEqual(['/auth/me', '/api/auth/refresh', '/auth/me'])
    expect(aufrufe[2].auth).toBe('Bearer neu')
  })

  it('löst bei parallelen 401 nur EINE Erneuerung aus', async () => {
    const { adapter, aufrufe } = adapterMit({
      '/auth/refresh': [{ status: 200, data: { access_token: 'neu' } }],
      '/auth/me': [{ status: 401 }, { status: 401 }, { status: 200 }, { status: 200 }],
    })
    api.defaults.adapter = adapter
    axios.defaults.adapter = adapter
    setAccessToken('alt')

    await Promise.all([api.get('/auth/me'), api.get('/auth/me')])
    expect(aufrufe.filter((a) => a.url === '/api/auth/refresh')).toHaveLength(1)
  })

  it('meldet ab, wenn auch die Erneuerung scheitert', async () => {
    const { adapter } = adapterMit({
      '/auth/refresh': [{ status: 401 }],
      '/auth/me': [{ status: 401 }],
    })
    api.defaults.adapter = adapter
    axios.defaults.adapter = adapter
    const abmelden = vi.fn()
    setAbmeldeHandler(abmelden)
    setAccessToken('alt')

    await expect(api.get('/auth/me')).rejects.toBeTruthy()
    expect(abmelden).toHaveBeenCalledTimes(1)
    expect(getAccessToken()).toBeNull()
    expect(warAngemeldet()).toBe(false)
  })

  it('versucht bei einem 401 der Anmeldung selbst KEINE Erneuerung', async () => {
    const { adapter, aufrufe } = adapterMit({
      '/auth/login': [{ status: 401 }],
      '/auth/refresh': [{ status: 200, data: { access_token: 'x' } }],
    })
    api.defaults.adapter = adapter
    axios.defaults.adapter = adapter

    await expect(api.post('/auth/login', {})).rejects.toBeTruthy()
    expect(aufrufe.map((a) => a.url)).toEqual(['/auth/login'])
  })
})
