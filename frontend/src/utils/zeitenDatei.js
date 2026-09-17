/**
 * Zeiten-Import: Dateien aus Fremdsystemen in eine Tabelle überführen.
 *
 * Jeder Leser liefert dasselbe: { spalten: [..], zeilen: [{spalte: text}], hinweise: [..] }.
 * Der Assistent (components/ZeitenImport.jsx) weiß danach nicht mehr, woher die
 * Tabelle kam — CSV, Excel, JSON, Kalender oder (über den Server) ein PDF gehen
 * denselben Weg: Spalten zuordnen → Probelauf → Bericht → bewusst importieren.
 *
 * Gelesen wird im Browser (Beschluss vom Stammdaten-Import, 18.08.2026): kein
 * Upload-Endpunkt, keine Python-Abhängigkeit, zum Server gehen nur zugeordnete
 * Zeilen. Einzige Ausnahme ist das PDF, das die KI-Schnittstelle liest.
 *
 * Die Werte bleiben TEXT, so wie ein Mensch sie in der Datei sieht. Gedeutet
 * wird ausschließlich am Server (services/zeiten_import.py) — zwei Stellen, die
 * Datumsangaben deuten, deuten sie irgendwann verschieden.
 */
import Papa from 'papaparse'

const zwei = (n) => String(n).padStart(2, '0')

// ── Excel ────────────────────────────────────────────────────────────────────

/**
 * Zellwert in die Schreibweise bringen, die in Excel zu sehen ist.
 *
 * Anders als beim Stammdaten-Import zählt hier die Uhrzeit: Excel kennt nur
 * einen Zahlentyp für Datum UND Zeit. Eine reine Uhrzeit-Zelle kommt als Datum
 * am 30.12.1899 an, ein reines Datum mit 00:00 Uhr. ExcelJS liefert beides in
 * UTC — deshalb die getUTC*-Zugriffe, sonst verschiebt die Zeitzone des
 * Browsers jede Uhrzeit um ein bis zwei Stunden.
 */
export function excelZellwert(wert) {
  if (wert === null || wert === undefined) return ''
  if (wert instanceof Date) {
    const zeit = `${zwei(wert.getUTCHours())}:${zwei(wert.getUTCMinutes())}`
    const tag = `${zwei(wert.getUTCDate())}.${zwei(wert.getUTCMonth() + 1)}.${wert.getUTCFullYear()}`
    if (wert.getUTCFullYear() < 1901) return zeit            // reine Uhrzeit
    if (zeit === '00:00' && wert.getUTCSeconds() === 0) return tag
    return `${tag} ${zeit}`
  }
  if (typeof wert === 'object') {
    if ('result' in wert) return excelZellwert(wert.result)             // Formel
    if (Array.isArray(wert.richText)) return wert.richText.map(r => r.text).join('')
    if ('text' in wert) return excelZellwert(wert.text)                 // Hyperlink
    if ('error' in wert) return ''
    return String(wert)
  }
  if (typeof wert === 'boolean') return wert ? 'ja' : 'nein'
  return String(wert)
}

async function excelLesen(datei) {
  // Erst beim ersten Excel-Import nachgeladen (rund 1 MB).
  const { default: ExcelJS } = await import('exceljs')
  const mappe = new ExcelJS.Workbook()
  await mappe.xlsx.load(await datei.arrayBuffer())
  const blatt = mappe.worksheets[0]
  const tabelle = []
  blatt?.eachRow({ includeEmpty: false }, (zeile) => {
    tabelle.push(zeile.values.slice(1).map(excelZellwert))   // values ist 1-basiert
  })
  if (!tabelle.length) throw new Error('Das erste Tabellenblatt ist leer')
  const hinweise = mappe.worksheets.length > 1
    ? [`Gelesen wurde nur das erste Tabellenblatt „${blatt.name}".`] : []
  return ausMatrix(tabelle, hinweise)
}

/** Erste Zeile = Überschriften; leere und doppelte Überschriften eindeutig machen. */
export function ausMatrix(tabelle, hinweise = []) {
  const spalten = []
  tabelle[0].forEach((z, i) => {
    const basis = String(z ?? '').trim() || `Spalte ${i + 1}`
    let name = basis
    for (let n = 2; spalten.includes(name); n++) name = `${basis} (${n})`
    spalten.push(name)
  })
  const zeilen = tabelle.slice(1)
    .filter(r => r.some(z => String(z ?? '').trim() !== ''))
    .map(r => Object.fromEntries(spalten.map((s, i) => [s, String(r[i] ?? '').trim()])))
  return { spalten, zeilen, hinweise }
}

// ── CSV ──────────────────────────────────────────────────────────────────────

function csvLesen(datei) {
  return new Promise((ok, fehler) => {
    Papa.parse(datei, {
      header: false, skipEmptyLines: true, delimiter: '',     // Trennzeichen wird erkannt
      complete: (e) => {
        if (!e.data.length) { fehler(new Error('Die Datei ist leer')); return }
        ok(ausMatrix(e.data))
      },
      error: () => fehler(new Error('Die Datei konnte nicht gelesen werden')),
    })
  })
}

// ── JSON ─────────────────────────────────────────────────────────────────────

/** {a: {b: 1}} → {"a.b": "1"} — Clockify liefert z.B. timeInterval.start. */
function flach(objekt, vorsilbe = '', ziel = {}) {
  Object.entries(objekt || {}).forEach(([k, v]) => {
    const name = vorsilbe ? `${vorsilbe}.${k}` : k
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) flach(v, name, ziel)
    else if (Array.isArray(v)) ziel[name] = v.map(x => (typeof x === 'object' ? JSON.stringify(x) : x)).join(', ')
    else if (typeof v === 'boolean') ziel[name] = v ? 'ja' : 'nein'
    else ziel[name] = v === null || v === undefined ? '' : String(v)
  })
  return ziel
}

export function jsonZuTabelle(text) {
  let daten
  try { daten = JSON.parse(text) } catch { throw new Error('Die Datei enthält kein gültiges JSON') }

  // Entweder die Liste selbst oder ein Umschlag mit genau einer Liste von
  // Objekten ({"data": [...]}, {"time_entries": [...]}).
  let liste = Array.isArray(daten) ? daten : null
  if (!liste && daten && typeof daten === 'object') {
    const listen = Object.values(daten)
      .filter(v => Array.isArray(v) && v.length && typeof v[0] === 'object')
    if (listen.length === 1) liste = listen[0]
    else if (listen.length > 1) {
      throw new Error('Die JSON-Datei enthält mehrere Listen — es ist nicht klar, welche die Zeiteinträge sind')
    }
  }
  liste = (liste || []).filter(e => e && typeof e === 'object' && !Array.isArray(e))
  if (!liste.length) throw new Error('In der JSON-Datei wurde keine Liste von Einträgen gefunden')

  const zeilenRoh = liste.map(e => flach(e))
  const spalten = []
  zeilenRoh.forEach(z => Object.keys(z).forEach(k => { if (!spalten.includes(k)) spalten.push(k) }))
  const zeilen = zeilenRoh.map(z => Object.fromEntries(spalten.map(s => [s, z[s] ?? ''])))
  return { spalten, zeilen, hinweise: [] }
}

// ── Kalender (ICS) ───────────────────────────────────────────────────────────

const ICS_TEXT = (s) => s.replace(/\\n/gi, ' ').replace(/\\([,;\\])/g, '$1').trim()

/**
 * DTSTART/DTEND in Text für den Server.
 *   20260803T053000Z           → ISO mit Z (der Server rechnet in Ortszeit um)
 *   20260803T073000 (+ TZID)   → „03.08.2026 07:30" — Wanduhrzeit
 *   20260803 (ganztägig)       → „03.08.2026" — hat keine Uhrzeit und wird
 *                                 vom Server deshalb beanstandet, nicht erfunden
 */
function icsZeit(wert) {
  const m = /^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?$/.exec(wert.trim())
  if (!m) return wert
  const [, j, mo, t, h, mi, , z] = m
  if (h === undefined) return `${t}.${mo}.${j}`
  if (z) return `${j}-${mo}-${t}T${h}:${mi}:00Z`
  return `${t}.${mo}.${j} ${h}:${mi}`
}

export function icsZuTabelle(text) {
  // Zeilenfortsetzung auflösen: Eine Folgezeile beginnt mit Leerzeichen oder Tab.
  const zeilenRoh = text.replace(/\r\n/g, '\n').replace(/\n[ \t]/g, '').split('\n')
  const spalten = ['Beginn', 'Ende', 'Titel', 'Beschreibung', 'Ort']
  const zeilen = []
  const fremdeZonen = new Set()
  let serien = 0
  let termin = null

  zeilenRoh.forEach(zeile => {
    if (zeile === 'BEGIN:VEVENT') { termin = {}; return }
    if (zeile === 'END:VEVENT') {
      if (termin) {
        zeilen.push(Object.fromEntries(spalten.map(s => [s, termin[s] || ''])))
        if (termin.serie) serien++
      }
      termin = null
      return
    }
    if (!termin) return
    const trenner = zeile.indexOf(':')
    if (trenner < 0) return
    const [name, ...parameter] = zeile.slice(0, trenner).split(';')
    const wert = zeile.slice(trenner + 1)
    const tzid = parameter.find(p => p.toUpperCase().startsWith('TZID='))?.slice(5)
    if (tzid) fremdeZonen.add(tzid)
    switch (name.toUpperCase()) {
      case 'DTSTART': termin.Beginn = icsZeit(wert); break
      case 'DTEND': termin.Ende = icsZeit(wert); break
      case 'SUMMARY': termin.Titel = ICS_TEXT(wert); break
      case 'DESCRIPTION': termin.Beschreibung = ICS_TEXT(wert); break
      case 'LOCATION': termin.Ort = ICS_TEXT(wert); break
      case 'RRULE': termin.serie = true; break
      default:
    }
  })

  if (!zeilen.length) throw new Error('In der Kalenderdatei wurden keine Termine gefunden')
  const hinweise = []
  if (serien) {
    hinweise.push(`${serien} Serientermin(e): Übernommen wird nur der erste Termin der Serie, die Wiederholungen nicht.`)
  }
  if (fremdeZonen.size) {
    hinweise.push(`Uhrzeiten mit Zeitzonen-Angabe (${[...fremdeZonen].join(', ')}) werden als Ortszeit übernommen, so wie sie im Kalender stehen.`)
  }
  return { spalten, zeilen, hinweise }
}

// ── Einstieg ─────────────────────────────────────────────────────────────────

export const DATEITYPEN = '.csv,.txt,.xlsx,.xlsm,.json,.ics,.pdf'

export const istPdf = (datei) =>
  /\.pdf$/i.test(datei.name) || datei.type === 'application/pdf'

/** Alles außer PDF — das geht über den Server (zeiterfassungApi.importPdf). */
export async function dateiZuTabelle(datei) {
  const name = datei.name.toLowerCase()
  if (name.endsWith('.xls')) {
    // Siehe CsvImportExport.jsx: .xls wird seit dem Audit (SEC-008) nicht mehr gelesen.
    throw new Error('Das alte Excel-Format (.xls) wird nicht unterstützt — bitte in Excel als .xlsx speichern')
  }
  if (/\.(xlsx|xlsm)$/.test(name)) return excelLesen(datei)
  if (name.endsWith('.json')) return jsonZuTabelle(await datei.text())
  if (name.endsWith('.ics')) return icsZuTabelle(await datei.text())
  return csvLesen(datei)
}

/** Tabelle als CSV (Semikolon, mit BOM — so öffnet Excel-AT sie richtig). */
export function tabelleAlsCsv({ spalten, zeilen }) {
  return '﻿' + Papa.unparse(
    { fields: spalten, data: zeilen.map(z => spalten.map(s => z[s] ?? '')) },
    { delimiter: ';' })
}

/** Zuordnungsvorschlag: Spalte → Zielfeld, über Name, Schlüssel und Synonyme. */
export function zuordnungVorschlagen(spalten, zielfelder) {
  const vorschlag = {}
  const vergeben = new Set()
  spalten.forEach(spalte => {
    const s = String(spalte).toLowerCase().trim()
    const treffer = zielfelder.find(f => !vergeben.has(f.key) && (
      f.name.toLowerCase() === s || f.key.toLowerCase() === s ||
      (f.synonyme || []).includes(s)))
    if (treffer) { vorschlag[spalte] = treffer.key; vergeben.add(treffer.key) }
  })
  return vorschlag
}
