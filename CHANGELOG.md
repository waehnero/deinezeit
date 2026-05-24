# Changelog – DeineZeit

Alle Änderungen werden hier dokumentiert.
Format: [Version] – Datum – Was hat sich geändert

---

## [0.1.0] – 2026-05-21 – Grundfundament

### Neu
- Projektstruktur mit Backend (Python/FastAPI), Frontend (React) und Datenbank (PostgreSQL)
- Docker Compose Setup für einfaches Deployment
- Benutzerverwaltung mit Rollen (Admin / Mitarbeiter)
- Sicheres Login-System:
  - Passwort-Login mit verschlüsselter Speicherung
  - Zwei-Faktor-Authentifizierung (TOTP / Google Authenticator)
  - Face ID / Fingerabdruck Login via WebAuthn/Passkeys
- JWT-Token-basierte Authentifizierung mit automatischer Erneuerung
- Mehrsprachigkeit: Deutsch und Englisch (sprachabhängig pro Benutzer)
- Responsives Design (Mobile-First für Handy, Tablet und Desktop)
- Datenbank-Migrationen via Alembic (sichere Schema-Updates)
- nginx Reverse Proxy mit HTTPS / Let's Encrypt Unterstützung
- Sicherheits-Header (HSTS, XSS-Schutz, Frame-Schutz)

### Technische Details
- Backend: FastAPI 0.111, Python 3.12
- Frontend: React 18, Tailwind CSS, i18next
- Datenbank: PostgreSQL 16 mit Alembic-Migrationen
- Deployment: Docker Compose, nginx, Certbot (Let's Encrypt)

---

---

## [0.2.0] – 2026-05-21 – Dynamische Stammdaten-Verwaltung

### Neu
- **Stammdaten-Typen**: Kunden, Lieferanten und Projekte vorinstalliert
- **Beliebige neue Typen**: Jederzeit weitere anlegen (z.B. Mitarbeiter, Fahrzeuge, Verträge…)
- **Dynamischer Formular-Builder**: Felder direkt in der Oberfläche hinzufügen, bearbeiten und entfernen — ohne Programmieraufwand
- **9 Feldtypen**: Text, mehrzeiliger Text, Zahl, Datum, E-Mail, Telefon, Auswahlliste, Ja/Nein, Webseite
- **Pflichtfelder** und **Listenansicht** pro Feld konfigurierbar
- **Datensatz-Verwaltung**: Anlegen, bearbeiten und löschen mit automatisch generiertem Formular
- **Suche**: Volltextsuche über alle Felder eines Stammdaten-Typs
- **Paginierung**: Große Datenmengen werden seitenweise angezeigt
- **Dashboard**: Schnellübersicht aller Stammdaten-Typen mit Eintrags-Zähler
- **Datenbank**: JSONB-basierter Speicher mit GIN-Index für schnelle Suche

### Technische Details
- Neue Datenbankmodelle: `entity_types`, `field_definitions`, `entity_records`
- Migration 0002 mit vordefinierten Standard-Feldern für Kunden/Lieferanten/Projekte
- Neue API-Endpoints: `/api/masterdata/types/*` und `/api/masterdata/types/{slug}/records/*`
- Neue Komponenten: `FieldBuilder`, `DynamicForm`, `MasterDataOverview`, `MasterDataDetail`

---

---

## [0.3.0] – 2026-05-21 – Grid-Layout, Import/Export & Benutzerverwaltung

### Neu
- **Snap-to-Grid Drag & Drop Layout-Builder**: Felder per Maus oder Touch-Geste frei verschieben — ein unsichtbares 12-Spalten-Raster sorgt dafür, dass alles sauber einrastet
- **Feldbreite frei wählbar**: 25% / 33% / 50% / 75% / 100% — direkt per Klick am Feld einstellbar; mehrere Felder können nebeneinander in einer Zeile angezeigt werden
- **Formular respektiert Layout**: Die Erfassungsmaske zeigt Felder exakt im definierten Raster-Layout — auf Desktop und Tablet; auf Mobilgeräten werden alle Felder automatisch auf volle Breite gestreckt
- **CSV Export**: Alle Datensätze eines Stammdaten-Typs mit einem Klick als CSV exportieren (Excel-kompatibel mit BOM und Semikolon-Trennung)
- **CSV Import**: CSV-Datei hochladen, Spalten per Dropdown den Feldern zuordnen, Vorschau prüfen, dann importieren
- **Profilseite**: Jeder Benutzer kann Name, Sprache und Passwort selbst ändern sowie 2FA und Passkeys verwalten
- **Benutzerverwaltung**: Admin-Seite zum Anlegen neuer Benutzer mit Rolle und Sprache, Deaktivierung bestehender Benutzer

### Technische Details
- Neue Spalte `col_span` in `field_definitions` (Migration 0003)
- Neue Backend-Endpoints: `/fields-layout` (Bulk-Update), `/records/export/csv`, `/records/import/csv`
- Neue npm-Pakete: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`, `papaparse`
- Neue Komponenten: `GridFieldBuilder`, `CsvImportExport`, `ProfilePage`, `UserManagementPage`

---

## Geplant für [0.4.0]

- Verknüpfungen zwischen Stammdaten-Typen (z.B. Projekt → Kunde zuordnen)
- Excel (.xlsx) Export
- Erweiterte Filterung und Sortierung in Datensatz-Listen
- Druckansicht / PDF-Export einzelner Datensätze
