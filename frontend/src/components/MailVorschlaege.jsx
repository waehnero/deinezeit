import { useState, useEffect } from 'react'
import {
  Sparkles, ChevronDown, ChevronUp, Check, X, Loader2, Mail,
  CalendarDays, Flag,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { mailImportApi } from '../services/api'

/**
 * Offene KI-Aufgabenvorschläge aus E-Mails (Aufgabenmodul, Etappe 3).
 * Erscheint als aufklappbares Banner über der Aufgabenliste, sobald
 * offene Vorschläge existieren. Übernehmen erzeugt ein Todo (source=email).
 *
 * Props:
 *   onAccepted() – nach Übernahme (Aufgabenliste neu laden)
 */
export default function MailVorschlaege({ onAccepted }) {
  const [vorschlaege, setVorschlaege] = useState([])
  const [offen, setOffen] = useState(false)
  const [busy, setBusy] = useState({})   // id -> true

  const load = () => {
    mailImportApi.listSuggestions('offen')
      .then(r => setVorschlaege(r.data))
      .catch(() => {})
  }
  useEffect(() => { load() }, [])

  const uebernehmen = async (v) => {
    setBusy(b => ({ ...b, [v.id]: true }))
    try {
      const { data } = await mailImportApi.acceptSuggestion(v.id)
      if (data.mail_flagged === true) {
        toast.success('Als Aufgabe übernommen — E-Mail in Outlook als erledigt markiert')
      } else if (data.mail_flagged === false) {
        toast.success('Als Aufgabe übernommen')
        toast.error('E-Mail konnte in Outlook nicht als erledigt markiert werden (Mail.ReadWrite-Berechtigung prüfen)')
      } else {
        toast.success('Als Aufgabe übernommen')
      }
      setVorschlaege(list => list.filter(x => x.id !== v.id))
      onAccepted?.()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Übernahme fehlgeschlagen')
    } finally {
      setBusy(b => ({ ...b, [v.id]: false }))
    }
  }

  const verwerfen = async (v) => {
    setBusy(b => ({ ...b, [v.id]: true }))
    try {
      await mailImportApi.dismissSuggestion(v.id)
      setVorschlaege(list => list.filter(x => x.id !== v.id))
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fehler beim Verwerfen')
    } finally {
      setBusy(b => ({ ...b, [v.id]: false }))
    }
  }

  if (vorschlaege.length === 0) return null

  const datum = (d) => d ? new Date(d).toLocaleDateString('de-AT') : null

  return (
    <div className="mb-5 border border-amber-200 bg-amber-50 rounded-xl overflow-hidden">
      <button onClick={() => setOffen(o => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 text-left">
        <Sparkles size={17} className="text-amber-600 shrink-0" />
        <span className="text-sm font-medium text-amber-900 flex-1">
          {vorschlaege.length} Aufgabenvorschl{vorschlaege.length === 1 ? 'ag' : 'äge'} aus deinen E-Mails
        </span>
        {offen ? <ChevronUp size={16} className="text-amber-600" /> : <ChevronDown size={16} className="text-amber-600" />}
      </button>

      {offen && (
        <div className="divide-y divide-amber-100 border-t border-amber-100 bg-surface">
          {vorschlaege.map(v => (
            <div key={v.id} className="px-4 py-3">
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-neutral-900">{v.title}</p>
                  {v.description && (
                    <p className="text-xs text-neutral-500 mt-0.5">{v.description}</p>
                  )}
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 mt-1 text-[11px] text-neutral-400">
                    <span className="flex items-center gap-1 truncate">
                      <Mail size={11} /> {v.sender}{v.subject ? ` · „${v.subject}"` : ''}
                    </span>
                    {v.due_date && (
                      <span className="flex items-center gap-1">
                        <CalendarDays size={11} /> fällig {datum(v.due_date)}
                      </span>
                    )}
                    {v.priority && v.priority !== 'mittel' && (
                      <span className="flex items-center gap-1"><Flag size={11} /> {v.priority}</span>
                    )}
                    {v.account_name && <span>{v.account_name}</span>}
                  </div>
                </div>
                <div className="flex gap-1.5 shrink-0">
                  <button onClick={() => uebernehmen(v)} disabled={busy[v.id]}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50">
                    {busy[v.id] ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
                    Übernehmen
                  </button>
                  <button onClick={() => verwerfen(v)} disabled={busy[v.id]}
                    className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border border-gray-300 text-neutral-600 hover:bg-neutral-50 disabled:opacity-50">
                    <X size={12} /> Verwerfen
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
