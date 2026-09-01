/**
 * Zeitprojekte — der Stammdaten-Typ, auf den Projektzeiten gebucht werden.
 *
 * Begriffe (seit 01.09.2026 im ganzen Modul einheitlich):
 *   Zeitprojekt  Stammsatz (Kunde/Projekt), auf den gebucht wird
 *   Projektzeit  einzelner Zeiteintrag
 *
 * Der Slug steht hier an einer Stelle: Er hieß bis Migration 0038 'projekte',
 * danach 'projektzeiten' und seit 0059 'zeitprojekte'. Verstreute Zeichenketten
 * überleben solche Umbenennungen erfahrungsgemäß nicht vollständig, und eine
 * vergessene fällt erst im Betrieb auf ("Stammdaten-Typ nicht gefunden").
 *
 * Das Gegenstück im Backend: app/core/zeitprojekte.py
 */
export const ZEITPROJEKTE_SLUG = 'zeitprojekte'

/** Frühere Slugs — nur für Weiterleitungen alter Lesezeichen. */
export const ZEITPROJEKTE_ALTE_SLUGS = ['projektzeiten', 'projekte']

/** Adresse der Zeitprojekte-Seite (liegt im Zeiterfassungs-Menü). */
export const ZEITPROJEKTE_PFAD = '/zeiterfassung/zeitprojekte'
