import { useState, useRef } from 'react'
import { masterdataApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import toast from 'react-hot-toast'
import Papa from 'papaparse'
import {
  Download, Upload, X, Check, Loader2, AlertCircle, FileText, Plus, ArrowLeft,
} from 'lucide-react'

// ── CSV Export ────────────────────────────────────────────────────────────────
export function CsvExportButton({ slug, entityName }) {
  const [loading, setLoading] = useState(false)

  const handleExport = async () => {
    setLoading(true)
    try {
      const res = await masterdataApi.exportCsv(slug)
      const bom = '﻿'  // BOM für Excel-Kompatibilität
      const blob = new Blob([bom + res.data], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${slug}_export_${new Date().toISOString().slice(0, 10)}.csv`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`${entityName} als CSV exportiert`)
    } catch {
      toast.error('Export fehlgeschlagen')
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={loading}
      className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition"
      title="Als CSV exportieren"
    >
      {loading ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
      Export
    </button>
  )
}

// ── Import ────────────────────────────────────────────────────────────────────

// Zellwert aus ExcelJS in die Schreibweise bringen, die ein Mensch in Excel
// sieht — so, wie sie auch der Server erwartet (services/masterdata_import.py):
// ein Datum als „31.12.2026", keine Tageszahl seit 1900; Formeln über ihr
// Ergebnis; Zahlen unverändert (die maschinelle Schreibweise mit Punkt versteht
// der Import).
function zellwertAlsText(wert) {
  if (wert === null || wert === undefined) return ''
  if (wert instanceof Date) {
    const t = String(wert.getUTCDate()).padStart(2, '0')
    const m = String(wert.getUTCMonth() + 1).padStart(2, '0')
    return `${t}.${m}.${wert.getUTCFullYear()}`
  }
  if (typeof wert === 'object') {
    if ('result' in wert) return zellwertAlsText(wert.result)          // Formel
    if (Array.isArray(wert.richText)) return wert.richText.map(r => r.text).join('')
    if ('text' in wert) return zellwertAlsText(wert.text)              // Hyperlink
    if ('error' in wert) return ''                                     // #DIV/0! u. ä.
    return String(wert)
  }
  if (typeof wert === 'boolean') return wert ? 'ja' : 'nein'
  return String(wert)
}

const IGNORIEREN = '__ignore__'

// Muss zu make_key() im Backend passen, damit der angezeigte Feldschlüssel
// derselbe ist wie der gespeicherte.
function machKey(text) {
  return String(text).toLowerCase().trim()
    .replace(/[äöüß]/g, m => ({ ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss' }[m]))
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

const FELDTYPEN = [
  ['text', 'Text'],
  ['textarea', 'Mehrzeiliger Text'],
  ['number', 'Zahl'],
  ['date', 'Datum'],
  ['email', 'E-Mail'],
  ['phone', 'Telefon'],
  ['url', 'Internetadresse'],
  ['checkbox', 'Ja/Nein'],
  ['dropdown', 'Auswahlliste'],
]

export function CsvImportButton({ slug, entityType, onImported }) {
  const [showModal, setShowModal] = useState(false)

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        className="flex items-center gap-2 px-3 py-2 border border-gray-300 rounded-xl text-sm text-gray-700 hover:bg-gray-50 transition"
        title="Aus CSV oder Excel importieren"
      >
        <Upload size={15} />
        Import
      </button>

      {showModal && (
        <ImportAssistent
          slug={slug}
          entityType={entityType}
          onClose={() => setShowModal(false)}
          onImported={(anzahl) => {
            setShowModal(false)
            onImported?.(anzahl)
          }}
        />
      )}
    </>
  )
}

/**
 * Import-Assistent für CSV und Excel.
 *
 * Vier Schritte: Datei → Zuordnen → Prüfbericht → Ergebnis. Der Bericht kommt
 * aus einem Probelauf am Server; geschrieben wird erst, wenn der Benutzer ihn
 * gesehen und bestätigt hat. Beide Durchgänge rufen denselben Endpunkt auf,
 * damit der Bericht auch wirklich das beschreibt, was gleich passiert.
 */
function ImportAssistent({ slug, entityType, onClose, onImported }) {
  const { isAdmin } = useAuth()
  const fileRef = useRef()

  const [schritt, setSchritt] = useState('datei')   // datei|zuordnen|bericht|laeuft|fertig
  const [dateiname, setDateiname] = useState('')
  const [spalten, setSpalten] = useState([])
  const [zeilen, setZeilen] = useState([])
  const [zuordnung, setZuordnung] = useState({})    // Spalte → Feldschlüssel
  const [abgleichsfeld, setAbgleichsfeld] = useState('')
  const [felder, setFelder] = useState(
    [...(entityType.fields || [])].sort((a, b) => a.sort_order - b.sort_order))
  const [neuesFeldFuer, setNeuesFeldFuer] = useState(null)
  const [bericht, setBericht] = useState(null)
  const [ergebnis, setErgebnis] = useState(null)
  const [laeuft, setLaeuft] = useState(false)

  // ── Datei einlesen ─────────────────────────────────────────────────────────

  const uebernehmen = (kopfzeilen, datensaetze) => {
    if (!datensaetze.length) {
      toast.error('Die Datei enthält keine Datenzeilen')
      return
    }
    setSpalten(kopfzeilen)
    setZeilen(datensaetze)

    // Vorschlag: Spalte auf gleichnamiges Feld (Name oder Schlüssel)
    const vorschlag = {}
    kopfzeilen.forEach(spalte => {
      const treffer = felder.find(f =>
        f.name.toLowerCase() === String(spalte).toLowerCase() ||
        f.key.toLowerCase() === String(spalte).toLowerCase())
      if (treffer) vorschlag[spalte] = treffer.key
    })
    setZuordnung(vorschlag)
    setSchritt('zuordnen')
  }

  const dateiGewaehlt = (e) => {
    const datei = e.target.files?.[0]
    if (!datei) return
    setDateiname(datei.name)
    // Altes Binärformat (.xls, Excel 97–2003) wird nicht mehr gelesen: Die
    // frühere Bibliothek „xlsx" hatte auf npm bekannte, nicht behobene
    // Sicherheitslücken (Audit SEC-008) und wurde durch ExcelJS ersetzt, das
    // nur das heutige .xlsx-Format kennt. Wer noch .xls hat, speichert die
    // Datei in Excel einmal als .xlsx.
    if (/\.xls$/i.test(datei.name)) {
      toast.error('Das alte Excel-Format (.xls) wird nicht unterstützt — bitte in Excel als .xlsx speichern')
      return
    }
    const istExcel = /\.(xlsx|xlsm)$/i.test(datei.name)

    if (istExcel) {
      const leser = new FileReader()
      leser.onload = async (ev) => {
        try {
          // Erst beim ersten Excel-Import nachgeladen: ExcelJS ist rund 1 MB
          // groß und wird von den wenigsten Seitenaufrufen gebraucht.
          const { default: ExcelJS } = await import('exceljs')
          const mappe = new ExcelJS.Workbook()
          await mappe.xlsx.load(ev.target.result)
          const blatt = mappe.worksheets[0]
          if (!blatt || blatt.rowCount === 0) { toast.error('Das erste Tabellenblatt ist leer'); return }
          const tabelle = []
          blatt.eachRow({ includeEmpty: false }, (zeile) => {
            // zeile.values ist 1-basiert (Index 0 bleibt leer)
            const werte = zeile.values.slice(1).map(zellwertAlsText)
            tabelle.push(werte)
          })
          if (!tabelle.length) { toast.error('Das erste Tabellenblatt ist leer'); return }
          const kopf = tabelle[0].map(z => String(z).trim())
          const daten = tabelle.slice(1)
            .filter(r => r.some(z => String(z).trim() !== ''))
            .map(r => Object.fromEntries(kopf.map((s, i) => [s, r[i] ?? ''])))
          uebernehmen(kopf, daten)
          if (mappe.worksheets.length > 1) {
            toast(`Es wurde das erste Tabellenblatt „${blatt.name}" gelesen`)
          }
        } catch {
          toast.error('Die Excel-Datei konnte nicht gelesen werden')
        }
      }
      leser.onerror = () => toast.error('Datei konnte nicht gelesen werden')
      leser.readAsArrayBuffer(datei)
      return
    }

    Papa.parse(datei, {
      header: true, skipEmptyLines: true, delimiter: '',
      complete: (ergebnis) => uebernehmen(ergebnis.meta.fields || [], ergebnis.data),
      error: () => toast.error('Datei konnte nicht gelesen werden'),
    })
  }

  // ── Zeilen für den Server aufbereiten ──────────────────────────────────────

  const zugeordnet = Object.entries(zuordnung)
    .filter(([, key]) => key && key !== IGNORIEREN)

  const zeilenFuerServer = () => zeilen.map(zeile => {
    const daten = {}
    zugeordnet.forEach(([spalte, key]) => { daten[key] = zeile[spalte] ?? '' })
    return daten
  })

  const senden = async (optionen) => {
    setLaeuft(true)
    try {
      const res = await masterdataApi.importRecords(slug, zeilenFuerServer(), {
        match_field: abgleichsfeld || null,
        ...optionen,
      })
      return res.data
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Import fehlgeschlagen')
      return null
    } finally {
      setLaeuft(false)
    }
  }

  const pruefen = async () => {
    const ergebnis = await senden({ dry_run: true })
    if (ergebnis) { setBericht(ergebnis); setSchritt('bericht') }
  }

  const schreiben = async (fehlerhafteUeberspringen) => {
    setSchritt('laeuft')
    const res = await senden({
      dry_run: false, skip_invalid: fehlerhafteUeberspringen })
    if (!res) { setSchritt('bericht'); return }
    setErgebnis(res)
    setSchritt('fertig')
  }

  // ── Neues Feld beim Zuordnen anlegen (nur Admin) ───────────────────────────

  const feldAngelegt = (feld, fuerSpalte) => {
    setFelder(bisher => [...bisher, feld])
    setZuordnung(bisher => ({ ...bisher, [fuerSpalte]: feld.key }))
    setNeuesFeldFuer(null)
    toast.success(`Feld „${feld.name}" angelegt`)
  }

  const titel = {
    datei: 'Import — Datei wählen',
    zuordnen: 'Import — Spalten zuordnen',
    bericht: 'Import — Prüfergebnis',
    laeuft: 'Import läuft',
    fertig: 'Import abgeschlossen',
  }[schritt]

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4 sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] flex flex-col">

        <div className="flex items-center justify-between p-5 border-b border-gray-100 flex-shrink-0">
          <div>
            <h2 className="text-lg font-bold text-gray-900">{titel} — {entityType.name}</h2>
            {dateiname && schritt !== 'datei' && (
              <p className="text-xs text-gray-400 mt-0.5">{dateiname} · {zeilen.length} Zeilen</p>
            )}
          </div>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition">
            <X size={20} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">

          {/* Schritt 1: Datei */}
          {schritt === 'datei' && (
            <div className="space-y-4">
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
                <p className="font-medium mb-1">Was die Datei mitbringen muss:</p>
                <ul className="list-disc list-inside space-y-1 text-blue-700">
                  <li>Erste Zeile mit den Spaltenüberschriften</li>
                  <li>CSV mit Semikolon oder Komma (wird erkannt), Zeichensatz UTF-8</li>
                  <li>Excel: gelesen wird das erste Tabellenblatt</li>
                  <li>Datum wie 31.12.2026, Zahlen wie 1.234,56 — beides wird verstanden</li>
                </ul>
              </div>

              <div
                onClick={() => fileRef.current?.click()}
                className="border-2 border-dashed border-gray-300 hover:border-primary-400 hover:bg-primary-50 rounded-xl p-10 text-center cursor-pointer transition"
              >
                <FileText size={40} className="mx-auto mb-3 text-gray-300" />
                <p className="font-medium text-gray-600">CSV- oder Excel-Datei auswählen</p>
                <p className="text-sm text-gray-400 mt-1">.csv oder .xlsx</p>
                <input ref={fileRef} type="file" accept=".csv,.txt,.xlsx,.xlsm"
                  className="hidden" onChange={dateiGewaehlt} />
              </div>
            </div>
          )}

          {/* Schritt 2: Zuordnen */}
          {schritt === 'zuordnen' && (
            <div className="space-y-5">
              <div className="flex items-center gap-2 text-sm text-gray-600 bg-gray-50 rounded-xl p-3">
                <Check size={16} className="text-green-500" />
                <span>{zeilen.length} Zeilen · {spalten.length} Spalten erkannt</span>
              </div>

              <div>
                <p className="text-sm font-semibold text-gray-800 mb-1">Spaltenzuordnung</p>
                <p className="text-xs text-gray-500 mb-3">
                  Nicht benötigte Spalten auf „Ignorieren" lassen — sie werden übergangen.
                  {isAdmin && ' Fehlt ein Feld, kannst du es hier direkt anlegen.'}
                </p>
                <div className="space-y-2">
                  {spalten.map(spalte => (
                    <div key={spalte} className="flex items-center gap-2 text-sm">
                      <div className="w-1/3 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-gray-700 font-mono text-xs truncate">
                        {spalte}
                      </div>
                      <span className="text-gray-400">→</span>
                      <select
                        value={zuordnung[spalte] || IGNORIEREN}
                        onChange={e => setZuordnung({ ...zuordnung, [spalte]: e.target.value })}
                        className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface"
                      >
                        <option value={IGNORIEREN}>— Ignorieren —</option>
                        {felder.map(f => (
                          <option key={f.key} value={f.key}>{f.name}</option>
                        ))}
                      </select>
                      {isAdmin && (
                        <button
                          onClick={() => setNeuesFeldFuer(spalte)}
                          title="Neues Feld für diese Spalte anlegen"
                          className="p-2 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition">
                          <Plus size={15} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <p className="text-sm font-semibold text-gray-800 mb-1">Vorhandene Datensätze erkennen</p>
                <p className="text-xs text-gray-500 mb-2">
                  Feld wählen, an dem ein Datensatz wiedererkannt wird (z.B. Kundennummer).
                  Treffer werden aktualisiert statt ein zweites Mal angelegt. Ohne Auswahl
                  wird jede Zeile neu angelegt.
                </p>
                <select
                  value={abgleichsfeld}
                  onChange={e => setAbgleichsfeld(e.target.value)}
                  className="w-full sm:w-2/3 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface"
                >
                  <option value="">— Kein Abgleich, alles neu anlegen —</option>
                  {zugeordnet.map(([, key]) => {
                    const feld = felder.find(f => f.key === key)
                    return feld ? <option key={key} value={key}>{feld.name}</option> : null
                  })}
                </select>
              </div>

              {zeilen.slice(0, 3).length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                    Vorschau (erste {Math.min(3, zeilen.length)} von {zeilen.length} Zeilen)
                  </p>
                  <div className="overflow-x-auto border border-gray-200 rounded-xl">
                    <table className="w-full text-xs">
                      <thead className="bg-gray-50">
                        <tr>
                          {spalten.map(s => (
                            <th key={s} className="px-3 py-2 text-left text-gray-500 font-medium whitespace-nowrap">{s}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {zeilen.slice(0, 3).map((zeile, i) => (
                          <tr key={i} className="border-t border-gray-100">
                            {spalten.map(s => (
                              <td key={s} className="px-3 py-2 text-gray-600 max-w-[150px] truncate">{zeile[s]}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Schritt 3: Prüfbericht */}
          {schritt === 'bericht' && bericht && (
            <Pruefbericht bericht={bericht} abgleich={!!abgleichsfeld} />
          )}

          {/* Schritt 4: läuft */}
          {schritt === 'laeuft' && (
            <div className="flex flex-col items-center justify-center py-12 gap-4">
              <Loader2 size={40} className="animate-spin text-primary-500" />
              <p className="text-gray-600 font-medium">Datensätze werden geschrieben …</p>
            </div>
          )}

          {/* Schritt 5: fertig */}
          {schritt === 'fertig' && ergebnis && (
            <div className="flex flex-col items-center justify-center py-10 gap-4 text-center">
              <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center">
                <Check size={32} className="text-green-600" />
              </div>
              <div>
                <p className="text-xl font-bold text-gray-900">
                  {ergebnis.angelegt} angelegt · {ergebnis.aktualisiert} aktualisiert
                </p>
                {ergebnis.uebersprungen > 0 && (
                  <p className="text-amber-600 mt-1">
                    {ergebnis.uebersprungen} Zeilen übersprungen
                  </p>
                )}
              </div>
              <button
                onClick={() => onImported(ergebnis.angelegt + ergebnis.aktualisiert)}
                className="px-6 py-2.5 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 transition"
              >
                Fertig
              </button>
            </div>
          )}
        </div>

        {/* Fußzeile */}
        {schritt === 'zuordnen' && (
          <div className="flex gap-3 p-5 border-t border-gray-100 flex-shrink-0">
            <button onClick={onClose}
              className="flex-1 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition">
              Abbrechen
            </button>
            <button
              onClick={pruefen}
              disabled={laeuft || zugeordnet.length === 0}
              className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2"
            >
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
            {bericht.beanstandungen.length > 0 && (
              <button
                onClick={() => schreiben(true)}
                disabled={laeuft || bericht.anlegen + bericht.aktualisieren === 0}
                className="flex-1 py-2.5 border border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100 disabled:opacity-50 font-medium rounded-xl transition"
              >
                Beanstandete überspringen und {bericht.anlegen + bericht.aktualisieren} Zeilen importieren
              </button>
            )}
            {bericht.beanstandungen.length === 0 && (
              <button
                onClick={() => schreiben(false)}
                disabled={laeuft || bericht.geprueft === 0}
                className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2"
              >
                <Upload size={16} />
                {bericht.anlegen} anlegen{bericht.aktualisieren > 0 ? `, ${bericht.aktualisieren} aktualisieren` : ''}
              </button>
            )}
          </div>
        )}
      </div>

      {neuesFeldFuer !== null && (
        <NeuesFeldDialog
          slug={slug}
          spalte={neuesFeldFuer}
          beispiel={zeilen[0]?.[neuesFeldFuer]}
          vorhandeneKeys={felder.map(f => f.key)}
          onClose={() => setNeuesFeldFuer(null)}
          onAngelegt={(feld) => feldAngelegt(feld, neuesFeldFuer)}
        />
      )}
    </div>
  )
}

/** Ergebnis des Probelaufs — Zahlen oben, Beanstandungen mit Grund darunter. */
function Pruefbericht({ bericht, abgleich }) {
  const beanstandeteZeilen = new Set(bericht.beanstandungen.map(b => b.zeile)).size

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Kennzahl label="Geprüft" wert={bericht.geprueft} />
        <Kennzahl label="Neu anlegen" wert={bericht.anlegen} farbe="text-green-600" />
        <Kennzahl label="Aktualisieren" wert={bericht.aktualisieren}
          farbe="text-blue-600" grau={!abgleich} />
        <Kennzahl label="Beanstandet" wert={beanstandeteZeilen}
          farbe={beanstandeteZeilen ? 'text-amber-600' : 'text-gray-400'} />
      </div>

      {!abgleich && (
        <p className="text-xs text-gray-500">
          Ohne Abgleichsfeld wird jede Zeile neu angelegt — auch wenn es den
          Datensatz schon gibt.
        </p>
      )}

      {bericht.beanstandungen.length === 0 ? (
        <div className="flex items-center gap-2 bg-green-50 border border-green-200 rounded-xl p-4 text-sm text-green-800">
          <Check size={18} /> Alle Zeilen sind in Ordnung. Bisher wurde nichts geschrieben.
        </div>
      ) : (
        <div>
          <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-900 mb-3">
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <span>
              {beanstandeteZeilen} von {bericht.geprueft} Zeilen können so nicht
              übernommen werden. Es wurde noch nichts geschrieben — du kannst die
              Datei korrigieren und neu beginnen oder diese Zeilen auslassen.
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

function Kennzahl({ label, wert, farbe = 'text-gray-900', grau = false }) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-xl px-3 py-2.5">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={`text-lg font-bold ${grau ? 'text-gray-300' : farbe}`}>{wert}</p>
    </div>
  )
}

/**
 * Neues Feld direkt beim Zuordnen anlegen — nur für Administratoren, weil
 * Felddefinitionen im ganzen Modul Adminsache sind (require_admin am Endpunkt).
 * Der Typ wird aus dem ersten Wert vorgeschlagen, ist aber frei änderbar:
 * Ein Vorschlag spart Tipparbeit, eine Automatik würde falsch raten.
 */
function NeuesFeldDialog({ slug, spalte, beispiel, vorhandeneKeys, onClose, onAngelegt }) {
  const raten = () => {
    const wert = String(beispiel ?? '').trim()
    if (!wert) return 'text'
    if (/^\d{1,2}[.\/-]\d{1,2}[.\/-]\d{2,4}$/.test(wert) || /^\d{4}-\d{2}-\d{2}$/.test(wert)) return 'date'
    if (/^[^@\s]+@[^@\s]+\.[a-z]{2,}$/i.test(wert)) return 'email'
    if (/^https?:\/\//i.test(wert)) return 'url'
    if (/^-?[\d.]+,?\d*$/.test(wert) && /\d/.test(wert)) return 'number'
    if (/^(ja|nein|true|false|x)$/i.test(wert)) return 'checkbox'
    return 'text'
  }

  const [name, setName] = useState(String(spalte))
  const [typ, setTyp] = useState(raten())
  const [optionen, setOptionen] = useState('')
  const [pflicht, setPflicht] = useState(false)
  const [laeuft, setLaeuft] = useState(false)

  const key = machKey(name)
  const belegt = vorhandeneKeys.includes(key)

  const anlegen = async () => {
    if (!name.trim()) { toast.error('Bitte einen Feldnamen angeben'); return }
    if (belegt) { toast.error('Ein Feld mit diesem Namen gibt es bereits'); return }
    setLaeuft(true)
    try {
      const res = await masterdataApi.addField(slug, {
        name: name.trim(),
        key,                      // der Server bildet ihn selbst, wir schicken denselben
        field_type: typ,
        is_required: pflicht,
        show_in_list: false,      // eine importierte Spalte muss nicht gleich in der Liste stehen
        options: typ === 'dropdown'
          ? optionen.split(',').map(o => o.trim()).filter(Boolean)
          : null,
      })
      onAngelegt(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Feld konnte nicht angelegt werden')
    } finally {
      setLaeuft(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-[60] flex items-center justify-center p-4 sheet-safe">
      <div className="bg-surface rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h3 className="font-bold text-gray-900">Neues Feld für „{spalte}"</h3>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-lg">
            <X size={18} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Feldname</label>
            <input value={name} onChange={e => setName(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
            {belegt && (
              <p className="text-xs text-red-600 mt-1">
                Dieses Feld gibt es schon — bitte oben in der Liste zuordnen.
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Feldtyp</label>
            <select value={typ} onChange={e => setTyp(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 bg-surface">
              {FELDTYPEN.map(([wert, label]) => (
                <option key={wert} value={wert}>{label}</option>
              ))}
            </select>
            {beispiel !== undefined && beispiel !== '' && (
              <p className="text-xs text-gray-500 mt-1">
                Erster Wert in der Datei: <span className="font-mono">{String(beispiel)}</span>
              </p>
            )}
          </div>

          {typ === 'dropdown' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Auswahlmöglichkeiten (mit Komma getrennt)
              </label>
              <input value={optionen} onChange={e => setOptionen(e.target.value)}
                placeholder="Kunde, Lieferant, Interessent"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
              <p className="text-xs text-gray-500 mt-1">
                Werte in der Datei, die hier nicht vorkommen, werden beim Prüfen beanstandet.
              </p>
            </div>
          )}

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={pflicht} onChange={e => setPflicht(e.target.checked)}
              className="w-4 h-4 rounded" />
            Pflichtfeld
          </label>
        </div>

        <div className="flex gap-3 p-5 border-t border-gray-100">
          <button onClick={onClose}
            className="flex-1 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition">
            Abbrechen
          </button>
          <button onClick={anlegen} disabled={laeuft || belegt || !name.trim()}
            className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2">
            {laeuft ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
            Anlegen
          </button>
        </div>
      </div>
    </div>
  )
}
