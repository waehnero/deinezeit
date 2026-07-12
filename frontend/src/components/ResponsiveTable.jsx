// Einheitliche Listenansicht (Design-Verfassung, Regel 3):
// Desktop/Tablet = Tabelle · Handy = Karten — beide zeigen dieselben Felder
// in derselben Reihenfolge. Neue Module verwenden IMMER diese Komponente
// statt eigener <table>-Markups, damit Listen überall gleich aussehen.
//
// Verwendung:
//   <ResponsiveTable
//     columns={[
//       { key: 'name',  label: 'Name' },                                // Wert aus row[key]
//       { key: 'kunde', label: 'Kunde', render: r => r.kunde?.name },   // eigenes Rendering
//       { key: 'datum', label: 'Geändert', muted: true },               // gedämpfte Darstellung
//     ]}
//     rows={eintraege}
//     onRowClick={r => öffnen(r)}
//     actions={r => <RecordActions record={r} … />}                     // Knöpfe rechts
//   />

export default function ResponsiveTable({
  columns,
  rows,
  rowKey = (r) => r.id,
  onRowClick,
  actions,
  emptyText = 'Keine Einträge',
}) {
  const zelle = (c, r) => (c.render ? c.render(r) : (r[c.key] ?? '—'))

  if (!rows || rows.length === 0) {
    return <p className="px-4 py-10 text-sm text-neutral-400 text-center">{emptyText}</p>
  }

  const [erste, ...rest] = columns

  return (
    <>
      {/* ── Desktop / Tablet: Tabelle ── */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-neutral-100 bg-neutral-50">
              {columns.map(c => (
                <th key={c.key} className="px-4 py-3 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">
                  {c.label}
                </th>
              ))}
              {actions && <th className="px-4 py-3 w-20"></th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-50">
            {rows.map(r => (
              <tr key={rowKey(r)}
                className={`transition ${onRowClick ? 'hover:bg-neutral-50 cursor-pointer' : ''}`}
                onClick={() => onRowClick?.(r)}>
                {columns.map(c => (
                  <td key={c.key} className={`px-4 py-3 text-sm ${c.muted ? 'text-neutral-400 whitespace-nowrap' : 'text-neutral-700'}`}>
                    {zelle(c, r)}
                  </td>
                ))}
                {actions && (
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1" onClick={e => e.stopPropagation()}>
                      {actions(r)}
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Handy: Karten mit identischer Feldreihenfolge ── */}
      <div className="md:hidden divide-y divide-neutral-100">
        {rows.map(r => (
          <div key={rowKey(r)} className={`p-4 ${onRowClick ? 'active:bg-neutral-50' : ''}`}
            onClick={() => onRowClick?.(r)}>
            <div className="flex items-start justify-between gap-3">
              <div className="text-sm font-semibold text-neutral-900 min-w-0 pt-1">{zelle(erste, r)}</div>
              {actions && (
                <div className="flex items-center gap-1 flex-shrink-0" onClick={e => e.stopPropagation()}>
                  {actions(r)}
                </div>
              )}
            </div>
            {rest.length > 0 && (
              <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5">
                {rest.map(c => (
                  <div key={c.key} className="min-w-0">
                    <dt className="text-[10px] uppercase tracking-wide text-neutral-400">{c.label}</dt>
                    <dd className="text-sm text-neutral-700 truncate">{zelle(c, r)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        ))}
      </div>
    </>
  )
}
