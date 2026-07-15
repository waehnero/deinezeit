import { useState, useEffect, useRef } from 'react'
import { zeiterfassungApi } from '../services/api'
import toast from 'react-hot-toast'
import { Mic, Sparkles, Square, X, Loader2 } from 'lucide-react'

/**
 * Sprach-Nachtragen (Aufnahme → KI → Vorschlag).
 *
 * Nimmt Sprache über die Browser-Spracherkennung (de-DE) auf, schickt das
 * Transkript an die eingerichtete KI (Einstellungen → System → KI) und liefert
 * über onResult einen Vorschlag, der den Nachtragen-Dialog vorbefüllt.
 * Ohne Browser-Unterstützung (z.B. Firefox) kann der Text manuell eingegeben
 * werden. Wird von der Zeiterfassung UND dem Dashboard-Widget genutzt.
 */
export default function VoiceEntryDialog({ onClose, onResult }) {
  const SR = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)
  const [recording, setRecording] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [interim, setInterim] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const recRef = useRef(null)
  const baseRef = useRef('')   // Text vor der aktuellen Aufnahme-Session

  useEffect(() => () => { try { recRef.current?.abort() } catch {} }, [])

  const startRecording = () => {
    if (!SR) return
    const rec = new SR()
    rec.lang = 'de-DE'
    rec.continuous = true
    rec.interimResults = true
    baseRef.current = transcript ? transcript.trim() + ' ' : ''
    rec.onresult = (e) => {
      let final = '', inter = ''
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) final += r[0].transcript
        else inter += r[0].transcript
      }
      setTranscript(baseRef.current + final)
      setInterim(inter)
    }
    rec.onerror = (e) => {
      if (e.error === 'not-allowed') toast.error('Mikrofon-Zugriff wurde verweigert')
      else if (e.error !== 'aborted' && e.error !== 'no-speech') toast.error(`Spracherkennung: ${e.error}`)
      setRecording(false)
    }
    rec.onend = () => { setRecording(false); setInterim('') }
    recRef.current = rec
    rec.start()
    setRecording(true)
  }

  const stopRecording = () => { try { recRef.current?.stop() } catch {} }

  const handleAnalyze = async () => {
    const text = transcript.trim()
    if (text.length < 3) return toast.error('Bitte zuerst etwas aufnehmen oder eingeben')
    if (recording) stopRecording()
    setAnalyzing(true)
    try {
      const res = await zeiterfassungApi.kiNachtragen(text)
      onResult(res.data)
    } catch (err) {
      const detail = err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'KI-Auswertung fehlgeschlagen', { duration: 8000 })
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-start justify-center p-4 overflow-y-auto sheet-safe">
      <div className="max-h-full overflow-y-auto bg-surface rounded-2xl shadow-2xl w-full max-w-lg my-8">
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
            <Mic size={18} className="text-primary-600" />
            Projektzeit per Sprache nachtragen
            <Sparkles size={15} className="text-primary-500" />
          </h2>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-xl transition">
            <X size={20} />
          </button>
        </div>

        <div className="p-5 flex flex-col items-center gap-4">
          {SR ? (
            <>
              <button type="button" onClick={recording ? stopRecording : startRecording}
                className={`w-20 h-20 rounded-full flex items-center justify-center transition shadow-lg ${
                  recording ? 'bg-red-500 hover:bg-red-600 animate-pulse' : 'bg-primary-600 hover:bg-primary-700'}`}>
                {recording ? <Square size={26} fill="white" className="text-white" /> : <Mic size={30} className="text-white" />}
              </button>
              <p className="text-sm text-gray-500 text-center">
                {recording ? 'Aufnahme läuft – zum Beenden klicken' : 'Zum Aufnehmen klicken und Zeiteintrag ansagen'}
              </p>
            </>
          ) : (
            <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
              Dieser Browser unterstützt keine Spracherkennung (z.B. Firefox). Der Text
              kann unten manuell eingegeben und trotzdem per KI ausgewertet werden.
            </p>
          )}

          <p className="text-xs text-gray-400 text-center">
            Beispiel: „Projektzeit nachtragen beim Kunden Keplinger zum Projekt Eurofib am
            Dienstag den 13.07. von 13:28 bis 14:05 mit der Notiz Online-Meeting zur Datenmigration"
          </p>

          <div className="w-full">
            <label className="block text-sm font-medium text-gray-700 mb-1">Transkript (prüfen/anpassen)</label>
            <textarea
              value={interim ? `${transcript}${transcript ? ' ' : ''}${interim}` : transcript}
              onChange={(e) => { setTranscript(e.target.value); setInterim('') }}
              rows={4}
              placeholder="Hier erscheint der aufgenommene Text…"
              className="w-full px-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-none"
            />
          </div>
        </div>

        <div className="flex gap-3 p-5 border-t border-gray-100">
          <button onClick={onClose}
            className="flex-1 py-2.5 border border-gray-300 rounded-xl text-gray-700 hover:bg-gray-50 font-medium transition">
            Abbrechen
          </button>
          <button onClick={handleAnalyze} disabled={analyzing || !transcript.trim()}
            className="flex-1 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium rounded-xl transition flex items-center justify-center gap-2">
            {analyzing ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
            {analyzing ? 'KI wertet aus…' : 'Mit KI auswerten'}
          </button>
        </div>
      </div>
    </div>
  )
}
