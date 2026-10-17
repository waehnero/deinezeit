/**
 * Mail-Konten (Sicherheitsbefund zentrale Zugangsdaten, Oktober 2026).
 *
 * Maßgeblich ist die Prüfung im Backend (tests/test_mailimport_sicherheit.py).
 * Hier wird nur festgehalten, dass die Oberfläche das Modell richtig
 * wiedergibt: Persönliche Konten bieten die zentralen Zugangsdaten gar nicht
 * erst an und schicken sie nie mit; ein gesperrtes Konto zeigt den Grund.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

vi.mock('react-hot-toast', () => ({ default: { success: vi.fn(), error: vi.fn() } }))
vi.mock('../services/api', () => ({
  mailImportApi: {
    listAccounts: vi.fn(),
    createAccount: vi.fn(),
    updateAccount: vi.fn(),
    confirmCentral: vi.fn(),
  },
  groupsApi: { list: vi.fn() },
}))

import MailKonten from './MailImportVerwaltung'
import { mailImportApi, groupsApi } from '../services/api'

const altKonto = {
  id: 'k1', owner_user_id: 'u1', name: 'Altes Postfach', protocol: 'imap',
  imap_host: 'mail.example.com', imap_port: 993, imap_ssl: true, imap_user: '',
  folder: 'INBOX', use_central_credentials: true, auto_scan: false,
  scan_interval_minutes: 15, is_active: true, has_secret: false,
  zentral_sperrgrund: 'Zentrale Zugangsdaten sind für persönliche Mail-Konten nicht zulässig.',
}

beforeEach(() => {
  vi.clearAllMocks()
  groupsApi.list.mockResolvedValue({ data: [{ id: 'g1', name: 'Office-Team' }] })
})

describe('Persönliche Mail-Konten', () => {
  it('bieten keine zentralen Zugangsdaten an', async () => {
    mailImportApi.listAccounts.mockResolvedValue({ data: [] })
    render(<MailKonten />)
    fireEvent.click(await screen.findByText(/Konto anbinden/))
    expect(screen.queryByText(/Zentrale E-Mail-Zugangsdaten verwenden/)).toBeNull()
    expect(screen.queryByText(/Wer darf dieses Konto verwenden/)).toBeNull()
  })

  it('zeigen bei Altkonten den Sperrgrund und stellen beim Speichern auf eigene Daten um', async () => {
    mailImportApi.listAccounts.mockResolvedValue({ data: [altKonto] })
    mailImportApi.updateAccount.mockResolvedValue({ data: {} })
    render(<MailKonten />)
    expect(await screen.findByText(/nicht zulässig/)).toBeTruthy()

    fireEvent.click(screen.getByTitle('Bearbeiten'))
    fireEvent.change(screen.getByPlaceholderText('name@example.com'), { target: { value: 'ich@example.com' } })
    fireEvent.change(screen.getByPlaceholderText('••••••••'), { target: { value: 'eigenes-pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Speichern' }))

    await waitFor(() => expect(mailImportApi.updateAccount).toHaveBeenCalled())
    const payload = mailImportApi.updateAccount.mock.calls[0][1]
    expect(payload.use_central_credentials).toBe(false)
    expect(payload).not.toHaveProperty('freigabe_alle')
  })
})

describe('Globale Mail-Konten (Admin)', () => {
  it('bieten zentrale Zugangsdaten und die Freigabe nach Gruppen an', async () => {
    mailImportApi.listAccounts.mockResolvedValue({ data: [] })
    mailImportApi.createAccount.mockResolvedValue({ data: {} })
    render(<MailKonten global />)
    fireEvent.click(await screen.findByText(/Konto anbinden/))
    expect(screen.getByText(/Zentrale E-Mail-Zugangsdaten verwenden/)).toBeTruthy()
    fireEvent.click(await screen.findByLabelText('Office-Team'))

    fireEvent.change(screen.getByPlaceholderText('z.B. Office-Postfach'), { target: { value: 'Office' } })
    fireEvent.change(screen.getByPlaceholderText('imap.example.com'), { target: { value: 'imap.firma.example' } })
    fireEvent.click(screen.getByText(/Zentrale E-Mail-Zugangsdaten verwenden/))
    fireEvent.click(screen.getByRole('button', { name: 'Anlegen' }))

    await waitFor(() => expect(mailImportApi.createAccount).toHaveBeenCalled())
    const payload = mailImportApi.createAccount.mock.calls[0][0]
    expect(payload.is_global).toBe(true)
    expect(payload.use_central_credentials).toBe(true)
    expect(payload.freigabe_gruppen).toEqual(['g1'])
    expect(payload.freigabe_alle).toBe(false)
  })
})
