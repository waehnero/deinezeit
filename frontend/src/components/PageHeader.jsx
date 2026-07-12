import { Search } from 'lucide-react'
import { openCommandPalette } from './CommandPalette'

// Einheitlicher Seitenkopf für ALLE Module (Design-Verfassung, Regel 3):
// immer Symbol + Modultitel in gleicher Größe, optionale Beschreibung
// darunter, Aktionen (Buttons) immer rechts — gefolgt vom ⌘K-Suchknopf,
// der auf jeder Seite an derselben Stelle sitzt (Regel 5).
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
      <div className="flex items-center gap-2 flex-wrap">
        {children}
        {/* Globale Suche (⌘K) — immer ganz rechts, auf jeder Seite gleich */}
        <button onClick={openCommandPalette} title="Suchen & Befehle (⌘K)"
          className="flex items-center gap-2 px-2.5 py-2.5 rounded-xl border border-neutral-200 bg-surface text-neutral-400 hover:text-neutral-700 hover:bg-neutral-50 transition">
          <Search size={16} />
          <kbd className="hidden md:block text-[10px] border border-neutral-200 rounded px-1 py-0.5">⌘K</kbd>
        </button>
      </div>
    </div>
  )
}
