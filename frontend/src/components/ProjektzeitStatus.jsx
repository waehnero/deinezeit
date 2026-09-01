/**
 * Abrechnungs-Status einer Projektzeit (Schloss-Menü in den Listen).
 *
 * Gemeinsam genutzt von der Erfassungsseite und dem Bericht „Projektzeiten" —
 * dieselben erlaubten Wechsel an beiden Stellen. Die Regel selbst prüft der
 * Server (api/zeiterfassung.py, _apply_status_change); hier geht es nur
 * darum, nichts anzubieten, was dort abgewiesen würde.
 */
import { useState } from 'react'
import { Lock, LockOpen, CheckCircle2, Receipt } from 'lucide-react'

// ── Abrechnungs-Status ────────────────────────────────────────────────────────
// veraenderbar → gesperrt → freigegeben → abgerechnet (Wechsel: Admin;
// Mitarbeiter dürfen eigene Einträge nur freigeben)
export const ENTRY_STATUS = {
  veraenderbar: { label: 'Veränderbar', icon: LockOpen,     cls: 'text-gray-400 hover:text-gray-600',   badge: 'bg-gray-100 text-gray-500' },
  gesperrt:     { label: 'Gesperrt',    icon: Lock,         cls: 'text-amber-500 hover:text-amber-600', badge: 'bg-amber-50 text-amber-600' },
  freigegeben:  { label: 'Freigegeben', icon: CheckCircle2, cls: 'text-blue-500 hover:text-blue-600',   badge: 'bg-blue-50 text-blue-600' },
  abgerechnet:  { label: 'Abgerechnet', icon: Receipt,      cls: 'text-green-600 hover:text-green-700', badge: 'bg-green-50 text-green-700' },
}

// Welche Statuswechsel darf der aktuelle Benutzer bei diesem Eintrag?
export function allowedStatusTargets(entry, isAdmin, currentUserId) {
  const status = entry.status || 'veraenderbar'
  if (isAdmin) return Object.keys(ENTRY_STATUS).filter(s => s !== status)
  if (entry.user_id === currentUserId && status === 'veraenderbar') return ['freigegeben']
  return []
}

export default function StatusMenu({ entry, isAdmin, currentUserId, onSetStatus }) {
  const [open, setOpen] = useState(false)
  const status = entry.status || 'veraenderbar'
  const cfg = ENTRY_STATUS[status] || ENTRY_STATUS.veraenderbar
  const Icon = cfg.icon
  const targets = allowedStatusTargets(entry, isAdmin, currentUserId)

  return (
    <div className="relative">
      <button
        onClick={() => targets.length && setOpen(o => !o)}
        onBlur={() => setTimeout(() => setOpen(false), 200)}
        className={`p-1.5 rounded-lg transition ${cfg.cls} ${targets.length ? '' : 'cursor-default'}`}
        title={`Status: ${cfg.label}${targets.length ? ' — klicken zum Ändern' : ''}`}>
        <Icon size={14} />
      </button>
      {open && (
        <div className="absolute right-0 top-8 z-20 bg-surface border border-gray-200 rounded-xl shadow-lg py-1 w-48">
          <div className="px-3 py-1.5 text-xs text-gray-400 border-b border-gray-100">
            Status: {cfg.label}
          </div>
          {targets.map(t => {
            const tCfg = ENTRY_STATUS[t]
            const TIcon = tCfg.icon
            return (
              <button key={t}
                onMouseDown={(e) => e.preventDefault() /* Blur nicht vor Click */}
                onClick={() => { setOpen(false); onSetStatus(entry, t) }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 transition text-left">
                <TIcon size={14} className="text-gray-400" />
                Auf „{tCfg.label}“ setzen
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
