/**
 * Bericht „Projektzeiten" – alle Zeiteinträge filtern, runden, drucken.
 *
 * Nachfolger des Dialogs „Bericht erstellen" (components/BerichtDialog.jsx).
 * Aus dem Dialog wurde eine Seite, weil man vor dem Druck sehen soll, was im
 * Bericht landet: Der Dialog erzeugte ein PDF ins Blaue — stimmten die Filter
 * nicht, merkte man das erst im fertigen Dokument oder an der Meldung „keine
 * Einträge gefunden".
 *
 * Zwei Abfragen je Ansicht, absichtlich getrennt:
 *   reportsApi.uebersicht    Summen über ALLE Treffer (mit Rundung)
 *   zeiterfassungApi.listEntries  die sichtbare Seite der Liste (geblättert)
 * Die Summen dürfen nicht aus der angezeigten Seite berechnet werden — sonst
 * zeigt Seite 2 eine andere Gesamtsumme als Seite 1.
 */
import { useState, useEffect, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import PageHeader from '../components/PageHeader'
import ZeitraumLeiste, { zeitraumBerechnen, tagesbeginn, tagesende } from '../components/ZeitraumLeiste'
import { reportsApi, zeiterfassungApi, usersApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import {
  BarChart3, Download, Eye, Loader2, ChevronLeft, ChevronRight, Search,
  Pencil, Trash2,
} from 'lucide-react'
import ProjektzeitModal from '../components/ProjektzeitModal'
import StatusMenu, { ENTRY_STATUS } from '../components/ProjektzeitStatus'

const STATUS_LABEL = {
  veraenderbar: 'veränderbar',
  gesperrt:     'gesperrt',
  freigegeben:  'freigegeben',
  abgerechnet:  'abgerechnet',
}
const STATUS_FARBE = {
  veraenderbar: 'bg-green-50 text-green-700 border-green-200',
  gesperrt:     'bg-amber-50 text-amber-700 border-amber-200',
  freigegeben:  'bg-blue-50 text-blue-700 border-blue-200',
  abgerechnet:  'bg-gray-100 text-gray-500 border-gray-200',
}

const fmtMinuten = (min) => `${Math.floor((min || 0) / 60)}:${String((min || 0) % 60).padStart(2, '0')}`
const fmtZeit = (iso) => iso ? new Date(iso).toLocaleTimeString('de-AT', { hour: '2-digit', minute: '2-digit' }) : '—'
const fmtDatum = (iso) => iso ? new Date(iso).toLocaleDateString('de-AT', { weekday: 'short', day: '2-digit', month: '2-digit' }) : ''

const inputCls  = "w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface"

function Feld({ label, children }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  )
}

/** Fehlerdetail lesbar machen — auch wenn die Antwort ein Blob war (PDF-Weg). */
async function fehlerText(err) {
  if (!err.response) return err.message || 'Unbekannter Fehler'
  const daten = err.response.data
  if (daten instanceof Blob) {
    try { return JSON.parse(await daten.text())?.detail || 'Unbekannter Fehler' }
    catch { return 'Unbekannter Fehler' }
  }
  return daten?.detail || 'Unbekannter Fehler'
}

/**
 * Aktionen je Zeile: Bearbeiten, Löschen, Status.
 *
 * Dieselben Knöpfe wie in der Erfassungsliste — wer im Bericht einen Fehler
 * entdeckt, soll ihn dort beheben können, wo er ihn sieht, statt ihn sich zu
 * merken und in der Erfassung zu suchen. Gelöscht wird nur, was noch
 * veränderbar ist; alles Weitere weist der Server ab (Beleg-Sperre,
 * fremder Eintrag).
 */
function ZeilenAktionen({ eintrag, onBearbeiten, onLoeschen, onStatus, isAdmin, benutzerId }) {
  const [loeschenBestaetigen, setLoeschenBestaetigen] = useState(false)
  const veraenderbar = (eintrag.status || 'veraenderbar') === 'veraenderbar'
  return (
    <div className="flex items-center gap-1 justify-end" onClick={e => e.stopPropagation()}>
      <button onClick={() => onBearbeiten(eintrag)} title="Bearbeiten"
        className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
        <Pencil size={14} />
      </button>
      {veraenderbar && (
        <button
          onClick={() => { if (loeschenBestaetigen) onLoeschen(eintrag); else setLoeschenBestaetigen(true) }}
          onBlur={() => setTimeout(() => setLoeschenBestaetigen(false), 200)}
          title={loeschenBestaetigen ? 'Nochmal klicken zum Löschen' : 'Löschen'}
          className={`p-1.5 rounded-lg transition ${loeschenBestaetigen
            ? 'bg-red-100 text-red-600' : 'text-gray-400 hover:text-red-500 hover:bg-red-50'}`}>
          <Trash2 size={14} />
        </button>
      )}
      <StatusMenu entry={eintrag} isAdmin={isAdmin} currentUserId={benutzerId} onSetStatus={onStatus} />
    </div>
  )
}

export default function BerichtProjektzeitenPage() {
  const { nurEigene, isAdmin, currentUser } = useAuth()
  // Wer nur die eigenen Zeiten sehen darf, bekommt keine Benutzerauswahl —
  // der Server schränkt ohnehin ein (reports.py, _entry_query).
  const darfAlleSehen = !nurEigene('zeiterfassung')

  // Aus den Auswertungsseiten kommt man mit vorgewähltem Filter hierher
  // (Klick auf eine Zeile). Die Werte stehen in der Adresse, damit die Ansicht
  // als Lesezeichen taugt und der Zurück-Knopf des Browsers funktioniert.
  const [suchParams] = useSearchParams()

  const start = zeitraumBerechnen('monat', 0)
  const [zeitraum, setZeitraum] = useState(() => {
    const von = suchParams.get('von')
    const bis = suchParams.get('bis')
    return (von && bis)
      ? { voreinstellung: 'frei', versatz: 0, von, bis }
      : { voreinstellung: 'monat', versatz: 0, von: start.von, bis: start.bis }
  })

  // Filter
  const [zeitprojekt, setZeitprojekt] = useState(suchParams.get('zeitprojekt') || '')
  const [kontakt,     setKontakt]     = useState('')
  const [benutzerId,  setBenutzerId]  = useState(suchParams.get('benutzer') || '')
  const [verrechenbar, setVerrechenbar] = useState('all')
  const [status,      setStatus]      = useState('')
  const [notiz,       setNotiz]       = useState('')
  const [gruppierung, setGruppierung] = useState('aufgabe')   // für das PDF

  // Rundung
  const [rundenAuf,      setRundenAuf]      = useState(15)
  const [rundenRichtung, setRundenRichtung] = useState('up')

  // Auswahllisten
  const [benutzer,     setBenutzer]     = useState([])
  const [zeitprojekte, setZeitprojekte] = useState([])
  const [kontakte,     setKontakte]     = useState([])

  // Daten
  const [summe,   setSumme]   = useState(null)
  const [eintraege, setEintraege] = useState([])
  const [gesamt,  setGesamt]  = useState(0)
  const [seite,   setSeite]   = useState(1)
  const [laden,   setLaden]   = useState(true)
  const SEITENGROESSE = 50

  const [ladePdf,      setLadePdf]      = useState(false)
  const [ladeVorschau, setLadeVorschau] = useState(false)

  // undefined = Dialog zu, Objekt = dieser Eintrag wird bearbeitet
  const [bearbeiten, setBearbeiten] = useState(undefined)

  useEffect(() => {
    usersApi.list().then(r => setBenutzer(r.data)).catch(() => {})
    reportsApi.getTasks().then(r => setZeitprojekte(r.data.tasks || [])).catch(() => {})
    reportsApi.getContacts().then(r => setKontakte(r.data.contacts || [])).catch(() => {})
  }, [])

  // Filter → Parameter für Bericht/Auswertung
  const berichtParams = useCallback((extra = {}) => {
    const p = {
      // Grenzen mit Zeitzonen-Versatz: Der Server soll den Ortstag meinen,
      // nicht den UTC-Tag (siehe tagesbeginn/tagesende).
      date_from: tagesbeginn(zeitraum.von),
      date_to:   tagesende(zeitraum.bis),
      group_by:  gruppierung,
      round_to:  rundenAuf,
      round_dir: rundenRichtung,
      ...extra,
    }
    if (zeitprojekt) p.project_name = zeitprojekt
    if (kontakt)     p.contact_name = kontakt
    if (benutzerId)  p.user_id = benutzerId
    if (verrechenbar !== 'all') p.billable = verrechenbar
    return p
  }, [zeitraum, gruppierung, rundenAuf, rundenRichtung, zeitprojekt, kontakt, benutzerId, verrechenbar])

  const laden_ = useCallback(async () => {
    setLaden(true)
    try {
      const [uebersicht, liste] = await Promise.all([
        reportsApi.uebersicht(berichtParams({ group_by: 'zeitprojekt' })),
        zeiterfassungApi.listEntries({
          date_from: tagesbeginn(zeitraum.von),
          date_to:   tagesende(zeitraum.bis),
          ...(zeitprojekt  ? { project_name: zeitprojekt } : {}),
          ...(kontakt      ? { contact_name: kontakt } : {}),
          ...(benutzerId   ? { user_id: benutzerId } : {}),
          ...(verrechenbar !== 'all' ? { billable: verrechenbar } : {}),
          ...(status       ? { status } : {}),
          ...(notiz        ? { search: notiz } : {}),
          page: seite,
          page_size: SEITENGROESSE,
        }),
      ])
      setSumme(uebersicht.data.summe)
      setEintraege(liste.data.items)
      setGesamt(liste.data.total)
    } catch {
      toast.error('Auswertung konnte nicht geladen werden')
    } finally {
      setLaden(false)
    }
  }, [berichtParams, zeitraum, zeitprojekt, kontakt, benutzerId, verrechenbar, status, notiz, seite])

  useEffect(() => { laden_() }, [laden_])
  // Filteränderung führt zurück auf Seite 1 — sonst steht man auf einer
  // Seitenzahl, die es im neuen Ergebnis nicht mehr gibt, und sieht nichts.
  useEffect(() => { setSeite(1) }, [zeitraum.von, zeitraum.bis, zeitprojekt, kontakt, benutzerId, verrechenbar, status, notiz])

  const pdfLaden = async () => {
    setLadePdf(true)
    try {
      const res = await reportsApi.downloadZeiterfassung(berichtParams({ format: 'pdf' }))
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }))
      const a = document.createElement('a')
      const cd = res.headers['content-disposition'] || ''
      const m = cd.match(/filename="?([^"]+)"?/)
      a.href = url
      a.download = m ? m[1] : `Projektzeitbericht_${zeitraum.von}_${zeitraum.bis}.pdf`
      a.click()
      window.URL.revokeObjectURL(url)
      toast.success('Bericht heruntergeladen')
    } catch (err) {
      toast.error(err.response?.status === 404
        ? 'Keine Zeiteinträge für die gewählten Filter gefunden'
        : await fehlerText(err))
    } finally { setLadePdf(false) }
  }

  const vorschau = async () => {
    setLadeVorschau(true)
    try {
      const res = await reportsApi.previewZeiterfassung(berichtParams())
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'text/html; charset=utf-8' }))
      window.open(url, '_blank')
      setTimeout(() => window.URL.revokeObjectURL(url), 10_000)
    } catch (err) {
      toast.error(err.response?.status === 404
        ? 'Keine Zeiteinträge für die gewählten Filter gefunden'
        : 'Vorschau konnte nicht geladen werden')
    } finally { setLadeVorschau(false) }
  }

  const loeschen = async (eintrag) => {
    try {
      await zeiterfassungApi.deleteEntry(eintrag.id)
      toast.success('Zeiteintrag gelöscht')
      laden_()
    } catch (err) {
      // 403 = fremder Eintrag, 409 = abgerechnet oder auf einem Beleg
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Löschen fehlgeschlagen', { duration: 6000 })
    }
  }

  const statusSetzen = async (eintrag, neuerStatus) => {
    try {
      await zeiterfassungApi.setEntryStatus(eintrag.id, neuerStatus)
      toast.success(`Status auf „${ENTRY_STATUS[neuerStatus]?.label || neuerStatus}“ gesetzt`)
      laden_()
    } catch (err) {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Statuswechsel fehlgeschlagen', { duration: 6000 })
    }
  }

  const seiten = Math.max(1, Math.ceil(gesamt / SEITENGROESSE))

  return (
    <div>
      <PageHeader icon={BarChart3} title="Projektzeiten"
        subtitle="Zeiteinträge filtern, runden und als Bericht ausgeben">
        <div className="flex gap-2">
          <button onClick={vorschau} disabled={ladeVorschau}
            className="flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm font-medium border bg-surface text-gray-600 border-gray-300 hover:border-primary-400 hover:text-primary-600 transition disabled:opacity-50">
            {ladeVorschau ? <Loader2 size={16} className="animate-spin" /> : <Eye size={16} />}
            <span className="hidden sm:inline">Vorschau</span>
          </button>
          <button onClick={pdfLaden} disabled={ladePdf}
            className="flex items-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white px-4 py-2.5 rounded-xl font-medium text-sm transition">
            {ladePdf ? <Loader2 size={16} className="animate-spin" /> : <Download size={16} />}
            <span className="hidden sm:inline">Druck / Export</span>
          </button>
        </div>
      </PageHeader>

      <ZeitraumLeiste {...zeitraum} onChange={setZeitraum} />

      {/* ── Suche ─────────────────────────────────────────────────────────── */}
      <div className="bg-surface rounded-2xl shadow-card p-4 sm:p-5 mb-4">
        <h2 className="text-sm font-semibold text-gray-900 mb-3">Suche</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          <Feld label="Zeitprojekt">
            <select value={zeitprojekt} onChange={e => setZeitprojekt(e.target.value)} className={inputCls}>
              <option value="">Alle Zeitprojekte</option>
              {zeitprojekte.map(z => <option key={z} value={z}>{z}</option>)}
            </select>
          </Feld>
          <Feld label="Kontakt">
            <select value={kontakt} onChange={e => setKontakt(e.target.value)} className={inputCls}>
              <option value="">Alle Kontakte</option>
              {kontakte.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
          </Feld>
          {darfAlleSehen && (
            <Feld label="Benutzer">
              <select value={benutzerId} onChange={e => setBenutzerId(e.target.value)} className={inputCls}>
                <option value="">Alle Benutzer</option>
                {benutzer.map(b => <option key={b.id} value={b.id}>{b.full_name}</option>)}
              </select>
            </Feld>
          )}
          <Feld label="Notiz enthält">
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input type="text" value={notiz} onChange={e => setNotiz(e.target.value)}
                placeholder="Freitext…" className={`${inputCls} pl-8`} />
            </div>
          </Feld>
          <Feld label="Verrechenbar">
            <select value={verrechenbar} onChange={e => setVerrechenbar(e.target.value)} className={inputCls}>
              <option value="all">Alle</option>
              <option value="yes">Nur verrechenbar</option>
              <option value="no">Nur nicht verrechenbar</option>
            </select>
          </Feld>
          <Feld label="Status">
            <select value={status} onChange={e => setStatus(e.target.value)} className={inputCls}>
              <option value="">Alle</option>
              {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Feld>
        </div>
      </div>

      {/* ── Summen + Rundung ──────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-end gap-6 sm:gap-10 mb-4">
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Gesamt</p>
          <p className="text-2xl font-bold tabular-nums text-gray-900">{fmtMinuten(summe?.minuten)}</p>
        </div>
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Verrechenbar</p>
          <p className="text-2xl font-bold tabular-nums text-green-700">{fmtMinuten(summe?.verrechenbar_minuten)}</p>
        </div>
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Nicht verrechenbar</p>
          <p className="text-2xl font-bold tabular-nums text-gray-400">{fmtMinuten(summe?.nicht_verrechenbar_minuten)}</p>
        </div>
        <div className="flex gap-3 sm:ml-auto">
          <Feld label="Runden">
            <select value={rundenRichtung} onChange={e => setRundenRichtung(e.target.value)} className={inputCls}
              disabled={rundenAuf === 0}>
              <option value="up">Aufrunden</option>
              <option value="down">Abrunden</option>
            </select>
          </Feld>
          <Feld label="Minuten">
            <select value={rundenAuf} onChange={e => setRundenAuf(Number(e.target.value))} className={inputCls}>
              <option value={0}>keine</option>
              <option value={5}>5</option>
              <option value={10}>10</option>
              <option value={15}>15</option>
              <option value={30}>30</option>
              <option value={60}>60</option>
            </select>
          </Feld>
          <Feld label="Gruppierung (PDF)">
            <select value={gruppierung} onChange={e => setGruppierung(e.target.value)} className={inputCls}>
              <option value="aufgabe">Nach Zeitprojekt</option>
              <option value="benutzer">Nach Benutzer</option>
              <option value="kontakt">Nach Kunde</option>
            </select>
          </Feld>
        </div>
      </div>

      {/* ── Trefferliste ──────────────────────────────────────────────────── */}
      <div className="bg-surface rounded-2xl shadow-card overflow-hidden">
        {laden ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={26} className="animate-spin text-primary-400" />
          </div>
        ) : eintraege.length === 0 ? (
          <p className="text-center text-gray-400 py-16 text-sm">Keine Einträge gefunden.</p>
        ) : (
          <>
            {/* Tabelle (ab Tablet) */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-neutral-50 border-b border-gray-200">
                    <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Benutzer</th>
                    <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Zeitprojekt</th>
                    <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Zeit</th>
                    <th className="text-right px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Pause</th>
                    <th className="text-right px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Dauer</th>
                    <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Notiz</th>
                    <th className="text-left px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-gray-500">Status</th>
                    <th className="w-28" />
                  </tr>
                </thead>
                <tbody>
                  {eintraege.map(e => (
                    <tr key={e.id} onClick={() => setBearbeiten(e)}
                      title="Zum Bearbeiten anklicken"
                      className="border-b border-gray-100 hover:bg-primary-50/40 cursor-pointer transition">
                      <td className="px-4 py-2.5 text-gray-700">{e.user?.full_name || '—'}</td>
                      <td className="px-4 py-2.5">
                        <span className="font-medium text-gray-900">{e.project_name || '—'}</span>
                        {e.contact_name && <span className="block text-xs text-gray-400">{e.contact_name}</span>}
                      </td>
                      <td className="px-4 py-2.5 text-gray-600 whitespace-nowrap">
                        {fmtDatum(e.started_at)} &nbsp;{fmtZeit(e.started_at)} – {fmtZeit(e.ended_at)}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums text-gray-500">{fmtMinuten(e.pause_minutes)}</td>
                      <td className="px-4 py-2.5 text-right tabular-nums font-semibold text-gray-900">{fmtMinuten(e.duration_minutes)}</td>
                      <td className="px-4 py-2.5 text-gray-500 max-w-[220px] truncate" title={e.note || ''}>{e.note || '—'}</td>
                      <td className="px-4 py-2.5">
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium border ${STATUS_FARBE[e.status] || 'bg-gray-100 text-gray-500 border-gray-200'}`}>
                          {STATUS_LABEL[e.status] || e.status}
                        </span>
                        {!e.billable && <span className="block text-[11px] text-gray-400 mt-0.5">nicht verrechenbar</span>}
                      </td>
                      <td className="px-3 py-2.5">
                        <ZeilenAktionen eintrag={e} onBearbeiten={setBearbeiten}
                          onLoeschen={loeschen} onStatus={statusSetzen}
                          isAdmin={isAdmin} benutzerId={currentUser?.id} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Karten (Handy) */}
            <div className="sm:hidden divide-y divide-gray-100">
              {eintraege.map(e => (
                <div key={e.id} className="p-4" onClick={() => setBearbeiten(e)}>
                  <div className="flex justify-between items-start gap-3 mb-1">
                    <span className="font-medium text-gray-900 text-sm">{e.project_name || '—'}</span>
                    <span className="tabular-nums font-semibold text-gray-900 text-sm">{fmtMinuten(e.duration_minutes)}</span>
                  </div>
                  <p className="text-xs text-gray-500">{e.user?.full_name} · {fmtDatum(e.started_at)} {fmtZeit(e.started_at)}–{fmtZeit(e.ended_at)}</p>
                  {e.note && <p className="text-xs text-gray-400 mt-1">{e.note}</p>}
                  <div className="mt-2">
                    <ZeilenAktionen eintrag={e} onBearbeiten={setBearbeiten}
                      onLoeschen={loeschen} onStatus={statusSetzen}
                      isAdmin={isAdmin} benutzerId={currentUser?.id} />
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Blättern */}
        {seiten > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
            <p className="text-xs text-gray-400">{gesamt} Einträge · Seite {seite} von {seiten}</p>
            <div className="flex gap-1">
              <button onClick={() => setSeite(s => s - 1)} disabled={seite === 1}
                className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 disabled:opacity-40 transition">
                <ChevronLeft size={16} />
              </button>
              <button onClick={() => setSeite(s => s + 1)} disabled={seite >= seiten}
                className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 disabled:opacity-40 transition">
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-400 mt-3">
        Die Summen oben gelten für alle Treffer des Zeitraums (mit Rundung), nicht nur für die angezeigte Seite.
        Der Ausdruck übernimmt dieselben Filter.
      </p>

      {/* Derselbe Dialog wie in der Erfassung — nach dem Speichern wird die
          Liste neu geladen, damit Summen und Zeile zusammenpassen. */}
      {bearbeiten !== undefined && (
        <ProjektzeitModal
          entry={bearbeiten}
          onClose={() => setBearbeiten(undefined)}
          onSaved={() => { setBearbeiten(undefined); laden_() }}
        />
      )}
    </div>
  )
}
