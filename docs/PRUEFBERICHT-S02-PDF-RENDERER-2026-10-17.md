# Prüfbericht – S02: PDF-Erzeugung mit nicht vertrauenswürdigem HTML (Version 2.1.3)

**Datum:** 17.10.2026 · **Anlass:** Sicherheitsbefund S02 „Untrusted HTML im PDF-Renderer ohne
Ressourcenfilter" (Bestandsaufnahme zu Commit `1a5787e49216c953650980eed285aba80ae22667`,
zuletzt nachgeprüft auf `6f15aaa045ace2e35863c43b9ad3c2cf975a966a`, Version 2.1.2) ·
**Branch:** `fix/s02-pdf-renderer` (Basis `main` @ `6f15aaa`) · **Migration:** keine

---

## 1. Zusammenfassung

1. **Befund bestätigt und erweitert** — mit dem echten Renderer und einer eigens angelegten
   Markerdatei: Am unveränderten Stand (WeasyPrint 69.0, `base_url="/"`) übernimmt
   `<link rel="attachment" href="/pfad/zur/markerdatei">` aus einem Feldinhalt die **Datei als
   PDF-Anhang**. WeasyPrints Standardabruf erlaubt außerdem `http(s)`, `ftp` und `file` samt
   Weiterleitungen. Das Backend läuft im Container als root und hat `/etc/letsencrypt` sowie
   seine Umgebungsvariablen (Datenbank-, MinIO-, Schlüsselwerte) im Zugriff. Ein tatsächlicher
   Abfluss solcher Dateien in Produktion wurde **nicht** nachgewiesen (nicht versucht); die
   Gegenprobe steht als Test im Repo (`test_relativer_und_file_anhang_wird_nicht_eingebettet`).
2. **Ein Weg für alle PDFs:** `services/pdf_render.render_pdf()` — Belege (5 Vorlagen),
   Mahnungen, Projektzeitbericht, Belegbuch, Umsatzsteuer-Aufstellung, Aufgaben-Laufzettel,
   DSGVO-Bescheinigung. Ein Wächtertest verbietet direkte WeasyPrint-Aufrufe im Anwendungscode.
3. **Ressourcen standardmäßig gesperrt:** Aufgelöst werden nur `data:`-Bilder (PNG, JPEG, GIF,
   WebP, SVG ohne DTD) mit Inhalts- und Größenprüfung. Kein `http(s)`, `ftp`, `file`, kein
   relativer Pfad, keine Weiterleitung — der Filter baut auf keinem urllib-Opener auf, es gibt
   also keinen Standardabruf, auf den ein Fehler zurückfallen könnte.
4. **Abgeschotteter Renderprozess:** eigener, kurzlebiger Prozess mit leerer Umgebung (keine
   Zugangsdaten), als `nobody` (65534), wenn das Backend als root läuft, mit Speicher-, CPU-,
   Datei- und Zeitgrenze; bei Überschreitung wird die ganze Prozessgruppe per SIGKILL beendet.
   Darin zusätzlich ein Audit-Hook: kein Netz, keine Unterprozesse, Lesen nur aus Bibliotheks-
   und Schriftverzeichnissen. Höchstens 2 gleichzeitige Renderprozesse je Arbeitsprozess,
   sonst HTTP 503.
5. **Feldinhalte sicher:** Gewöhnlicher Text wird maskiert, ausdrücklich erlaubter Rich Text
   parserbasiert (nh3/ammonia) auf eine enge Positivliste reduziert. Farben nur als Hex-Wert,
   das Admin-CSS kann den `<style>`-Block nicht verlassen und nichts importieren.
6. **Bilder:** Logos nur aus dem static-Verzeichnis (vorher genügte `/api/static/../…`),
   Positionsbilder nur aus `belege/positionsbilder/` (vorher jede vom Client gelieferte
   Speicherreferenz, also auch Datacenter-Dateien), Inhalt muss zum Bildtyp passen, Größen-
   und Pixelgrenzen beim Hochladen und beim Einbetten.
7. **Vorschauen:** Server-Antwort mit eigener CSP (`default-src 'none'; img-src data:; …;
   sandbox`) plus `<meta>`-CSP im Dokument; das Frontend öffnet die Vorschau in einem
   `<iframe sandbox="">` statt als Blob im App-Ursprung. Ein XSS oder CSP-Bypass wurde
   **nicht** nachgewiesen; die Absicherung ist vorbeugend.
8. **Keine sichtbaren Änderungen:** Alle 5 Belegvorlagen, Projektzeitbericht, Aufgabe und
   DSGVO-Bescheinigung sind mit Beispieldaten (Logo, Positionsbild, Umlaute, Seitenumbruch,
   Fettdruck) **pixelgleich** zum Stand vorher (Abschnitt 7.5).

## 2. Ausgangslage

| Stelle (Stand `6f15aaa`) | Problem |
|---|---|
| `services/invoice_pdf.py` | Beschreibung, Detail, Einleitung, Schlusstext, Titel, Referenz, Einheit, Adressen, Bankdaten, Fußzeile ungefiltert in f-Strings; `primary_color` und `custom_template_css` ungefiltert in `<style>`; `WeasyprintHTML(string=html, base_url="/")` mit Standardabruf |
| `services/dunning_pdf.py` | Mahnstufentext, Bezeichnung, Belegnummern ungefiltert; `base_url="/"` |
| `api/berichtsvorlage.py`, `api/reports.py` | Filterwerte aus der URL, Projekt-/Kunden-/Benutzernamen, Notizen ungefiltert; Benutzername in CSS-Zeichenkette; HTML-Vorschau ohne eigene CSP |
| `api/invoice_buchhaltung.py` | Belegnummer, Titel, Firmenname ungefiltert (Belegbuch, Umsatzsteuer) |
| `services/gdpr_pdf.py` | Personendaten, Anmerkung, Firmenzeilen ungefiltert |
| `services/aufgaben_pdf.py` | Texte bereits maskiert; Status-/Prioritätsfarben ungefiltert in `style` |
| `_logo_b64` / `_logo_base64` | Pfad per `replace("/api/static", …)` gebildet, keine Prüfung → beliebige lesbare Datei als „Logo" in Vorschau und PDF |
| `position_image.als_datenurl` | `image_key` aus den Positionsdaten des Clients, ohne Prüfung geladen; MIME-Typ vom Speicher übernommen |
| Frontend | Beleg- und Berichtsvorschau als Blob-URL im App-Ursprung geöffnet (HTTP-Header gelten dort nicht) |

Erreichbare Eingabepfade: Beleg anlegen/ändern (Positionen, Texte), Artikel → Position,
Stammdaten (Kontakte inkl. eigener Firma), Stammdaten-Import, Verkaufseinstellungen
(Hinweistexte, CSS, Farben, Mahnstufen), Zeiterfassung (Notiz, Projekt, Kunde) samt
Zeiten-Import, Berichtsfilter in der URL, Aufgaben, DSGVO-Löschung. Alle mit Anmeldung;
die Einstellungen nur für Berechtigte.

## 3. Umfang

| Datei | Änderung |
|---|---|
| `backend/app/core/dokument_html.py` **neu** | `text`, `rich_text`, `nur_text`, `farbe`, `css_block`, `css_zeichenkette`, `static_bild_datenurl`, `bild_datenurl`, `vorschau_antwort` (CSP-Header + meta-CSP) |
| `backend/app/services/pdf_render.py` **neu** | Prozessstart, Grenzen, Parallelität, Abbruch, Aufräumen, Fehlerklassen |
| `backend/app/services/pdf_render_worker.py` **neu** | Ressourcenfilter, Audit-Hook, rlimits, Rendern, E-Rechnung-Finisher |
| `services/invoice_pdf.py`, `dunning_pdf.py`, `aufgaben_pdf.py`, `gdpr_pdf.py`, `api/berichtsvorlage.py`, `api/reports.py`, `api/invoice_buchhaltung.py` | alle Feldwerte über `text`/`rich_text`/`farbe`/`css_block`; PDF über `render_pdf` |
| `services/position_image.py`, `schemas/invoice.py`, `api/invoice_einstellungen.py` | Bildreferenz-Muster, Speicher-Positivliste, Pixel-/Höhen-/Größengrenzen; Prüfung beim Speichern (422), beim Einbetten und im Bildvorschau-Endpunkt |
| `api/invoice_belege.py`, `api/invoice_einstellungen.py`, `api/reports.py` | HTML-Vorschauen über `vorschau_antwort` |
| `main.py` | zentrale Fehlerbehandlung: Überlastung → 503, Renderfehler → 500 |
| `services/period_service.py` | Übergabepaket (Monatsabschluss): Beleg-PDFs im Threadpool statt im Event-Loop — Folge des Prozessstarts je PDF (Review-Befund 2) |
| `requirements.txt` | `nh3==0.3.7` (neu) |
| `requirements-dev.txt` | `pypdf==6.21.1` (nur Tests: Anhänge und Text aus PDFs lesen) |
| `frontend/src/utils/htmlVorschau.js` **neu** + Test | Vorschau im `iframe sandbox=""` |
| `InvoiceFormPage.jsx`, `BerichtProjektzeitenPage.jsx`, `SettingsPage.jsx` | Vorschauen darüber bzw. `sandbox=""` statt `allow-same-origin` |
| `tests/test_pdf_render.py`, `tests/test_dokument_sicherheit.py` **neu** | 92 Tests (Abschnitt 7) |
| Versionsdateien, `CHANGELOG.md` | 2.1.3 über `scripts/bump_version.py` |

**Bewusst nicht angefasst:** gespeicherte Daten (keine Migration, keine Umschreibung), bereits
archivierte PDFs, Docker-Dateien (Abschnitt 4.4), E-Mail-Texte (kein PDF-Weg), der Upload
von Logos und Datacenter-Dateien, die Mail-Zugangsdaten-Absicherung aus 2.1.2 (unverändert
übernommen).

## 4. Sicherheitsregeln

### 4.1 Text und Rich Text

| Art | Felder | Regel |
|---|---|---|
| Gewöhnlicher Text | Namen, Adressen, UID, E-Mail, Telefon, Webseite, Bankdaten, Firmenbuch, Gericht, Belegnummer, Titel, Referenz, Einheit, Währung, Mahnbezeichnung, Berichtsfilter, Projekt-/Kunden-/Benutzernamen, Zeitnotizen, DSGVO-Angaben, Umsatzsteuer-Hinweise | vollständig maskiert (`text`) |
| Erlaubter Rich Text | Positionsbeschreibung (alle Positionsarten), Zusatztext, Einleitung, Schlusstext, Kleinunternehmer-/Reverse-Charge-Hinweis, Fußzeilen-Freitext aus dem Firmenkontakt, Mahnstufentext | `rich_text`: nh3 mit Positivliste |
| Admin-CSS | `custom_template_css` | `css_block`: ohne `<`, ohne `@import`; `url()` greift im Renderer nur für `data:`-Bilder, in der Vorschau gar nicht (CSP) |
| Farben | `primary_color`, `brand_color`, Aufgaben-Status-/Prioritätsfarben | nur `#rgb`/`#rrggbb`(/aa), sonst Standardfarbe |
| CSS-Zeichenkette | Benutzername in der Berichtsfußzeile (`content: "…"`) | `css_zeichenkette`: Sonderzeichen als CSS-Hex-Escape |

**Positivliste Rich Text:** `b strong i em u s br p ul ol li span small sub sup`; Attribute nur
`style` an `p`/`li`/`span` und davon nur `text-align: left|center|right|justify`.
Entfernt werden u. a. `script`/`style` samt Inhalt, `img`, `link`, `a`, `svg`, `iframe`,
`object`, `table`, `div`, `font`, Eventhandler, Kommentare und alle URLs.

**Auswirkung auf bestehende Inhalte** (Ausgabe-seitig, gespeicherte Texte bleiben unverändert):
- Formatierungen aus der Positivliste erscheinen wie bisher; doppelte Maskierung entsteht
  nicht (`&amp;` bleibt `&amp;`).
- Entfallen: Links (der Text bleibt), Bilder, Tabellen, `<div>`/`<font>` (Inhalt bleibt),
  Inline-Stile außer der Textausrichtung (z. B. Farbe oder Schriftgröße in einem Positionstext).
- Wie schon bisher im PDF verschwindet in Rich-Text-Feldern ein Text wie `<GmbH>`, weil er als
  Tag gilt. In Feldern für gewöhnlichen Text (z. B. Name) steht er jetzt wörtlich da.
- Die Eingabefelder im Belegformular sind einfache Textfelder; im Normalbetrieb entsteht dort
  kein HTML. Betroffen sind nur Altbestände oder Importe mit eigenem HTML.

### 4.2 Ressourcen

- **Renderer:** nur `data:image/png|jpeg|gif|webp|svg+xml`; Inhalt muss zum Typ passen
  (Dateisignatur bzw. SVG-Anfang), SVG ohne externe Entitäten (`SYSTEM`/`PUBLIC`) — DOCTYPE
  und interne Entitäten wie in Illustrator-Exporten bleiben erlaubt —, höchstens 8 MB je Bild
  und 40 MB je Dokument.
  Alles andere wird abgewiesen; das Dokument entsteht ohne die Ressource (Hinweis im Log).
- **Logo:** nur Dateien innerhalb von `/app/static` (aufgelöster Pfad, also auch kein Symlink
  hinaus), nur Bildendungen, höchstens 2 MB, Inhalt passend.
- **Positionsbild:** Schlüssel nur `belege/positionsbilder/<Name>.<jpg|jpeg|png|gif|webp>`,
  Speicher nur `minio|onedrive|webdav|nextcloud|seadrive` oder leer; Typ aus der Endung, am
  Inhalt geprüft; höchstens 4 MB und 40 Megapixel. Beim Hochladen: Pixelzahl wird **vor** dem
  Dekodieren geprüft (max. 40 MP), gespeicherte Höhe höchstens 3000 px.
- **Berechtigung:** Ein Positionsbild ist an den Positionsbild-Ordner gebunden, nicht an einen
  einzelnen Beleg. Wer Belege bearbeiten darf, kann also ein Positionsbild eines anderen
  Belegs referenzieren — das entspricht dem bestehenden Rechtemodell (Belege sind im Verkauf
  für alle Berechtigten sichtbar). Fremde Speicherbereiche (Datacenter, DSGVO, Anhänge) sind
  ausgeschlossen.

### 4.3 Isolation und Grenzen

| Grenze | Standard | Umgebungsvariable |
|---|---|---|
| Wanduhr je Dokument | 60 s | `PDF_RENDER_ZEITLIMIT` |
| CPU je Dokument | 60 s | `PDF_RENDER_CPU_SEKUNDEN` |
| Adressraum | 1024 MB | `PDF_RENDER_MAX_SPEICHER_MB` |
| Eingabe (HTML + Bilder) | 40 MB | `PDF_RENDER_MAX_EINGABE_MB` |
| Ausgabe (PDF) | 50 MB | `PDF_RENDER_MAX_AUSGABE_MB` |
| Einzelbild | 8 MB | `PDF_RENDER_MAX_RESSOURCE_MB` |
| gleichzeitig je Arbeitsprozess | 2 | `PDF_RENDER_PARALLEL` |
| Wartezeit auf freien Platz | 30 s | `PDF_RENDER_WARTEZEIT` (danach 503) |
| Benutzer des Renderprozesses | 65534 | `PDF_RENDER_UID` (nur wenn das Backend als root läuft) |

Der Renderprozess wird mit `python -I` gestartet (keine `PYTHON*`-Variablen, kein
Benutzerverzeichnis), in einem eigenen, leeren Arbeitsverzeichnis (0700), mit eigener
Prozessgruppe. Ohne `preexec_fn` (unter uvicorn nicht thread-sicher): Benutzerwechsel macht
`Popen` selbst, die rlimits setzt der Renderprozess als Allererstes, und er bricht ab, falls er
doch als root liefe. Zeitüberschreitung → `killpg(SIGKILL)` und Abräumen; das Arbeitsverzeichnis
wird in jedem Fall gelöscht.

### 4.4 Warum keine Docker-Änderung

Ein eigener Render-Container wäre die stärkste Trennung, bräuchte aber einen zusätzlichen
Dienst, eine interne Schnittstelle und Änderungen an Deploy und Backup. Der gewählte
Prozess-Ansatz erreicht die geforderten Eigenschaften im bestehenden Image, ohne Änderung am
Dockerfile: Der Benutzerwechsel arbeitet mit der numerischen ID (kein Eintrag in `/etc/passwd`
nötig), Ausgaben gehen über Pipes, das Arbeitsverzeichnis legt der Backend-Prozess an.
**Annahme, hier nicht im Image geprüft** (kein Docker in der Sandbox): Python-Pakete und
`/app` sind im Image für alle lesbar (pip und `COPY` setzen 644/755). Trifft das nicht zu,
schlägt jede PDF-Erzeugung mit einer klaren Meldung fehl, statt unsicher weiterzulaufen —
deshalb steht die Prüfung auf der Abnahme-Checkliste.
**Verbleibende Grenzen** (Abschnitt 9): gleicher Kernel und gleiches Netz-Namespace wie das
Backend (Netz ist im Prozess per Audit-Hook gesperrt, nicht per Namespace); Dateien, die für
alle lesbar sind, könnte ein Fehler in einer C-Bibliothek (Pango/Cairo/HarfBuzz) lesen — der
Audit-Hook sieht nur Python-Zugriffe.

## 5. Bestehende Daten

Keine Migration, keine Umschreibung gespeicherter Inhalte. Die Bereinigung geschieht bei
jeder Ausgabe. Bereits archivierte PDFs im Datacenter bleiben unverändert; neue
Archivkopien entstehen wie bisher mit Zeitstempel im Dateinamen und überschreiben nichts.
Ein neu erzeugtes PDF eines Altbelegs kann sich nur dort vom Archiv unterscheiden, wo der
Altbestand nicht erlaubtes HTML enthielt (Abschnitt 4.1).

## 6. Administrative Schritte nach dem Einspielen

Keine Pflichtschritte. Optional:
- Bei sehr großen Belegen (viele Positionsbilder) oder großen Periodenexporten können die
  Grenzen über die Umgebungsvariablen aus 4.3 angehoben werden (in `docker-compose.yml` beim
  Dienst `backend` ergänzen).
- Nach dem Deploy im Serverlog auf Zeilen `PDF-Renderprozess endete mit Code …` bzw.
  `Ressource(n) abgewiesen` achten — sie zeigen Altbestände mit nicht erlaubten Verweisen.

## 7. Prüfungen (tatsächlich ausgeführt)

Umgebung: Cloud-Sandbox, Python 3.12, WeasyPrint 69.0, nh3 0.3.7, PostgreSQL 16, Node 22;
Tests als root (damit der Benutzerwechsel echt geprüft wird).

### 7.1 Befund am Ausgangsstand (Gegenprobe im Test)

`test_relativer_und_file_anhang_wird_nicht_eingebettet` rendert dasselbe HTML einmal über
`render_pdf` und einmal wie früher (`WeasyPrint HTML(string, base_url="/")`):

| Weg | PDF-Anhänge (pypdf) |
|---|---|
| früher (`base_url="/"`, Standardabruf) | `marker.txt` mit Inhalt `S02-MARKER-7f3a` |
| `render_pdf` | keine |

`test_netzwerk_css_und_svg_ressourcen_werden_nicht_abgerufen`: Lokaler Zählserver auf
127.0.0.1; `<link rel=stylesheet>`, `@import`, `@font-face`, `background:url()`, `<img>`
(direkt und mit 302 auf `file://`), `<object>`, `<embed>`, `<iframe>`, Anhang-Link, SVG mit
`<image href>`, `<use href>` und `@import` → **0 Anfragen**. Gegenprobe mit WeasyPrints
Standardabruf: Anfrage kommt an.

### 7.2 Backend-Testreihe

```
$ ruff check --select F,E9,B904 --ignore F841 app/ alembic/env.py
All checks passed!

$ python -m pytest -q                       # vor der Änderung (main @ 6f15aaa)
1054 passed, 33 warnings in 484.83s (0:08:04)

$ python -m pytest -q                       # Endstand Branch
1146 passed, 33 warnings in 581.52s (0:09:41)

$ python -m pytest -q tests/test_pdf_render.py tests/test_dokument_sicherheit.py
92 passed, 32 warnings in 23.92s

$ bandit -r app/ -ll
2 × B310 in services/email_service.py (bestand schon vorher, unverändert)
```

Neu, mit dem echten Renderer (Auswahl):
- Ressourcenfilter: 16 gesperrte URL-Formen (Groß-/Kleinschreibung, `file://localhost`,
  relativ, prozentkodiert, `javascript:`, `data:text/html` …), Typ-/Inhaltsprüfung,
  Größengrenze, externe SVG-Entitäten; Illustrator-SVG mit DOCTYPE wird gerendert;
  Entity-Flut endet ohne Hängen.
- Audit-Hook (eigener Prozess): Markerdatei lesen, `os.open`, `/etc/hostname`,
  `/proc/self/environ`, Schreiben/`truncate`/`mkdir` außerhalb, `listdir` außerhalb, SQLite,
  Socket, Namensauflösung, Unterprozess, `os.system`, Signal an den Elternprozess → gesperrt;
  Bibliotheken lesen/auflisten und Schreiben im Arbeitsverzeichnis → erlaubt.
- Prozessrahmen: keine Zugangsdaten in der Umgebung; als root gestartet läuft der Prozess
  **nicht** als root und kann eine nur für root lesbare Markerdatei nicht lesen.
- Grenzen: Zeitlimit 1 s beendet das echte Rendern eines 30.000-Zeilen-Dokuments nach ~1,2 s,
  danach kein Renderprozess und kein Arbeitsverzeichnis mehr; CPU-Grenze 1 s ebenso;
  64 MB Adressraum → Fehler statt Hängen; Eingabe- und Ausgabegrenze; 6 gleichzeitige
  Aufträge bei Grenze 2 → Höchststand 2; Grenze 1 + Wartezeit 0,3 s → zweiter Auftrag
  `PdfRenderUeberlastet`, API antwortet 503; Fehler beim Anlegen des Arbeitsverzeichnisses
  gibt den Platz zurück.
- Feldinhalte: Positivliste, entfernte Tags/Attribute/Stile, keine doppelte Maskierung,
  Farben, CSS, CSS-Zeichenkette, meta-CSP; Logo-Pfade (Traversal, Symlink, falscher Inhalt).
- Dokumentwege: Vorschau (CSP-Header, meta-CSP, Struktur ohne aktive Elemente), alle fünf
  Vorlagen mit manipulierter Farbe und Admin-CSS, PDF-Download (pypdf: Text ohne sichtbare
  Tags, Umlaute, keine eingeschleusten Anhänge), **E-Mail-Versand und Archivierung** (beide
  über `render_pdf`, Anhang und Archivkopie sind PDFs), Positionsbild über den regulären
  Upload erscheint im PDF, fremde Bildreferenzen → 422/400, Speicherinhalt „HTML statt Bild"
  wird nicht eingebettet, Pixel- und Höhengrenze beim Hochladen, Mahnung (Mahntext Rich Text,
  Bezeichnung Text), Projektzeitbericht (Vorschau + PDF, Filter aus der URL), Belegbuch,
  Umsatzsteuer, Aufgabe (Farben), DSGVO, Vorlagenvorschau.
- Bestehende Tests zur E-Rechnung (`test_verkauf_erechnung.py`: PDF/A-3, `factur-x.xml`,
  `/AF`, XMP) laufen unverändert grün — jetzt durch den Renderprozess.

### 7.3 Frontend

```
$ npm ci && npx vitest run
Test Files  8 passed (8)
     Tests  38 passed (38)          # davon 5 neu: utils/htmlVorschau.test.js
$ npm run build
✓ built in 2.46s
```

### 7.4 Browser-Vorschau (Chromium, Playwright)

Beleg-Vorschau (Vorlage 1) mit eingeschleustem `<img onerror>` und `<script>` in der
Einleitung, eingebettet wie im Frontend (`iframe sandbox=""` + `srcdoc`): Logo und
Positionsbild werden angezeigt, Layout wie bisher, **keine einzige Netzanfrage**, kein
Skript ausgeführt (Titel unverändert), keine Konsolenmeldung.

### 7.5 Visuelle Regression (alt gegen neu)

Dieselben Beispieldaten (Logo, Positionsbild, Überschrift, Text-, Rabatt- und
Zwischensummenzeile, 24 Positionen → Seitenumbruch, Umlaute, Fettdruck in Rich Text,
Skonto, Fußzeile aus dem Firmenkontakt) mit Stand `6f15aaa` und Branch erzeugt, mit
`pdftoppm` bei 110 dpi gerastert und mit ImageMagick ohne Toleranz verglichen:

| Dokument | Seiten | Abweichende Pixel |
|---|---|---|
| Beleg Vorlage 1–5 | je 2 | **0** |
| DSGVO-Bescheinigung | 1 | **0** |
| Aufgaben-Laufzettel | 2 | 44 auf Seite 1 — nur die Uhrzeit „Gedruckt am … 21:52/21:53" |
| Projektzeitbericht | 4 | 45–90 je Seite — nur die Uhrzeit „Erstellt am" in der Fußzeile |

Textvergleich (`pdftotext -layout`, Uhrzeiten ausgeblendet): alle 8 Dokumente gleich.
Selbst angesehen: Vorlage 1 und 5 (Seite 1) sowie die Browser-Vorschau.

### 7.6 Unabhängige Durchsicht

Ein separater Prüfer ohne Beteiligung an der Umsetzung hat Diff und Verhalten geprüft und
eigene Angriffe gegen `render_pdf`, `rich_text`, `ressource_holen`, `css_block` und den
Audit-Hook ausgeführt. Ergebnis: kein Weg für Dateien, Netz oder ungemaskierte Feldwerte;
E-Rechnung unverändert. Seine Befunde und ihre Behandlung:

| # | Befund | Schwere | Behandlung |
|---|---|---|---|
| 1 | Scheitert `mkdtemp`, geht ein Parallelitätsplatz verloren (nach 2 Fehlern dauerhaft 503) | mittel | behoben, Test `test_fehler_beim_anlegen_gibt_den_platz_zurueck` |
| 2 | Übergabepaket rief `generate_pdf` direkt im Event-Loop — jetzt ~0,75 s statt ~0,08 s je Beleg | mittel | behoben (`run_in_threadpool`) |
| 3 | SVG-Logos mit DOCTYPE/Entitäten (Illustrator) wurden still verworfen | niedrig/mittel | behoben: nur externe Entitäten gesperrt; Tests für Illustrator-SVG und Entity-Flut |
| 4 | Audit-Hook ließ `os.truncate`, `os.mkdir`, `listdir`, SQLite u. a. durch | niedrig | behoben: Änderungen nur im Arbeitsverzeichnis, Verzeichnislisten nur in Lesewurzeln, SQLite/Signale gesperrt; Test erweitert |
| 5 | Bildreferenz-Muster ließ einen Zeilenumbruch am Ende zu | niedrig | behoben (`fullmatch`), Testfall ergänzt |
| – | `@import` lässt sich in `css_block` per CSS-Escape schreiben | vermutet, nicht ausnutzbar | bewusst so belassen: `css_block` ist keine Ressourcengrenze — die sind Renderfilter und Vorschau-CSP (beide getestet) |

## 8. Nicht geprüft

- Lauf im Produktions-Image und am Server (Benutzer `nobody`, Leserechte im Image,
  Schriftpfade, Speichergrenze mit echten Großbelegen) — kein Docker in der Sandbox; Teil der
  Abnahme (Abschnitt 10). Die CI baut das Image, rendert darin aber nicht.
- Lokal unter Docker Desktop (`./test.sh`) — die Reihe lief hier gegen eine eigene PostgreSQL.
- Ein tatsächlicher Abfluss von Server-Dateien oder ein XSS/CSP-Bypass in Produktion — nicht
  versucht; die Aussagen in Abschnitt 1 beruhen auf Markerdateien und dem lokalen Renderer.
- Drucken aus der HTML-Vorschau (siehe Risiken).

### Beobachtet, aber nicht Teil dieses PR (eigene Befunde)

- **Positionsbilder fehlen in den Vorlagen 2–5** — schon vor S02: `_positions_html()` baut die
  Bildzeile (`bild_row`), hängt sie aber nicht an. Nur Vorlage 1 zeigt Positionsbilder. Im
  Bildvergleich identisch zum Altstand, also keine Regression.
- **Vertragsanhänge und Eingangsrechnungs-Originale** werden im Frontend als Blob-URL im
  App-Ursprung geöffnet (`InvoiceFormPage.handleContractOpen`, `EingangsrechnungenPage
  .originalOeffnen`). Betrifft hochgeladene Dateien, nicht den PDF-Renderer; sollte beim
  Thema Uploads/Datacenter mitgeprüft werden.

## 9. Risiken und Rückweg

| Risiko | Bewertung | Gegenmaßnahme |
|---|---|---|
| Altbestände verlieren Formatierung außerhalb der Positivliste | gering | Abschnitt 4.1; Positivliste bei Bedarf gezielt erweitern (`RICH_TEXT_TAGS`) |
| ~0,6–0,8 s mehr je PDF (Prozessstart) | gering, spürbar nur bei Massenexporten (Monatsabschluss) | `PDF_RENDER_PARALLEL` anheben |
| Speichergrenze zu knapp für sehr große Belege | gering | `PDF_RENDER_MAX_SPEICHER_MB` anheben; Fehlermeldung statt Absturz |
| Bei mehreren uvicorn-Arbeitsprozessen gilt die Parallelitätsgrenze je Prozess | bekannt | dokumentiert; derzeit 1 Arbeitsprozess |
| Wartende PDF-Anfragen belegen bis zu 30 s einen Threadpool-Platz | gering (nur angemeldete Benutzer) | `PDF_RENDER_WARTEZEIT` senken |
| SVG mit einer gesperrten Unterreferenz erscheint im PDF gar nicht (WeasyPrint verwirft das ganze Bild) | gering | gewollt strenger als vorher |
| C-Bibliotheken umgehen den Audit-Hook | Restrisiko | Prozess als `nobody` ohne Umgebung; vollständige Trennung nur mit eigenem Container |
| Drucken aus der Vorschau druckt nur den sichtbaren Rahmen | gering | Zum Drucken das PDF verwenden (Release-Notes) |

**Rückweg:** Revert des Merge-Commits stellt den Stand 2.1.2 her; keine Datenbankänderung.

## 10. Abnahme-Checkliste

- [ ] CI grün (pytest, Vitest, ruff, Docker-Build)
- [ ] Nach dem Deploy: einen Beleg je Vorlage als PDF öffnen — Logo, Positionsbild, Umlaute
- [ ] E-Rechnung: PDF eines vollständigen Belegs enthält weiterhin `factur-x.xml`
- [ ] Beleg-Vorschau und Projektzeitbericht-Vorschau öffnen sich (neuer Tab, Rahmen)
- [ ] Mahnschreiben, Belegbuch, Umsatzsteuer, Aufgabe drucken, DSGVO-Bescheinigung (Testkontakt)
- [ ] Am Server (optional): `docker compose exec backend python -c "from app.services.pdf_render import render_pdf; print(len(render_pdf('<p>Test Ä</p>')))"` gibt eine Zahl aus (Renderprozess als `nobody` lauffähig)
