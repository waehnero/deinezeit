// Tabellen-Einstellungen PRO BENUTZER/GERÄT (wie utils/anzeige.js).
// Jede Liste, die <ResponsiveTable tableId="…"> verwendet, merkt sich hier
// individuell:
//   breiten     { spaltenkey: pixel }   – per Ziehen am Spaltenrand geändert
//   reihenfolge [spaltenkey, …]         – per Pfeiltasten im Spaltenmenü
//   versteckt   [spaltenkey, …]         – abgehakte Spalten
//   sortierung  { key, richtung }       – 'auf' | 'ab'
//
// Gespeichert wird unter dz_tabelle_<tableId>. Unbekannte oder entfernte
// Spalten werden beim Laden ignoriert, damit alte Einstellungen nach einem
// Update nicht stören.

const PRAEFIX = 'dz_tabelle_'

const LEER = { breiten: {}, reihenfolge: [], versteckt: [], sortierung: null }

export function ladeTabellenEinstellungen(tableId) {
  if (!tableId) return { ...LEER }
  try {
    const roh = localStorage.getItem(PRAEFIX + tableId)
    if (!roh) return { ...LEER }
    const daten = JSON.parse(roh)
    return {
      breiten:     (daten && typeof daten.breiten === 'object' && daten.breiten) || {},
      reihenfolge: Array.isArray(daten?.reihenfolge) ? daten.reihenfolge : [],
      versteckt:   Array.isArray(daten?.versteckt) ? daten.versteckt : [],
      sortierung:  daten?.sortierung?.key ? daten.sortierung : null,
    }
  } catch {
    return { ...LEER }   // kaputter Eintrag oder localStorage gesperrt
  }
}

export function speichereTabellenEinstellungen(tableId, einstellungen) {
  if (!tableId) return
  try {
    localStorage.setItem(PRAEFIX + tableId, JSON.stringify(einstellungen))
  } catch { /* ignorieren – Einstellungen sind Komfort, kein Muss */ }
}

export function loescheTabellenEinstellungen(tableId) {
  if (!tableId) return
  try {
    localStorage.removeItem(PRAEFIX + tableId)
  } catch { /* ignorieren */ }
}
