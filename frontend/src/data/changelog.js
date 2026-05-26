/**
 * Strukturierte Changelog-Daten für das News-Panel auf der Anmeldeseite.
 * Bei neuen Releases hier oben einen Eintrag hinzufügen.
 */
export const changelog = [
  {
    version: '0.8.1',
    day: '25',
    month: 'Mai',
    year: '2026',
    features: [],
    updates: [
      'Passkeys & Face ID / Windows Hello vollständig implementiert — Anmeldung ohne Passwort funktioniert jetzt',
      'Passkey hinzufügen (Profilseite) speichert Gerät korrekt in der Datenbank',
      'Passkey-Login schließt den Vorgang ab und setzt den JWT-Token',
    ],
  },
  {
    version: '0.8.0',
    day: '25',
    month: 'Mai',
    year: '2026',
    features: [
      'Register (Tabs) in Stammdaten-Formularen — Felder auf benannte Reiter aufteilen',
      'Drag & Drop auf Tab-Reiter zum Verschieben von Feldern',
      'Relation-Felder: Verknüpfungen zwischen verschiedenen Stammdaten-Typen',
      'Neuen Stammdaten-Typ anlegen direkt aus der Übersicht',
    ],
    updates: [
      'Anlegen neuer Stammdaten-Typen funktioniert wieder korrekt',
      'Neue Felder übernehmen Tab-Zugehörigkeit und Feldbreite',
      'React-Absturz bei Backend-Fehlermeldungen behoben',
    ],
  },
  {
    version: '0.7.0',
    day: '23',
    month: 'Mai',
    year: '2026',
    features: [
      'Datacenter: Zentrale Datei-Verwaltung für alle Datensätze',
      'Datei-Upload direkt an Datensätze anhängen (Dokumente, Bilder)',
      'Weblinks als Verknüpfungen speichern',
      'Download & Vorschau direkt im Browser',
      'Shareable Links mit Ablaufdatum generieren',
      'Explorer-Ansicht mit Ordnerstruktur (Datensatz-Namen statt UUIDs)',
    ],
    updates: [],
  },
  {
    version: '0.6.0',
    day: '23',
    month: 'Mai',
    year: '2026',
    features: [
      'Einstellungs-Seite: Logo, Favicon, Design, Backup & E-Mail',
      'Logo-Varianten automatisch generiert (hell/dunkel)',
      'Automatisches Backup-Skript für Windows Task Scheduler',
      'Backup-Watcher kopiert Backups in Cloud-Speicher',
      'E-Mail-Konfiguration (SMTP) mit Test-Funktion',
    ],
    updates: [],
  },
  {
    version: '0.5.0',
    day: '22',
    month: 'Mai',
    year: '2026',
    features: [
      'Zeiterfassung mit Timer und manuellen Einträgen',
      'Eigene Zusatzfelder für Zeiteinträge',
      'Projektzeitbericht als druckfertiges PDF',
      'Zeitrundung auf 15/30 Minuten, Filterung nach Aufgabe',
    ],
    updates: [],
  },
  {
    version: '0.4.0',
    day: '22',
    month: 'Mai',
    year: '2026',
    features: [
      'Farbschema zur Laufzeit änderbar — kein Neustart nötig',
      'Login-, Sidebar- und Dashboard-Design komplett überarbeitet',
      'Kontakte: Kunden und Lieferanten zusammengeführt mit Typ-Filter',
      'Rate Limiting gegen Brute-Force-Angriffe',
      'Sicherheits-Header (HSTS, XSS-Schutz, Frame-Schutz)',
    ],
    updates: [],
  },
  {
    version: '0.3.0',
    day: '21',
    month: 'Mai',
    year: '2026',
    features: [
      'Snap-to-Grid Drag & Drop Layout-Builder für Felder',
      'Feldbreite frei wählbar: 25% / 33% / 50% / 75% / 100%',
      'CSV Export (Excel-kompatibel) und CSV Import mit Spalten-Zuordnung',
      'Profilseite: Name, Sprache, Passwort, 2FA und Passkeys',
      'Benutzerverwaltung für Admins',
    ],
    updates: [],
  },
  {
    version: '0.2.0',
    day: '21',
    month: 'Mai',
    year: '2026',
    features: [
      'Dynamische Stammdaten-Typen: Kunden, Lieferanten, Projekte — und beliebig mehr',
      'Formular-Builder: Felder direkt in der Oberfläche definieren',
      '9 Feldtypen: Text, Zahl, Datum, E-Mail, Telefon, Auswahl, Checkbox, URL, Textarea',
      'Volltextsuche und Paginierung in Datensatz-Listen',
    ],
    updates: [],
  },
]
