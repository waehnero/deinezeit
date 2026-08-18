import { Info } from 'lucide-react'

/**
 * Rechtematrix einer Gruppe: je Modul Ansehen / Ändern / Löschen und Umfang.
 *
 * Der Modulkatalog kommt vom Server (`/api/groups/katalog`), nicht aus einer
 * Liste im Frontend. Zwei gepflegte Listen laufen mit der Zeit auseinander,
 * und das fällt erst auf, wenn ein neues Modul in der Rechteverwaltung fehlt —
 * also genau dann, wenn jemand es freischalten möchte.
 *
 * `rechte` ist das Rechteblatt der Gruppe, `onChange` bekommt das geänderte
 * Blatt. Die Komponente hält keinen eigenen Zustand.
 */
export default function RechteMatrix({ katalog, rechte, onChange, disabled }) {
  if (!katalog?.length) return null

  const setzen = (modul, feld, wert) => {
    const neu = {
      ...rechte,
      [modul]: { ...(rechte[modul] || {}), [feld]: wert },
    }
    // Ändern oder Löschen ohne Ansehen ergibt kein sinnvolles Recht — man käme
    // an kein Formular. Statt das später zu verbieten, hier gleich mitziehen;
    // der Server tut dasselbe (core/berechtigungen._leseweg_ergaenzen).
    if ((feld === 'schreiben' || feld === 'loeschen') && wert) {
      neu[modul].lesen = true
    }
    // Umgekehrt: Wer nicht ansehen darf, darf auch nicht ändern.
    if (feld === 'lesen' && !wert) {
      neu[modul].schreiben = false
      neu[modul].loeschen = false
    }
    onChange(neu)
  }

  return (
    <div className="border border-neutral-200 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-neutral-50 border-b border-neutral-200">
            <th className="px-3 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">
              Modul
            </th>
            <th className="px-2 py-2 text-center text-xs font-semibold text-neutral-500 uppercase tracking-wide w-20">
              Ansehen
            </th>
            <th className="px-2 py-2 text-center text-xs font-semibold text-neutral-500 uppercase tracking-wide w-20">
              Ändern
            </th>
            <th className="px-2 py-2 text-center text-xs font-semibold text-neutral-500 uppercase tracking-wide w-20">
              Löschen
            </th>
            <th className="px-3 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide w-44">
              Umfang
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-neutral-100">
          {katalog.map((m) => {
            const werte = rechte[m.modul] || {}
            const hatRecht = (key) => m.rechte.some((r) => r.key === key)
            return (
              <tr key={m.modul} className="hover:bg-neutral-50">
                <td className="px-3 py-2 font-medium text-neutral-800">
                  {m.label}
                </td>

                {['lesen', 'schreiben', 'loeschen'].map((recht) => (
                  <td key={recht} className="px-2 py-2 text-center">
                    {hatRecht(recht) ? (
                      <input
                        type="checkbox"
                        checked={!!werte[recht]}
                        disabled={disabled}
                        onChange={(e) => setzen(m.modul, recht, e.target.checked)}
                        className="w-4 h-4 rounded border-neutral-300 text-primary-600 focus:ring-primary-500"
                      />
                    ) : (
                      // Das Dashboard hat keine eigenen Datensätze — ein
                      // Häkchen dort wäre eine Zusage ohne Wirkung.
                      <span className="text-neutral-300" title="Für dieses Modul nicht anwendbar">—</span>
                    )}
                  </td>
                ))}

                <td className="px-3 py-2">
                  {m.umfang_relevant ? (
                    <select
                      value={werte.umfang || 'eigene'}
                      disabled={disabled || !werte.lesen}
                      onChange={(e) => setzen(m.modul, 'umfang', e.target.value)}
                      className="input py-1 text-sm w-full disabled:bg-neutral-50 disabled:text-neutral-400"
                    >
                      <option value="eigene">Nur eigene</option>
                      <option value="alle">Alle</option>
                    </select>
                  ) : (
                    <span className="text-xs text-neutral-400">
                      alle
                    </span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <div className="flex items-start gap-2 px-3 py-2 bg-neutral-50 border-t border-neutral-200">
        <Info size={14} className="text-neutral-400 flex-shrink-0 mt-0.5" />
        <p className="text-xs text-neutral-500 leading-relaxed">
          <strong>Umfang</strong> steuert, wessen Datensätze sichtbar sind —
          „Nur eigene“ zeigt einem Mitarbeiter ausschließlich seine eigenen
          Einträge. Er wirkt nur dort, wo Datensätze einer Person zugeordnet
          sind; bei Stammdaten oder Verkauf gibt es keinen Eigentümer, deshalb
          steht dort fest „alle“.
        </p>
      </div>
    </div>
  )
}
