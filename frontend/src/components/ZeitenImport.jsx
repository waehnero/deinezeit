import { useState, useRef, useEffect } from 'react'
import { zeiterfassungApi, usersApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import {
  Upload, X, Check, Loader2, AlertCircle, FileText, ArrowLeft, Download, Sparkles,
} from 'lucide-react'
import {
  DATEITYPEN, istPdf, dateiZuTabelle, tabelleAlsCsv, zuordnungVorschlagen,
} from '../utils/zeitenDatei'

const IGNORIEREN = '__ignore__'
const BENUTZER_AUS_SPALTE = '__spalte__'

const stunden = (minuten) =>
  `${Math.floor(minuten / 60)}:${String(minuten % 60).padStart(2, '0')} h`

/**
 * Import-Assistent für Projektzeiten aus Fremdsystemen.
 *
 * Gleiche Schrittfolge wie der Stammdaten-Import (CsvImportExport.jsx):
 * Datei → Zuordnen → Prüfbericht → Ergebnis. Der Bericht kommt aus einem
 * Probelauf am Server; geschrieben wird erst nach ausdrücklicher Bestätigung,
 * und beide Durchgänge rufen denselben Endpunkt auf.
 *
 * CSV, Excel, JSON und Kalender liest der Browser (utils/zeitenDatei.js). Ein
 * PDF geht an die KI-Schnittstelle und kommt als Tabelle zurück — danach ist
 * es eine Datei wie jede andere. Weil eine KI sich verlesen kann, zeigt der
 * Zuordnungsschritt dann die Hinweise der KI und bietet die Tabelle als CSV
 * zum Herunterladen an: korrigieren, neu einspielen.
 */
export default function ZeitenImport({ onClose, onImported }) {
  const { isAdmin, currentUser } = useAuth()
  const fileRef = useRef()

  const [schritt, setSchritt] = useState('datei')   // datei|pdf|zuordnen|bericht|laeuft|fertig
  const [dateiname, setDateiname] = useState('')
  const [ausPdf, setAusPdf] = useState(false)
  const [pdfWartet, setPdfWartet] = useState(null)   // gewähltes PDF vor der Bestätigung
  const [tabelle, setTabelle] = useState({ spalten: [], zeilen: [], hinweise: [] })
  const [zielfelder, setZielfelder] = useState([])
  const [zuordnung, setZuordnung] = useState({})     // Spalte → Zielfeld
  const [benutzerListe, setBenutzerListe] = useState([])
  const [benutzerWahl, setBenutzerWahl] = useState('')   // '' = ich selbst
  const [bericht, setBericht] = useState(null)
  const [ergebnis, setErgebnis] = useState(null)
  const [laeuft, setLaeuft] = useState(false)

  useEffect(() => {
    zeiterfassungApi.importFelder()
      .then(res => setZielfelder(res.data))
      .catch(() => toast.error('Die Importfelder konnten nicht geladen werden'))
    if (isAdmin) {
      usersApi.list().then(res => setBenutzerListe(res.data || [])).catch(() => {})
    }
  }, [isAdmin])

  const { spalten, zeilen, hinweise } = tabelle

  // ── Datei einlesen ─────────────────────────────────────────────────────────

  const uebernehmen = (ergebnisTabelle) => {
    if (!ergebnisTabelle.zeilen.length) {
      toast.error('Die Datei enthält keine Datenzeilen')
      return false
    }
    setTabelle(ergebnisTabelle)
    const vorschlag = zuordnungVorschlagen(ergebnisTabelle.spalten, zielfelder)
    setZuordnung(vorschlag)
    // Bringt die Datei eine Benutzerspalte mit, ist das die Vorgabe.
    setBenutzerWahl(Object.values(vorschlag).includes('benutzer') ? BENUTZER_AUS_SPALTE : '')
    setSchritt('zuordnen')
    return true
  }

  const dateiGewaehlt = async (e) => {
    const datei = e.target.files?.[0]
    e.target.value = ''            // dieselbe Datei muss sich erneut wählen lassen
    if (!datei) return
    setDateiname(datei.name)
    if (istPdf(datei)) {
      // Nicht sofort senden: Das PDF verlässt den Server Richtung KI-Anbieter.
      setPdfWartet(datei)
      return
    }
    setAusPdf(false)
    try {
      uebernehmen(await dateiZuTabelle(datei))
    } catch (err) {
      toast.error(err.message || 'Die Datei konnte nicht gelesen werden')
    }
  }

  const pdfLesen = async () => {
    const datei = pdfWartet
    setPdfWartet(null)
    setSchritt('pdf')
    try {
      const res = await zeiterfassungApi.importPdf(datei)
      setAusPdf(true)
      if (!uebernehmen(res.data)) {
        ;(res.data.hinweise || []).forEach(h => toast(h))
        setSchritt('datei')
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Das PDF konnte nicht gelesen werden')
      setSchritt('datei')
    }
  }

  const csvHerunterladen = () => {
    const blob = new Blob([tabelleAlsCsv(tabelle)], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${dateiname.replace(/\.[^.]+$/, '') || 'zeiten'}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ── Zeilen für den Server aufbereiten ──────────────────────────────────────

  const benutzerAusSpalte = benutzerWahl === BENUTZER_AUS_SPALTE
  const zugeordnet = Object.entries(zuordnung)
    .filter(([, key]) => key && key !== IGNORIEREN)
    // Ist ein fixer Benutzer gewählt, zählt die Benutzerspalte nicht.
    .filter(([, key]) => key !== 'benutzer' || benutzerAusSpalte)
  const zugeordneteFelder = zugeordnet.map(([, key]) => key)

  const doppelt = zugeordneteFelder.filter((k, i) => zugeordneteFelder.indexOf(k) !== i)
  const fehlend = []
  if (!zugeordneteFelder.includes('beginn')) fehlend.push('Beginn')
  if (!zugeordneteFelder.includes('ende')) fehlend.push('Ende')
  if (benutzerAusSpalte && !zugeordneteFelder.includes('benutzer')) fehlend.push('Benutzer')

  const zeilenFuerServer = () => zeilen.map(zeile => {
    const daten = {}
    zugeordnet.forEach(([spalte, key]) => { daten[key] = zeile[spalte] ?? '' })
    return daten
  })

  const senden = async (optionen) => {
    setLaeuft(true)
    try {
      const res = await zeiterfassungApi.importZeiten(zeilenFuerServer(), {
        user_id: benutzerAusSpalte ? null : (benutzerWahl || null),
        ...optionen,
      })
      return res.data
    } catch (err) {
      const detail = err.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Import fehlgeschlagen')
      return null
    } finally {
      setLaeuft(false)
    }
  }

  const pruefen = async () => {
    const res = await senden({ dry_run: true })
    if (res) { setBericht(res); setSchritt('bericht') }
  }

  const schreiben = async (fehlerhafteUeberspringen) => {
    setSchritt('laeuft')
    const res = await senden({ dry_run: false, skip_invalid: fehlerhafteUeberspringen })
    if (!res) { setSchritt('bericht'); return }
    setErgebnis(res)
    setSchritt('fertig')
  }

  const feldName = (key) => zielfelder.find(f => f.key === key)?.name || key
  const zielBenutzer = benutzerAusSpalte
    ? 'laut Spalte'
    : (benutzerListe.find(b => b.id === benutzerWahl)?.full_name || currentUser?.full_name || 'dich')

  const titel = {
    datei: 'Zeiten importieren — Datei wählen',
    pdf: 'Zeiten importieren — PDF wird gelesen',
    zuordnen: 'Zeiten importieren — Spalten zuordnen',
    bericht: 'Zeiten importieren — Prüfergebnis',
    laeuft: 'Import läuft',
    fertig: 'Import abgeschlossen',
  }[schritt]

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 sheet-safe">
      <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">

        <div className="flex items-center justify-between p-5 border-b border-gray-100 flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold text-gray-900">{titel}</h2>
            {dateiname && !['datei', 'pdf'].includes(schritt) && (
              <p className="text-xs text-gray-400 mt-0.5">
                {dateiname} · {zeilen.length} Zeilen{ausPdf ? ' · von der KI gelesen' : ''}
              </p>
            )}
          </div>
          <button aria-label="Schließen" onClick={onClose}
            className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">

          {/* Schritt 1: Datei */}
          {schritt === 'datei' && !pdfWartet && (
            <div className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
                <p className="font-medium mb-1">Was gelesen wird:</p>
                <ul className="list-disc list-inside space-y-1 text-blue-700">
                  <li><b>CSV, Excel (.xlsx)</b> — erste Zeile mit Spaltenüberschriften, bei Excel das erste Tabellenblatt</li>
                  <li><b>JSON</b> — Exporte z.B. aus Toggl oder Clockify</li>
                  <li><b>Kalender (.ics)</b> — jeder Termin wird eine Projektzeit</li>
                  <li><b>PDF</b> — Stundenzettel, auch gescannt; die KI liest sie in eine Tabelle</li>
                </ul>
                <p className="mt-2 text-blue-700">
                  Jeder Eintrag braucht <b>Beginn und Ende</b>. Zeilen, die nur Datum und Dauer
                  kennen, werden beanstandet — eine Uhrzeit wird nicht erfunden.
                  Zeitprojekte müssen vor dem Import angelegt sein.
                </p>
              </div>

              <div
                onClick={() => fileRef.current?.click()}
                className="border-2 border-dashed border-gray-300 hover:border-primary-400 hover:bg-primary-50 rounded-xl p-10 text-center cursor-pointer transition"
              >
                <FileText size={40} className="mx-auto mb-3 text-gray-300" />
                <p className="font-medium text-gray-600">Datei auswählen</p>
                <p className="text-sm text-gray-400 mt-1">.csv · .xlsx · .json · .ics · .pdf</p>
                <input ref={fileRef} type="file" accept={DATEITYPEN} id="zeiten-import-datei"
                  name="zeiten-import-datei" className="hidden" onChange={dateiGewaehlt} />
              </div>
            </div>
          )}

          {/* PDF: Bestätigung, bevor die Datei den Server verlässt */}
          {schritt === 'datei' && pdfWartet && (
            <div className="space-y-4">
              <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-900">
                <Sparkles size={18} className="mt-0.5 shrink-0" />
                <div className="space-y-2">
                  <p className="font-medium">„{pdfWartet.name}" wird von der KI gelesen</p>
                  <p>
                    Dazu wird das PDF an den in den Einstellungen hinterlegten KI-Anbieter
                    übertragen — samt den Namen und Arbeitszeiten, die darin stehen.
                    DeineZeit selbst speichert die Datei nicht.
                  </p>
                  <p>
                    Das Lesen dauert bis zu drei Minuten. Danach ordnest du die Spalten zu
                    und siehst einen Prüfbericht; importiert wird erst nach deiner Bestätigung.
                  </p>
                </div>
              </div>
            </div>
          )}

          {schritt === 'pdf' && (
            <div className="flex flex-col items-center justify-center py-12 gap-4 text-center">
              <Loader2 size={40} className="animate-spin text-primary-500" />
              <p className="text-gray-600 font-medium">Die KI liest „{dateiname}" …</p>
              <p className="text-sm text-gray-400">Das kann bis zu drei Minuten dauern. Bitte das Fenster offen lassen.</p>
            </div>
          )}

          {/* Schritt 2: Zuordnen */}
          {schritt === 'zuordnen' && (
            <div className="space-y-5">
              <div className="flex items-center gap-2 text-sm text-gray-600 bg-gray-50 rounded-xl p-3">
                <Check size={16} className="text-green-500" />
                <span>{zeilen.length} Zeilen · {spalten.length} Spalten erkannt</span>
              </div>

              {(ausPdf || hinweise.length > 0) && (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-900 space-y-2">
                  {ausPdf && (
                    <p>
                      <b>Von der KI gelesen — bitte gegenprüfen.</b> Vergleiche die Vorschau und
                      später die Stundensumme im Prüfbericht mit dem PDF. Du kannst die Tabelle
                      auch herunterladen, in Excel korrigieren und als CSV neu einspielen.
                    </p>
                  )}
                  {hinweise.length > 0 && (
                    <ul className="list-disc list-inside space-y-0.5">
                      {hinweise.map((h, i) => <li key={i}>{h}</li>)}
                    </ul>
                  )}
                  {ausPdf && (
                    <button onClick={csvHerunterladen}
                      className="flex items-center gap-2 px-3 py-1.5 border border-amber-300 bg-white rounded-lg text-amber-900 hover:bg-amber-100 transition">
                      <Download size={14} /> Tabelle als CSV herunterladen
                    </button>
                  )}
                </div>
              )}

              {isAdmin && (
                <div>
                  <label htmlFor="zeiten-import-benutzer" className="block text-sm font-semibold text-gray-800 mb-1">
                    Wem gehören die Zeiten?
                  </label>
                  <select id="zeiten-import-benutzer" name="zeiten-import-benutzer"
                    value={benutzerWahl} onChange={e => setBenutzerWahl(e.target.value)}
                    className="w-full sm:w-2/3 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface">
                    <option value="">Mir selbst ({currentUser?.full_name})</option>
                    <option value={BENUTZER_AUS_SPALTE}>Laut Spalte in der Datei (Name oder E-Mail)</option>
                    {benutzerListe.filter(b => b.id !== currentUser?.id).map(b => (
                      <option key={b.id} value={b.id}>{b.full_name} — ganze Datei</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <p className="text-sm font-semibold text-gray-800 mb-1">Spaltenzuordnung</p>
                <p className="text-xs text-gray-500 mb-3">
                  Beginn und Ende sind Pflicht — als Uhrzeit (dann auch das Datum zuordnen) oder
                  als Datum mit Uhrzeit in einer Spalte. Alles andere darf auf „Ignorieren" bleiben.
                </p>
                <div className="space-y-2">
                  {spalten.map((spalte, i) => (
                    <div key={spalte} className="flex items-center gap-2 text-sm">
                      <div className="w-1/3 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-gray-700 font-mono text-xs truncate" title={spalte}>
                        {spalte}
                      </div>
                      <span className="text-gray-400">→</span>
                      <select
                        id={`zeiten-import-spalte-${i}`} name={`zeiten-import-spalte-${i}`}
                        aria-label={`Zielfeld für Spalte ${spalte}`}
                        value={zuordnung[spalte] || IGNORIEREN}
                        onChange={e => setZuordnung({ ...zuordnung, [spalte]: e.target.value })}
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface"
                      >
                        <option value={IGNORIEREN}>— Ignorieren —</option>
                        {zielfelder
                          .filter(f => f.key !== 'benutzer' || benutzerAusSpalte)
                          .map(f => <option key={f.key} value={f.key}>{f.name}</option>)}
                      </select>
                    </div>
                  ))}
                </div>
                {doppelt.length > 0 && (
                  <p className="text-xs text-red-600 mt-2">
                    Mehrfach zugeordnet: {[...new Set(doppelt)].map(feldName).join(', ')} — jedes Feld nur einer Spalte zuordnen.
                  </p>
                )}
                {fehlend.length > 0 && (
                  <p className="text-xs text-amber-700 mt-2">Noch nicht zugeordnet: {fehlend.join(', ')}</p>
                )}
              </div>

              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Vorschau (erste {Math.min(5, zeilen.length)} von {zeilen.length} Zeilen)
                </p>
                <div className="overflow-x-auto border border-gray-200 rounded-xl">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50">
                      <tr>{spalten.map(s => (
                        <th key={s} className="px-3 py-2 text-left text-gray-500 font-medium whitespace-nowrap">{s}</th>
                      ))}</tr>
                    </thead>
                    <tbody>
                      {zeilen.slice(0, 5).map((zeile, i) => (
                        <tr key={i} className="border-t border-gray-100">
                          {spalten.map(s => (
                            <td key={s} className="px-3 py-2 text-gray-600 max-w-[170px] truncate">{zeile[s]}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Schritt 3: Prüfbericht */}
          {schritt === 'bericht' && bericht && (
            <ZeitenPruefbericht bericht={bericht} zielBenutzer={zielBenutzer} />
          )}

          {schritt === 'laeuft' && (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
              <Loader2 size={40} className="animate-spin text-primary-500" />
              <p className="text-gray-600 font-medium">Projektzeiten werden geschrieben …</p>
            </div>
          )}

          {schritt === 'fertig' && ergebnis && (
            <div className="flex flex-col items-center justify-center py-10 gap-4 text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center">
                <Check size={32} className="text-green-600" />
              </div>
              <div>
                <p className="text-xl font-bold text-gray-900">
                  {ergebnis.angelegt} Projektzeiten importiert · {stunden(ergebnis.minuten_gesamt)}
                </p>
                {ergebnis.uebersprungen > 0 && (
                  <p className="text-amber-600 mt-1">{ergebnis.uebersprungen} Zeilen übersprungen</p>
                )}
                <p className="text-sm text-gray-500 mt-2">
                  Die Einträge stehen auf „veränderbar" und lassen sich wie jede Projektzeit bearbeiten.
                </p>
              </div>
              <button onClick={() => onImported(ergebnis.angelegt)}
                className="px-6 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition">
                Fertig
              </button>
            </div>
          )}
        </div>

        {/* Fußzeilen */}
        {schritt === 'datei' && pdfWartet && (
          <div className="flex gap-3 p-5 border-t border-gray-100 flex-shrink-0">
            <button onClick={() => setPdfWartet(null)}
              className="flex-1 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition">
              Andere Datei wählen
            </button>
            <button onClick={pdfLesen}
              className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 text-white font-medium rounded-xl transition flex items-center justify-center gap-2">
              <Sparkles size={16} /> An die KI senden und lesen
            </button>
          </div>
        )}

        {schritt === 'zuordnen' && (
          <div className="flex gap-3 p-5 border-t border-gray-100 flex-shrink-0">
            <button onClick={() => setSchritt('datei')}
              className="py-2.5 px-4 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition flex items-center justify-center gap-2">
              <ArrowLeft size={16} /> Andere Datei
            </button>
            <button onClick={pruefen}
              disabled={laeuft || fehlend.length > 0 || doppelt.length > 0}
              className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2">
              {laeuft ? <Loader2 size={16} className="animate-spin" /> : <Check size={16} />}
              Prüfen
            </button>
          </div>
        )}

        {schritt === 'bericht' && bericht && (
          <div className="flex flex-col sm:flex-row gap-3 p-5 border-t border-gray-100 flex-shrink-0">
            <button onClick={() => setSchritt('zuordnen')}
              className="py-2.5 px-4 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition flex items-center justify-center gap-2">
              <ArrowLeft size={16} /> Zurück
            </button>
            {bericht.beanstandungen.length > 0 ? (
              <button onClick={() => schreiben(true)} disabled={laeuft || bericht.anlegen === 0}
                className="flex-1 py-2.5 border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 disabled:opacity-50 font-medium rounded-xl transition">
                Beanstandete überspringen und {bericht.anlegen} Zeilen importieren
              </button>
            ) : (
              <button onClick={() => schreiben(false)} disabled={laeuft || bericht.anlegen === 0}
                className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2">
                <Upload size={16} /> {bericht.anlegen} Projektzeiten importieren
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/** Ergebnis des Probelaufs — Zahlen oben, Beanstandungen mit Grund darunter. */
function ZeitenPruefbericht({ bericht, zielBenutzer }) {
  const beanstandet = new Set(bericht.beanstandungen.map(b => b.zeile)).size
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Kennzahl label="Geprüft" wert={bericht.geprueft} />
        <Kennzahl label="Importieren" wert={bericht.anlegen} farbe="text-green-600" />
        <Kennzahl label="Stundensumme" wert={stunden(bericht.minuten_gesamt)} farbe="text-blue-600" />
        <Kennzahl label="Beanstandet" wert={beanstandet}
          farbe={beanstandet ? 'text-amber-600' : 'text-gray-400'} />
      </div>
      <p className="text-xs text-gray-500">
        Die Einträge gehen an: <b>{zielBenutzer}</b>. Die Stundensumme (ohne Pausen) eignet sich
        zum Vergleich mit der Summe im Fremdsystem.
      </p>

      {bericht.beanstandungen.length === 0 ? (
        <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-800">
          <Check size={18} /> Alle Zeilen sind in Ordnung. Bisher wurde nichts geschrieben.
        </div>
      ) : (
        <div>
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-900 mb-3">
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <span>
              {beanstandet} von {bericht.geprueft} Zeilen können so nicht übernommen werden.
              Es wurde noch nichts geschrieben — du kannst die Datei korrigieren und neu
              beginnen oder diese Zeilen auslassen.
            </span>
          </div>
          <div className="overflow-x-auto border border-gray-200 rounded-xl max-h-64 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-3 py-2 text-left text-gray-500 font-medium">Zeile</th>
                  <th className="px-3 py-2 text-left text-gray-500 font-medium">Feld</th>
                  <th className="px-3 py-2 text-left text-gray-500 font-medium">Wert</th>
                  <th className="px-3 py-2 text-left text-gray-500 font-medium">Grund</th>
                </tr>
              </thead>
              <tbody>
                {bericht.beanstandungen.map((b, i) => (
                  <tr key={i} className="border-t border-gray-100">
                    <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{b.zeile}</td>
                    <td className="px-3 py-2 text-gray-700 whitespace-nowrap">{b.feld || '—'}</td>
                    <td className="px-3 py-2 text-gray-600 max-w-[160px] truncate font-mono">{b.wert}</td>
                    <td className="px-3 py-2 text-amber-700">{b.grund}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function Kennzahl({ label, wert, farbe = 'text-gray-900' }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-bold ${farbe}`}>{wert}</p>
    </div>
  )
}
