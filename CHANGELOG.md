# C
## [1.7.2] - 2026-06-07 - Versionspr�fung robuster + nginx Healthcheck


### Aktualisierungen
- Versionspr�fung: GitHub-Fallback via git wenn raw.githubusercontent.com nicht erreichbar
- SettingsPage: zeigt Warnung wenn GitHub-Pr�fung fehlschl�gt
- nginx Healthcheck: wartet auf Backend-Bereitschaft vor Start
- nginx IP-Aufl�sung: Container-IPs dynamisch alle 10s neu aufgel�st
- docker-compose.yml: certbot_conf Volume und Networks erg�nzt

---

## [1.7.1] - 2026-06-07 - Datacenter Freigaben-Verwaltung

### Neu
- Datacenter: Freigaben-Ansicht zeigt alle aktiven Share-Links
- Freigaben verlängerbar ohne Token-Änderung (1/7/30/90 Tage oder unbegrenzt)
- Freigaben einzeln widerrufbar direkt aus der Übersicht

### Fixes
- Share-Link Route-Reihenfolge fix (war: "Not authenticated" im privaten Browserfenster)

---

## [1.7.0] - 2026-06-07 - E-Mail-Vorlagen System


### Neu
- TipTap Rich-Text Editor fuer E-Mail-Vorlagen
- Vorlagen pro Belegart editierbar
- CC-Feld im Versand-Dialog

### Aktualisierungen
- Versionsanzeige-Logik korrigiert
- bump-version.ps1 git-add repariert

---

## [1.7.1] – 2026-06-07 – Share-Link Route-Optimierung

### Aktualisierungen
- Share-Link Route wurde vor der generischen Entity-Route verschoben, um Routing-Konflikte zu beheben.

---
hangelog – DeineZeit

Alle Änderungen werden hier dokumentiert.
Format: [Version] – Datum – Was hat sich geändert

---

## [1.6.8] – 2026-06-07 – Versionsanzeige-Korrektur

### Aktualisierungen
- Versionsanzeige zeigt korrekt die installierte Version an, auch wenn der GitHub-Cache veraltet ist

---

## [1.6.7] – 2026-06-06 – Stabilität und Mail-Verwaltung

### Aktualisierungen
- Mail-Icon in Rechnungsstatus bleibt nach Seitenwechsel erhalten
- API und Abhängigkeiten wiederhergestellt, CC-Feld hinzugefügt

---

## [1.6.6] – 2026-06-06 – E-Mail-Kommunikation erweitert

### Neu
- E-Mail-Dialog mit Kontaktinfo, Empfänger-Mail und CC-Feld hinzugefügt

---

## [1.6.5] – 2026-06-06 – Kontaktname in Belegliste korrigiert

### Aktualisierungen
- Kontaktnamen werden in der Belegliste nun korrekt angezeigt

---

## [1.6.4] – 2026-06-06 – Kontaktsuche Bugfix

### Aktualisierungen
- ContactSearch zeigt Kontaktnamen nach asynchronem Laden korrekt an

---

## [1.6.3] – 2026-06-06 – Kontaktanzeige in Belegen

### Aktualisierungen
- Kontakt wird nun in der Belegliste angezeigt
- Kontaktfeld im Formular repariert

---

## [1.6.2] – 2026-06-06 – DatacenterPicker API-Kompatibilität

### Aktualisierungen
- DatacenterPicker verarbeitet API-Antworten korrekt, wenn Anhänge als leeres Objekt statt Array zurückgegeben werden

---

## [1.6.1] – 2026-06-06 – Anhänge-Feature korrigiert

### Aktualisierungen
- InvoicePage: Anhänge-Feature korrekt integriert ohne Duplikate

---

## [1.9.0] – 2026-06-07 – E-Mail-Vorlagen System

### Neu
- E-Mail-Vorlagen pro Belegart (Rechnung, Angebot, AB, Gutschrift, Lieferschein)
- Neuer Tab „E-Mail-Vorlagen" in Einstellungen mit Rich-Text-Editor (TipTap)
- Platzhalter: {nummer}, {kontakt}, {firma}, {betrag}, {datum}, {faellig}, {belegart}
- Versand-Dialog: Betreff und E-Mail-Text vor dem Senden editierbar
- Betreff und Body werden aus der Vorlage vorausgefüllt

---

## [1.8.0] – 2026-06-07 – E-Mail-Dialog: Kontaktinfo & CC-Empfänger

### Neu
- E-Mail-Versand-Dialog zeigt Kontaktname und Empfänger-E-Mail an
- CC-Adresse kann optional eingetragen werden
- Backend: CC-Unterstützung für SMTP und Microsoft Graph API

---

## [1.7.0] – 2026-06-06 – Kontakt in Belegliste & Formular

### Neu
- Belegliste: Spalte "Titel / Kontakt" in zwei getrennte Spalten "Titel" und "Kontakt" aufgeteilt
- Belegliste: Kontaktname wird jetzt korrekt aus Stammdaten geladen und angezeigt
- Beleg-Formular: Kontaktfeld zeigt beim Bearbeiten wieder den gespeicherten Kontakt an

---

## [1.6.0] – 2026-06-06 – E-Mail-Anhänge & Datacenter-Browser

### Neu
- Anhänge beim E-Mail-Versand hinzufügen
- Datacenter-Browser für Dateiauswahl nutzen
- Lokale Dateien als E-Mail-Anhänge hochladen

---

## [1.5.0] – 2026-06-06 – Mail-Icons (grün/orange) nach Versand + Status immer auf gesendet setzen

### Neu
- Mail-Icons (grün/orange) nach Versand + Status immer auf gesendet setzen

---

## [1.4.5] – 2026-06-06 – E-Mail-Versand und Abrechnung

### Aktualisierungen
- PDF-Kontext korrekt geladen
- Unbilled Time Entries vollständig implementiert
- E-Mail-Versand repariert

---

## [1.4.4] – 2026-06-06 – E-Mail-Fehlerbehandlung verbessert

### Aktualisierungen
- Fehlermeldungen beim E-Mail-Versand werden nun dauerhaft im Dialog angezeigt.

---

## [1.4.3] – 2026-06-06 – E-Mail-Versand repariert

### Aktualisierungen
- E-Mail-Versand und Rechnungsgenerierung wiederhergestellt

---

## [1.4.2] – 2026-06-06 – Nginx-Stabilität und Docker-Verbesserungen

### Aktualisierungen
- Healthcheck und dynamische DNS-Auflösung für Nginx optimiert
- Docker-Compose-Konfiguration vervollständigt

---

## [1.4.1] – 2026-06-06 – nginx Healthcheck-Fix

### Behoben
- nginx wartet beim Start auf Backend-Healthcheck (`/api/health`) bevor es Anfragen weiterleitet
- nginx löst Container-IPs dynamisch alle 10 Sekunden neu auf (Docker DNS-Resolver `127.0.0.11`) — kein manueller Neustart nach Backend-Recreate nötig
- docker-compose.yml: fehlende Named Volumes (`certbot_conf`) und Networks-Sektion ergänzt

---

## [1.4.0] – 2026-06-06 – E-Mail-Integration und Stabilität

### Neu
- Office 365 E-Mail-Integration via Microsoft Graph API

### Aktualisierungen
- Weißer Bildschirm im Changelog-Panel der Anmeldeseite behoben
- Update-Watchdog und HTTPS Health-Check optimiert
- Belegbuch-Endpoints implementiert (Listenansicht, CSV- und PDF-Export)
- Backup-Watcher mit Administratorrechten ausgeführt
- Quellcode-Verwaltung für zuverlässige Docker-basierte Updates verbessert

---

## [1.3.13] – 2026-06-06 – Update-Mechanismus Test

### Neu
- Update-Mechanismus End-to-End erfolgreich getestet

---

## [1.3.12] – 2026-06-06 – Weißer Bildschirm nach Update behoben

### Behoben
- Absturz auf der Anmeldeseite wenn ein Changelog-Eintrag weder "features" noch "updates" enthält (optional chaining)
- changelog.js v1.3.11: "changes" in "updates" umbenannt damit Eintrag im Updates-Tab erscheint

---

## [1.3.11] – 2026-06-06 – Update-Prozess Stabilitätsverbesserungen

### Behoben
- Update-Status bleibt nicht mehr dauerhaft auf "updating" wenn kein neuer Commit vorhanden (Watchdog nach 5 Min)
- Health-Check im Update-Script nutzt jetzt HTTPS statt HTTP (verhindert Rollback-Schleife)
- nginx.conf-Verzeichnis-Bug wird beim Update automatisch korrigiert
- update.sh, nginx-Konfiguration und docker-compose.yml in git aufgenommen (gehen nicht mehr verloren)

---

## [1.3.10] – 2026-06-05 – Lokale Instanzerkennung und Stabilitätsverbesserungen

### Neu
- Lokale Instanzerkennung implementiert

### Aktualisierungen
- Update-Tab zeigt git pull Anleitung statt Button
- Changelog-Konflikte gelöst
- Changelog mit fehlenden Versionen 1.2.1–1.3.8 synchronisiert

---

## [1.3.9] – 2026-06-05 – Lokale Instanz erkennung

### Aktualisierungen
- Lokale Entwicklungsinstanz wird automatisch erkannt — Update-Button zeigt stattdessen Anleitung für git pull
- Backend blockiert Update-Start in lokalem Modus mit klarer Fehlermeldung

---

## [1.3.8] – 2026-06-05 – Frontend-Integration

### Aktualisierungen
- Gesamtes Frontend in Versionskontrolle integriert

---

## [1.3.7] – 2026-06-05 – Backend-Infrastruktur aktualisiert

### Aktualisierungen
- Backend-App-Verzeichnis in Versionskontrolle integriert

---

## [1.3.6] – 2026-06-05 – Konfigurationsstabilität verbessert

### Aktualisierungen
- ConfigParser-Interpolation in alembic.ini entfernt

---

## [1.3.5] – 2026-06-05 – Datenbankmigrationen hinzugefügt

### Aktualisierungen
- Alembic-Migrationen zur Versionskontrolle hinzugefügt

---

## [1.3.4] – 2026-06-05 – Backend-Infrastruktur erweitert

### Aktualisierungen
- Backend-Grunddateien für Docker-Containerisierung hinzugefügt

---

## [1.3.3] – 2026-06-05 – Docker-Compose Integration

### Aktualisierungen
- Docker-Compose Dateien zum Repository hinzugefügt

---

## [1.3.2] – 2026-06-05 – Versions-Anzeige korrigiert

### Aktualisierungen
- Versions-Anzeige liest nun aus CHANGELOG.md statt aus package.json oder config.py

---

## [1.3.1] – 2026-06-05 – Rechnungs-Widget Darstellung optimiert

### Aktualisierungen
- Rechnungs-Widget wird nun auch bei bestehender Dashboard-Konfiguration korrekt angezeigt.

---

## [1.3.0] – 2026-06-05 – Dashboard und Einstellungen überarbeitet

### Neu
- Rechnungs-Widget im Dashboard hinzugefügt
- Automatischer Versions-Bump via GitHub Actions
- E-Mail als Unter-Tab unter System verschoben
- Backup als Unter-Tab unter System integriert
- Design als Unter-Tab unter Allgemein eingebaut

### Aktualisierungen
- auto_version.py robustheit bei fehlenden Dateien verbessert
- Version aus CHANGELOG.md ausgelesen
- Arbeitsverzeichnis auf Repo-Root gesetzt
- Git-Log-Parsing stabilisiert
- Git-Config vor Script initialisiert

---

## [1.2.1] – 2026-06-05 – Dashboard: Rechnungs-Widget

### Neu
- Dashboard-Widget „Rechnungen": zeigt offene, überfällige und diesen Monat bezahlte Rechnungen mit Anzahl und Brutto-Summe
- Widget ist standardmäßig im Dashboard enthalten, verschiebbar und in der Größe anpassbar

---

## [1.2.0] – 2026-06-05 – Auftragsbestätigung & Rechnungsmodul-Erweiterungen

### Neu
- Auftragsbestätigung (AB) als neuer Dokumenttyp mit eigenem Nummernkreis (AB-2026-001, …)
- E-Mail-Versand direkt aus dem Rechnungsmodul — einzeln oder als Bulk-Versand für mehrere Belege
- Statusworkflow mit kontextabhängigem Aktionsmenü: Entwurf → Offen → Bezahlt, Angenommen / Abgelehnt, Storniert
- Angebote können nach Annahme direkt in eine Auftragsbestätigung oder Rechnung umgewandelt werden

### Aktualisierungen
- Parameter-Tab in den Einstellungen: Präfixe und Nummernformate pro Dokumenttyp frei konfigurierbar
- Dokumenttyp-Bezeichnungen können umbenannt werden

---

## [1.1.0] – 2026-06-04 – Buchhaltungsmodul

### Neu
- Kontenplan nach EKR (Einheitskontenrahmen) vorbefüllt und durchsuchbar
- BMD-Export für die steuerliche Übergabe an den Steuerberater
- Debitor- und Kreditornummern direkt bei Kontakten hinterlegbar
- Erlöskonto pro Artikel festlegbar — wird automatisch auf Rechnungspositionen übernommen
- Konto pro Rechnungsposition individuell überschreibbar
- Kontakte: neuer Finanz-Tab mit IBAN, BIC und Bankname (Migration 0012/0013)

---

## [1.0.0] – 2026-06-03 – Rechnungsmodul

### Neu
- Rechnungen, Angebote, Gutschriften und Lieferscheine erstellen
- Automatische Nummerierung pro Dokumenttyp (RE-2026-001, AN-2026-001, …)
- Stornierung mit automatischer Gutschrift oder nur Statusänderung
- Angebote können direkt in Rechnungen umgewandelt werden
- Zeiteinträge aus der Zeiterfassung direkt auf Rechnung übernehmen
- Positionen aus Artikel-Stammdaten oder als Freitext
- MwSt.: pro Position wählbar, ein Satz, oder Kleinunternehmerregelung
- PDF-Export mit 5 wählbaren Vorlagen (Klassisch, Modern, Kompakt, Elegant, Farbenfroh)
- Rechnungsbuch filterbar nach Monat/Quartal/Jahr und/oder Kunde — als PDF oder CSV
- Zahlungsstatus: offen, bezahlt, überfällig, storniert
- Wiederkehrende Rechnungsvorlagen (wöchentlich, monatlich, quartalsweise, jährlich)
- Bankverbindung aus den App-Einstellungen automatisch auf jedem Dokument

---

## [0.9.5] – 2026-06-03 – Dashboard konfigurierbar

### Neu
- Dashboard-Bausteine per Drag & Drop frei anordnen
- Breite der Bausteine stufenweise anpassen (¼ / ½ / Vollbreite)
- Layout wird im Browser gespeichert und beim nächsten Besuch wiederhergestellt
- Neues Zeiterfassung-Widget auf dem Dashboard mit Heute/Woche/Monat-Übersicht

---

## [0.9.4] – 2026-06-03 – Update-Prozess robuster

### Aktualisierungen
- Backend führt Alembic-Migrationen jetzt automatisch beim Start aus — zukünftige Updates brauchen kein manuelles `alembic upgrade head` mehr
- Migrations-Fehler beim Start verhindern nun das Hochkommen des Backends → Health-Check schlägt fehl → automatischer Rollback greift korrekt
- Rollback im Update-Skript stellt jetzt auch die gesicherten Docker-Images wieder her, nicht nur den Git-Commit

---

## [0.9.3] – 2026-06-02 – Stammdaten vereinheitlicht

### Aktualisierungen
- Stammdaten-Typen vereinheitlicht: Kunden und Lieferanten zusammengeführt zu „Kontakte" mit Typ-Feld (Kunde / Lieferant / Interessent)
- Neuer Stammdaten-Typ „Artikel" für Produkte und Dienstleistungen (Bezeichnung, Artikelnummer, Preis, Beschreibung)
- Bestehende Kunden- und Lieferanten-Datensätze werden bei Migration automatisch nach Kontakte übernommen
- Alembic-Migration 0010 stellt einheitlichen Stand bei Neu- und Bestandsinstallationen sicher

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

---

## [0.4.0] – 2026-05-22 – Sicherheit & Design-Upgrade

### Neu
- **Farbschema zur Laufzeit änderbar**: Primärfarbe und Akzentfarbe über die Einstellungen wählbar — kein Neustart nötig
- **Login-Seite neu gestaltet**: Modernes Design mit Markenbild
- **Sidebar neu gestaltet**: Schlankere Navigation, bessere Lesbarkeit
- **Dashboard neu gestaltet**: Übersichtlichere Kacheldarstellung
- **Admin-Benutzerbearbeitung**: Admins können Benutzerdaten direkt bearbeiten
- **Passwort vergessen Seite**: Eigene Seite mit Kontaktinformationen für Passwort-Reset
- **Kontakte zusammengeführt**: Kunden und Lieferanten wurden zu einem gemeinsamen „Kontakte"-Typ zusammengeführt, Typ-Filter (Kunden / Lieferanten / Interessenten) in der Listenansicht
- **Rate Limiting**: Login-Endpunkt ist gegen Brute-Force-Angriffe geschützt
- **Sicherheits-Header**: HSTS, XSS-Schutz, Frame-Schutz, Content-Type-Sniffing-Schutz
- **API-Docs gesperrt**: Swagger-UI nur noch im Debug-Modus erreichbar
- **Upload-Limit**: Maximale Dateigröße für Uploads konfigurierbar

### Technische Details
- Migration 0004: Kontakte-Konsolidierung (Kunden + Lieferanten → Kontakte mit `typ`-Feld)
- Neue npm-Pakete: `slowapi` (Rate Limiting)
- Tailwind CSS auf CSS-Variablen umgestellt (`--color-primary-*`) für Laufzeit-Farbwechsel

---

## [0.5.0] – 2026-05-22 – Zeiterfassung

### Neu
- **Zeiterfassung**: Timer starten/stoppen mit Projekt- und Aufgabenzuordnung
- **Manuelle Einträge**: Zeiten nachträglich eintragen und bearbeiten
- **Eigene Felder für Zeiteinträge**: Admin kann beliebige Zusatzfelder definieren (z.B. Ort, Fahrtzeit, Notiz)
- **Statistik**: Tages- und Wochenübersicht der erfassten Stunden
- **Projektzeitbericht als PDF**: Gefilterte Auswertung nach Zeitraum, Mitarbeiter, Projekt als druckfertiges PDF
- **Bericht-Optionen**: Zeitrunden auf 15/30 Minuten, Filterung nach Aufgabe, verschiedene Zeitraum-Voreinstellungen

### Technische Details
- Migration 0005: Tabellen `time_entries` und `zeiterfassung_fields`
- Neue Backend-API: `/api/zeiterfassung/*`
- Neue Komponenten: `ZeiterfassungPage`, `ZeiterfassungFelder`, `BerichtDialog`
- WeasyPrint für PDF-Generierung serverseitig

---

## [0.6.0] – 2026-05-23 – Einstellungen, Backup & Branding

### Neu
- **Einstellungs-Seite**: Zentrales Admin-Panel mit vier Reitern
  - *Allgemein*: Firmenname, Kontaktperson, Logo und Favicon hochladen
  - *Design*: Primärfarbe und Akzentfarbe zur Laufzeit wechseln
  - *Backup*: Datenbank-Backup herunterladen, Cloud-Speicher konfigurieren (OneDrive, Google Drive, Dropbox)
  - *E-Mail*: SMTP-Konfiguration und Test-E-Mail
- **Logo-Varianten**: Hochgeladenes Logo wird automatisch in hell/dunkel-Varianten generiert
- **Favicon**: Eigenes Favicon hochladbar
- **Automatisches Backup**: PowerShell-Skript für geplante Backups (Windows Task Scheduler)
- **Backup-Watcher**: Überwacht Backup-Verzeichnis und kopiert bei Änderung in Cloud-Speicher
- **Wiederherstellungs-Skript**: Backup mit einem Befehl wiederherstellen

### Technische Details
- Migration 0006: `settings`-Tabelle für alle App-Konfigurationen
- Pillow für Logo-Verarbeitung (Varianten, Transparenz)
- Neue Skripte: `backup.ps1`, `backup.bat`, `backup-einrichten.ps1`, `wiederherstellen.ps1`, `backup-watcher.ps1`

---

## [0.7.0] – 2026-05-23 – Datacenter (Datei-Verwaltung)

### Neu
- **Datacenter**: Zentrale Dateiverwaltung für alle Stammdaten-Datensätze
- **Datei-Upload**: Beliebige Dateien direkt an Datensätze anhängen (Dokumente, Bilder, etc.)
- **Weblinks speichern**: URLs als Verknüpfungen hinterlegen
- **Download & Vorschau**: Dateien herunterladen oder direkt im Browser ansehen
- **Shareable Links**: Zeitlich begrenzte Download-Links generieren und teilen
- **Explorer-Ansicht**: Datacenter-Seite mit Ordnerstruktur (links) und Dateiliste (rechts)
- **Ordner nach Datensatz benannt**: Statt UUIDs werden die echten Namen der verknüpften Datensätze als Ordnernamen angezeigt
- **Datei-Anhänge im Bearbeitungs-Dialog**: Anhänge direkt beim Bearbeiten eines Datensatzes sehen und hochladen

### Technische Details
- Migration 0007/0008: `attachments`-Tabelle mit MinIO-Integration
- MinIO (S3-kompatibler Objektspeicher) als separater Docker-Service
- Presigned URLs für sichere Downloads und Vorschauen
- Neue Backend-API: `/api/datacenter/*`

---

## [0.8.1] – 2026-05-25 – Passkey & Face ID Bugfix

### Bugfixes
- **Passkeys / Face ID / Windows Hello vollständig implementiert**: Anmeldung ohne Passwort funktioniert jetzt korrekt
- Passkey hinzufügen (Profilseite) speichert Gerät korrekt in der Datenbank
- Passkey-Login schließt den Vorgang ab und setzt den JWT-Token — vorher war kein Login möglich
- Backend: Challen