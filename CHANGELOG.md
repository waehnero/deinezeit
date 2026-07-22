# Changelog

## [1.12.31] – 2026-07-20 – Postecke: Facebook-Seiten direkt angebunden

### Neu
- Postecke: Facebook-Seiten sind jetzt direkt angebunden — „Jetzt veröffentlichen" postet Text, Hashtags und Fotos ohne Umweg direkt auf die Seite
- Postecke: Geplante Posts auf angebundenen Kanälen werden zur eingestellten Zeit vollautomatisch veröffentlicht; Fehler werden am Post angezeigt und automatisch erneut versucht
- Postecke: Zugangsdaten (Seiten-ID + Token) werden verschlüsselt je Profil gespeichert, mit „Verbindung testen"-Knopf — Einrichtungsanleitung liegt bei (FACEBOOK-SEITE-ANBINDEN.md)

---

## [1.12.30] – 2026-07-20 – Postecke: Profil-Parameter für Fotos & neue Kanäle

### Neu
- Postecke: Je Profil sind jetzt Bildformat (z. B. 1:1 Quadrat, 4:5, 16:9, 9:16 Story) und ein Foto-Filter (Brillant, Warm, Kühl, Kontrast+, Schwarz-Weiß) hinterlegbar — beim Teilen und Herunterladen werden alle Fotos automatisch so ausgespielt, die Originale bleiben erhalten
- Postecke: Neue Kanäle für Profile — TikTok, YouTube, WhatsApp (Status/Kanal), X (Twitter), Threads, Google Unternehmensprofil und Pinterest

---

## [1.12.29] – 2026-07-20 – iPhone-Anzeige stabilisiert

### Aktualisierungen
- Kein ungewolltes Hineinzoomen mehr bei Eingabefeldern am iPhone und iPad — die Ansicht bleibt stabil im Geräterahmen

---

## [1.12.28] – 2026-07-15 – Zeiterfassung: Sprach-Eintrag per KI & flexible Zeiten

### Neu
- Projektzeit per Sprache nachtragen: neuer Aufnahme-Knopf in der Zeiterfassung — die Ansage wird per KI ausgewertet und der Nachtragen-Dialog automatisch vorbefüllt
- Start- und Endzeit im Timer-Bereich jederzeit manuell anpassbar, mit Vorschlägen wie letzter Endzeit oder aktueller Uhrzeit

### Aktualisierungen
- Aktions-Symbole in der Eintragsliste sind jetzt bei jedem Eintrag dauerhaft sichtbar (auch auf Touch-Geräten)

---

## [1.12.27] – 2026-07-12 – Layout-Redesign: Handy-Optimierung & Barrierefreiheit

### Neue Funktionen
- Menüleiste unten am Handy mit den wichtigsten Modulen und rundem Plus-Knopf für „Neu anlegen"
- Schnellsuche mit Cmd/Strg+K über Module, Stammdaten und Aktionen
- Dunkelmodus und Barrierefreiheit pro Benutzer (Hell/Dunkel/Automatisch, hoher Kontrast, größere Schrift, weniger Animation)

### Aktualisierungen
- Dialogfenster verdecken am Handy die Menüleiste nicht mehr und sind durchscrollbar
- Stammdaten-Listen erscheinen am Handy als Karten

---

## [1.12.26] – 2026-07-12 – Layout-Redesign: Designvorlagen & Whitelabel

### Neue Funktionen
- 8 Designvorlagen mit Live-Vorschau (Einstellungen → Design)
- Eigene Markenfarbe färbt die gesamte App (Whitelabel)
- Stammdaten-Typen direkt im Menü aufklappbar

### Aktualisierungen
- Einheitlicher Seitenaufbau in allen Modulen (Symbol, Titel, Aktionen an fester Position)
- Feinanpassung für Text-, Hintergrund- und Flächenfarben

---

## [1.12.25] – 2026-07-12 – Layout-Redesign: Fundament

### Aktualisierungen
- Technisches Fundament für das neue Design (Design-Tokens) — Optik unverändert

---

## [1.12.24] – 2026-07-12 – Modulrechte pro Benutzer

### Neu
- Der Admin kann jetzt pro Benutzer festlegen, welche Module er verwenden darf (Benutzerverwaltung → Bearbeiten) — z.B. nur Zeiterfassung für Erfassungs-Mitarbeiter
- Menü und Dashboard zeigen nur noch die freigeschalteten Module; die Startseite ist das erste erlaubte Modul

### Aktualisierungen
- Bestehende Benutzer behalten automatisch alle Module — es ändert sich nichts, bis der Admin Module abschaltet
- Stammdaten bleiben für alle lesbar (Auswahlfelder), Bearbeiten erfordert das Stammdaten-Modul; Datei-Anhänge an Datensätzen funktionieren weiterhin in allen Modulen

---

## [1.12.23] – 2026-07-11 – Sichere Löschregeln & Archivierung

### Neu
- Stammdaten können jetzt archiviert und wiederhergestellt werden (Archiv-Ansicht) — verknüpfte Daten bleiben nachvollziehbar erhalten
- Neue Verwendungs-Prüfung: Vor dem Löschen zeigt das System, wo ein Datensatz überall verwendet wird
- Zeiterfassung: Neuer Abrechnungs-Status je Eintrag (Veränderbar → Gesperrt → Freigegeben → Abgerechnet) mit Schloss-Symbol, einzeln oder per Mehrfachauswahl umstellbar — auch manuell abgerechnete Zeiten sind damit geschützt

### Aktualisierungen
- Stammdaten mit Verknüpfungen (Zeiten, Belege, Projekte, Dateien) sind vor versehentlichem Löschen geschützt; endgültiges Löschen nur noch durch Admins
- Bereits abgerechnete Zeiteinträge können nicht mehr geändert oder gelöscht werden; Zeiteinträge anderer Benutzer sind schreibgeschützt
- Projekte und Aufgaben mit gebuchten Zeiten können nicht mehr gelöscht werden — stattdessen archivieren
- Stundenkonten werden beim Löschen einer Projektzeit nicht mehr mitgelöscht
- Aufgaben: Entfernen fragt jetzt nach (Archivieren oder endgültig löschen); Aufgaben mit verknüpftem Zeiteintrag sind unlöschbar, löschen dürfen nur Ersteller, Zugewiesener oder Admin
- Datacenter: Löschen fragt jetzt immer nach; Dateien, die mit einem Verkaufsbeleg verknüpft sind (z.B. Verträge wiederkehrender Rechnungen), können nur über das Verkaufsmodul entfernt werden; automatisch archivierte Belege löscht nur der Admin

---

## [1.12.22] – 2026-07-11 – Fehlerbehebungen Postecke & Mobil

### Aktualisierungen
- Postecke: Foto-Upload zuverlässig auch mit großen iPhone-Fotos (Fotos werden einzeln übertragen, Server-Limit erhöht, klare Fehlermeldung je Foto)
- Postecke: KI-Vorschläge mit vielen Fotos brechen nicht mehr durch Server-Timeout ab
- Einstellungen: Neues Logo/Favicon erscheint nach dem Hochladen sofort (kein veraltetes Bild aus dem Browser-Cache mehr)
- iPhone: Hinweismeldungen erscheinen nicht mehr unter der Notch; Unter-Tabs in den Einstellungen laufen nicht mehr über den Bildschirmrand

---

## [1.12.21] – 2026-07-10 – Neues Modul: Postecke – Social-Media-Posts mit KI vorbereiten

### Neu
- Postecke: Fotos hochladen, kurz beschreiben (auch per Diktat) – die KI erstellt Posttext, Hashtags, Ort und Gefühl im Stil des gewählten Kontos
- Postecke: Profile je Social-Media-Konto (Facebook, Instagram, LinkedIn u. a.) mit eigenen Stil-Vorgaben für die KI
- Postecke: Assistiertes Posten – am iPhone/iPad mit Fotos direkt über das Teilen-Menü, der Text liegt in der Zwischenablage
- Postecke: Redaktionsplan mit drei Ansichten – Liste, Kanban-Board (Status per Drag & Drop) und Monatskalender, dazu Volltextsuche über alle Posts
- Postecke: Posts können einem Kontakt zugeordnet und archiviert werden – das Archiv landet samt Text und Fotos im Datacenter beim Kontakt im Ordner „Postsarchiv" (ohne Kontakt global), inklusive Wiederherstellung

### Aktualisierungen
- KI-Anbindung zentralisiert: Postecke und Mail-Importer nutzen dieselben KI-Einstellungen, jetzt mit Foto-Erkennung
- Datacenter: Textdateien (z. B. das Postsarchiv) werden in der Vorschau jetzt lesbar angezeigt; die Vorschau respektiert am iPhone den Bildschirmrand und lässt sich immer schließen

---

## [1.12.20] – 2026-07-08 – Verkauf: Duplizieren, wiederkehrende Rechnungen, erweiterte Suche & Beleg-Archiv

### Neu
- Belege duplizieren: Über das Kontextmenü lässt sich jeder Beleg als neuer Entwurf duplizieren – im Dialog wählbar, welche Teile übernommen werden (Positionen, Texte, Kontakt/Referenz, Anhänge).
- Wiederkehrende Rechnungen: Rechnungen als Serie mit Intervall und Laufzeit anlegen; fällige Rechnungen entstehen automatisch als Entwurf und sind farblich markiert.
- Erweiterte Suche im Verkauf: Belege lassen sich jetzt auch nach Kontakt, Artikel und Projekt durchsuchen.
- Automatisches Beleg-Archiv: Bei frei wählbaren Ereignissen wird ein PDF des Belegs automatisch im Datacenter unter dem Kunden – je Belegart in eigenem Unterordner – abgelegt.

### Aktualisierungen
- Verträge zu wiederkehrenden Rechnungen: mehrere Verträge je Beleg möglich, im Datacenter unter dem Kunden im Ordner „Verträge“ mit Belegnummer, direkt im Formular öffnen und entfernen.
- Wiederkehrende Vorlagen erscheinen nun auch in der Gesamtliste (violett markiert).

---

## [1.12.19] – 2026-07-08 – Aussagekräftigere Release-Notes

### Aktualisierungen
- Die Änderungsliste auf der Anmeldeseite zeigt jetzt aussagekräftigere Release-Notes

---

## [1.12.18] – 2026-07-08 – Zeiterfassung & Verkauf

### Neu
- Zeiterfassung um ein Stundenkonto erweitert

### Aktualisierungen
- Das Beleg-Modul heißt in der Oberfläche jetzt durchgängig „Verkauf"

---

## [1.12.17] – 2026-07-06 – Datenschutz

### Neu
- DSGVO-konforme Datenlöschung unter Einstellungen → Datenschutz

---

## [1.12.16] – 2026-07-06 – Automatische Versionierung

### Aktualisierungen
- Versionsnummer und Änderungsliste werden automatisch aktuell gehalten

---

## [1.12.15] – 2026-07-02 – Projekte-Menü & stabileres Deployment

### Aktualisierungen
- Projekte: Aktionsmenü (drei Punkte) wird wieder korrekt angezeigt und nicht mehr doppelt dargestellt
- Automatisches Server-Deployment robuster (Frontend-Update und nginx zuverlässiger)

---

## [1.12.14] – 2026-06-26 – Zeiterfassung Datei-Upload repariert

### Aktualisierungen
- Race-Condition beim Datei-Upload in der Zeiterfassung behoben

---

## [1.12.13] – 2026-06-25 – Kompaktere Sidebar für mehr Platz

### Neu
- Sidebar lässt sich einklappen und zeigt nur noch Symbole an

---

## [1.12.12] – 2026-06-25 – Benutzer-Verwaltung überarbeitet

### Aktualisierungen
- Benutzer-Verwaltung in die Einstellungen integriert und separater Menüpunkt entfernt

---

## [1.12.11] – 2026-06-25 – Datacenter-Reorganisation mit Vererbung

### Neu
- Dateien werden jetzt nach Modul und Kontakt organisiert
- Vererbungsmechanismus für Dateistrukturen implementiert
- Automatisches Backfill von Bestandsdaten

---

## [1.12.10] – 2026-06-25 – Bugfix Zeiteintrag-Dialog

### Aktualisierungen
- Dialog zum Bearbeiten von Zeiteinträgen wurde korrigiert.

---

## [1.12.9] – 2026-06-25 – Datei-Upload Stabilität

### Aktualisierungen
- Datei-Upload mit korrekter Multipart-Boundary-Handhabung repariert
- Anhänge-Zähler wird nun zuverlässig aktualisiert

---

## [1.12.8] – 2026-06-21 – Navigation zum Dashboard vereinfacht

### Neu
- Logo oder Firmennamen können zum Dashboard angetippt werden

---

## [1.12.7] – 2026-06-21 – Schnellzugriff für Projekte

### Neu
- Neues Projekte-Widget für schnellen Zugriff

---

## [1.12.6] – 2026-06-21 – iPhone Header Bugfix

### Aktualisierungen
- iPhone Header lokal behoben

---

## [1.12.5] – 2026-06-21 – Board und Projektübersicht erweitert

### Neu
- Neues Board-System für verbesserte Projektorganisation
- Erweiterte Automatisierungsmöglichkeiten für Workflows
- Neue Projektübersicht mit besserer Darstellung
- Neue Typen zur flexibleren Datenverwaltung

### Aktualisierungen
- Abhängigkeiten aktualisiert und optimiert
- Desktop-Ansicht für bessere Usability überarbeitet

---

## [1.12.4] – 2026-06-21 – Stabilitätsverbesserung Projekt-Details

### Aktualisierungen
- Projekt-Detail stürzt nicht mehr bei verschachtelten Aufgaben ab

---

## [1.12.3] – 2026-06-20 – Automatische Versionsverwaltung mit Schutz

### Aktualisierungen
- Automatische Versionserkennung in check.sh implementiert
- Lock-Schutz für Versionsverwaltung hinzugefügt

---

## [1.12.2] – 2026-06-20 – Versionsprüfung und Release-Management

### Neu
- Versionsprüfungstool zur Überprüfung von Versionsnummern
- Automatisierte Versionscheck-Funktion implementiert
- Push-Freigabe basierend auf Versionsstatus

---

## [1.12.1] – 2026-06-20 – Projektplanung und Stabilität

### Neu
- Neues Projektplanungs-Modul für erweiterte Projektverwaltung
- News-Panel auf der Anmeldeseite für aktuelle Informationen

### Aktualisierungen
- Vite PWA Plugin als Abhängigkeit hinzugefügt
- Docker-Compose-Konfiguration mit Volumes und Networks erweitert
- Neu-laden-Button in Einstellungen mit visuellen Rückmeldungen verbessert
- config.py vollständig wiederhergestellt
- Kontextmenü Portal-Rendering gegen unerwünschtes Abschneiden optimiert
- Entrypoint-Skript als ausführbar markiert

---

## [1.12.0] - 2026-06-20 - Neues Modul: Projektplanung

### Neu
- **Projektplanungs-Modul** (Menüpunkt „Projekte"): eigenständiges Projekt-Aufzeichnungstool ähnlich MS Project / OpenProject, mobile-first
- Planungsprojekte anlegen, bearbeiten, duplizieren (mit Auswahl, wie viel mitkopiert wird), archivieren und löschen
- Aufgaben & beliebig tief verschachtelbare Teilaufgaben mit Quick-Add zur raschen Erfassung am Handy
- Konfigurierbare Status, Prioritäten, Tags und eigene Aufgaben-Felder (Projekt-Einstellungen)
- Verantwortliche und Kontakte je Projekt und je Aufgabe (Aufgaben erben den Projekt-Kontakt, überschreibbar)
- Anlagen (Dateien/Fotos) an Aufgaben über den bestehenden MinIO-Speicher
- Checklisten an Projekten und Aufgaben: Elemente abhaken, als Aufgabe anlegen, an Benutzer/Kontakt zuweisen inkl. E-Mail-Benachrichtigung
- Gantt-/Zeitschienen-Ansicht: Aufgabenbalken, Meilensteine, Heute-Linie, Abhängigkeiten mit kritischem Pfad, Termine per Drag verschiebbar
- Zeiterfassung: optionale Verknüpfung eines Zeiteintrags mit einer Planungsaufgabe (Ist-/Soll-Stunden)

### Geändert
- Stammdaten „Projekte" in „Projektzeiten" umbenannt
- Projektfarbe wird als Farbkreis in Projektübersicht und -detail angezeigt

### Datenbank
- Migrationen 0016–0019 (Planungsprojekte, Aufgaben, Abhängigkeiten, Meilensteine, konfigurierbare Felder, Checklisten; Kontakt- und Aufgaben-Verknüpfung an Zeiteinträgen)


---

## [1.11.3] - 2026-06-17 - Kontextmenü Portal-Fix


---

## [1.11.1] - 2026-06-17
### GeÃƒÂ¤ndert
- Graph API: Gesendete E-Mails werden jetzt im Outlook-Ordner Ã¢â‚¬Å¾Gesendete Elemente" gespeichert

## [1.10.3] - 2026-06-15
### GeÃƒÂ¤ndert
- Belege-Liste: Header-Buttons, Belegtypen-Tabs und Tabelle fÃƒÂ¼r MobilgerÃƒÂ¤te optimiert (scrollbar, gestapelt, weniger Spalten)
- Beleg bearbeiten: Header-Buttons und Positionszeilen passen sich auf schmalen Bildschirmen an
- Datacenter: OrdnerÃƒÂ¼bersicht ist am Handy als ausklappbares MenÃƒÂ¼ verfÃƒÂ¼gbar, Aktionssymbole immer sichtbar
- Kontakte/Stammdaten: Header-Buttons und Typ-Filter wurden fÃƒÂ¼r MobilgerÃƒÂ¤te responsiv gestaltet

## [1.10.2] - 2026-06-15
### GeÃƒÂ¤ndert
- Berichts-Dialog: Datum-, Gruppierungs- und Filterfelder stapeln sich auf schmalen Bildschirmen statt sich zu ÃƒÂ¼berlappen
- AnhÃƒÂ¤nge-Verwaltung: Aktionssymbole (Ãƒâ€“ffnen, Teilen, LÃƒÂ¶schen) sind am Handy immer sichtbar; Vorschau-Kacheln zeigen auf schmalen Bildschirmen 2 statt 3 Spalten

## [1.10.1] - 2026-06-13
### GeÃƒÂ¤ndert
- Projektzeit-Seite: Buttons "Bericht erstellen" und "Projektzeit nachtragen" zeigen auf schmalen Bildschirmen (Handy) nur noch Icons
- Start-Formular: "Verrechenbar"-Option steht jetzt neben der Startzeit statt darunter, spart Platz auf mobilen GerÃƒÂ¤ten

## [1.10.0] - 2026-06-13
### Neu
- Progressive Web App (PWA) ermÃƒÂ¶glicht die Nutzung von DeineZeit als installierbare App

## [1.9.0] - 2026-06-13
### Neu
- DeineZeit als PWA: Installation ÃƒÂ¼ber "Zum Home-Bildschirm hinzufÃƒÂ¼gen" (eigenes Icon, Vollbildmodus ohne Browserleiste)
- Web App Manifest mit Icons (192px, 512px, maskable, Apple Touch Icon) und Theme-Farbe
- Service Worker (vite-plugin-pwa) fÃƒÂ¼r Caching der App-Shell und grundlegende Offline-Nutzung
### GeÃƒÂ¤ndert
- iOS-Meta-Tags fÃƒÂ¼r Installation ÃƒÂ¼ber Safari ergÃƒÂ¤nzt
- nginx-Konfiguration: Service Worker und Manifest werden nicht mehr langfristig gecacht

## [1.8.5] - 2026-06-13
### GeÃƒÂ¤ndert
- Anhang-Buttons (Cloud-Link, Foto aufnehmen, Hochladen) zeigen auf schmalen Bildschirmen nur noch Icons Ã¢â‚¬â€œ passen jetzt in eine Zeile

## [1.8.4] - 2026-06-13
### GeÃƒÂ¤ndert
- Projektzeit-Hauptseite: Layout der Start- und laufenden Timer-Karte fÃƒÂ¼r MobilgerÃƒÂ¤te (Hoch- und Querformat) ÃƒÂ¼berarbeitet, Spalten stapeln sich statt sich zu ÃƒÂ¼berlappen
- "Projektzeit nachtragen"-Dialog: Formularfelder stapeln sich auf schmalen Bildschirmen statt sich zu ÃƒÂ¼berlappen
- Anhang-Schnellzugriff-Buttons umbrechen jetzt bei wenig Platz

## [1.8.3] - 2026-06-13
### Neu
- Schnellzugriff-Leiste fÃƒÂ¼r AnhÃƒÂ¤nge (Cloud-Link, Foto aufnehmen, Hochladen) direkt auf der Projektzeit-Hauptseite (Start- und laufende Timer-Karte) und im "Projektzeit nachtragen"-Dialog
### GeÃƒÂ¤ndert
- Wird ein Anhang hinzugefÃƒÂ¼gt, bevor der Zeiteintrag gespeichert wurde, wird die Aufgabe automatisch validiert und gespeichert

## [1.8.1] - 2026-06-12
### Neu
- Zeiterfassung-AnhÃƒÂ¤nge: Neuer Button Ã¢â‚¬Å¾Foto aufnehmen" ÃƒÂ¶ffnet direkt die Kamera des GerÃƒÂ¤ts (iPhone/Android/Tablet)
- Bestehender Drag & Drop-Upload-Bereich bleibt fÃƒÂ¼r lokale Dateien erhalten

## [1.8.0] - 2026-06-08
### Neu
- OneDrive-Integration mit Microsoft Graph API (persÃƒÂ¶nliche Konten & SharePoint)

## [1.7.8] - 2026-06-08
### Neu
- OneDrive-Integration: Microsoft OneDrive & SharePoint als Cloudspeicher-Option
- Graph-Anmeldedaten aus E-Mail-Einstellungen kÃƒÂ¶nnen fÃƒÂ¼r OneDrive wiederverwendet werden
- PersÃƒÂ¶nliches OneDrive und SharePoint-Laufwerk konfigurierbar (inkl. Site-ID)

## [1.7.7] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ Cloudspeicher-Integration abgeschlossen

### Neu
- Cloudspeicher: Nextcloud, SeaDrive und MinIO als Storage-Provider wÃƒÂ¤hlbar
- Speicher-Tab in Einstellungen (Provider-Auswahl, WebDAV-URL, Verbindungstest)
- MSG-Datei (.msg Outlook) Vorschau im Datacenter

### Fixes
- Upload-Fortschrittsanzeige (ProgressEvent Ã¢â€ â€™ korrekter Prozentwert)
- WebDAV-Upload: db=db an storage_service ÃƒÂ¼bergeben (Provider aus DB gelesen)
- storage_backend wird korrekt als Providername (nextcloud/seadrive/minio) gespeichert
- requests-Bibliothek in requirements.txt ergÃƒÂ¤nzt

---

## [1.11.0] Ã¢â‚¬â€œ 2026-06-16 Ã¢â‚¬â€œ Office 365 E-Mail Integration

### Neu
- Office 365 E-Mail-Anbindung ÃƒÂ¼ber Microsoft Graph API

---

## [1.10.4] Ã¢â‚¬â€œ 2026-06-15 Ã¢â‚¬â€œ Mobile-Responsiveness verbessert

### Aktualisierungen
- Mobile-Responsiveness fÃƒÂ¼r Belege, Beleg-Formular, Datacenter und Kontakte optimiert
- Synchronisierungsfehler bei mobilen Ansichten behoben

---

## [1.10.3] Ã¢â‚¬â€œ 2026-06-15 Ã¢â‚¬â€œ Mobile-Optimierungen und Verbesserungen

### Aktualisierungen
- Berichts-Dialog fÃƒÂ¼r mobile GerÃƒÂ¤te optimiert
- AnhÃƒÂ¤nge-Handling verbessert

---

## [1.10.2] Ã¢â‚¬â€œ 2026-06-13 Ã¢â‚¬â€œ Merge-Konflikte aufgelÃƒÂ¶st

### Aktualisierungen
- Merge-Konflikte behoben

---

## [1.10.0] Ã¢â‚¬â€œ 2026-06-13 Ã¢â‚¬â€œ PWA-UnterstÃƒÂ¼tzung fÃƒÂ¼r DeineZeit

### Neu
- Progressive Web App (PWA) ermÃƒÂ¶glicht die Nutzung von DeineZeit als installierbare App

---

## [1.8.5] Ã¢â‚¬â€œ 2026-06-12 Ã¢â‚¬â€œ AnhÃƒÂ¤nge und Mobile-Optimierung

### Neu
- Schnellzugriff auf AnhÃƒÂ¤nge hinzugefÃƒÂ¼gt
- Mobiles Layout fÃƒÂ¼r Projektzeit verbessert

---

## [1.8.2] Ã¢â‚¬â€œ 2026-06-11 Ã¢â‚¬â€œ Behobene Dateien und Dokumentation

### Aktualisierungen
- AttachmentExplorer.jsx vollstÃƒÂ¤ndig repariert
- CHANGELOG.md vollstÃƒÂ¤ndig repariert

---

## [1.8.2] Ã¢â‚¬â€œ 2026-06-11 Ã¢â‚¬â€œ Changelog-Reparatur

### Aktualisierungen
- Changelog-Datei vollstÃƒÂ¤ndig repariert und wiederhergestellt

---

## [1.8.2] Ã¢â‚¬â€œ 2026-06-11 Ã¢â‚¬â€œ Foto-Upload fÃƒÂ¼r Zeiterfassung

### Neu
- Fotos direkt per Kamera bei Zeiterfassung-AnhÃƒÂ¤ngen aufnehmen

---

## [1.8.0] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ OneDrive-Integration

### Neu
- OneDrive-Integration mit Microsoft Graph API
- UnterstÃƒÂ¼tzung fÃƒÂ¼r persÃƒÂ¶nliche OneDrive-Konten
- UnterstÃƒÂ¼tzung fÃƒÂ¼r SharePoint-Dateien

---


## [1.7.5] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ Cloudspeicher-Integration

### Neu
- Cloudspeicher-Integration: Nextcloud und SeaDrive als Alternative zu MinIO
- WebDAV-Provider (storage_service.py) mit automatischer Ordnererstellung via MKCOL
- Speicher-Tab in den Einstellungen (Provider-Auswahl, WebDAV-Felder, Verbindungstest)
- Backend-Endpunkte: POST /settings/storage/test + POST /settings/storage/apply
- TTL-Cache (30 s) fÃƒÂ¼r Storage-Provider mit invalidate_provider_cache()
- extract-msg==0.55.0 fÃƒÂ¼r MSG-Outlook-Datei-Vorschau

---

## [1.7.6] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ WebDAV-Upload Fehlerbehebung

### Aktualisierungen
- WebDAV-Upload funktioniert wieder korrekt nach Datenbankverbindungs-Fix

---

## [1.7.6] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ Upload-Fortschritt Optimierung

### Aktualisierungen
- Upload-Fortschritt wird nun korrekt aus ProgressEvent berechnet (Fehler in bestimmten Browsern behoben)

---

## [1.7.6] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ Speicher-Backend Optimierung

### Aktualisierungen
- Storage-Backend speichert Providernamen direkt (Nextcloud/Seadrive/Minio)

---

## [1.7.6] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ WebDAV-SpeicherunterstÃƒÂ¼tzung hinzugefÃƒÂ¼gt

### Aktualisierungen
- WebDAV-Felder in den Einstellungen integriert

---

## [1.7.6] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ WebDAV-Integration stabilisiert

### Aktualisierungen
- requests-Bibliothek in WebDAV-Provider integriert

---

## [1.8.0] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ Cloudspeicher-Integration und StabilitÃƒÂ¤t

### Neu
- Cloudspeicher-Integration fÃƒÂ¼r Nextcloud, SeaDrive und WebDAV
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

## [1.7.4] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ StabilitÃƒÂ¤t und Wiederherstellung

### Aktualisierungen
- API und Datacenter-Seite wiederhergestellt

---

## [1.7.4] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ Datacenter-Seite neu aufgebaut

### Aktualisierungen
- DatacenterPage vollstÃƒÂ¤ndig rekonstruiert mit verbesserter StabilitÃƒÂ¤t
- EML/MSG-Datei-Vorschau hinzugefÃƒÂ¼gt

---

## [1.7.4] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ MSG-Vorschau und EML-Optimierung

### Neu
- MSG-Vorschau im Datacenter hinzugefÃƒÂ¼gt

### Aktualisierungen
- EML-Verarbeitung bei application/octet-stream-Dateien korrigiert

---

## [1.7.4] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ E-Mail-Vorschau verbessert

### Aktualisierungen
- E-Mail-Vorschau funktioniert nun auch bei application/octet-stream Dateitypen.

---

## [1.7.4] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ UTF-8 Encoding Verbesserungen

### Aktualisierungen
- UTF-8 Encoding in bump-version.ps1 korrigiert
- Update-Prozess in system.py optimiert

---

## [1.7.4] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ Dokumentation und Datacenter-Updates

---

## [1.7.4] Ã¢â‚¬â€œ 2026-06-08 Ã¢â‚¬â€œ Datacenter-Vorschau optimiert

### Neu
- Datacenter: EML-Vorschau direkt im Browser (E-Mail-Dateien)

### Aktualisierungen
- Datacenter: Vorschau-Route repariert (GIF und andere Formate wurden nicht geladen)

---

## [1.7.2] - 2026-06-07 - VersionsprÃƒÂ¼fung robuster + nginx Healthcheck

### Aktualisierungen
- VersionsprÃƒÂ¼fung: GitHub-Fallback via git wenn raw.githubusercontent.com nicht erreichbar
- SettingsPage: zeigt Warnung wenn GitHub-PrÃƒÂ¼fung fehlschlÃƒÂ¤gt
- nginx Healthcheck: wartet auf Backend-Bereitschaft vor Start
- nginx IP-AuflÃƒÂ¶sung: Container-IPs dynamisch alle 10s neu aufgelÃƒÂ¶st
- docker-compose.yml: certbot_conf Volume und Networks ergÃƒÂ¤nzt

---

## [1.7.1] - 2026-06-07 - Datacenter Freigaben-Verwaltung

### Neu
- Datacenter: Freigaben-Ansicht zeigt alle aktiven Share-Links
- Freigaben verlÃƒÂ¤ngerbar ohne Token-Ãƒâ€žnderung (1/7/30/90 Tage oder unbegrenzt)
- Freigaben einzeln widerrufbar direkt aus der ÃƒÅ“bersicht

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

## [1.7.1] Ã¢â‚¬â€œ 2026-06-07 Ã¢â‚¬â€œ Share-Link Route-Optimierung

### Aktualisierungen
- Share-Link Route wurde vor der generischen Entity-Route verschoben, um Routing-Konflikte zu beheben.

---
hangelog Ã¢â‚¬â€œ DeineZeit

Alle Ãƒâ€žnderungen werden hier dokumentiert.
Format: [Version] Ã¢â‚¬â€œ Datum Ã¢â‚¬â€œ Was hat sich geÃƒÂ¤ndert

---

## [1.6.8] Ã¢â‚¬â€œ 2026-06-07 Ã¢â‚¬â€œ Versionsanzeige-Korrektur

### Aktualisierungen
- Versionsanzeige zeigt korrekt die installierte Version an, auch wenn der GitHub-Cache veraltet ist

---

## [1.6.7] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ StabilitÃƒÂ¤t und Mail-Verwaltung

### Aktualisierungen
- Mail-Icon in Rechnungsstatus bleibt nach Seitenwechsel erhalten
- API und AbhÃƒÂ¤ngigkeiten wiederhergestellt, CC-Feld hinzugefÃƒÂ¼gt

---

## [1.6.6] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ E-Mail-Kommunikation erweitert

### Neu
- E-Mail-Dialog mit Kontaktinfo, EmpfÃƒÂ¤nger-Mail und CC-Feld hinzugefÃƒÂ¼gt

---

## [1.6.5] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ Kontaktname in Belegliste korrigiert

### Aktualisierungen
- Kontaktnamen werden in der Belegliste nun korrekt angezeigt

---

## [1.6.4] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ Kontaktsuche Bugfix

### Aktualisierungen
- ContactSearch zeigt Kontaktnamen nach asynchronem Laden korrekt an

---

## [1.6.3] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ Kontaktanzeige in Belegen

### Aktualisierungen
- Kontakt wird nun in der Belegliste angezeigt
- Kontaktfeld im Formular repariert

---

## [1.6.2] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ DatacenterPicker API-KompatibilitÃƒÂ¤t

### Aktualisierungen
- DatacenterPicker verarbeitet API-Antworten korrekt, wenn AnhÃƒÂ¤nge als leeres Objekt statt Array zurÃƒÂ¼ckgegeben werden

---

## [1.6.1] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ AnhÃƒÂ¤nge-Feature korrigiert

### Aktualisierungen
- InvoicePage: AnhÃƒÂ¤nge-Feature korrekt integriert ohne Duplikate

---

## [1.9.0] Ã¢â‚¬â€œ 2026-06-07 Ã¢â‚¬â€œ E-Mail-Vorlagen System

### Neu
- E-Mail-Vorlagen pro Belegart (Rechnung, Angebot, AB, Gutschrift, Lieferschein)
- Neuer Tab Ã¢â‚¬Å¾E-Mail-Vorlagen" in Einstellungen mit Rich-Text-Editor (TipTap)
- Platzhalter: {nummer}, {kontakt}, {firma}, {betrag}, {datum}, {faellig}, {belegart}
- Versand-Dialog: Betreff und E-Mail-Text vor dem Senden editierbar
- Betreff und Body werden aus der Vorlage vorausgefÃƒÂ¼llt

---

## [1.8.0] Ã¢â‚¬â€œ 2026-06-07 Ã¢â‚¬â€œ E-Mail-Dialog: Kontaktinfo & CC-EmpfÃƒÂ¤nger

### Neu
- E-Mail-Versand-Dialog zeigt Kontaktname und EmpfÃƒÂ¤nger-E-Mail an
- CC-Adresse kann optional eingetragen werden
- Backend: CC-UnterstÃƒÂ¼tzung fÃƒÂ¼r SMTP und Microsoft Graph API

---

## [1.7.0] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ Kontakt in Belegliste & Formular

### Neu
- Belegliste: Spalte "Titel / Kontakt" in zwei getrennte Spalten "Titel" und "Kontakt" aufgeteilt
- Belegliste: Kontaktname wird jetzt korrekt aus Stammdaten geladen und angezeigt
- Beleg-Formular: Kontaktfeld zeigt beim Bearbeiten wieder den gespeicherten Kontakt an

---

## [1.6.0] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ E-Mail-AnhÃƒÂ¤nge & Datacenter-Browser

### Neu
- AnhÃƒÂ¤nge beim E-Mail-Versand hinzufÃƒÂ¼gen
- Datacenter-Browser fÃƒÂ¼r Dateiauswahl nutzen
- Lokale Dateien als E-Mail-AnhÃƒÂ¤nge hochladen

---

## [1.5.0] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ Mail-Icons (grÃƒÂ¼n/orange) nach Versand + Status immer auf gesendet setzen

### Neu
- Mail-Icons (grÃƒÂ¼n/orange) nach Versand + Status immer auf gesendet setzen

---

## [1.4.5] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ E-Mail-Versand und Abrechnung

### Aktualisierungen
- PDF-Kontext korrekt geladen
- Unbilled Time Entries vollstÃƒÂ¤ndig implementiert
- E-Mail-Versand repariert

---

## [1.4.4] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ E-Mail-Fehlerbehandlung verbessert

### Aktualisierungen
- Fehlermeldungen beim E-Mail-Versand werden nun dauerhaft im Dialog angezeigt.

---

## [1.4.3] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ E-Mail-Versand repariert

### Aktualisierungen
- E-Mail-Versand und Rechnungsgenerierung wiederhergestellt

---

## [1.4.2] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ Nginx-StabilitÃƒÂ¤t und Docker-Verbesserungen

### Aktualisierungen
- Healthcheck und dynamische DNS-AuflÃƒÂ¶sung fÃƒÂ¼r Nginx optimiert
- Docker-Compose-Konfiguration vervollstÃƒÂ¤ndigt

---

## [1.4.1] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ nginx Healthcheck-Fix

### Behoben
- nginx wartet beim Start auf Backend-Healthcheck (`/api/health`) bevor es Anfragen weiterleitet
- nginx lÃƒÂ¶st Container-IPs dynamisch alle 10 Sekunden neu auf (Docker DNS-Resolver `127.0.0.11`) Ã¢â‚¬â€ kein manueller Neustart nach Backend-Recreate nÃƒÂ¶tig
- docker-compose.yml: fehlende Named Volumes (`certbot_conf`) und Networks-Sektion ergÃƒÂ¤nzt

---

## [1.4.0] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ E-Mail-Integration und StabilitÃƒÂ¤t

### Neu
- Office 365 E-Mail-Integration via Microsoft Graph API

### Aktualisierungen
- WeiÃƒÅ¸er Bildschirm im Changelog-Panel der Anmeldeseite behoben
- Update-Watchdog und HTTPS Health-Check optimiert
- Belegbuch-Endpoints implementiert (Listenansicht, CSV- und PDF-Export)
- Backup-Watcher mit Administratorrechten ausgefÃƒÂ¼hrt
- Quellcode-Verwaltung fÃƒÂ¼r zuverlÃƒÂ¤ssige Docker-basierte Updates verbessert

---

## [1.3.13] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ Update-Mechanismus Test

### Neu
- Update-Mechanismus End-to-End erfolgreich getestet

---

## [1.3.12] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ WeiÃƒÅ¸er Bildschirm nach Update behoben

### Behoben
- Absturz auf der Anmeldeseite wenn ein Changelog-Eintrag weder "features" noch "updates" enthÃƒÂ¤lt (optional chaining)
- changelog.js v1.3.11: "changes" in "updates" umbenannt damit Eintrag im Updates-Tab erscheint

---

## [1.3.11] Ã¢â‚¬â€œ 2026-06-06 Ã¢â‚¬â€œ Update-Prozess StabilitÃƒÂ¤tsverbesserungen

### Behoben
- Update-Status bleibt nicht mehr dauerhaft auf "updating" wenn kein neuer Commit vorhanden (Watchdog nach 5 Min)
- Health-Check im Update-Script nutzt jetzt HTTPS statt HTTP (verhindert Rollback-Schleife)
- nginx.conf-Verzeichnis-Bug wird beim Update automatisch korrigiert
- update.sh, nginx-Konfiguration und docker-compose.yml in git aufgenommen (gehen nicht mehr verloren)

---

## [1.3.10] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Lokale Instanzerkennung und StabilitÃƒÂ¤tsverbesserungen

### Neu
- Lokale Instanzerkennung implementiert

### Aktualisierungen
- Update-Tab zeigt git pull Anleitung statt Button
- Changelog-Konflikte gelÃƒÂ¶st
- Changelog mit fehlenden Versionen 1.2.1Ã¢â‚¬â€œ1.3.8 synchronisiert

---

## [1.3.9] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Lokale Instanz erkennung

### Aktualisierungen
- Lokale Entwicklungsinstanz wird automatisch erkannt Ã¢â‚¬â€ Update-Button zeigt stattdessen Anleitung fÃƒÂ¼r git pull
- Backend blockiert Update-Start in lokalem Modus mit klarer Fehlermeldung

---

## [1.3.8] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Frontend-Integration

### Aktualisierungen
- Gesamtes Frontend in Versionskontrolle integriert

---

## [1.3.7] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Backend-Infrastruktur aktualisiert

### Aktualisierungen
- Backend-App-Verzeichnis in Versionskontrolle integriert

---

## [1.3.6] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ KonfigurationsstabilitÃƒÂ¤t verbessert

### Aktualisierungen
- ConfigParser-Interpolation in alembic.ini entfernt

---

## [1.3.5] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Datenbankmigrationen hinzugefÃƒÂ¼gt

### Aktualisierungen
- Alembic-Migrationen zur Versionskontrolle hinzugefÃƒÂ¼gt

---

## [1.3.4] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Backend-Infrastruktur erweitert

### Aktualisierungen
- Backend-Grunddateien fÃƒÂ¼r Docker-Containerisierung hinzugefÃƒÂ¼gt

---

## [1.3.3] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Docker-Compose Integration

### Aktualisierungen
- Docker-Compose Dateien zum Repository hinzugefÃƒÂ¼gt

---

## [1.3.2] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Versions-Anzeige korrigiert

### Aktualisierungen
- Versions-Anzeige liest nun aus CHANGELOG.md statt aus package.json oder config.py

---

## [1.3.1] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Rechnungs-Widget Darstellung optimiert

### Aktualisierungen
- Rechnungs-Widget wird nun auch bei bestehender Dashboard-Konfiguration korrekt angezeigt.

---

## [1.3.0] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Dashboard und Einstellungen ÃƒÂ¼berarbeitet

### Neu
- Rechnungs-Widget im Dashboard hinzugefÃƒÂ¼gt
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

## [1.2.1] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ Dashboard: Rechnungs-Widget

### Neu
- Dashboard-Widget Ã¢â‚¬Å¾Rechnungen": zeigt offene, ÃƒÂ¼berfÃƒÂ¤llige und diesen Monat bezahlte Rechnungen mit Anzahl und Brutto-Summe
- Widget ist standardmÃƒÂ¤ÃƒÅ¸ig im Dashboard enthalten, verschiebbar und in der GrÃƒÂ¶ÃƒÅ¸e anpassbar

---

## [1.2.0] Ã¢â‚¬â€œ 2026-06-05 Ã¢â‚¬â€œ AuftragsbestÃƒÂ¤tigung & Rechnungsmodul-Erweiterungen

### Neu
- AuftragsbestÃƒÂ¤tigung (AB) als neuer Dokumenttyp mit eigenem Nummernkreis (AB-2026-001, Ã¢â‚¬Â¦)
- E-Mail-Versand direkt aus dem Rechnungsmodul Ã¢â‚¬â€ einzeln oder als Bulk-Versand fÃƒÂ¼r mehrere Belege
- Statusworkflow mit kontextabhÃƒÂ¤ngigem AktionsmenÃƒÂ¼: Entwurf Ã¢â€ â€™ Offen Ã¢â€ â€™ Bezahlt, Angenommen / Abgelehnt, Storniert
- Angebote kÃƒÂ¶nnen nach Annahme direkt in eine AuftragsbestÃƒÂ¤tigung oder Rechnung umgewandelt werden

### Aktualisierungen
- Parameter-Tab in den Einstellungen: PrÃƒÂ¤fixe und Nummernformate pro Dokumenttyp frei konfigurierbar
- Dokumenttyp-Bezeichnungen kÃƒÂ¶nnen umbenannt werden

---

## [1.1.0] Ã¢â‚¬â€œ 2026-06-04 Ã¢â‚¬â€œ Buchhaltungsmodul

### Neu
- Kontenplan nach EKR (Einheitskontenrahmen) vorbefÃƒÂ¼llt und durchsuchbar
- BMD-Export fÃƒÂ¼r die steuerliche ÃƒÅ“bergabe an den Steuerberater
- Debitor- und Kreditornummern direkt bei Kontakten hinterlegbar
- ErlÃƒÂ¶skonto pro Artikel festlegbar Ã¢â‚¬â€ wird automatisch auf Rechnungspositionen ÃƒÂ¼bernommen
- Konto pro Rechnungsposition individuell ÃƒÂ¼berschreibbar
- Kontakte: neuer Finanz-Tab mit IBAN, BIC und Bankname (Migration 0012/0013)

---

## [1.0.0] Ã¢â‚¬â€œ 2026-06-03 Ã¢â‚¬â€œ Rechnungsmodul

### Neu
- Rechnungen, Angebote, Gutschriften und Lieferscheine erstellen
- Automatische Nummerierung pro Dokumenttyp (RE-2026-001, AN-2026-001, Ã¢â‚¬Â¦)
- Stornierung mit automatischer Gutschrift oder nur StatusÃƒÂ¤nderung
- Angebote kÃƒÂ¶nnen direkt in Rechnungen umgewandelt werden
- ZeiteintrÃƒÂ¤ge aus der Zeiterfassung direkt auf Rechnung ÃƒÂ¼bernehmen
- Positionen aus Artikel-Stammdaten oder als Freitext
- MwSt.: pro Position wÃƒÂ¤hlbar, ein Satz, oder Kleinunternehmerregelung
- PDF-Export mit 5 wÃƒÂ¤hlbaren Vorlagen (Klassisch, Modern, Kompakt, Elegant, Farbenfroh)
- Rechnungsbuch filterbar nach Monat/Quartal/Jahr und/oder Kunde Ã¢â‚¬â€ als PDF oder CSV
- Zahlungsstatus: offen, bezahlt, ÃƒÂ¼berfÃƒÂ¤llig, storniert
- Wiederkehrende Rechnungsvorlagen (wÃƒÂ¶chentlich, monatlich, quartalsweise, jÃƒÂ¤hrlich)
- Bankverbindung aus den App-Einstellungen automatisch auf jedem Dokument

---

## [0.9.5] Ã¢â‚¬â€œ 2026-06-03 Ã¢â‚¬â€œ Dashboard konfigurierbar

### Neu
- Dashboard-Bausteine per Drag & Drop frei anordnen
- Breite der Bausteine stufenweise anpassen (Ã‚Â¼ / Ã‚Â½ / Vollbreite)
- Layout wird im Browser gespeichert und beim nÃƒÂ¤chsten Besuch wiederhergestellt
- Neues Zeiterfassung-Widget auf dem Dashboard mit Heute/Woche/Monat-ÃƒÅ“bersicht

---

## [0.9.4] Ã¢â‚¬â€œ 2026-06-03 Ã¢â‚¬â€œ Update-Prozess robuster

### Aktualisierungen
- Backend fÃƒÂ¼hrt Alembic-Migrationen jetzt automatisch beim Start aus Ã¢â‚¬â€ zukÃƒÂ¼nftige Updates brauchen kein manuelles `alembic upgrade head` mehr
- Migrations-Fehler beim Start verhindern nun das Hochkommen des Backends Ã¢â€ â€™ Health-Check schlÃƒÂ¤gt fehl Ã¢â€ â€™ automatischer Rollback greift korrekt
- Rollback im Update-Skript stellt jetzt auch die gesicherten Docker-Images wieder her, nicht nur den Git-Commit

---

## [0.9.3] Ã¢â‚¬â€œ 2026-06-02 Ã¢â‚¬â€œ Stammdaten vereinheitlicht

### Aktualisierungen
- Stammdaten-Typen vereinheitlicht: Kunden und Lieferanten zusammengefÃƒÂ¼hrt zu Ã¢â‚¬Å¾Kontakte" mit Typ-Feld (Kunde / Lieferant / Interessent)
- Neuer Stammdaten-Typ Ã¢â‚¬Å¾Artikel" fÃƒÂ¼r Produkte und Dienstleistungen (Bezeichnung, Artikelnummer, Preis, Beschreibung)
- Bestehende Kunden- und Lieferanten-DatensÃƒÂ¤tze werden bei Migration automatisch nach Kontakte ÃƒÂ¼bernommen
- Alembic-Migration 0010 stellt einheitlichen Stand bei Neu- und Bestandsinstallationen sicher

---

## [0.1.0] Ã¢â‚¬â€œ 2026-05-21 Ã¢â‚¬â€œ Grundfundament

### Neu
- Projektstruktur mit Backend (Python/FastAPI), Frontend (React) und Datenbank (PostgreSQL)
- Docker Compose Setup fÃƒÂ¼r einfaches Deployment
- Benutzerverwaltung mit Rollen (Admin / Mitarbeiter)
- Sicheres Login-System:
  - Passwort-Login mit verschlÃƒÂ¼sselter Speicherung
  - Zwei-Faktor-Authentifizierung (TOTP / Google Authenticator)
  - Face ID / Fingerabdruck Login via WebAuthn/Passkeys
- JWT-Token-basierte Authentifizierung mit automatischer Erneuerung
- Mehrsprachigkeit: Deutsch und Englisch (sprachabhÃƒÂ¤ngig pro Benutzer)
- Responsives Design (Mobile-First fÃƒÂ¼r Handy, Tablet und Desktop)
- Datenbank-Migrationen via Alembic (sichere Schema-Updates)
- nginx Reverse Proxy mit HTTPS / Let's Encrypt UnterstÃƒÂ¼tzung
- Sicherheits-Header (HSTS, XSS-Schutz, Frame-Schutz)

### Technische Details
- Backend: FastAPI 0.111, Python 3.12
- Frontend: React 18, Tailwind CSS, i18next
- Datenbank: PostgreSQL 16 mit Alembic-Migrationen
- Deployment: Docker Compose, nginx, Certbot (Let's Encrypt)

---

---

## [0.2.0] Ã¢â‚¬â€œ 2026-05-21 Ã¢â‚¬â€œ Dynamische Stammdaten-Verwaltung

### Neu
- **Stammdaten-Typen**: Kunden, Lieferanten und Projekte vorinstalliert
- **Beliebige neue Typen**: Jederzeit weitere anlegen (z.B. Mitarbeiter, Fahrzeuge, VertrÃƒÂ¤geÃ¢â‚¬Â¦)
- **Dynamischer Formular-Builder**: Felder direkt in der OberflÃƒÂ¤che hinzufÃƒÂ¼gen, bearbeiten und entfernen Ã¢â‚¬â€ ohne Programmieraufwand
- **9 Feldtypen**: Text, mehrzeiliger Text, Zahl, Datum, E-Mail, Telefon, Auswahlliste, Ja/Nein, Webseite
- **Pflichtfelder** und **Listenansicht** pro Feld konfigurierbar
- **Datensatz-Verwaltung**: Anlegen, bearbeiten und lÃƒÂ¶schen mit automatisch generiertem Formular
- **Suche**: Volltextsuche ÃƒÂ¼ber alle Felder eines Stammdaten-Typs
- **Paginierung**: GroÃƒÅ¸e Datenmengen werden seitenweise angezeigt
- **Dashboard**: SchnellÃƒÂ¼bersicht aller Stammdaten-Typen mit Eintrags-ZÃƒÂ¤hler
- **Datenbank**: JSONB-basierter Speicher mit GIN-Index fÃƒÂ¼r schnelle Suche

### Technische Details
- Neue Datenbankmodelle: `entity_types`, `field_definitions`, `entity_records`
- Migration 0002 mit vordefinierten Standard-Feldern fÃƒÂ¼r Kunden/Lieferanten/Projekte
- Neue API-Endpoints: `/api/masterdata/types/*` und `/api/masterdata/types/{slug}/records/*`
- Neue Komponenten: `FieldBuilder`, `DynamicForm`, `MasterDataOverview`, `MasterDataDetail`

---

---

## [0.3.0] Ã¢â‚¬â€œ 2026-05-21 Ã¢â‚¬â€œ Grid-Layout, Import/Export & Benutzerverwaltung

### Neu
- **Snap-to-Grid Drag & Drop Layout-Builder**: Felder per Maus oder Touch-Geste frei verschieben Ã¢â‚¬â€ ein unsichtbares 12-Spalten-Raster sorgt dafÃƒÂ¼r, dass alles sauber einrastet
- **Feldbreite frei wÃƒÂ¤hlbar**: 25% / 33% / 50% / 75% / 100% Ã¢â‚¬â€ direkt per Klick am Feld einstellbar; mehrere Felder kÃƒÂ¶nnen nebeneinander in einer Zeile angezeigt werden
- **Formular respektiert Layout**: Die Erfassungsmaske zeigt Felder exakt im definierten Raster-Layout Ã¢â‚¬â€ auf Desktop und Tablet; auf MobilgerÃƒÂ¤ten werden alle Felder automatisch auf volle Breite gestreckt
- **CSV Export**: Alle DatensÃƒÂ¤tze eines Stammdaten-Typs mit einem Klick als CSV exportieren (Excel-kompatibel mit BOM und Semikolon-Trennung)
- **CSV Import**: CSV-Datei hochladen, Spalten per Dropdown den Feldern zuordnen, Vorschau prÃƒÂ¼fen, dann importieren
- **Profilseite**: Jeder Benutzer kann Name, Sprache und Passwort selbst ÃƒÂ¤ndern sowie 2FA und Passkeys verwalten
- **Benutzerverwaltung**: Admin-Seite zum Anlegen neuer Benutzer mit Rolle und Sprache, Deaktivierung bestehender Benutzer

### Technische Details
- Neue Spalte `col_span` in `field_definitions` (Migration 0003)
- Neue Backend-Endpoints: `/fields-layout` (Bulk-Update), `/records/export/csv`, `/records/import/csv`
- Neue npm-Pakete: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`, `papaparse`
- Neue Komponenten: `GridFieldBuilder`, `CsvImportExport`, `ProfilePage`, `UserManagementPage`

---

---

## [0.4.0] Ã¢â‚¬â€œ 2026-05-22 Ã¢â‚¬â€œ Sicherheit & Design-Upgrade

### Neu
- **Farbschema zur Laufzeit ÃƒÂ¤nderbar**: PrimÃƒÂ¤rfarbe und Akzentfarbe ÃƒÂ¼ber die Einstellungen wÃƒÂ¤hlbar Ã¢â‚¬â€ kein Neustart nÃƒÂ¶tig
- **Login-Seite neu gestaltet**: Modernes Design mit Markenbild
- **Sidebar neu gestaltet**: Schlankere Navigation, bessere Lesbarkeit
- **Dashboard neu gestaltet**: ÃƒÅ“bersichtlichere Kacheldarstellung
- **Admin-Benutzerbearbeitung**: Admins kÃƒÂ¶nnen Benutzerdaten direkt bearbeiten
- **Passwort vergessen Seite**: Eigene Seite mit Kontaktinformationen fÃƒÂ¼r Passwort-Reset
- **Kontakte zusammengefÃƒÂ¼hrt**: Kunden und Lieferanten wurden zu einem gemeinsamen Ã¢â‚¬Å¾Kontakte"-Typ zusammengefÃƒÂ¼hrt, Typ-Filter (Kunden / Lieferanten / Interessenten) in der Listenansicht
- **Rate Limiting**: Login-Endpunkt ist gegen Brute-Force-Angriffe geschÃƒÂ¼tzt
- **Sicherheits-Header**: HSTS, XSS-Schutz, Frame-Schutz, Content-Type-Sniffing-Schutz
- **API-Docs gesperrt**: Swagger-UI nur noch im Debug-Modus erreichbar
- **Upload-Limit**: Maximale DateigrÃƒÂ¶ÃƒÅ¸e fÃƒÂ¼r Uploads konfigurierbar

### Technische Details
- Migration 0004: Kontakte-Konsolidierung (Kunden + Lieferanten Ã¢â€ â€™ Kontakte mit `typ`-Feld)
- Neue npm-Pakete: `slowapi` (Rate Limiting)
- Tailwind CSS auf CSS-Variablen umgestellt (`--color-primary-*`) fÃƒÂ¼r Laufzeit-Farbwechsel

---

## [0.5.0] Ã¢â‚¬â€œ 2026-05-22 Ã¢â‚¬â€œ Zeiterfassung

### Neu
- **Zeiterfassung**: Timer starten/stoppen mit Projekt- und Aufgabenzuordnung
- **Manuelle EintrÃƒÂ¤ge**: Zeiten nachtrÃƒÂ¤glich eintragen und bearbeiten
- **Eigene Felder fÃƒÂ¼r ZeiteintrÃƒÂ¤ge**: Admin kann beliebige Zusatzfelder definieren (z.B. Ort, Fahrtzeit, Notiz)
- **Projektzeitbericht als PDF**: Gefilterte Auswertung nach Zeitraum, Mitarbeiter, Projekt als druckfertiges PDF
- **Bericht-Optionen**: Zeitrunden auf 15/30 Minuten, Filterung nach Aufgabe, verschiedene Zeitraum-Voreinstellungen

### Technische Details
- 
