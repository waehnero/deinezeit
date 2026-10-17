/**
 * Sichere HTML-Vorschau von Dokumenten (Belege, Projektzeitbericht) — S02.
 *
 * Bisher wurde das vom Server gelieferte Vorschau-HTML als Blob-URL direkt
 * geöffnet. Ein Blob-Dokument läuft im Ursprung der App: Wäre im HTML trotz
 * serverseitiger Bereinigung ein Skript durchgerutscht, liefe es mit Zugriff
 * auf die Sitzung. Die HTTP-Header der Vorschau (CSP, sandbox) gelten für ein
 * Blob nicht mehr.
 *
 * Jetzt kommt das Dokument in ein <iframe sandbox="">: undurchsichtiger
 * Ursprung, keine Skripte, keine Formulare, keine Pop-ups, keine Navigation
 * des Fensters. Die Hülle selbst enthält nur statisches Markup und wird über
 * die DOM-API gebaut — das Vorschau-HTML steht ausschließlich als korrekt
 * maskierter Attributwert in `srcdoc`.
 *
 * Einschränkung: Drucken aus dem Vorschaufenster druckt die Hülle (sichtbarer
 * Ausschnitt). Zum Drucken ist das PDF da.
 */

const HUELLE_CSS =
  'html,body{margin:0;height:100%;background:#ebebeb}' +
  'iframe{border:0;display:block;width:100%;height:100%}'

/** Baut die Hüllseite (vollständiges HTML-Dokument als Text). */
export function vorschauSeite(html, titel = 'Vorschau') {
  const doc = document.implementation.createHTMLDocument(String(titel))
  const meta = doc.createElement('meta')
  meta.setAttribute('charset', 'utf-8')
  doc.head.prepend(meta)
  const stil = doc.createElement('style')
  stil.textContent = HUELLE_CSS
  doc.head.appendChild(stil)

  const rahmen = doc.createElement('iframe')
  rahmen.setAttribute('sandbox', '')               // nichts erlaubt
  rahmen.setAttribute('referrerpolicy', 'no-referrer')
  rahmen.setAttribute('title', String(titel))
  rahmen.setAttribute('srcdoc', String(html ?? ''))
  doc.body.appendChild(rahmen)
  return '<!DOCTYPE html>\n' + doc.documentElement.outerHTML
}

/** Öffnet die Vorschau in einem neuen Tab. */
export function oeffneHtmlVorschau(html, titel = 'Vorschau') {
  const blob = new Blob([vorschauSeite(html, titel)], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener')
  setTimeout(() => URL.revokeObjectURL(url), 60_000)
}
