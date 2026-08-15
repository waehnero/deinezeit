/**
 * Widget-Registry für das Dashboard
 * =================================
 *
 * Zentrale Liste aller verfügbaren Dashboard-Bausteine. Vorher waren die
 * Bausteine in `DashboardPage.jsx` über drei parallele Strukturen verteilt
 * (FIXED_WIDGETS, WIDGET_LABELS, WIDGET_MODULE) — hier stehen sie an einer
 * Stelle beisammen.
 *
 * Ein neues Widget hinzufügen:
 *   1. Hier einen Eintrag ergänzen (Typ, Beschriftung, Icon, Standardgröße,
 *      ggf. `modul` und `adminOnly`).
 *   2. In `DashboardPage.jsx` die Darstellung im Render-Zweig ergänzen.
 *   3. Fertig — Katalog, Modulrechte und Standard-Layout ziehen automatisch nach.
 *
 * Felder:
 *   type        eindeutiger Schlüssel, wird in der gespeicherten Konfiguration
 *               abgelegt (nicht mehr ändern, sonst verlieren Benutzer das Widget)
 *   label       Beschriftung im Katalog und Standard-Kacheltitel
 *   beschreibung  kurzer Hinweis im Katalog-Dialog
 *   icon        lucide-Icon für den Katalog
 *   defaultSize Standardbreite (1 = ¼, 2 = ½, 4 = ganze Zeile)
 *   modul       benötigtes Modulrecht (siehe backend/app/core/modules.py);
 *               null = für alle sichtbar
 *   adminOnly   nur für Administratoren
 *   imStandard  Teil des Standard-Dashboards eines neuen Benutzers
 *   mehrfach    darf mehrmals im selben Layout vorkommen (nur Stammdaten-Typen)
 */
import {
  CheckSquare, Clock, FileText, GanttChartSquare, Zap,
  Database, BarChart3, Landmark, ShieldCheck, Package,
} from 'lucide-react'

export const WIDGET_REGISTRY = [
  {
    type: 'aufgaben',
    label: 'Aufgaben',
    beschreibung: 'Offene und überfällige Aufgaben samt Mail-Vorschlägen',
    icon: CheckSquare,
    defaultSize: 2,
    modul: 'aufgaben',
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'zeiterfassung',
    label: 'Zeiterfassung',
    beschreibung: 'Laufender Zeitgeber, heutige und wöchentliche Summen',
    icon: Clock,
    defaultSize: 2,
    modul: 'zeiterfassung',
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'rechnungen',
    label: 'Finanzen',
    beschreibung: 'Offene, überfällige und im Monat bezahlte Rechnungen',
    icon: FileText,
    defaultSize: 2,
    modul: 'verkauf',
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'projekte',
    label: 'Projekte',
    beschreibung: 'Zuletzt bearbeitete Projekte mit Fortschritt',
    icon: GanttChartSquare,
    defaultSize: 2,
    modul: 'projekte',
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'quick_access',
    label: 'Schnellzugriff',
    beschreibung: 'Selbst gewählte Verknüpfungen und Sofort-Aktionen',
    icon: Zap,
    defaultSize: 2,
    modul: null,
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'datacenter',
    label: 'Datacenter',
    beschreibung: 'Anzahl Dateien und die jüngsten Neuzugänge',
    icon: Database,
    defaultSize: 1,
    modul: 'datacenter',
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'berichte',
    label: 'Berichte',
    beschreibung: 'Einstieg in die Auswertungen der Zeiterfassung',
    icon: BarChart3,
    defaultSize: 1,
    modul: 'zeiterfassung',
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'buchhaltung',
    label: 'Buchhaltung',
    beschreibung: 'Kontenplan und BMD-Export',
    icon: Landmark,
    defaultSize: 2,
    modul: 'buchhaltung',
    adminOnly: true,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'benutzer_system',
    label: 'Benutzer & System',
    beschreibung: 'Aktive Benutzer und installierte Version',
    icon: ShieldCheck,
    defaultSize: 2,
    modul: null,
    adminOnly: true,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'entity_type',
    label: 'Stammdaten-Typ',
    beschreibung: 'Anzahl der Einträge eines Stammdaten-Typs',
    icon: Package,
    defaultSize: 1,
    modul: 'stammdaten',
    adminOnly: false,
    imStandard: true,   // je vorhandenem Typ eine Kachel
    mehrfach: true,     // einmal pro Stammdaten-Typ
  },
]

/** Registry als Nachschlagetabelle nach Typ. */
export const WIDGET_BY_TYPE = Object.fromEntries(
  WIDGET_REGISTRY.map(w => [w.type, w]),
)

/** Definition zu einem Typ (oder undefined, wenn unbekannt/entfernt). */
export function widgetDef(type) {
  return WIDGET_BY_TYPE[type]
}

/** Alle Typen, die der Registry aktuell bekannt sind. */
export const ALLE_TYPEN = WIDGET_REGISTRY.map(w => w.type)

/**
 * Darf der Benutzer dieses Widget überhaupt sehen?
 * Prüft Adminrecht und Modulfreigabe (modules = null bedeutet „alles erlaubt").
 */
export function widgetErlaubt(type, { isAdmin, modules }) {
  const def = widgetDef(type)
  if (!def) return false                       // unbekannter Typ (z. B. altes Widget)
  if (def.adminOnly && !isAdmin) return false
  if (!def.modul || modules === null || modules === undefined) return true
  return modules.includes(def.modul)
}

/** Standard-Beschriftung eines Widgets (ohne benutzereigenen Titel). */
export function widgetLabel(type) {
  return widgetDef(type)?.label || type
}
