import { describe, it, expect, beforeEach, vi } from 'vitest'
import { lazySeite } from './lazySeite'

// React.lazy speichert die Fabrik und ruft sie erst beim Rendern; für den Test
// reicht es, die Fabrik selbst zu holen: lazy() legt sie unter _payload._result ab.
const fabrik = (komponente) => komponente._payload._result

describe('lazySeite', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.unstubAllGlobals()
  })

  it('liefert das Modul durch und löscht den Reload-Merker', async () => {
    sessionStorage.setItem('deinezeit.chunk-neu-geladen', '1')
    const modul = { default: () => null }
    const k = lazySeite(() => Promise.resolve(modul))
    await expect(fabrik(k)()).resolves.toBe(modul)
    expect(sessionStorage.getItem('deinezeit.chunk-neu-geladen')).toBeNull()
  })

  it('lädt die Seite beim ersten Fehlschlag genau einmal neu', async () => {
    const reload = vi.fn()
    vi.stubGlobal('location', { ...window.location, reload })
    const k = lazySeite(() => Promise.reject(new Error('Failed to fetch dynamically imported module')))
    // Erster Versuch: Reload, Promise bleibt offen (kein Fehler nach oben)
    const p = fabrik(k)()
    await new Promise(r => setTimeout(r, 0))
    expect(reload).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem('deinezeit.chunk-neu-geladen')).toBe('1')
    // Zweiter Versuch nach dem Reload: kein weiterer Reload, Fehler geht zur ErrorBoundary
    await expect(fabrik(k)()).rejects.toThrow('Failed to fetch')
    expect(reload).toHaveBeenCalledTimes(1)
    void p
  })
})
