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
 *      ggf. `module` und `adminOnly`).
 *   2. In `DashboardPage.jsx` die Darstellung im Render-Zweig ergänzen.
 *   3. Kennzahlen in `backend/app/services/dashboard.py` ergänzen und dort in
 *      `BAUSTEIN_MODUL` dieselben Module eintragen (ein Test wacht darüber).
 *   4. Fertig — Katalog, Modulrechte und Standard-Layout ziehen automatisch nach.
 *      Bestandsbenutzer bekommen das neue Widget über das `bekannt`-Gedächtnis
 *      in utils/dashboardConfig.js einmalig ins Standard-Layout gelegt.
 *
 * Felder:
 *   type        eindeutiger Schlüssel, wird in der gespeicherten Konfiguration
 *               abgelegt (nicht mehr ändern, sonst verlieren Benutzer das Widget)
 *   label       Beschriftung im Katalog und Standard-Kacheltitel
 *   beschreibung  kurzer Hinweis im Katalog-Dialog
 *   icon        lucide-Icon für den Katalog
 *   defaultSize Standardbreite (1 = ¼, 2 = ½, 4 = ganze Zeile)
 *   module      benötigte Modulrechte (siehe backend/app/core/modules.py) —
 *               eine Liste, weil Auswertungen „verkauf" UND „buchhaltung"
 *               verlangen; leere Liste = für alle sichtbar
 *   adminOnly   nur für Administratoren
 *   imStandard  Teil des Standard-Dashboards eines neuen Benutzers
 *   mehrfach    darf mehrmals im selben Layout vorkommen (nur Stammdaten-Typen)
 */
import {
  CheckSquare, Clock, FileText, GanttChartSquare, Zap,
  Database, BarChart3, Landmark, ShieldCheck, Package,
  AlertTriangle, Megaphone, TrendingUp, Receipt,
} from 'lucide-react'

export const WIDGET_REGISTRY = [
  {
    type: 'aufgaben',
    label: 'Aufgaben',
    beschreibung: 'Offene und überfällige Aufgaben samt Mail-Vorschlägen',
    icon: CheckSquare,
    defaultSize: 2,
    module: ['aufgaben'],
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
    module: ['zeiterfassung'],
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
    module: ['verkauf'],
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
    module: ['projekte'],
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
    module: [],
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
    module: ['datacenter'],
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
    module: ['zeiterfassung'],
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
    module: ['buchhaltung'],
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
    module: [],
    adminOnly: true,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'offene_posten',
    label: 'Offene Posten',
    beschreibung: 'Überfällige Forderungen nach Alter gestaffelt, dazu der Mahnstand',
    icon: AlertTriangle,
    defaultSize: 2,
    module: ['verkauf', 'buchhaltung'],
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'postecke',
    label: 'Postecke',
    beschreibung: 'Beiträge je Spalte, nächste Veröffentlichungen, gescheiterte Sendungen',
    icon: Megaphone,
    defaultSize: 2,
    module: ['postecke'],
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'umsatz',
    label: 'Umsatz-Verlauf',
    beschreibung: 'Monatsumsätze des Jahres im Vergleich zum Vorjahr',
    icon: TrendingUp,
    defaultSize: 4,
    module: ['verkauf', 'buchhaltung'],
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'eingangsrechnungen',
    label: 'Eingangsrechnungen',
    beschreibung: 'Offene Lieferantenrechnungen, Vorsteuer und Stand des Monatsabschlusses',
    icon: Receipt,
    defaultSize: 2,
    module: ['buchhaltung'],
    adminOnly: false,
    imStandard: true,
    mehrfach: false,
  },
  {
    type: 'entity_type',
    label: 'Stammdaten-Typ',
    beschreibung: 'Anzahl der Einträge eines Stammdaten-Typs',
    icon: Package,
    defaultSize: 1,
    module: ['stammdaten'],
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
 *
 * Prüft Adminrecht und Modulfreigaben; `modules = null` heißt „alles erlaubt"
 * (Standard für Bestandsbenutzer, siehe backend/app/core/modules.py). Es
 * müssen **alle** in `module` genannten Rechte vorliegen.
 */
export function widgetErlaubt(type, { isAdmin, modules }) {
  const def = widgetDef(type)
  if (!def) return false                       // unbekannter Typ (z. B. altes Widget)
  if (def.adminOnly && !isAdmin) return false
  const noetig = def.module || []
  if (noetig.length === 0 || modules === null || modules === undefined) return true
  return noetig.every(m => modules.includes(m))
}

/** Standard-Beschriftung eines Widgets (ohne benutzereigenen Titel). */
export function widgetLabel(type) {
  return widgetDef(type)?.label || type
}
