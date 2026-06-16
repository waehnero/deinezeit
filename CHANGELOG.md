# C
## [1.11.3] - 2026-06-17 - Kontextmenü-Fix Portal-Rendering


---
hangelog

## [1.11.1] - 2026-06-17
### GeÃ¤ndert
- Graph API: Gesendete E-Mails werden jetzt im Outlook-Ordner â€žGesendete Elemente" gespeichert

## [1.10.3] - 2026-06-15
### GeÃ¤ndert
- Belege-Liste: Header-Buttons, Belegtypen-Tabs und Tabelle fÃ¼r MobilgerÃ¤te optimiert (scrollbar, gestapelt, weniger Spalten)
- Beleg bearbeiten: Header-Buttons und Positionszeilen passen sich auf schmalen Bildschirmen an
- Datacenter: OrdnerÃ¼bersicht ist am Handy als ausklappbares MenÃ¼ verfÃ¼gbar, Aktionssymbole immer sichtbar
- Kontakte/Stammdaten: Header-Buttons und Typ-Filter wurden fÃ¼r MobilgerÃ¤te responsiv gestaltet

## [1.10.2] - 2026-06-15
### GeÃ¤ndert
- Berichts-Dialog: Datum-, Gruppierungs- und Filterfelder stapeln sich auf schmalen Bildschirmen statt sich zu Ã¼berlappen
- AnhÃ¤nge-Verwaltung: Aktionssymbole (Ã–ffnen, Teilen, LÃ¶schen) sind am Handy immer sichtbar; Vorschau-Kacheln zeigen auf schmalen Bildschirmen 2 statt 3 Spalten

## [1.10.1] - 2026-06-13
### GeÃ¤ndert
- Projektzeit-Seite: Buttons "Bericht erstellen" und "Projektzeit nachtragen" zeigen auf schmalen Bildschirmen (Handy) nur noch Icons
- Start-Formular: "Verrechenbar"-Option steht jetzt neben der Startzeit statt darunter, spart Platz auf mobilen GerÃ¤ten

## [1.10.0] - 2026-06-13
### Neu
- Progressive Web App (PWA) ermÃ¶glicht die Nutzung von DeineZeit als installierbare App

## [1.9.0] - 2026-06-13
### Neu
- DeineZeit als PWA: Installation Ã¼ber "Zum Home-Bildschirm hinzufÃ¼gen" (eigenes Icon, Vollbildmodus ohne Browserleiste)
- Web App Manifest mit Icons (192px, 512px, maskable, Apple Touch Icon) und Theme-Farbe
- Service Worker (vite-plugin-pwa) fÃ¼r Caching der App-Shell und grundlegende Offline-Nutzung
### GeÃ¤ndert
- iOS-Meta-Tags fÃ¼r Installation Ã¼ber Safari ergÃ¤nzt
- nginx-Konfiguration: Service Worker und Manifest werden nicht mehr langfristig gecacht

## [1.8.5] - 2026-06-13
### GeÃ¤ndert
- Anhang-Buttons (Cloud-Link, Foto aufnehmen, Hochladen) zeigen auf schmalen Bildschirmen nur noch Icons â€“ passen jetzt in eine Zeile

## [1.8.4] - 2026-06-13
### GeÃ¤ndert
- Projektzeit-Hauptseite: Layout der Start- und laufenden Timer-Karte fÃ¼r MobilgerÃ¤te (Hoch- und Querformat) Ã¼berarbeitet, Spalten stapeln sich statt sich zu Ã¼berlappen
- "Projektzeit nachtragen"-Dialog: Formularfelder stapeln sich auf schmalen Bildschirmen statt sich zu Ã¼berlappen
- Anhang-Schnellzugriff-Buttons umbrechen jetzt bei wenig Platz

## [1.8.3] - 2026-06-13
### Neu
- Schnellzugriff-Leiste fÃ¼r AnhÃ¤nge (Cloud-Link, Foto aufnehmen, Hochladen) direkt auf der Projektzeit-Hauptseite (Start- und laufende Timer-Karte) und im "Projektzeit nachtragen"-Dialog
### GeÃ¤ndert
- Wird ein Anhang hinzugefÃ¼gt, bevor der Zeiteintrag gespeichert wurde, wird die Aufgabe automatisch validiert und gespeichert

## [1.8.1] - 2026-06-12
### Neu
- Zeiterfassung-AnhÃ¤nge: Neuer Button â€žFoto aufnehmen" Ã¶ffnet direkt die Kamera des GerÃ¤ts (iPhone/Android/Tablet)
- Bestehender Drag & Drop-Upload-Bereich bleibt fÃ¼r lokale Dateien erhalten

## [1.8.0] - 2026-06-08
### Neu
- OneDrive-Integration mit Microsoft Graph API (persÃ¶nliche Konten & SharePoint)

## [1.7.8] - 2026-06-08
### Neu
- OneDrive-Integration: Microsoft OneDrive & SharePoint als Cloudspeicher-Option
- Graph-Anmeldedaten aus E-Mail-Einstellungen kÃ¶nnen fÃ¼r OneDrive wiederverwendet werden
- PersÃ¶nliches OneDrive und SharePoint-Laufwerk konfigurierbar (inkl. Site-ID)

## [1.7.7] â€“ 2026-06-08 â€“ Cloudspeicher-Integration abgeschlossen

### Neu
- Cloudspeicher: Nextcloud, SeaDrive und MinIO als Storage-Provider wÃ¤hlbar
- Speicher-Tab in Einstellungen (Provider-Auswahl, WebDAV-URL, Verbindungstest)
- MSG-Datei (.msg Outlook) Vorschau im Datacenter

### Fixes
- Upload-Fortschrittsanzeige (ProgressEvent â†’ korrekter Prozentwert)
- WebDAV-Upload: db=db an storage_service Ã¼bergeben (Provider aus DB gelesen)
- storage_backend wird korrekt als Providername (nextcloud/seadrive/minio) gespeichert
- requests-Bibliothek in requirements.txt ergÃ¤nzt

---

## [1.11.0] â€“ 2026-06-16 â€“ Office 365 E-Mail Integration

### Neu
- Office 365 E-Mail-Anbindung Ã¼ber Microsoft Graph API

---

## [1.10.4] â€“ 2026-06-15 â€“ Mobile-Responsiveness verbessert

### Aktualisierungen
- Mobile-Responsiveness fÃ¼r Belege, Beleg-Formular, Datacenter und Kontakte optimiert
- Synchronisierungsfehler bei mobilen Ansichten behoben

---

## [1.10.3] â€“ 2026-06-15 â€“ Mobile-Optimierungen und Verbesserungen

### Aktualisierungen
- Berichts-Dialog fÃ¼r mobile GerÃ¤te optimiert
- AnhÃ¤nge-Handling verbessert

---

## [1.10.2] â€“ 2026-06-13 â€“ Merge-Konflikte aufgelÃ¶st

### Aktualisierungen
- Merge-Konflikte behoben

---

## [1.10.0] â€“ 2026-06-13 â€“ PWA-UnterstÃ¼tzung fÃ¼r DeineZeit

### Neu
- Progressive Web App (PWA) ermÃ¶glicht die Nutzung von DeineZeit als installierbare App

---

## [1.8.5] â€“ 2026-06-12 â€“ AnhÃ¤nge und Mobile-Optimierung

### Neu
- Schnellzugriff auf AnhÃ¤nge hinzugefÃ¼gt
- Mobiles Layout fÃ¼r Projektzeit verbessert

---

## [1.8.2] â€“ 2026-06-11 â€“ Behobene Dateien und Dokumentation

### Aktualisierungen
- AttachmentExplorer.jsx vollstÃ¤ndig repariert
- CHANGELOG.md vollstÃ¤ndig repariert

---

## [1.8.2] â€“ 2026-06-11 â€“ Changelog-Reparatur

### Aktualisierungen
- Changelog-Datei vollstÃ¤ndig repariert und wiederhergestellt

---

## [1.8.2] â€“ 2026-06-11 â€“ Foto-Upload fÃ¼r Zeiterfassung

### Neu
- Fotos direkt per Kamera bei Zeiterfassung-AnhÃ¤ngen aufnehmen

---

## [1.8.0] â€“ 2026-06-08 â€“ OneDrive-Integration

### Neu
- OneDrive-Integration mit Microsoft Graph API
- UnterstÃ¼tzung fÃ¼r persÃ¶nliche OneDrive-Konten
- UnterstÃ¼tzung fÃ¼r SharePoint-Dateien

---


## [1.7.5] â€“ 2026-06-08 â€“ Cloudspeicher-Integration

### Neu
- Cloudspeicher-Integration: Nextcloud und SeaDrive als Alternative zu MinIO
- WebDAV-Provider (storage_service.py) mit automatischer Ordnererstellung via MKCOL
- Speicher-Tab in den Einstellungen (Provider-Auswahl, WebDAV-Felder, Verbindungstest)
- Backend-Endpunkte: POST /settings/storage/test + POST /settings/storage/apply
- TTL-Cache (30 s) fÃ¼r Storage-Provider mit invalidate_provider_cache()
- extract-msg==0.55.0 fÃ¼r MSG-Outlook-Datei-Vorschau

---

## [1.7.6] â€“ 2026-06-08 â€“ WebDAV-Upload Fehlerbehebung

### Aktualisierungen
- WebDAV-Upload funktioniert wieder korrekt nach Datenbankverbindungs-Fix

---

## [1.7.6] â€“ 2026-06-08 â€“ Upload-Fortschritt Optimierung

### Aktualisierungen
- Upload-Fortschritt wird nun korrekt aus ProgressEvent berechnet (Fehler in bestimmten Browsern behoben)

---

## [1.7.6] â€“ 2026-06-08 â€“ Speicher-Backend Optimierung

### Aktualisierungen
- Storage-Backend speichert Providernamen direkt (Nextcloud/Seadrive/Minio)

---

## [1.7.6] â€“ 2026-06-08 â€“ WebDAV-SpeicherunterstÃ¼tzung hinzugefÃ¼gt

### Aktualisierungen
- WebDAV-Felder in den Einstellungen integriert

---

## [1.7.6] â€“ 2026-06-08 â€“ WebDAV-Integration stabilisiert

### Aktualisierungen
- requests-Bibliothek in WebDAV-Provider integriert

---

## [1.8.0] â€“ 2026-06-08 â€“ Cloudspeicher-Integration und StabilitÃ¤t

### Neu
- Cloudspeicher-Integration fÃ¼r Nextcloud, SeaDrive und WebDAV
- Neuer Speicher-Tab in den Einstellungen

### Aktualisierungen
- Fehlerhafte package.json repariert

---


## [1.7.3] - 2026-06-08 - Einstellungen umstrukturiert

### Neu
- Einstellungen: Design als Unter-Tab unter Allgemein
- Einstellungen: Backup & E-Mail als Unter-Tabs unter System
- Einstellungen: E-Mail-Vorlagen als Unter-Tab unter Parameter

---

## [1.7.4] â€“ 2026-06-08 â€“ StabilitÃ¤t und Wiederherstellung

### Aktualisierungen
- API und Datacenter-Seite wiederhergestellt

---

## [1.7.4] â€“ 2026-06-08 â€“ Datacenter-Seite neu aufgebaut

### Aktualisierungen
- DatacenterPage vollstÃ¤ndig rekonstruiert mit verbesserter StabilitÃ¤t
- EML/MSG-Datei-Vorschau hinzugefÃ¼gt

---

## [1.7.4] â€“ 2026-06-08 â€“ MSG-Vorschau und EML-Optimierung

### Neu
- MSG-Vorschau im Datacenter hinzugefÃ¼gt

### Aktualisierungen
- EML-Verarbeitung bei application/octet-stream-Dateien korrigiert

---

## [1.7.4] â€“ 2026-06-08 â€“ E-Mail-Vorschau verbessert

### Aktualisierungen
- E-Mail-Vorschau funktioniert nun auch bei application/octet-stream Dateitypen.

---

## [1.7.4] â€“ 2026-06-08 â€“ UTF-8 Encoding Verbesserungen

### Aktualisierungen
- UTF-8 Encoding in bump-version.ps1 korrigiert
- Update-Prozess in system.py optimiert

---

## [1.7.4] â€“ 2026-06-08 â€“ Dokumentation und Datacenter-Updates

---

## [1.7.4] â€“ 2026-06-08 â€“ Datacenter-Vorschau optimiert

### Neu
- Datacenter: EML-Vorschau direkt im Browser (E-Mail-Dateien)

### Aktualisierungen
- Datacenter: Vorschau-Route repariert (GIF und andere Formate wurden nicht geladen)

---

## [1.7.2] - 2026-06-07 - VersionsprÃ¼fung robuster + nginx Healthcheck

### Aktualisierungen
- VersionsprÃ¼fung: GitHub-Fallback via git wenn raw.githubusercontent.com nicht erreichbar
- SettingsPage: zeigt Warnung wenn GitHub-PrÃ¼fung fehlschlÃ¤gt
- nginx Healthcheck: wartet auf Backend-Bereitschaft vor Start
- nginx IP-AuflÃ¶sung: Container-IPs dynamisch alle 10s neu aufgelÃ¶st
- docker-compose.yml: certbot_conf Volume und Networks ergÃ¤nzt

---

## [1.7.1] - 2026-06-07 - Datacenter Freigaben-Verwaltung

### Neu
- Datacenter: Freigaben-Ansicht zeigt alle aktiven Share-Links
- Freigaben verlÃ¤ngerbar ohne Token-Ã„nderung (1/7/30/90 Tage oder unbegrenzt)
- Freigaben einzeln widerrufbar direkt aus der Ãœbersicht

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

## [1.7.1] â€“ 2026-06-07 â€“ Share-Link Route-Optimierung

### Aktualisierungen
- Share-Link Route wurde vor der generischen Entity-Route verschoben, um Routing-Konflikte zu beheben.

---
hangelog â€“ DeineZeit

Alle Ã„nderungen werden hier dokumentiert.
Format: [Version] â€“ Datum â€“ Was hat sich geÃ¤ndert

---

## [1.6.8] â€“ 2026-06-07 â€“ Versionsanzeige-Korrektur

### Aktualisierungen
- Versionsanzeige zeigt korrekt die installierte Version an, auch wenn der GitHub-Cache veraltet ist

---

## [1.6.7] â€“ 2026-06-06 â€“ StabilitÃ¤t und Mail-Verwaltung

### Aktualisierungen
- Mail-Icon in Rechnungsstatus bleibt nach Seitenwechsel erhalten
- API und AbhÃ¤ngigkeiten wiederhergestellt, CC-Feld hinzugefÃ¼gt

---

## [1.6.6] â€“ 2026-06-06 â€“ E-Mail-Kommunikation erweitert

### Neu
- E-Mail-Dialog mit Kontaktinfo, EmpfÃ¤nger-Mail und CC-Feld hinzugefÃ¼gt

---

## [1.6.5] â€“ 2026-06-06 â€“ Kontaktname in Belegliste korrigiert

### Aktualisierungen
- Kontaktnamen werden in der Belegliste nun korrekt angezeigt

---

## [1.6.4] â€“ 2026-06-06 â€“ Kontaktsuche Bugfix

### Aktualisierungen
- ContactSearch zeigt Kontaktnamen nach asynchronem Laden korrekt an

---

## [1.6.3] â€“ 2026-06-06 â€“ Kontaktanzeige in Belegen

### Aktualisierungen
- Kontakt wird nun in der Belegliste angezeigt
- Kontaktfeld im Formular repariert

---

## [1.6.2] â€“ 2026-06-06 â€“ DatacenterPicker API-KompatibilitÃ¤t

### Aktualisierungen
- DatacenterPicker verarbeitet API-Antworten korrekt, wenn AnhÃ¤nge als leeres Objekt statt Array zurÃ¼ckgegeben werden

---

## [1.6.1] â€“ 2026-06-06 â€“ AnhÃ¤nge-Feature korrigiert

### Aktualisierungen
- InvoicePage: AnhÃ¤nge-Feature korrekt integriert ohne Duplikate

---

## [1.9.0] â€“ 2026-06-07 â€“ E-Mail-Vorlagen System

### Neu
- E-Mail-Vorlagen pro Belegart (Rechnung, Angebot, AB, Gutschrift, Lieferschein)
- Neuer Tab â€žE-Mail-Vorlagen" in Einstellungen mit Rich-Text-Editor (TipTap)
- Platzhalter: {nummer}, {kontakt}, {firma}, {betrag}, {datum}, {faellig}, {belegart}
- Versand-Dialog: Betreff und E-Mail-Text vor dem Senden editierbar
- Betreff und Body werden aus der Vorlage vorausgefÃ¼llt

---

## [1.8.0] â€“ 2026-06-07 â€“ E-Mail-Dialog: Kontaktinfo & CC-EmpfÃ¤nger

### Neu
- E-Mail-Versand-Dialog zeigt Kontaktname und EmpfÃ¤nger-E-Mail an
- CC-Adresse kann optional eingetragen werden
- Backend: CC-UnterstÃ¼tzung fÃ¼r SMTP und Microsoft Graph API

---

## [1.7.0] â€“ 2026-06-06 â€“ Kontakt in Belegliste & Formular

### Neu
- Belegliste: Spalte "Titel / Kontakt" in zwei getrennte Spalten "Titel" und "Kontakt" aufgeteilt
- Belegliste: Kontaktname wird jetzt korrekt aus Stammdaten geladen und angezeigt
- Beleg-Formular: Kontaktfeld zeigt beim Bearbeiten wieder den gespeicherten Kontakt an

---

## [1.6.0] â€“ 2026-06-06 â€“ E-Mail-AnhÃ¤nge & Datacenter-Browser

### Neu
- AnhÃ¤nge beim E-Mail-Versand hinzufÃ¼gen
- Datacenter-Browser fÃ¼r Dateiauswahl nutzen
- Lokale Dateien als E-Mail-AnhÃ¤nge hochladen

---

## [1.5.0] â€“ 2026-06-06 â€“ Mail-Icons (grÃ¼n/orange) nach Versand + Status immer auf gesendet setzen

### Neu
- Mail-Icons (grÃ¼n/orange) nach Versand + Status immer auf gesendet setzen

---

## [1.4.5] â€“ 2026-06-06 â€“ E-Mail-Versand und Abrechnung

### Aktualisierungen
- PDF-Kontext korrekt geladen
- Unbilled Time Entries vollstÃ¤ndig implementiert
- E-Mail-Versand repariert

---

## [1.4.4] â€“ 2026-06-06 â€“ E-Mail-Fehlerbehandlung verbessert

### Aktualisierungen
- Fehlermeldungen beim E-Mail-Versand werden nun dauerhaft im Dialog angezeigt.

---

## [1.4.3] â€“ 2026-06-06 â€“ E-Mail-Versand repariert

### Aktualisierungen
- E-Mail-Versand und Rechnungsgenerierung wiederhergestellt

---

## [1.4.2] â€“ 2026-06-06 â€“ Nginx-StabilitÃ¤t und Docker-Verbesserungen

### Aktualisierungen
- Healthcheck und dynamische DNS-AuflÃ¶sung fÃ¼r Nginx optimiert
- Docker-Compose-Konfiguration vervollstÃ¤ndigt

---

## [1.4.1] â€“ 2026-06-06 â€“ nginx Healthcheck-Fix

### Behoben
- nginx wartet beim Start auf Backend-Healthcheck (`/api/health`) bevor es Anfragen weiterleitet
- nginx lÃ¶st Container-IPs dynamisch alle 10 Sekunden neu auf (Docker DNS-Resolver `127.0.0.11`) â€” kein manueller Neustart nach Backend-Recreate nÃ¶tig
- docker-compose.yml: fehlende Named Volumes (`certbot_conf`) und Networks-Sektion ergÃ¤nzt

---

## [1.4.0] â€“ 2026-06-06 â€“ E-Mail-Integration und StabilitÃ¤t

### Neu
- Office 365 E-Mail-Integration via Microsoft Graph API

### Aktualisierungen
- WeiÃŸer Bildschirm im Changelog-Panel der Anmeldeseite behoben
- Update-Watchdog und HTTPS Health-Check optimiert
- Belegbuch-Endpoints implementiert (Listenansicht, CSV- und PDF-Export)
- Backup-Watcher mit Administratorrechten ausgefÃ¼hrt
- Quellcode-Verwaltung fÃ¼r zuverlÃ¤ssige Docker-basierte Updates verbessert

---

## [1.3.13] â€“ 2026-06-06 â€“ Update-Mechanismus Test

### Neu
- Update-Mechanismus End-to-End erfolgreich getestet

---

## [1.3.12] â€“ 2026-06-06 â€“ WeiÃŸer Bildschirm nach Update behoben

### Behoben
- Absturz auf der Anmeldeseite wenn ein Changelog-Eintrag weder "features" noch "updates" enthÃ¤lt (optional chaining)
- changelog.js v1.3.11: "changes" in "updates" umbenannt damit Eintrag im Updates-Tab erscheint

---

## [1.3.11] â€“ 2026-06-06 â€“ Update-Prozess StabilitÃ¤tsverbesserungen

### Behoben
- Update-Status bleibt nicht mehr dauerhaft auf "updating" wenn kein neuer Commit vorhanden (Watchdog nach 5 Min)
- Health-Check im Update-Script nutzt jetzt HTTPS statt HTTP (verhindert Rollback-Schleife)
- nginx.conf-Verzeichnis-Bug wird beim Update automatisch korrigiert
- update.sh, nginx-Konfiguration und docker-compose.yml in git aufgenommen (gehen nicht mehr verloren)

---

## [1.3.10] â€“ 2026-06-05 â€“ Lokale Instanzerkennung und StabilitÃ¤tsverbesserungen

### Neu
- Lokale Instanzerkennung implementiert

### Aktualisierungen
- Update-Tab zeigt git pull Anleitung statt Button
- Changelog-Konflikte gelÃ¶st
- Changelog mit fehlenden Versionen 1.2.1â€“1.3.8 synchronisiert

---

## [1.3.9] â€“ 2026-06-05 â€“ Lokale Instanz erkennung

### Aktualisierungen
- Lokale Entwicklungsinstanz wird automatisch erkannt â€” Update-Button zeigt stattdessen Anleitung fÃ¼r git pull
- Backend blockiert Update-Start in lokalem Modus mit klarer Fehlermeldung

---

## [1.3.8] â€“ 2026-06-05 â€“ Frontend-Integration

### Aktualisierungen
- Gesamtes Frontend in Versionskontrolle integriert

---

## [1.3.7] â€“ 2026-06-05 â€“ Backend-Infrastruktur aktualisiert

### Aktualisierungen
- Backend-App-Verzeichnis in Versionskontrolle integriert

---

## [1.3.6] â€“ 2026-06-05 â€“ KonfigurationsstabilitÃ¤t verbessert

### Aktualisierungen
- ConfigParser-Interpolation in alembic.ini entfernt

---

## [1.3.5] â€“ 2026-06-05 â€“ Datenbankmigrationen hinzugefÃ¼gt

### Aktualisierungen
- Alembic-Migrationen zur Versionskontrolle hinzugefÃ¼gt

---

## [1.3.4] â€“ 2026-06-05 â€“ Backend-Infrastruktur erweitert

### Aktualisierungen
- Backend-Grunddateien fÃ¼r Docker-Containerisierung hinzugefÃ¼gt

---

## [1.3.3] â€“ 2026-06-05 â€“ Docker-Compose Integration

### Aktualisierungen
- Docker-Compose Dateien zum Repository hinzugefÃ¼gt

---

## [1.3.2] â€“ 2026-06-05 â€“ Versions-Anzeige korrigiert

### Aktualisierungen
- Versions-Anzeige liest nun aus CHANGELOG.md statt aus package.json oder config.py

---

## [1.3.1] â€“ 2026-06-05 â€“ Rechnungs-Widget Darstellung optimiert

### Aktualisierungen
- Rechnungs-Widget wird nun auch bei bestehender Dashboard-Konfiguration korrekt angezeigt.

---

## [1.3.0] â€“ 2026-06-05 â€“ Dashboard und Einstellungen Ã¼berarbeitet

### Neu
- Rechnungs-Widget im Dashboard hinzugefÃ¼gt
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

## [1.2.1] â€“ 2026-06-05 â€“ Dashboard: Rechnungs-Widget

### Neu
- Dashboard-Widget â€žRechnungen": zeigt offene, Ã¼berfÃ¤llige und diesen Monat bezahlte Rechnungen mit Anzahl und Brutto-Summe
- Widget ist standardmÃ¤ÃŸig im Dashboard enthalten, verschiebbar und in der GrÃ¶ÃŸe anpassbar

---

## [1.2.0] â€“ 2026-06-05 â€“ AuftragsbestÃ¤tigung & Rechnungsmodul-Erweiterungen

### Neu
- AuftragsbestÃ¤tigung (AB) als neuer Dokumenttyp mit eigenem Nummernkreis (AB-2026-001, â€¦)
- E-Mail-Versand direkt aus dem Rechnungsmodul â€” einzeln oder als Bulk-Versand fÃ¼r mehrere Belege
- Statusworkflow mit kontextabhÃ¤ngigem AktionsmenÃ¼: Entwurf â†’ Offen â†’ Bezahlt, Angenommen / Abgelehnt, Storniert
- Angebote kÃ¶nnen nach Annahme direkt in eine AuftragsbestÃ¤tigung oder Rechnung umgewandelt werden

### Aktualisierungen
- Parameter-Tab in den Einstellungen: PrÃ¤fixe und Nummernformate pro Dokumenttyp frei konfigurierbar
- Dokumenttyp-Bezeichnungen kÃ¶nnen umbenannt werden

---

## [1.1.0] â€“ 2026-06-04 â€“ Buchhaltungsmodul

### Neu
- Kontenplan nach EKR (Einheitskontenrahmen) vorbefÃ¼llt und durchsuchbar
- BMD-Export fÃ¼r die steuerliche Ãœbergabe an den Steuerberater
- Debitor- und Kreditornummern direkt bei Kontakten hinterlegbar
- ErlÃ¶skonto pro Artikel festlegbar â€” wird automatisch auf Rechnungspositionen Ã¼bernommen
- Konto pro Rechnungsposition individuell Ã¼berschreibbar
- Kontakte: neuer Finanz-Tab mit IBAN, BIC und Bankname (Migration 0012/0013)

---

## [1.0.0] â€“ 2026-06-03 â€“ Rechnungsmodul

### Neu
- Rechnungen, Angebote, Gutschriften und Lieferscheine erstellen
- Automatische Nummerierung pro Dokumenttyp (RE-2026-001, AN-2026-001, â€¦)
- Stornierung mit automatischer Gutschrift oder nur StatusÃ¤nderung
- Angebote kÃ¶nnen direkt in Rechnungen umgewandelt werden
- ZeiteintrÃ¤ge aus der Zeiterfassung direkt auf Rechnung Ã¼bernehmen
- Positionen aus Artikel-Stammdaten oder als Freitext
- MwSt.: pro Position wÃ¤hlbar, ein Satz, oder Kleinunternehmerregelung
- PDF-Export mit 5 wÃ¤hlbaren Vorlagen (Klassisch, Modern, Kompakt, Elegant, Farbenfroh)
- Rechnungsbuch filterbar nach Monat/Quartal/Jahr und/oder Kunde â€” als PDF oder CSV
- Zahlungsstatus: offen, bezahlt, Ã¼berfÃ¤llig, storniert
- Wiederkehrende Rechnungsvorlagen (wÃ¶chentlich, monatlich, quartalsweise, jÃ¤hrlich)
- Bankverbindung aus den App-Einstellungen automatisch auf jedem Dokument

---

## [0.9.5] â€“ 2026-06-03 â€“ Dashboard konfigurierbar

### Neu
- Dashboard-Bausteine per Drag & Drop frei anordnen
- Breite der Bausteine stufenweise anpassen (Â¼ / Â½ / Vollbreite)
- Layout wird im Browser gespeichert und beim nÃ¤chsten Besuch wiederhergestellt
- Neues Zeiterfassung-Widget auf dem Dashboard mit Heute/Woche/Monat-Ãœbersicht

---

## [0.9.4] â€“ 2026-06-03 â€“ Update-Prozess robuster

### Aktualisierungen
- Backend fÃ¼hrt Alembic-Migrationen jetzt automatisch beim Start aus â€” zukÃ¼nftige Updates brauchen kein manuelles `alembic upgrade head` mehr
- Migrations-Fehler beim Start verhindern nun das Hochkommen des Backends â†’ Health-Check schlÃ¤gt fehl â†’ automatischer Rollback greift korrekt
- Rollback im Update-Skript stellt jetzt auch die gesicherten Docker-Images wieder her, nicht nur den Git-Commit

---

## [0.9.3] â€“ 2026-06-02 â€“ Stammdaten vereinheitlicht

### Aktualisierungen
- Stammdaten-Typen vereinheitlicht: Kunden und Lieferanten zusammengefÃ¼hrt zu â€žKontakte" mit Typ-Feld (Kunde / Lieferant / Interessent)
- Neuer Stammdaten-Typ â€žArtikel" fÃ¼r Produkte und Dienstleistungen (Bezeichnung, Artikelnummer, Preis, Beschreibung)
- Bestehende Kunden- und Lieferanten-DatensÃ¤tze werden bei Migration automatisch nach Kontakte Ã¼bernommen
- Alembic-Migration 0010 stellt einheitlichen Stand bei Neu- und Bestandsinstallationen sicher

---

## [0.1.0] â€“ 2026-05-21 â€“ Grundfundament

### Neu
- Projektstruktur mit Backend (Python/FastAPI), Frontend (React) und Datenbank (PostgreSQL)
- Docker Compose Setup fÃ¼r einfaches Deployment
- Benutzerverwaltung mit Rollen (Admin / Mitarbeiter)
- Sicheres Login-System:
  - Passwort-Login mit verschlÃ¼sselter Speicherung
  - Zwei-Faktor-Authentifizierung (TOTP / Google Authenticator)
  - Face ID / Fingerabdruck Login via WebAuthn/Passkeys
- JWT-Token-basierte Authentifizierung mit automatischer Erneuerung
- Mehrsprachigkeit: Deutsch und Englisch (sprachabhÃ¤ngig pro Benutzer)
- Responsives Design (Mobile-First fÃ¼r Handy, Tablet und Desktop)
- Datenbank-Migrationen via Alembic (sichere Schema-Updates)
- nginx Reverse Proxy mit HTTPS / Let's Encrypt UnterstÃ¼tzung
- Sicherheits-Header (HSTS, XSS-Schutz, Frame-Schutz)

### Technische Details
- Backend: FastAPI 0.111, Python 3.12
- Frontend: React 18, Tailwind CSS, i18next
- Datenbank: PostgreSQL 16 mit Alembic-Migrationen
- Deployment: Docker Compose, nginx, Certbot (Let's Encrypt)

---

---

## [0.2.0] â€“ 2026-05-21 â€“ Dynamische Stammdaten-Verwaltung

### Neu
- **Stammdaten-Typen**: Kunden, Lieferanten und Projekte vorinstalliert
- **Beliebige neue Typen**: Jederzeit weitere anlegen (z.B. Mitarbeiter, Fahrzeuge, VertrÃ¤geâ€¦)
- **Dynamischer Formular-Builder**: Felder direkt in der OberflÃ¤che hinzufÃ¼gen, bearbeiten und entfernen â€” ohne Programmieraufwand
- **9 Feldtypen**: Text, mehrzeiliger Text, Zahl, Datum, E-Mail, Telefon, Auswahlliste, Ja/Nein, Webseite
- **Pflichtfelder** und **Listenansicht** pro Feld konfigurierbar
- **Datensatz-Verwaltung**: Anlegen, bearbeiten und lÃ¶schen mit automatisch generiertem Formular
- **Suche**: Volltextsuche Ã¼ber alle Felder eines Stammdaten-Typs
- **Paginierung**: GroÃŸe Datenmengen werden seitenweise angezeigt
- **Dashboard**: SchnellÃ¼bersicht aller Stammdaten-Typen mit Eintrags-ZÃ¤hler
- **Datenbank**: JSONB-basierter Speicher mit GIN-Index fÃ¼r schnelle Suche

### Technische Details
- Neue Datenbankmodelle: `entity_types`, `field_definitions`, `entity_records`
- Migration 0002 mit vordefinierten Standard-Feldern fÃ¼r Kunden/Lieferanten/Projekte
- Neue API-Endpoints: `/api/masterdata/types/*` und `/api/masterdata/types/{slug}/records/*`
- Neue Komponenten: `FieldBuilder`, `DynamicForm`, `MasterDataOverview`, `MasterDataDetail`

---

---

## [0.3.0] â€“ 2026-05-21 â€“ Grid-Layout, Import/Export & Benutzerverwaltung

### Neu
- **Snap-to-Grid Drag & Drop Layout-Builder**: Felder per Maus oder Touch-Geste frei verschieben â€” ein unsichtbares 12-Spalten-Raster sorgt dafÃ¼r, dass alles sauber einrastet
- **Feldbreite frei wÃ¤hlbar**: 25% / 33% / 50% / 75% / 100% â€” direkt per Klick am Feld einstellbar; mehrere Felder kÃ¶nnen nebeneinander in einer Zeile angezeigt werden
- **Formular respektiert Layout**: Die Erfassungsmaske zeigt Felder exakt im