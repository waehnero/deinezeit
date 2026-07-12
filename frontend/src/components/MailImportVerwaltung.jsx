import { useState, useEffect } from 'react'
import {
  Mail, Plus, Trash2, Pencil, Loader2, X, FolderSearch, RefreshCw,
  AlertCircle, Sparkles, Check,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { mailImportApi } from '../services/api'

/**
 * Verwaltung der Mail-Import-Konten (Aufgabenmodul, Etappe 3).
 *
 * <MailKonten />          – persönliche Konten (Profil-Seite)
 * <MailKonten global />   – globale Konten (App-Einstellungen, Admin)
 * <KiEinstellungen />     – KI-Provider/-Key (App-Einstellungen, Admin)
 */

const inputCls = 'w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary-400'
const labelCls = 'block text-xs font-medium text-neutral-500 mb-1'

// ── KI-Einstellungen (Admin) ──────────────────────────────────────────────────
export function KiEinstellungen() {
  const [provider, setProvider] = useState('anthropic')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [hasKey, setHasKey] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    mailImportApi.getKiSettings().then(r => {
      setProvider(r.data.provider)
      setModel(r.data.model || '')
      setHasKey(r.data.has_api_key)
    }).catch(() => {})
  }, [])

  const speichern = async () => {
    setSaving(true)
    try {
      const { data } = await mailImportApi.updateKiSettings({
        provider, model: model || null, api_key: apiKey || null,
      })
      setHasKey(data.has_api_key)
      setApiKey('')
      toast.success('KI-Einstellungen gespeichert')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Sparkles size={18} className="text-primary-600" />
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">KI-Assistent (Mail-Import)</h3>
      </div>
      <p className="text-sm text-neutral-500">
        Der KI-Assistent liest die Nachrichten der angebundenen Mail-Ordner und
        schlägt daraus Aufgaben vor. Der API-Key wird verschlüsselt gespeichert.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>Provider</label>
          <select value={provider} onChange={e => setProvider(e.target.value)} className={inputCls}>
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai">OpenAI (GPT)</option>
          </select>
        </div>
        <div>
          <label className={labelCls}>Modell (leer = Standard)</label>
          <input value={model} onChange={e => setModel(e.target.value)}
            placeholder={provider === 'anthropic' ? 'claude-sonnet-4-5' : 'gpt-4o-mini'}
            className={inputCls} />
        </div>
      </div>
      <div>
        <label className={labelCls}>
          API-Key {hasKey && <span className="text-green-600">(hinterlegt — leer lassen zum Behalten)</span>}
        </label>
        <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
          placeholder={hasKey ? '••••••••••••' : 'API-Key eingeben'} className={inputCls} />
      </div>
      <button onClick={speichern} disabled={saving}
        className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2">
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
        Speichern
      </button>
    </div>
  )
}

// ── Konto-Dialog (anlegen/bearbeiten) ─────────────────────────────────────────
function KontoDialog({ konto, global, onClose, onSaved }) {
  const isNew = !konto?.id
  const [form, setForm] = useState({
    name: konto?.name || '',
    protocol: konto?.protocol || 'imap',
    imap_host: konto?.imap_host || '',
    imap_port: konto?.imap_port || '',
    imap_ssl: konto?.imap_ssl ?? true,
    imap_user: konto?.imap_user || '',
    graph_tenant_id: konto?.graph_tenant_id || '',
    graph_client_id: konto?.graph_client_id || '',
    graph_mailbox: konto?.graph_mailbox || '',
    folder: konto?.folder || 'INBOX',
    use_central_credentials: konto?.use_central_credentials ?? false,
    flag_erledigt: konto?.flag_erledigt ?? false,
    auto_scan: konto?.auto_scan ?? false,
    scan_interval_minutes: konto?.scan_interval_minutes || 15,
    secret: '',
  })
  const [saving, setSaving] = useState(false)
  const [folders, setFolders] = useState(null)
  const [testing, setTesting] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const istImap = form.protocol === 'imap'
  const zentral = form.use_central_credentials

  const speichern = async () => {
    if (!form.name.trim()) return toast.error('Bitte einen Namen eingeben')
    if (istImap && !form.imap_host) return toast.error('IMAP-Server angeben')
    if (!zentral) {
      if (istImap && !form.imap_user) return toast.error('IMAP-Benutzer angeben')
      if (!istImap && (!form.graph_tenant_id || !form.graph_client_id || !form.graph_mailbox))
        return toast.error('Tenant-ID, Client-ID und Mailbox angeben')
      if (isNew && !form.secret) return toast.error(istImap ? 'Passwort angeben' : 'Client-Secret angeben')
    }

    setSaving(true)
    const payload = {
      name: form.name.trim(),
      imap_host: form.imap_host || null,
      imap_port: form.imap_port ? Number(form.imap_port) : null,
      imap_ssl: form.imap_ssl,
      imap_user: form.imap_user || null,
      graph_tenant_id: form.graph_tenant_id || null,
      graph_client_id: form.graph_client_id || null,
      graph_mailbox: form.graph_mailbox || null,
      folder: form.folder || 'INBOX',
      use_central_credentials: form.use_central_credentials,
      flag_erledigt: form.flag_erledigt,
      auto_scan: form.auto_scan,
      scan_interval_minutes: Number(form.scan_interval_minutes) || 15,
      secret: form.secret || null,
    }
    try {
      if (isNew) {
        await mailImportApi.createAccount({ ...payload, protocol: form.protocol, is_global: !!global })
        toast.success('Mail-Konto angelegt')
      } else {
        await mailImportApi.updateAccount(konto.id, payload)
        toast.success('Mail-Konto gespeichert')
      }
      onSaved()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Speichern')
    } finally {
      setSaving(false)
    }
  }

  const ordnerTesten = async () => {
    if (isNew) return toast.error('Bitte zuerst speichern, dann Verbindung testen')
    setTesting(true)
    setFolders(null)
    try {
      const { data } = await mailImportApi.listFolders(konto.id)
      setFolders(data)
      toast.success(`Verbindung OK — ${data.length} Ordner gefunden`)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Verbindung fehlgeschlagen')
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <div className="bg-surface rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-auto"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100">
          <h2 className="font-semibold text-neutral-900">
            {isNew ? (global ? 'Neues globales Mail-Konto' : 'Neues Mail-Konto') : 'Mail-Konto bearbeiten'}
          </h2>
          <button onClick={onClose} className="text-neutral-400 hover:text-neutral-700"><X size={18} /></button>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Name *</label>
              <input value={form.name} onChange={e => set('name', e.target.value)}
                placeholder="z.B. Office-Postfach" className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Typ</label>
              <select value={form.protocol} onChange={e => set('protocol', e.target.value)}
                disabled={!isNew} className={`${inputCls} disabled:bg-neutral-50`}>
                <option value="imap">IMAP</option>
                <option value="graph">Microsoft 365 (Graph)</option>
              </select>
            </div>
          </div>

          {/* Zugangsdaten aus Einstellungen -> System -> E-Mail übernehmen */}
          <label className="flex items-start gap-2 text-sm text-neutral-700 cursor-pointer select-none bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2.5">
            <input type="checkbox" checked={form.use_central_credentials}
              onChange={e => set('use_central_credentials', e.target.checked)}
              className="rounded border-gray-300 mt-0.5" />
            <span>
              Zentrale E-Mail-Zugangsdaten verwenden
              <span className="block text-xs text-neutral-400">
                {istImap
                  ? 'Benutzer/Passwort aus Einstellungen → System → E-Mail (SMTP)'
                  : 'Tenant-ID, Client-ID und Client-Secret aus Einstellungen → System → E-Mail (Microsoft Graph)'}
              </span>
            </span>
          </label>

          {istImap ? (
            <>
              <div className="grid grid-cols-3 gap-3">
                <div className="col-span-2">
                  <label className={labelCls}>IMAP-Server *</label>
                  <input value={form.imap_host} onChange={e => set('imap_host', e.target.value)}
                    placeholder="imap.example.com" className={inputCls} />
                </div>
                <div>
                  <label className={labelCls}>Port</label>
                  <input type="number" value={form.imap_port} onChange={e => set('imap_port', e.target.value)}
                    placeholder="993" className={inputCls} />
                </div>
              </div>
              {!zentral && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Benutzer *</label>
                    <input value={form.imap_user} onChange={e => set('imap_user', e.target.value)}
                      placeholder="name@example.com" className={inputCls} />
                  </div>
                  <div>
                    <label className={labelCls}>
                      Passwort {!isNew && <span className="text-neutral-400">(leer = unverändert)</span>}
                    </label>
                    <input type="password" value={form.secret} onChange={e => set('secret', e.target.value)}
                      placeholder={isNew ? 'App-Passwort' : '••••••••'} className={inputCls} />
                  </div>
                </div>
              )}
              <label className="flex items-center gap-1.5 text-sm text-neutral-600 cursor-pointer select-none">
                <input type="checkbox" checked={form.imap_ssl} onChange={e => set('imap_ssl', e.target.checked)}
                  className="rounded border-gray-300" /> SSL/TLS (Port 993)
              </label>
            </>
          ) : (
            <>
              {!zentral && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className={labelCls}>Tenant-ID *</label>
                    <input value={form.graph_tenant_id} onChange={e => set('graph_tenant_id', e.target.value)} className={inputCls} />
                  </div>
                  <div>
                    <label className={labelCls}>Client-ID *</label>
                    <input value={form.graph_client_id} onChange={e => set('graph_client_id', e.target.value)} className={inputCls} />
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>Mailbox {zentral ? '' : '*'}</label>
                  <input value={form.graph_mailbox} onChange={e => set('graph_mailbox', e.target.value)}
                    placeholder={zentral ? 'leer = Absenderadresse aus E-Mail-Einstellungen' : 'office@firma.at'}
                    className={inputCls} />
                </div>
                {!zentral && (
                  <div>
                    <label className={labelCls}>
                      Client-Secret {!isNew && <span className="text-neutral-400">(leer = unverändert)</span>}
                    </label>
                    <input type="password" value={form.secret} onChange={e => set('secret', e.target.value)}
                      placeholder={isNew ? 'Secret' : '••••••••'} className={inputCls} />
                  </div>
                )}
              </div>
              <label className="flex items-start gap-2 text-sm text-neutral-700 cursor-pointer select-none">
                <input type="checkbox" checked={form.flag_erledigt}
                  onChange={e => set('flag_erledigt', e.target.checked)}
                  className="rounded border-gray-300 mt-0.5" />
                <span>
                  Outlook-Flagge an der Ursprungs-Mail pflegen
                  <span className="block text-xs text-neutral-400">
                    Vorschlag erkannt → rote Flagge · als Aufgabe übernommen → Erledigt-Hakerl ·
                    verworfen → Flagge bleibt rot (benötigt „Mail.ReadWrite")
                  </span>
                </span>
              </label>
              <p className="text-xs text-neutral-400">
                Benötigt eine Azure-App-Registrierung mit Applikationsberechtigung
                „{form.flag_erledigt ? 'Mail.ReadWrite' : 'Mail.Read'}"
                {zentral && ' (zusätzlich zu „Mail.Send" der zentralen App)'}.
              </p>
            </>
          )}

          <div className="grid grid-cols-2 gap-3 items-end">
            <div>
              <label className={labelCls}>Zu scannender Ordner</label>
              <input value={form.folder} onChange={e => set('folder', e.target.value)}
                placeholder={istImap ? 'INBOX' : 'inbox'} className={inputCls} />
            </div>
            <button onClick={ordnerTesten} disabled={testing || isNew}
              title={isNew ? 'Erst speichern, dann testen' : 'Verbindung testen und Ordner auflisten'}
              className="flex items-center justify-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-gray-300 text-neutral-600 hover:bg-neutral-50 disabled:opacity-50">
              {testing ? <Loader2 size={14} className="animate-spin" /> : <FolderSearch size={14} />}
              Verbindung testen
            </button>
          </div>

          {folders && (
            <div className="border border-neutral-200 rounded-lg max-h-36 overflow-auto divide-y divide-neutral-100">
              {folders.map(f => (
                <button key={f} onClick={() => set('folder', f)}
                  className={`w-full text-left px-3 py-1.5 text-sm hover:bg-primary-50
                    ${form.folder === f ? 'bg-primary-50 text-primary-700 font-medium' : 'text-neutral-700'}`}>
                  {f}
                </button>
              ))}
            </div>
          )}

          <div className="border-t border-neutral-100 pt-3 grid grid-cols-2 gap-3 items-center">
            <label className="flex items-center gap-1.5 text-sm text-neutral-600 cursor-pointer select-none">
              <input type="checkbox" checked={form.auto_scan} onChange={e => set('auto_scan', e.target.checked)}
                className="rounded border-gray-300" /> Automatisch scannen
            </label>
            <div className={form.auto_scan ? '' : 'opacity-40 pointer-events-none'}>
              <label className={labelCls}>Intervall (Minuten)</label>
              <input type="number" min={5} max={1440} value={form.scan_interval_minutes}
                onChange={e => set('scan_interval_minutes', e.target.value)} className={inputCls} />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 px-5 py-4 border-t border-neutral-100">
          <button onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg border border-gray-300 text-neutral-700 hover:bg-neutral-50">
            Abbrechen
          </button>
          <button onClick={speichern} disabled={saving}
            className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50 flex items-center gap-2">
            {saving && <Loader2 size={14} className="animate-spin" />}
            {isNew ? 'Anlegen' : 'Speichern'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Kontenliste ───────────────────────────────────────────────────────────────
export default function MailKonten({ global = false }) {
  const [konten, setKonten] = useState([])
  const [loading, setLoading] = useState(true)
  const [dialog, setDialog] = useState(null)   // null | {} | konto
  const [scanning, setScanning] = useState({}) // id -> true

  const load = async () => {
    setLoading(true)
    try {
      const { data } = await mailImportApi.listAccounts()
      // Profil zeigt nur persönliche, Einstellungen nur globale Konten
      setKonten(data.filter(a => global ? !a.owner_user_id : !!a.owner_user_id))
    } catch {
      toast.error('Mail-Konten konnten nicht geladen werden')
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const loeschen = async (konto) => {
    if (!window.confirm(`Mail-Konto „${konto.name}" wirklich löschen? Auch die zugehörigen Vorschläge werden entfernt.`)) return
    try {
      await mailImportApi.deleteAccount(konto.id)
      toast.success('Mail-Konto gelöscht')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Löschen')
    }
  }

  const scannen = async (konto) => {
    setScanning(s => ({ ...s, [konto.id]: true }))
    try {
      const { data } = await mailImportApi.scan(konto.id)
      toast.success(data.neue_vorschlaege > 0
        ? `${data.neue_vorschlaege} neue Aufgabenvorschläge — siehe Modul Aufgaben`
        : 'Keine neuen Aufgabenvorschläge')
      load()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Scan fehlgeschlagen')
    } finally {
      setScanning(s => ({ ...s, [konto.id]: false }))
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Mail size={18} className="text-primary-600" />
        <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
          {global ? 'Globale Mail-Konten (Aufgaben-Import)' : 'Meine Mail-Konten (Aufgaben-Import)'}
        </h3>
        <button onClick={() => setDialog({})}
          className="ml-auto flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700">
          <Plus size={15} /> Konto anbinden
        </button>
      </div>
      <p className="text-sm text-neutral-500">
        Aus den Nachrichten des gewählten Ordners schlägt der KI-Assistent Aufgaben vor,
        die im Modul Aufgaben bestätigt werden können.
        {global && ' Vorschläge aus globalen Konten sehen alle Benutzer.'}
      </p>

      {loading ? (
        <div className="flex justify-center py-6"><Loader2 size={20} className="animate-spin text-primary-400" /></div>
      ) : konten.length === 0 ? (
        <p className="text-sm text-neutral-400 py-2">Noch kein Mail-Konto angebunden.</p>
      ) : (
        <div className="border border-neutral-200 rounded-xl divide-y divide-neutral-100">
          {konten.map(k => (
            <div key={k.id} className="flex items-center gap-3 px-4 py-3">
              <Mail size={16} className="text-neutral-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-neutral-900 truncate">
                  {k.name}
                  <span className="ml-2 text-xs font-normal text-neutral-400">
                    {k.protocol === 'imap' ? `IMAP · ${k.imap_host}` : `Microsoft · ${k.graph_mailbox}`} · Ordner: {k.folder}
                  </span>
                </p>
                <p className="text-xs text-neutral-400">
                  {k.auto_scan ? `Auto-Scan alle ${k.scan_interval_minutes} Min` : 'Nur manueller Scan'}
                  {k.use_central_credentials && ' · zentrale Zugangsdaten'}
                  {k.last_scan_at && ` · zuletzt: ${new Date(k.last_scan_at).toLocaleString('de-AT')}`}
                </p>
                {k.last_error && (
                  <p className="text-xs text-red-600 flex items-center gap-1 mt-0.5">
                    <AlertCircle size={12} /> {k.last_error.slice(0, 160)}
                  </p>
                )}
              </div>
              <button onClick={() => scannen(k)} disabled={scanning[k.id]} title="Jetzt scannen"
                className="p-1.5 text-neutral-400 hover:text-primary-600">
                {scanning[k.id] ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
              </button>
              <button onClick={() => setDialog(k)} title="Bearbeiten"
                className="p-1.5 text-neutral-400 hover:text-primary-600"><Pencil size={16} /></button>
              <button onClick={() => loeschen(k)} title="Löschen"
                className="p-1.5 text-neutral-400 hover:text-red-600"><Trash2 size={16} /></button>
            </div>
          ))}
        </div>
      )}

      {dialog !== null && (
        <KontoDialog konto={dialog.id ? dialog : null} global={global}
          onClose={() => setDialog(null)}
          onSaved={() => { setDialog(null); load() }} />
      )}
    </div>
  )
}
