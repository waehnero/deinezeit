/**
 * Zeiten-Import-Assistent: der Weg Datei → Zuordnung → Probelauf.
 *
 * Geprüft wird die Nahtstelle zum Server: Es dürfen nur ZUGEORDNETE Spalten
 * unter ihrem Zielfeld ankommen, der erste Aufruf muss ein Probelauf sein, und
 * ein PDF darf erst nach der Bestätigung gesendet werden.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ isAdmin: false, currentUser: { id: 'u1', full_name: 'Test Benutzer' } }),
}))
vi.mock('../services/api', () => ({
  usersApi: { list: vi.fn() },
  zeiterfassungApi: {
    importFelder: vi.fn(),
    importZeiten: vi.fn(),
    importPdf: vi.fn(),
  },
}))

import ZeitenImport from './ZeitenImport'
import { zeiterfassungApi } from '../services/api'

const FELDER = [
  { key: 'datum', name: 'Datum', synonyme: ['datum'] },
  { key: 'beginn', name: 'Beginn', synonyme: ['von', 'start'] },
  { key: 'ende', name: 'Ende', synonyme: ['bis'] },
  { key: 'notiz', name: 'Notiz', synonyme: ['tätigkeit'] },
]
const BERICHT = { geprueft: 1, anlegen: 1, angelegt: 0, uebersprungen: 0,
  minuten_gesamt: 270, beanstandungen: [] }

function dateiWaehlen(container, datei) {
  fireEvent.change(container.querySelector('input[type=file]'), { target: { files: [datei] } })
}

beforeEach(() => {
  vi.clearAllMocks()
  zeiterfassungApi.importFelder.mockResolvedValue({ data: FELDER })
  zeiterfassungApi.importZeiten.mockResolvedValue({ data: BERICHT })
})

describe('ZeitenImport', () => {
  it('schickt nur zugeordnete Spalten und zuerst einen Probelauf', async () => {
    const { container } = render(<ZeitenImport onClose={() => {}} onImported={() => {}} />)
    await waitFor(() => expect(zeiterfassungApi.importFelder).toHaveBeenCalled())

    dateiWaehlen(container, new File(
      ['Datum;Von;Bis;Kostenstelle\n03.08.2026;07:30;12:00;4711\n'], 'zeiten.csv', { type: 'text/csv' }))

    const pruefen = await screen.findByRole('button', { name: /Prüfen/ })
    expect(pruefen.disabled).toBe(false)            // Von/Bis wurden über Synonyme erkannt
    fireEvent.click(pruefen)

    await waitFor(() => expect(zeiterfassungApi.importZeiten).toHaveBeenCalled())
    const [rows, optionen] = zeiterfassungApi.importZeiten.mock.calls[0]
    expect(rows).toEqual([{ datum: '03.08.2026', beginn: '07:30', ende: '12:00' }])
    expect(optionen).toMatchObject({ dry_run: true, user_id: null })
    expect(await screen.findByText('4:30 h')).toBeTruthy()
  })

  it('sperrt das Prüfen, solange Beginn oder Ende fehlen', async () => {
    const { container } = render(<ZeitenImport onClose={() => {}} onImported={() => {}} />)
    await waitFor(() => expect(zeiterfassungApi.importFelder).toHaveBeenCalled())
    dateiWaehlen(container, new File(['Datum;Dauer\n03.08.2026;7,5\n'], 'dauer.csv'))
    const pruefen = await screen.findByRole('button', { name: /Prüfen/ })
    expect(pruefen.disabled).toBe(true)
    expect(screen.getByText(/Noch nicht zugeordnet: Beginn, Ende/)).toBeTruthy()
  })

  it('sendet ein PDF erst nach der Bestätigung an die KI', async () => {
    zeiterfassungApi.importPdf.mockResolvedValue({ data: {
      spalten: ['Datum', 'Von', 'Bis'],
      zeilen: [{ Datum: '03.08.2026', Von: '07:30', Bis: '12:00' }],
      hinweise: ['Zeile 1 handschriftlich korrigiert'] } })
    const { container } = render(<ZeitenImport onClose={() => {}} onImported={() => {}} />)
    await waitFor(() => expect(zeiterfassungApi.importFelder).toHaveBeenCalled())

    dateiWaehlen(container, new File(['%PDF-1.7'], 'zettel.pdf', { type: 'application/pdf' }))
    const senden = await screen.findByRole('button', { name: /An die KI senden/ })
    expect(zeiterfassungApi.importPdf).not.toHaveBeenCalled()
    expect(screen.getByText(/an den in den Einstellungen hinterlegten KI-Anbieter/)).toBeTruthy()

    fireEvent.click(senden)
    expect(await screen.findByText(/Von der KI gelesen — bitte gegenprüfen/)).toBeTruthy()
    expect(screen.getByText('Zeile 1 handschriftlich korrigiert')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Tabelle als CSV herunterladen/ })).toBeTruthy()
  })
})
