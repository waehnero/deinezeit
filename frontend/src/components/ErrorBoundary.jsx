import { Component } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

/**
 * Fängt Render-Fehler der Seiten ab (Audit UX-001).
 *
 * Ohne Error Boundary hängt React bei einem Fehler im Render den ganzen Baum
 * aus — der Benutzer sieht eine weiße Seite ohne Hinweis, und ungespeicherte
 * Eingaben in anderen Teilen der Oberfläche sind verloren. Hier bekommt er
 * stattdessen eine Meldung, den technischen Text zum Weitergeben und einen
 * Knopf zum Neuladen. Fehler in Event-Handlern und Promises fängt eine
 * Boundary bewusst nicht — dafür sind die toast-Meldungen zuständig.
 */
export default class ErrorBoundary extends Component {
  state = { fehler: null }

  static getDerivedStateFromError(fehler) {
    return { fehler }
  }

  componentDidCatch(fehler, info) {
    // Ins Browser-Log — mit Komponentenstapel, damit man die Stelle findet.
    console.error('Unbehandelter Fehler in der Oberfläche:', fehler, info?.componentStack)
  }

  render() {
    if (!this.state.fehler) return this.props.children
    const text = String(this.state.fehler?.message || this.state.fehler || 'Unbekannter Fehler')
    return (
      <div className="min-h-[60vh] flex items-center justify-center p-6">
        <div className="max-w-lg w-full bg-surface border border-neutral-200 rounded-xl p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <AlertTriangle size={22} className="text-red-500 shrink-0 mt-0.5" />
            <div className="min-w-0 flex-1">
              <h1 className="text-lg font-semibold text-neutral-900">Diese Ansicht konnte nicht angezeigt werden</h1>
              <p className="text-sm text-neutral-600 mt-1">
                Ein Fehler in der Oberfläche hat die Seite angehalten. Deine übrigen Daten sind davon nicht betroffen.
                Lade die Seite neu; tritt der Fehler erneut auf, gib die Meldung unten an den Administrator weiter.
              </p>
              <pre className="mt-3 text-xs text-neutral-500 bg-neutral-50 border border-neutral-100 rounded-lg p-3 overflow-x-auto whitespace-pre-wrap break-words">{text}</pre>
              <div className="mt-4 flex gap-2">
                <button type="button" onClick={() => window.location.reload()}
                  className="btn-primary inline-flex items-center gap-1.5">
                  <RefreshCw size={14} /> Seite neu laden
                </button>
                <button type="button" onClick={() => { this.setState({ fehler: null }); window.location.assign('/') }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm border border-neutral-200 rounded-lg hover:bg-neutral-50">
                  Zur Startseite
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }
}
