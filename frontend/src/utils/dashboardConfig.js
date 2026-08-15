/**
 * Dashboard-Konfiguration (Format v2 mit mehreren Layouts)
 * ========================================================
 *
 * Gespeichert wird die Konfiguration je Benutzer in `users.dashboard_config`
 * (JSONB) über GET/PUT /api/users/me/dashboard. Die Spalte ist schemafrei,
 * eine Alembic-Migration ist deshalb nicht nötig.
 *
 * Format v2:
 * {
 *   version: 2,
 *   aktivesLayout: 'standard',
 *   bekannt: { typen: ['aufgaben', …], slugs: ['kunde', …] },
 *   layouts: [
 *     { id: 'standard', name: 'Standard', widgets: [
 *         { id, type, slug?, size, titel? }, …
 *     ] }, …
 *   ]
 * }
 *
 * Format v1 (Vorgänger, wird beim Laden automatisch übernommen):
 *   { widgets: [{ id, type, slug?, size, hidden }] }   – oder das nackte Array
 *   aus dem alten localStorage-Eintrag.
 *
 * Zu `bekannt`: hier merken wir uns, welche Widget-Typen und Stammdaten-Typen
 * dem Benutzer schon einmal angeboten wurden. Nur wirklich *neue* Einträge
 * werden dem Standard-Layout automatisch hinzugefügt. Ohne dieses Gedächtnis
 * käme ein bewusst entferntes Widget beim nächsten Laden wieder zurück.
 *
 * Zu `hidden` aus v1: ein ausgeblendetes Widget wird bei der Übernahme
 * entfernt (nicht übernommen), der Typ aber als „bekannt" vermerkt. Damit gibt
 * es nur noch einen Zustand — vorhanden oder nicht — statt vorher zwei.
 */
import { WIDGET_REGISTRY, widgetDef, widgetErlaubt } from '../data/dashboardWidgets'

export const CONFIG_VERSION = 2
export const STANDARD_LAYOUT_ID = 'standard'
export const MAX_LAYOUTS = 5

/** Eindeutige Widget-Id erzeugen. */
export function neueWidgetId(type, slug) {
  const basis = type === 'entity_type' ? `et_${slug}` : type
  return `w_${basis}_${Math.random().toString(36).slice(2, 8)}`
}

function neueLayoutId() {
  return `layout_${Math.random().toString(36).slice(2, 8)}`
}

/** Einzelnes Widget auf die erwarteten Felder zurechtstutzen. */
function normalisiereWidget(w) {
  const eintrag = {
    id: w.id || neueWidgetId(w.type, w.slug),
    type: w.type,
    size: [1, 2, 4].includes(w.size) ? w.size : (widgetDef(w.type)?.defaultSize ?? 1),
  }
  if (w.type === 'entity_type') eintrag.slug = w.slug
  // Leerer Titel = Standardbeschriftung aus der Registry verwenden
  if (w.titel && String(w.titel).trim()) eintrag.titel = String(w.titel).trim().slice(0, 40)
  return eintrag
}

/** Neues Widget aus der Registry (für den Katalog). */
export function neuesWidget(type, slug) {
  return normalisiereWidget({
    id: neueWidgetId(type, slug),
    type,
    slug,
    size: widgetDef(type)?.defaultSize ?? 1,
  })
}

/**
 * Standard-Widgets: alle Registry-Einträge mit `imStandard`, die der Benutzer
 * sehen darf — plus je eine Kachel pro Stammdaten-Typ.
 */
export function standardWidgets(types, ctx) {
  const feste = WIDGET_REGISTRY
    .filter(def => def.imStandard && !def.mehrfach && widgetErlaubt(def.type, ctx))
    .map(def => neuesWidget(def.type))

  const stammdaten = widgetErlaubt('entity_type', ctx)
    ? (types || []).map(t => neuesWidget('entity_type', t.slug))
    : []

  return [...feste, ...stammdaten]
}

/** Vollständige Standard-Konfiguration für einen Benutzer. */
export function standardConfig(types, ctx) {
  return {
    version: CONFIG_VERSION,
    aktivesLayout: STANDARD_LAYOUT_ID,
    bekannt: {
      // Nur was der Benutzer sehen darf — damit ein später freigeschaltetes
      // Modul seine Kachel nachliefern kann (siehe normalisiereConfig).
      typen: WIDGET_REGISTRY.filter(d => widgetErlaubt(d.type, ctx)).map(d => d.type),
      slugs: (types || []).map(t => t.slug),
    },
    layouts: [
      { id: STANDARD_LAYOUT_ID, name: 'Standard', widgets: standardWidgets(types, ctx) },
    ],
  }
}

/** v1 → v2: die eine Widget-Liste wird zum Standard-Layout. */
function ausV1(v1Widgets) {
  const liste = Array.isArray(v1Widgets) ? v1Widgets : []
  const uebernommen = liste
    .filter(w => w && w.type && !w.hidden)      // ausgeblendete gelten als entfernt
    .map(normalisiereWidget)

  return {
    version: CONFIG_VERSION,
    aktivesLayout: STANDARD_LAYOUT_ID,
    // Bekannt ist genau das, was in v1 tatsächlich vorkam — auch das
    // Ausgeblendete, sonst tauchten ausgeblendete Widgets sofort wieder auf.
    // Bewusst NICHT die aktuellen Stammdaten-Typen dazunehmen: ein Typ, den
    // der Benutzer unter v1 noch nie zu sehen bekam, ist neu und gehört
    // ergänzt (in v1 geschah das automatisch).
    bekannt: {
      typen: [...new Set(liste.map(w => w?.type).filter(Boolean))],
      slugs: [...new Set(
        liste.filter(w => w?.type === 'entity_type').map(w => w.slug).filter(Boolean),
      )],
    },
    layouts: [
      { id: STANDARD_LAYOUT_ID, name: 'Standard', widgets: uebernommen },
    ],
  }
}

/**
 * Gespeicherte Konfiguration einlesen: Format angleichen, ungültige Einträge
 * entfernen und neu ausgelieferte Widgets ergänzen.
 *
 * @param roh    was vom Server (oder aus dem alten localStorage) kam
 * @param types  aktuelle Stammdaten-Typen
 * @param ctx    { isAdmin, modules }
 */
export function normalisiereConfig(roh, types, ctx) {
  const typeListe = types || []

  // ── Ausgangsformat bestimmen ──────────────────────────────────────────────
  let cfg
  if (!roh) {
    return standardConfig(typeListe, ctx)
  } else if (Array.isArray(roh)) {
    cfg = ausV1(roh)                                              // altes localStorage-Array
  } else if (roh.version === CONFIG_VERSION && Array.isArray(roh.layouts)) {
    cfg = roh
  } else if (Array.isArray(roh.widgets)) {
    cfg = ausV1(roh.widgets)                                      // v1 vom Server
  } else {
    return standardConfig(typeListe, ctx)
  }

  const gueltigeSlugs = new Set(typeListe.map(t => t.slug))

  // ── Layouts bereinigen ────────────────────────────────────────────────────
  let layouts = (cfg.layouts || [])
    .filter(l => l && l.id)
    .slice(0, MAX_LAYOUTS)
    .map(l => {
      const gesehen = new Set()
      const widgets = (l.widgets || [])
        .filter(w => w && w.type)
        .filter(w => widgetDef(w.type))                     // unbekannter Typ → raus
        // Nach Modulrechten wird hier bewusst NICHT gefiltert: sonst würde ein
        // vorübergehend entzogenes Recht die Kachel dauerhaft aus der
        // gespeicherten Anordnung löschen. Das Ausblenden übernimmt die
        // Darstellung in DashboardPage.jsx.
        .filter(w => w.type !== 'entity_type' || gueltigeSlugs.has(w.slug))
        .filter(w => {                                      // Doubletten abfangen
          const def = widgetDef(w.type)
          const schluessel = def.mehrfach ? `${w.type}:${w.slug}` : w.type
          if (gesehen.has(schluessel)) return false
          gesehen.add(schluessel)
          return true
        })
        .map(normalisiereWidget)
      return {
        id: l.id,
        name: String(l.name || 'Ansicht').slice(0, 30),
        widgets,
      }
    })

  if (layouts.length === 0) {
    layouts = [{ id: STANDARD_LAYOUT_ID, name: 'Standard', widgets: standardWidgets(typeListe, ctx) }]
  }

  // ── Neu ausgelieferte Widgets ins Standard-Layout aufnehmen ───────────────
  // Absichtlich nur dort: selbst angelegte Ansichten bleiben unangetastet.
  const bekannteTypen = new Set(cfg.bekannt?.typen || [])
  const bekannteSlugs = new Set(cfg.bekannt?.slugs || [])
  const standardIdx = Math.max(0, layouts.findIndex(l => l.id === STANDARD_LAYOUT_ID))

  const neueFeste = WIDGET_REGISTRY
    .filter(def => def.imStandard && !def.mehrfach)
    .filter(def => !bekannteTypen.has(def.type))
    .filter(def => widgetErlaubt(def.type, ctx))
    .map(def => neuesWidget(def.type))

  const neueSlugs = widgetErlaubt('entity_type', ctx)
    ? typeListe.filter(t => !bekannteSlugs.has(t.slug)).map(t => neuesWidget('entity_type', t.slug))
    : []

  if (neueFeste.length || neueSlugs.length) {
    layouts = layouts.map((l, i) => i === standardIdx
      ? { ...l, widgets: [...l.widgets, ...neueFeste, ...neueSlugs] }
      : l)
  }

  const aktiv = layouts.some(l => l.id === cfg.aktivesLayout)
    ? cfg.aktivesLayout
    : layouts[0].id

  return {
    version: CONFIG_VERSION,
    aktivesLayout: aktiv,
    bekannt: {
      // Als bekannt gilt nur, was der Benutzer auch sehen darf. Schaltet der
      // Admin später ein Modul frei, taucht dessen Kachel dadurch von selbst
      // im Standard-Layout auf — die Freischaltung bliebe sonst wirkungslos.
      // Einmal Bekanntes wird nie wieder vergessen, ein entzogenes Recht führt
      // also nicht dazu, dass eine entfernte Kachel zurückkehrt.
      typen: [...new Set([
        ...bekannteTypen,
        ...WIDGET_REGISTRY.filter(d => widgetErlaubt(d.type, ctx)).map(d => d.type),
      ])],
      slugs: [...new Set([...bekannteSlugs, ...typeListe.map(t => t.slug)])],
    },
    layouts,
  }
}

// ── Zugriffs- und Änderungshelfer ────────────────────────────────────────────

/** Das gerade aktive Layout (nie undefined, solange die Config normalisiert ist). */
export function aktivesLayout(config) {
  if (!config?.layouts?.length) return null
  return config.layouts.find(l => l.id === config.aktivesLayout) || config.layouts[0]
}

/** Widgets des aktiven Layouts ersetzen. */
export function setzeWidgets(config, widgets) {
  const aktiv = aktivesLayout(config)
  if (!aktiv) return config
  return {
    ...config,
    layouts: config.layouts.map(l => l.id === aktiv.id ? { ...l, widgets } : l),
  }
}

/** Auf ein anderes Layout umschalten. */
export function wechsleLayout(config, layoutId) {
  if (!config.layouts.some(l => l.id === layoutId)) return config
  return { ...config, aktivesLayout: layoutId }
}

/** Neue Ansicht anlegen (leer oder als Kopie der aktuellen). */
export function fuegeLayoutHinzu(config, name, { kopieren = false } = {}) {
  if (config.layouts.length >= MAX_LAYOUTS) return config
  const id = neueLayoutId()
  const quelle = kopieren ? aktivesLayout(config) : null
  const widgets = quelle
    ? quelle.widgets.map(w => ({ ...w, id: neueWidgetId(w.type, w.slug) }))
    : []
  return {
    ...config,
    aktivesLayout: id,
    layouts: [...config.layouts, { id, name: String(name || 'Neue Ansicht').slice(0, 30), widgets }],
  }
}

/** Ansicht umbenennen. */
export function benenneLayoutUm(config, layoutId, name) {
  return {
    ...config,
    layouts: config.layouts.map(l => l.id === layoutId
      ? { ...l, name: String(name || l.name).slice(0, 30) }
      : l),
  }
}

/** Ansicht löschen — die Standard-Ansicht bleibt immer bestehen. */
export function loescheLayout(config, layoutId) {
  if (layoutId === STANDARD_LAYOUT_ID || config.layouts.length <= 1) return config
  const layouts = config.layouts.filter(l => l.id !== layoutId)
  return {
    ...config,
    aktivesLayout: config.aktivesLayout === layoutId ? layouts[0].id : config.aktivesLayout,
    layouts,
  }
}

/** Aktive Ansicht auf die Werkseinstellung zurücksetzen. */
export function setzeLayoutZurueck(config, types, ctx) {
  return setzeWidgets(config, standardWidgets(types, ctx))
}
