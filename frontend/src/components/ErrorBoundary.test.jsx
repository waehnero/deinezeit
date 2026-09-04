/**
 * ErrorBoundary (Audit UX-001, K-23): Ein Render-Fehler darf nicht in einer
 * weißen Seite enden, sondern in einer Meldung mit dem Fehlertext.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import ErrorBoundary from './ErrorBoundary'

function Kaputt() {
  throw new Error('Kaputte Komponente 42')
}

afterEach(() => vi.restoreAllMocks())

describe('ErrorBoundary', () => {
  it('rendert die Kinder, solange nichts passiert', () => {
    render(<ErrorBoundary><p>Alles gut</p></ErrorBoundary>)
    expect(screen.getByText('Alles gut')).toBeTruthy()
  })

  it('zeigt bei einem Render-Fehler Meldung, Fehlertext und Neuladen-Knopf', () => {
    // React protokolliert den Fehler laut auf console.error — im Test stumm.
    vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<ErrorBoundary><Kaputt /></ErrorBoundary>)
    expect(screen.getByText('Diese Ansicht konnte nicht angezeigt werden')).toBeTruthy()
    expect(screen.getByText('Kaputte Komponente 42')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Seite neu laden/ })).toBeTruthy()
    expect(console.error).toHaveBeenCalled()
  })
})
