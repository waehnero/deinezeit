import React, { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import api, { settingsApi } from '../services/api'
import {
  ShieldCheck, Search, Loader2, AlertTriangle, Trash2, Save,
  FileText, Download, CheckCircle2, XCircle, Info,
} from 'lucide-react'

// ── Hilfen ────────────────────────────────────────────────────────────────────

const CATEGORY_LABELS = {
  time_entries:         'Zeiteinträge',
  invoices_total:       'Belege gesamt',
  invoices_open:        'Nicht abgeschlossene Rechnungen',
  invoices_retention:   'Aufbewahrungspflichtige Belege',
  invoices_snapshotted: 'Belege mit nachgezogenem Snapshot',
  planning_projects:    'Planungsprojekte',
  planning_tasks:       'Projektaufgaben',
  checklist_items:      'Checklisten-Zuweisungen',
  todos:                'Aufgaben (To-dos)',
  attachments:          'Datacenter-Dateien',
  attachments_deleted:  'Gelöschte Dateien',
}

function fmtDate(iso) {
  if (!iso) return '—'
  try { return new Date(iso).toLocaleDateString('de-AT') } catch { return iso }
}

function downloadPdfB64(b64, filename) {
  const bytes = atob(b64)
  const arr = new Uint8Array(bytes.length)
  for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
  const url = URL.createObjectURL(new Blob([arr], { type: 'application/pdf' }))
  const a = document.createElement('a')
  a.href = url; a.download = filename
  document.body.appendChild(a); a.click(); a.remove()
  URL.revokeObjectURL(url)
}

// ── Aufbewahrungsfrist ────────────────────────────────────────────────────────

function RetentionSetting({ settings, onSaved }) {
  const [years, setYears] = useState(settings.gdpr_retention_years || '7')
  const [saving, setSaving] = useState(false)

  const save = async () => {
    const n = parseInt(years, 10)
    if (!n || n < 1 || n > 30) { toast.error('Bitte 1–30 Jahre angeben'); return }
    setSaving(true)
    try {
      await settingsApi.update({ gdpr_retention_years: String(n) })
      toast.success('Aufbewahrungsfrist gespeichert')
      onSaved?.()
    } catch { toast.error('Fehler beim Speichern') }
    finally { setSaving(false) }
  }

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900 mb-1">Aufbewahrungsfrist</h3>
      <p className="text-xs text-gray-400 mb-3">
        Gesetzliche Aufbewahrungsfrist für Belege — Österreich: 7 Jahre (§ 132 BAO),
        Deutschland: 10 Jahre (§ 147 AO). Daraus wird berechnet, wann eingefrorene
        Belegdaten endgültig gelöscht werden dürfen.
      </p>
      <div className="flex items-center gap-2">
        <input type="number" min="1" max="30" value={years}
               onChange={e => setYears(e.target.value)}
               className="input w-24" />
        <span className="text-sm text-gray-500">Jahre</span>
        <button onClick={save} disabled={saving}
                className="btn-primary text-sm py-1.5 px-3 flex items-center gap-1.5 ml-2">
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
          Speichern
        </button>
      </div>
    </div>
  )
}

// ── Lösch-Wizard ──────────────────────────────────────────────────────────────

function LoeschWizard({ onErased }) {
  const [groups, setGroups] = useState([])
  const [recordId, setRecordId] = useState('')
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [filesAction, setFilesAction] = useState('none')
  const [note, setNote] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [erasing, setErasing] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    settingsApi.getContactOptions()
      .then(r => setGroups(r.data.groups || []))
      .catch(() => {})
  }, [])

  const loadReport = async (id) => {
    setRecordId(id); setReport(null); setResult(null); setConfirmed(false)
    if (!id) return
    setLoading(true)
    try {
      const r = await api.get(`/gdpr/records/${id}/report`)
      setReport(r.data)
    } catch { toast.error('Analyse konnte nicht geladen werden') }
    finally { setLoading(false) }
  }

  const erase = async () => {
    if (!confirmed || !report) return
    setErasing(true)
    try {
      const r = await api.post(`/gdpr/records/${recordId}/erase`,
                               { files_action: filesAction, note: note || null })
      downloadPdfB64(r.data.certificate_pdf_b64, r.data.certificate_filename)
      setResult(r.data)
      setReport(null); setRecordId(''); setConfirmed(false); setNote('')
      toast.success('Kontakt wurde DSGVO-konform gelöscht (anonymisiert)')
      onErased?.()
    } catch (err) {
      const detail = err.response?.data?.detail
      if (err.response?.status === 409 && detail?.blockers) {
        toast.error('Löschung blockiert — Details in der Analyse')
        loadReport(recordId)
      } else {
        toast.error(typeof detail === 'string' ? detail : 'Löschung fehlgeschlagen')
      }
    } finally { setErasing(false) }
  }

  const cats = report?.categories || {}
  const blockers = report?.blockers || []
  const alreadyAnonymized = !!report?.record?.anonymized_at

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900 mb-1">DSGVO-Löschung eines Kontakts</h3>
      <p className="text-xs text-gray-400 mb-3">
        Löschung durch Anonymisierung (Art. 17 DSGVO): Der Personenbezug wird in allen
        Modulen entfernt, Verweise und Auswertungen bleiben konsistent. Aufbewahrungspflichtige
        Belege bleiben mit eingefrorenem Empfänger erhalten. Dieser Vorgang ist <strong>unwiderruflich</strong>.
      </p>

      {/* Schritt 1: Kontakt wählen */}
      <label className="block text-xs font-medium text-gray-500 mb-1">Kontakt / Datensatz</label>
      <select value={recordId} onChange={e => loadReport(e.target.value)} className="input w-full max-w-md">
        <option value="">— Datensatz wählen —</option>
        {groups.map(g => (
          <optgroup key={g.type_slug} label={g.type_name}>
            {g.records.map(r => (
              <option key={r.id} value={r.id}>{r.display_name}</option>
            ))}
          </optgroup>
        ))}
      </select>

      {loading && (
        <div className="flex items-center gap-2 mt-4 text-sm text-gray-400">
          <Loader2 size={16} className="animate-spin" /> Analyse wird erstellt …
        </div>
      )}

      {/* Schritt 2: Betroffenheitsanalyse */}
      {report && (
        <div className="mt-4 border border-neutral-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Search size={15} className="text-gray-400" />
            <span className="text-sm font-medium text-gray-800">
              Betroffenheitsanalyse: {report.record.display_name}
            </span>
            {alreadyAnonymized && (
              <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">
                bereits anonymisiert am {fmtDate(report.record.anonymized_at)}
              </span>
            )}
          </div>

          <table className="w-full text-sm mb-3">
            <tbody>
              {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
                key in cats && (
                  <tr key={key} className="border-b border-neutral-100 last:border-0">
                    <td className="py-1 text-gray-600">{label}</td>
                    <td className="py-1 text-right font-medium">{cats[key]}</td>
                  </tr>
                )
              ))}
            </tbody>
          </table>

          {report.retention?.deletable_after && (
            <p className="text-xs text-gray-400 flex items-start gap-1.5 mb-3">
              <Info size={13} className="mt-0.5 shrink-0" />
              Aufbewahrungspflichtige Belegdaten (eingefrorene Empfängerdaten) bleiben bis
              zum {fmtDate(report.retention.deletable_after)} erhalten
              ({report.retention.years} Jahre Frist) und sind bis dahin für andere Zwecke gesperrt.
            </p>
          )}

          {/* Blocker */}
          {blockers.length > 0 && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 mb-1">
              <div className="flex items-center gap-1.5 text-sm font-medium text-red-700 mb-1">
                <XCircle size={15} /> Löschung derzeit nicht möglich
              </div>
              <ul className="text-xs text-red-600 list-disc ml-5">
                {blockers.map(b => <li key={b.code}>{b.label}</li>)}
              </ul>
            </div>
          )}

          {/* Schritt 3: Optionen + Bestätigung */}
          {blockers.length === 0 && !alreadyAnonymized && (
            <div className="border-t border-neutral-100 pt-3 mt-2">
              <label className="block text-xs font-medium text-gray-500 mb-1.5">
                Datacenter-Dateien dieses Kontakts ({cats.attachments ?? 0})
              </label>
              <div className="space-y-1.5 mb-3">
                <label className="flex items-start gap-2 text-sm text-gray-700">
                  <input type="radio" name="filesAction" checked={filesAction === 'none'}
                         onChange={() => setFilesAction('none')} className="mt-0.5" />
                  <span>Dateien <strong>behalten</strong> — nur der Kontaktbezug wird anonymisiert
                    <span className="block text-xs text-gray-400">
                      Empfohlen, wenn die Dateien Belege mit Aufbewahrungspflicht sind.
                    </span>
                  </span>
                </label>
                <label className="flex items-start gap-2 text-sm text-gray-700">
                  <input type="radio" name="filesAction" checked={filesAction === 'deleted'}
                         onChange={() => setFilesAction('deleted')} className="mt-0.5" />
                  <span>Dateien <strong>endgültig löschen</strong> (aus Datenbank und Speicher)
                    <span className="block text-xs text-gray-400">
                      Wählen, wenn die Dateien selbst personenbezogene Inhalte haben und
                      keiner Aufbewahrungspflicht unterliegen.
                    </span>
                  </span>
                </label>
              </div>

              <label className="block text-xs font-medium text-gray-500 mb-1">
                Anmerkung (optional, erscheint auf der Löschbescheinigung)
              </label>
              <input type="text" value={note} onChange={e => setNote(e.target.value)}
                     placeholder="z.B. Löschung auf Anfrage vom 01.07.2026"
                     className="input w-full max-w-md mb-3" />

              <label className="flex items-center gap-2 text-sm text-gray-700 mb-3">
                <input type="checkbox" checked={confirmed}
                       onChange={e => setConfirmed(e.target.checked)} />
                Ich bestätige die <strong>unwiderrufliche</strong> Löschung
                (Anonymisierung) dieses Kontakts.
              </label>

              <button onClick={erase} disabled={!confirmed || erasing}
                      className="btn-danger text-sm py-2 px-4 flex items-center gap-2 disabled:opacity-50">
                {erasing ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                Jetzt DSGVO-konform löschen
              </button>
              <p className="text-xs text-gray-400 mt-2 flex items-center gap-1.5">
                <FileText size={13} />
                Die Löschbescheinigung für die betroffene Person wird automatisch heruntergeladen;
                ein anonymisiertes Protokoll wird im Datacenter abgelegt.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Ergebnis */}
      {result && (
        <div className="mt-4 bg-green-50 border border-green-200 rounded-xl p-4">
          <div className="flex items-center gap-1.5 text-sm font-medium text-green-700 mb-1">
            <CheckCircle2 size={15} /> Löschung durchgeführt
          </div>
          <p className="text-xs text-green-700">
            Vorgangs-ID: <code>{result.log_id}</code>
            {result.filed_attachment_id
              ? ' — anonymisiertes Protokoll wurde im Datacenter abgelegt.'
              : ' — Hinweis: Ablage im Datacenter nicht möglich (Speicher prüfen); das Protokoll ist in der Datenbank gesichert.'}
          </p>
          <button
            onClick={() => downloadPdfB64(result.certificate_pdf_b64, result.certificate_filename)}
            className="btn-secondary text-xs py-1 px-2.5 mt-2 flex items-center gap-1.5">
            <Download size={13} /> Löschbescheinigung erneut herunterladen
          </button>
          <p className="text-xs text-green-600 mt-1.5">
            Achtung: Die Bescheinigung enthält die gelöschten Personendaten und wird
            nirgends gespeichert — bitte jetzt sichern und an die betroffene Person übergeben.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Löschprotokoll ────────────────────────────────────────────────────────────

function LoeschProtokoll({ reloadKey }) {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.get('/gdpr/log')
      .then(r => setLogs(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [reloadKey])

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-900 mb-1">Löschprotokoll</h3>
      <p className="text-xs text-gray-400 mb-3">
        Nachweis durchgeführter DSGVO-Löschungen (Rechenschaftspflicht, Art. 5 Abs. 2) —
        bewusst ohne personenbezogene Daten.
      </p>
      {loading ? (
        <div className="text-sm text-gray-400 flex items-center gap-2">
          <Loader2 size={15} className="animate-spin" /> Laden …
        </div>
      ) : logs.length === 0 ? (
        <p className="text-sm text-gray-400">Noch keine Löschungen durchgeführt.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400 border-b border-neutral-200">
              <th className="py-1.5 pr-2">Datum</th>
              <th className="py-1.5 pr-2">Vorgangs-ID</th>
              <th className="py-1.5 pr-2">Durchgeführt von</th>
              <th className="py-1.5 pr-2 text-right">Einträge</th>
              <th className="py-1.5">Dateien</th>
            </tr>
          </thead>
          <tbody>
            {logs.map(l => {
              const total = Object.entries(l.categories || {})
                .filter(([k]) => !k.startsWith('invoices_') || k === 'invoices_total')
                .reduce((s, [, v]) => s + (typeof v === 'number' ? v : 0), 0)
              return (
                <tr key={l.id} className="border-b border-neutral-100 last:border-0">
                  <td className="py-1.5 pr-2 whitespace-nowrap">{fmtDate(l.executed_at)}</td>
                  <td className="py-1.5 pr-2"><code className="text-xs">{l.id.slice(0, 8)}</code></td>
                  <td className="py-1.5 pr-2">{l.executed_by || '—'}</td>
                  <td className="py-1.5 pr-2 text-right">{total}</td>
                  <td className="py-1.5 text-xs text-gray-500">
                    {l.files_action === 'deleted' ? 'gelöscht' : 'behalten'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ── Hauptkomponente ───────────────────────────────────────────────────────────

export default function DatenschutzEinstellungen({ settings, onSaved }) {
  const [reloadKey, setReloadKey] = useState(0)

  return (
    <div className="space-y-8">
      <div className="flex items-start gap-2 bg-blue-50 border border-blue-100 rounded-xl p-3">
        <ShieldCheck size={17} className="text-blue-500 mt-0.5 shrink-0" />
        <p className="text-xs text-blue-700 leading-relaxed">
          Umsetzung des Rechts auf Löschung (Art. 17 DSGVO) durch Anonymisierung — von den
          Datenschutzbehörden (AT/DE) als Löschung anerkannt. Kein Rechtsrat: Im Zweifel
          bitte rechtliche Beratung einholen.
        </p>
      </div>

      <RetentionSetting settings={settings} onSaved={onSaved} />
      <div className="border-t border-neutral-100 pt-6">
        <LoeschWizard onErased={() => setReloadKey(k => k + 1)} />
      </div>
      <div className="border-t border-neutral-100 pt-6">
        <LoeschProtokoll reloadKey={reloadKey} />
      </div>
    </div>
  )
}
