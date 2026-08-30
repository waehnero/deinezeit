import { useState } from 'react'
import { GripVertical, Plus, X, ArrowUp, ArrowDown } from 'lucide-react'

/**
 * Editor für die Auswahlliste eines Dropdown-Feldes.
 *
 * Bisher ließen sich Optionen nur beim **Anlegen** eines Feldes setzen. Wer
 * eine Mengeneinheit, einen Steuersatz oder eine Artikelart ergänzen wollte,
 * musste das Feld löschen und neu anlegen — und verlor dabei alle bereits
 * erfassten Werte, weil sie am Feldschlüssel hängen.
 *
 * Von beiden Feld-Editoren genutzt (Liste und Raster), damit es nur eine
 * Auslegung davon gibt, was eine gültige Optionsliste ist.
 *
 * Zwei Regeln, die hier durchgesetzt werden:
 *
 * 1. **Keine Doppelten.** Zwei gleichnamige Optionen sind im Auswahlfeld nicht
 *    unterscheidbar; welche gespeichert wird, entscheidet dann der Zufall.
 * 2. **Umbenennen ist keine Umbuchung.** Wird eine Option umbenannt, behalten
 *    bereits gespeicherte Datensätze den alten Text — sie sind nur nicht mehr
 *    in der Liste. Deshalb der Hinweis unter dem Editor: Das ist bewusst so,
 *    denn ein stilles Nachziehen aller Datensätze wäre eine Massenänderung,
 *    die niemand angefordert hat.
 */
export default function OptionsEditor({ optionen, onChange, disabled = false }) {
  const [neu, setNeu] = useState('')
  const [fehler, setFehler] = useState('')

  const liste = Array.isArray(optionen) ? optionen : []

  const hinzufuegen = () => {
    const wert = neu.trim()
    if (!wert) return
    if (liste.some(o => o.toLowerCase() === wert.toLowerCase())) {
      setFehler(`„${wert}“ steht schon in der Liste`)
      return
    }
    onChange([...liste, wert])
    setNeu('')
    setFehler('')
  }

  const entfernen = (i) => onChange(liste.filter((_, idx) => idx !== i))

  const umbenennen = (i, wert) => {
    const kopie = [...liste]
    kopie[i] = wert
    onChange(kopie)
  }

  const verschieben = (i, richtung) => {
    const ziel = i + richtung
    if (ziel < 0 || ziel >= liste.length) return
    const kopie = [...liste]
    ;[kopie[i], kopie[ziel]] = [kopie[ziel], kopie[i]]
    onChange(kopie)
  }

  // Beim Verlassen eines Feldes prüfen — nicht bei jedem Tastendruck, sonst
  // meldet der Editor „doppelt", während man den Text gerade erst tippt.
  const pruefen = () => {
    const gesehen = new Set()
    for (const o of liste) {
      const k = o.trim().toLowerCase()
      if (!k) { setFehler('Eine Option ist leer'); return }
      if (gesehen.has(k)) { setFehler(`„${o}“ kommt doppelt vor`); return }
      gesehen.add(k)
    }
    setFehler('')
  }

  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">
        Auswahlmöglichkeiten
      </label>

      <div className="space-y-1.5">
        {liste.map((opt, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <GripVertical size={13} className="text-gray-300 flex-shrink-0" />
            <input
              type="text"
              value={opt}
              disabled={disabled}
              onChange={(e) => umbenennen(i, e.target.value)}
              onBlur={pruefen}
              className="flex-1 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:bg-gray-50"
            />
            <button type="button" onClick={() => verschieben(i, -1)} disabled={disabled || i === 0}
              className="p-1 text-gray-400 hover:text-gray-700 disabled:opacity-25" title="Nach oben">
              <ArrowUp size={13} />
            </button>
            <button type="button" onClick={() => verschieben(i, 1)} disabled={disabled || i === liste.length - 1}
              className="p-1 text-gray-400 hover:text-gray-700 disabled:opacity-25" title="Nach unten">
              <ArrowDown size={13} />
            </button>
            <button type="button" onClick={() => entfernen(i)} disabled={disabled}
              className="p-1 text-gray-400 hover:text-red-500" title="Entfernen">
              <X size={13} />
            </button>
          </div>
        ))}

        {liste.length === 0 && (
          <p className="text-xs text-gray-400 py-1">Noch keine Auswahlmöglichkeiten.</p>
        )}
      </div>

      <div className="flex gap-1.5 mt-2">
        <input
          type="text"
          value={neu}
          disabled={disabled}
          onChange={(e) => { setNeu(e.target.value); setFehler('') }}
          onKeyDown={(e) => {
            // Enter darf hier nicht das umgebende Formular abschicken —
            // sonst speichert ein Enter beim Eintippen einer Option das
            // ganze Feld und der halb getippte Wert geht verloren.
            if (e.key === 'Enter') { e.preventDefault(); hinzufuegen() }
          }}
          placeholder="Neue Möglichkeit, z.B. m²"
          className="flex-1 px-2 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:bg-gray-50"
        />
        <button type="button" onClick={hinzufuegen} disabled={disabled || !neu.trim()}
          className="flex items-center gap-1 px-2.5 py-1.5 bg-primary-600 text-white text-xs rounded-lg hover:bg-primary-700 disabled:bg-primary-300">
          <Plus size={12} /> Hinzufügen
        </button>
      </div>

      {fehler && <p className="text-xs text-red-500 mt-1">{fehler}</p>}

      <p className="text-[11px] text-gray-400 mt-1.5">
        Wird eine Möglichkeit umbenannt oder entfernt, behalten bereits
        gespeicherte Datensätze ihren bisherigen Wert — sie stehen dann nur
        nicht mehr zur Auswahl.
      </p>
    </div>
  )
}
