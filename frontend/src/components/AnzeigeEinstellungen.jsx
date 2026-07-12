import { useState } from 'react'
import { Monitor, Sun, Moon, Eye, Contrast, Type, Wind } from 'lucide-react'
import { getPrefs, setPref } from '../utils/anzeige'

// „Anzeige & Barrierefreiheit" (Mein Profil · Layout-Redesign Etappe 4):
// Schalter PRO BENUTZER/GERÄT — wirken sofort, unabhängig von der globalen
// Designvorlage des Admins, und bleiben auf diesem Gerät gespeichert.

const DARK_OPTIONEN = [
  { id: 'auto',   label: 'Automatisch', Icon: Monitor, hint: 'folgt der Systemeinstellung' },
  { id: 'hell',   label: 'Hell',        Icon: Sun,     hint: '' },
  { id: 'dunkel', label: 'Dunkel',      Icon: Moon,    hint: '' },
]

function Schalter({ label, beschreibung, Icon, checked, onChange }) {
  return (
    <label className="flex items-center gap-3 py-3 cursor-pointer select-none">
      <Icon size={18} className="text-gray-400 flex-shrink-0" />
      <span className="flex-1 min-w-0">
        <span className="block text-sm font-medium text-gray-800">{label}</span>
        <span className="block text-xs text-gray-400">{beschreibung}</span>
      </span>
      <button type="button" role="switch" aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`w-11 h-6 rounded-full transition-colors flex-shrink-0 relative ${
          checked ? 'bg-primary-600' : 'bg-neutral-300'
        }`}>
        <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all ${
          checked ? 'left-[22px]' : 'left-0.5'
        }`} />
      </button>
    </label>
  )
}

export default function AnzeigeEinstellungen() {
  const [prefs, setPrefs] = useState(getPrefs())

  const aendern = (name, value) => {
    setPref(name, value)          // sofort anwenden + speichern
    setPrefs(getPrefs())
  }

  return (
    <div className="bg-surface rounded-2xl border border-gray-200 p-6">
      <h2 className="font-semibold text-gray-900 mb-1 flex items-center gap-2">
        <Eye size={18} className="text-gray-400" /> Anzeige &amp; Barrierefreiheit
      </h2>
      <p className="text-xs text-gray-400 mb-4">
        Gilt nur für dich auf diesem Gerät — unabhängig von der Designvorlage der Firma.
      </p>

      {/* Dunkelmodus */}
      <p className="text-sm font-medium text-gray-800 mb-2">Erscheinungsbild</p>
      <div className="grid grid-cols-3 gap-2 mb-2">
        {DARK_OPTIONEN.map(({ id, label, Icon }) => (
          <button key={id} type="button" onClick={() => aendern('dark', id)}
            className={`flex flex-col items-center gap-1.5 py-3 rounded-xl border-2 text-xs font-medium transition
              ${prefs.dark === id
                ? 'border-primary-500 bg-primary-50/40 text-primary-700'
                : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}>
            <Icon size={18} />
            {label}
          </button>
        ))}
      </div>
      <p className="text-xs text-gray-400 mb-4">
        „Automatisch" folgt der Hell/Dunkel-Einstellung deines Geräts.
      </p>

      {/* Barrierefreiheit */}
      <div className="divide-y divide-gray-100 border-t border-gray-100">
        <Schalter label="Hoher Kontrast" Icon={Contrast}
          beschreibung="Schwarz auf Weiß, kräftige Rahmen und deutliche Fokus-Ringe (WCAG 2.2)"
          checked={prefs.contrast} onChange={v => aendern('contrast', v)} />
        <Schalter label="Größere Schrift" Icon={Type}
          beschreibung="Erhöht die Schriftgröße in der gesamten App"
          checked={prefs.bigtext} onChange={v => aendern('bigtext', v)} />
        <Schalter label="Weniger Animation" Icon={Wind}
          beschreibung="Reduziert Übergänge und Bewegungen (angenehmer bei Bewegungsempfindlichkeit)"
          checked={prefs.calm} onChange={v => aendern('calm', v)} />
      </div>
    </div>
  )
}
