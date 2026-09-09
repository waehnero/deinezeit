import { lazy } from 'react'

/**
 * Seiten erst beim ersten Aufruf laden (Audit PERF-002, K-26b).
 *
 * Vorher steckten alle ~35 Seiten in einem 1,7-MB-Bundle, das jeder Benutzer
 * beim Anmelden komplett herunterlud — auch der, der nur Zeiten bucht. Mit
 * `React.lazy` bekommt jede Seite ihre eigene Datei, die der Browser erst
 * holt, wenn die Route aufgerufen wird.
 *
 * Der Haken bei einer App ohne Service Worker: Nach einem Deploy tragen die
 * Dateien neue Hash-Namen. Ein Browser, der die Anwendung noch mit dem alten
 * index.html offen hat, fragt beim nächsten Seitenwechsel nach einer Datei,
 * die es am Server nicht mehr gibt — der Import scheitert. Dafür laden wir die
 * Seite genau einmal neu (Merker in sessionStorage, damit es bei einem echten
 * Fehler nicht endlos kreist); danach hat der Browser das neue index.html mit
 * den richtigen Namen. Ungespeicherte Eingaben der alten Seite sind in dem
 * Moment ohnehin schon verlassen, weil der Benutzer gerade navigiert.
 */
const MERKER = 'deinezeit.chunk-neu-geladen'

export function lazySeite(laden) {
  return lazy(() =>
    laden().then(modul => {
      try { sessionStorage.removeItem(MERKER) } catch { /* privater Modus */ }
      return modul
    }).catch(fehler => {
      let schonNeuGeladen = false
      try {
        schonNeuGeladen = sessionStorage.getItem(MERKER) === '1'
        if (!schonNeuGeladen) sessionStorage.setItem(MERKER, '1')
      } catch { /* privater Modus: dann ohne Merker, ein Versuch */ }
      if (!schonNeuGeladen) {
        window.location.reload()
        // Bis der Reload greift, eine leere Seite liefern statt eines Fehlers.
        return new Promise(() => {})
      }
      throw fehler
    })
  )
}
