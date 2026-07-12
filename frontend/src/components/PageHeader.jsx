// Einheitlicher Seitenkopf für ALLE Module (Design-Verfassung, Regel 3):
// immer Symbol + Modultitel in gleicher Größe, optionale Beschreibung
// darunter, Aktionen (Buttons) immer rechts. Seiten definieren keine
// eigenen Kopfzeilen mehr.
//
// Verwendung:
//   <PageHeader icon={Clock} title="Zeiterfassung" subtitle="...">
//     <button className="btn-primary">+ Neuer Eintrag</button>
//   </PageHeader>

export default function PageHeader({ icon: Icon, title, subtitle, children }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
      <div className="flex items-center gap-3 min-w-0">
        {Icon && (
          <div className="w-10 h-10 rounded-xl bg-primary-50 text-primary-600 flex items-center justify-center flex-shrink-0">
            <Icon size={21} />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-neutral-900 leading-tight truncate">{title}</h1>
          {subtitle && (
            <p className="text-sm text-neutral-500 mt-0.5 truncate">{subtitle}</p>
          )}
        </div>
      </div>
      {children && (
        <div className="flex items-center gap-2 flex-wrap">{children}</div>
      )}
    </div>
  )
}
