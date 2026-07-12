import { Plus } from 'lucide-react'

// Floating Action Button (Design-Verfassung, Regel 2):
// Am Handy sitzt die Primäraktion („+ Neu anlegen") JEDES Moduls als runder
// Knopf unten rechts — immer an derselben Stelle, oberhalb der Bottom-Tab-Bar.
// Ab Desktop-Breite übernimmt der Button im Seitenkopf; der FAB verschwindet.
//
// Verwendung:  <Fab onClick={() => setModal(null)} title="Neue Aufgabe" />

export default function Fab({ onClick, title = 'Neu anlegen', icon: Icon = Plus }) {
  return (
    <button onClick={onClick} title={title} aria-label={title}
      className="lg:hidden fixed right-4 z-40 w-14 h-14 rounded-full bg-primary-600 hover:bg-primary-700 text-on-accent shadow-lg shadow-primary-600/30 flex items-center justify-center active:scale-95 transition"
      style={{ bottom: 'calc(4.5rem + env(safe-area-inset-bottom) + 0.75rem)' }}>
      <Icon size={26} />
    </button>
  )
}
