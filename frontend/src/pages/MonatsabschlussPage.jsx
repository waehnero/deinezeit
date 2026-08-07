import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { periodApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import PageHeader from '../components/PageHeader'
import {
  CalendarCheck, RefreshCw, ArrowLeft, Lock, LockOpen, Download,
  CheckCircle2, AlertTriangle, Info, History,
} from 'lucide-react'

const THIS_YEAR = new Date().getFullYear()

function fmtEuro(n) {
  return Number(n || 0).toLocaleString('de-AT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €'
}
function fmtDateTime(d) {
  return d ? new Date(d).toLocaleString('de-AT') : '—'
}
function fmtBytes(n) {
  return n > 1024 * 1024 ? (n / 1024 / 1024).toFixed(1) + ' MB' : Math.round(n / 1024) + ' KB'
}

const STATUS = {
  offen:            { label: 'Offen',           cls: 'bg-neutral-100 text-neutral-600' },
  abgeschlossen:    { label: 'Abgeschlossen',   cls: 'bg-green-100 text-green-700' },
  wieder_geoeffnet: { label: 'Wieder geöffnet', cls: 'bg-amber-100 text-amber-700' },
}

export default function MonatsabschlussPage() {
  const navigate = useNavigate()
  const { isAdmin } = useAuth()
  const [jahr, setJahr] = useState(THIS_YEAR)
  const [monate, setMonate] = useState([])
  const [gewaehlt, setGewaehlt] = useState(null)
  const [pruefung, setPruefung] = useState(null)
  const [historie, setHistorie] = useState([])
  const [laden, setLaden] = useState(true)
  const [laeuft, setLaeuft] = useState(false)

  const monateLaden = useCallback(async () => {
    setLaden(true)
    try {
      const res = await periodApi.list(jahr)
      setMonate(res.data)
    } catch { toast.error('Monate konnten nicht geladen werden') }
    finally { setLaden(false) }
  }, [jahr])

  useEffect(() => { monateLaden() }, [monateLaden])

  const detailsLaden = useCallback(async (monat) => {
    try {
      const [p, h] = await Promise.all([
        periodApi.check(jahr, monat),
        periodApi.handovers(jahr, monat),
      ])
      setPruefung(p.data)
      setHistorie(h.data)
    } catch { toast.error('Prüfung konnte nicht geladen werden') }
  }, [jahr])

  function waehlen(monat) {
    setGewaehlt(monat)
    setPruefung(null)
    detailsLaden(monat)
  }

  async function abschliessen() {
    if (!window.confirm(
      `${pruefung.monatsname} ${jahr} abschließen?\n\n` +
      'Danach lassen sich in diesem Monat keine Belege mehr anlegen oder ändern. ' +
      'Ein Admin kann den Monat mit Begründung wieder öffnen.')) return
    setLaeuft(true)
    try {
      await periodApi.close(jahr, gewaehlt)
      toast.success('Monat abgeschlossen')
      await monateLaden(); await detailsLaden(gewaehlt)
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler beim Abschließen') }
    finally { setLaeuft(false) }
  }

  async function wiederOeffnen() {
    const grund = window.prompt(
      'Warum soll dieser Monat wieder geöffnet werden?\n' +
      'Die Begründung bleibt am Monat dokumentiert.')
    if (grund === null) return
    setLaeuft(true)
    try {
      await periodApi.reopen(jahr, gewaehlt, grund)
      toast.success('Monat wieder geöffnet')
      await monateLaden(); await detailsLaden(gewaehlt)
    } catch (e) { toast.error(e.response?.data?.detail || 'Fehler') }
    finally { setLaeuft(false) }
  }

  async function paketLaden() {
    setLaeuft(true)
    try {
      const res = await periodApi.package(jahr, gewaehlt)
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/zip' }))
      const a = document.createElement('a')
      a.href = url; a.download = `uebergabe_${jahr}-${String(gewaehlt).padStart(2, '0')}.zip`
      a.click(); URL.revokeObjectURL(url)
      toast.success('Übergabepaket erstellt')
      detailsLaden(gewaehlt)
    } catch (e) { toast.error(e.response?.data?.detail || 'Paket konnte nicht erstellt werden') }
    finally { setLaeuft(false) }
  }

  if (laden) return <div className="flex justify-center py-16"><RefreshCw size={22} className="animate-spin text-neutral-400" /></div>

  const monat = monate.find(m => m.monat === gewaehlt)

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button onClick={() => navigate('/buchhaltung')} className="p-2 rounded-lg hover:bg-neutral-100 text-neutral-500">
          <ArrowLeft size={18} />
        </button>
        <PageHeader icon={CalendarCheck} title="Monatsabschluss"
          subtitle="Prüfen, abschließen und an die Buchhaltung übergeben" />
        <select value={jahr} onChange={e => { setJahr(Number(e.target.value)); setGewaehlt(null) }}
          className="ml-auto border border-neutral-200 rounded-lg px-3 py-2 text-sm">
          {[THIS_YEAR + 1, THIS_YEAR, THIS_YEAR - 1, THIS_YEAR - 2].map(j =>
            <option key={j} value={j}>{j}</option>)}
        </select>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
        {monate.map(m => {
          const st = STATUS[m.status] || STATUS.offen
          return (
            <button key={m.monat} onClick={() => waehlen(m.monat)}
              className={`text-left rounded-xl border p-3 transition-all bg-surface ${
                gewaehlt === m.monat ? 'border-primary-400 ring-2 ring-primary-100' : 'border-neutral-200 hover:border-neutral-300'}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-neutral-800">{m.monatsname}</span>
                {m.status === 'abgeschlossen' && <Lock size={13} className="text-green-600" />}
                {m.status === 'wieder_geoeffnet' && <LockOpen size={13} className="text-amber-600" />}
              </div>
              <span className={`text-xs px-1.5 py-0.5 rounded ${st.cls}`}>{st.label}</span>
              <p className="text-xs text-neutral-400 mt-2">
                {m.summen?.anzahl || 0} Belege · {fmtEuro(m.summen?.brutto)}
              </p>
            </button>
          )
        })}
      </div>

      {!gewaehlt && (
        <div className="bg-surface border border-neutral-200 rounded-xl py-16 text-center text-neutral-400">
          <CalendarCheck size={28} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">Einen Monat auswählen, um ihn zu prüfen und abzuschließen.</p>
        </div>
      )}

      {pruefung && (
        <div className="space-y-5">
          {/* Prüfliste */}
          <div className="bg-surface border border-neutral-200 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-neutral-700 mb-4">
              Prüfung — {pruefung.monatsname} {jahr}
            </h2>
            <div className="space-y-3">
              {pruefung.punkte.map(p => {
                const Icon = p.erfuellt ? CheckCircle2 : (p.art === 'blockierend' ? AlertTriangle : Info)
                const farbe = p.erfuellt ? 'text-green-600' : (p.art === 'blockierend' ? 'text-red-600' : 'text-amber-600')
                return (
                  <div key={p.schluessel} className="flex items-start gap-3">
                    <Icon size={16} className={`mt-0.5 shrink-0 ${farbe}`} />
                    <div>
                      <p className="text-sm font-medium text-neutral-800">
                        {p.titel}
                        {!p.erfuellt && p.art === 'hinweis' && (
                          <span className="text-xs font-normal text-amber-600 ml-2">Hinweis, kein Hindernis</span>
                        )}
                      </p>
                      <p className="text-xs text-neutral-500 mt-0.5">{p.text}</p>
                    </div>
                  </div>
                )
              })}
            </div>

            <div className="flex flex-wrap items-center gap-4 mt-5 pt-4 border-t text-sm">
              <span className="text-neutral-500">Belege <strong className="text-neutral-800">{pruefung.summen.anzahl}</strong></span>
              <span className="text-neutral-500">Netto <strong className="text-neutral-800">{fmtEuro(pruefung.summen.netto)}</strong></span>
              <span className="text-neutral-500">USt. <strong className="text-neutral-800">{fmtEuro(pruefung.summen.steuer)}</strong></span>
              <span className="text-neutral-500">Brutto <strong className="text-neutral-900">{fmtEuro(pruefung.summen.brutto)}</strong></span>

              <div className="ml-auto flex gap-2">
                <button onClick={paketLaden} disabled={laeuft}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50 disabled:opacity-60">
                  <Download size={14} /> Übergabepaket
                </button>
                {isAdmin && pruefung.status !== 'abgeschlossen' && (
                  <button onClick={abschliessen} disabled={laeuft || !pruefung.abschluss_moeglich}
                    title={!pruefung.abschluss_moeglich ? 'Erst die blockierenden Punkte erledigen' : undefined}
                    className="flex items-center gap-1.5 px-3 py-2 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50">
                    <Lock size={14} /> Monat abschließen
                  </button>
                )}
                {isAdmin && pruefung.status === 'abgeschlossen' && (
                  <button onClick={wiederOeffnen} disabled={laeuft}
                    className="flex items-center gap-1.5 px-3 py-2 text-sm border border-amber-300 text-amber-700 rounded-lg hover:bg-amber-50">
                    <LockOpen size={14} /> Wieder öffnen
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Abschluss-Angaben */}
          {monat && monat.status !== 'offen' && (
            <div className="bg-surface border border-neutral-200 rounded-xl p-5 text-sm">
              <p className="text-neutral-700">
                Abgeschlossen am <strong>{fmtDateTime(monat.closed_at)}</strong> von {monat.closed_by || '—'}
                {monat.totals && <> · Stand damals: {fmtEuro(monat.totals.brutto)} bei {monat.totals.anzahl} Belegen</>}
              </p>
              {monat.status === 'wieder_geoeffnet' && (
                <p className="text-amber-700 mt-2">
                  Wieder geöffnet am {fmtDateTime(monat.reopened_at)} von {monat.reopened_by} —
                  „{monat.reopen_reason}"
                </p>
              )}
            </div>
          )}

          {/* Übergabe-Historie */}
          <div className="bg-surface border border-neutral-200 rounded-xl p-5">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-neutral-700 mb-3">
              <History size={15} className="text-neutral-500" /> Übergaben
            </h2>
            {historie.length === 0 ? (
              <p className="text-sm text-neutral-400">Für diesen Monat wurde noch kein Paket erstellt.</p>
            ) : (
              <ol className="divide-y">
                {historie.map(h => (
                  <li key={h.id} className="py-2">
                    <p className="text-sm text-neutral-800">
                      {fmtDateTime(h.created_at)}
                      <span className="text-xs text-neutral-400 ml-2">
                        {h.created_by} · {h.file_count} Dateien · {fmtBytes(h.byte_size)}
                      </span>
                    </p>
                    <p className="text-xs text-neutral-400 font-mono mt-0.5 break-all">
                      SHA-256 {h.checksum}
                    </p>
                  </li>
                ))}
              </ol>
            )}
            <p className="text-xs text-neutral-400 mt-3">
              Das Paket enthält die Verkaufsseite: Buchungsjournal, Belegjournal,
              Umsatzsteuer-Aufstellung, offene Posten und jeden Beleg als PDF.
              Eingangsrechnungen und Vorsteuer erfasst DeineZeit nicht — sie sind
              gesondert beizubringen.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
