# Prüfbericht – Zeiterfassung: Import aus Fremdsystemen (Version 2.1.0)

**Datum:** 18.09.2026 · **Anlass:** Auftrag Oliver vom 18.09.2026 — Import-Schnittstelle für
Zeiterfassungsdaten aus Fremdsystemen, unterschiedliche Dateitypen, PDF über die vorhandene
KI-Schnittstelle mit Feldzuweisung durch den Anwender ·
**Branch (Vorschlag):** `feature/zeiterfassung-import`

> Stand bei Abgabe: Änderungen im Working Tree auf `main`, nichts committet. Keine Migration,
> keine Schema-Änderung, keine neue Python- oder npm-Abhängigkeit.

---

## 1. Zusammenfassung

1. **Neuer Knopf „Import" in der Zeiterfassung** (sichtbar mit Änderungsrecht am Modul). Der
   Assistent hat dieselbe Schrittfolge wie der Stammdaten-Import: Datei → Spalten zuordnen →
   Prüfbericht aus einem Probelauf → bewusst importieren. Probelauf und Schreiblauf gehen durch
   denselben Code; geschrieben wird in einer Transaktion.
2. **Fünf Dateitypen.** CSV, Excel (.xlsx), JSON und Kalender (.ics) liest der Browser
   (`utils/zeitenDatei.js`). **PDF** geht an die KI-Schnittstelle und kommt als Tabelle zurück
   (`services/zeiten_pdf.py`) — danach ist es eine Datei wie jede andere: Feldzuweisung durch den
   Anwender, Prüfbericht, Import. Die Tabelle lässt sich als CSV herunterladen und korrigieren.
3. **Es wird nichts geraten.** Beanstandet werden u.a.: Zeilen ohne Beginn/Ende (nur Datum +
   Dauer), Datumsangaben wie `03/04/2026`, Ende vor Beginn, Einträge über 24 h, Pause ≥ Dauer,
   unbekannte oder mehrdeutige Zeitprojekte und Benutzer, doppelte Einträge (in der Datei und
   gegen den Bestand).
4. **KI-Schnittstelle erweitert** (`services/ki.py`): `call_ki` nimmt jetzt PDF-Dokumente
   (Anthropic `document`, OpenAI `file`), ein eigenes Zeitlimit und meldet über `meta`, ob die
   Antwort am Token-Limit abgerissen ist. Bestehende Aufrufer sind unverändert (alles optionale
   Parameter).

Neu: 28 Backend-Tests, 16 Frontend-Tests.

## 2. Beschlüsse (Oliver, 18.09.2026)

| Frage | Beschluss |
|---|---|
| Dateitypen | CSV + Excel, JSON, ICS, PDF über KI — alle in dieser Etappe |
| Wem gehören die Einträge? | Admin: Spalte (Name/E-Mail) ODER ein Benutzer je Datei. Alle anderen nur für sich selbst |
| Nur Datum + Dauer | **Beanstanden** — keine erfundene Uhrzeit |
| PDF-Weg | PDF **direkt** an den KI-Provider, mit deutlichem Hinweis vor dem Senden |

Von mir entschieden (bitte widersprechen, wenn es nicht passt):

| Punkt | Entscheidung | Grund |
|---|---|---|
| Doppelte | gleicher Benutzer + gleicher Beginn + gleiches Ende = derselbe Eintrag → Beanstandung | zweimal eingespielte Datei darf keine Stunden verdoppeln |
| Unbekanntes Zeitprojekt | Beanstandung, kein Freitext-Projekt | Zeitprojekte lassen sich vorab über den Stammdaten-Import anlegen; Freitext-Projekte tauchen in keinem Bericht je Zeitprojekt auf |
| Ende vor Beginn | Beanstandung; über Mitternacht nur mit Datum in Beginn UND Ende | Tippfehler und Nachtschicht sind sonst nicht unterscheidbar |
| `TT/MM/JJJJ` | nur wenn eindeutig (ein Teil > 12), sonst Beanstandung | Clockify exportiert US-Datum; ein vertauschter Tag fiele nie auf |
| Zeitzone | Angaben ohne Zone = Ortszeit der Installation (`TZ`); ISO mit `Z`/Offset wird umgerechnet | Toggl/Clockify liefern UTC |
| Status | importierte Einträge sind `veraenderbar` | normaler Abrechnungs-Workflow greift danach |
| Custom-Felder | zuordenbar, Schlüssel mit Vorsilbe `feld:` | ein Custom-Feld „notiz" darf das Kernfeld nicht überdecken |
| Grenzen | 5000 Zeilen je Import; PDF 10 MB, `max_tokens` 10000, Zeitlimit 170 s | nginx `proxy_read_timeout` ist 180 s |
| Abgerissene KI-Antwort | wird **abgelehnt** („bitte aufteilen"), nie teilweise übernommen | sonst fehlen die letzten Wochen, ohne dass es jemand merkt |
| Version | 2.1.0 (neue Funktion) | |

## 3. Umfang

| Datei | Änderung |
|---|---|
| `backend/app/services/zeiten_import.py` | **neu** — Zielfelder, Werte-Deutung, Prüfung, Schreiben |
| `backend/app/services/zeiten_pdf.py` | **neu** — Prompt, KI-Aufruf, Antwort → Tabelle |
| `backend/app/api/zeiterfassung_import.py` | **neu** — `GET /zeiterfassung/import/felder`, `POST /zeiterfassung/import/pdf`, `POST /zeiterfassung/import` |
| `backend/app/main.py` | Router eingebunden, gleiche Modulsperre wie die Zeiterfassung (GET → Ansehen, POST → Ändern) |
| `backend/app/services/ki.py` | `call_ki(..., dokumente=, timeout=, meta=)` |
| `backend/tests/test_zeiten_import.py` | **neu** — 28 Tests |
| `frontend/src/utils/zeitenDatei.js` (+ `.test.js`) | **neu** — Leser CSV/Excel/JSON/ICS, CSV-Ausgabe, Zuordnungsvorschlag |
| `frontend/src/components/ZeitenImport.jsx` (+ `.test.jsx`) | **neu** — Assistent |
| `frontend/src/services/api.js` | `importFelder`, `importZeiten`, `importPdf` |
| `frontend/src/pages/ZeiterfassungPage.jsx` | Knopf „Import" + Dialog |
| Versionsdateien, `CHANGELOG.md`, `changelog.js` | 2.0.5 → 2.1.0 über `bump_version.py` |

**Bewusst nicht angefasst:** `CsvImportExport.jsx` (Stammdaten-Import). Der Excel-Leser ist dort
ähnlich, aber der Zeiten-Import braucht Uhrzeiten aus Excel-Zellen, der Stammdaten-Import nicht.
Zusammenlegen wäre ein zweites Thema im selben Branch. Ebenfalls unverändert:
`api/zeiterfassung.py`, alle Modelle, alle Migrationen.

## 4. Prüfungen

### 4.1 Backend-Testreihe (vollständig)

Gelaufen in der Sandbox gegen PostgreSQL 16 (Python 3.11; Produktion 3.12):

```
$ python -m pytest tests/test_zeiten_import.py -q
28 passed, 32 warnings in 3.87s

$ python -m pytest tests -q
993 passed, 2 skipped in 515.42s (0:08:35)
```

```
$ ruff check --select F,E9,B904 --ignore F841 app/ alembic/env.py      # wie in ci.yml
All checks passed!
```

Was die 28 Tests festhalten: Probelauf schreibt nichts · Ortszeit (07:30 Wien = 05:30 UTC) ·
ISO/`Z` · ohne Entscheidung wird bei Beanstandungen nichts geschrieben · nur Datum + Dauer wird
beanstandet · acht Fälle „Unklares wird beanstandet" · eindeutiges Schrägstrich-Datum ·
zweimal dieselbe Datei · doppelte Zeile · Mitarbeiter darf nicht für andere (403, Spalte UND
`user_id`) · Admin über Spalte / fixer Benutzer · gleicher Name zweimal · Benutzerspalte nur für
Admins · Zeitprojekt über Namen inkl. Kontakt · Custom-Feld überdeckt Kernfeld nicht ·
5001 Zeilen → 422 · PDF → Tabelle, nichts gespeichert · abgerissene KI-Antwort → 422 ·
kein PDF / unbrauchbare Antwort → 422 · beide Provider bekommen das PDF als Dokument.

### 4.2 Frontend (Arbeitskopie in der Geräte-VM, Node 22)

```
$ npx vitest run
 Test Files  5 passed (5)        # vor ZeitenImport.test.jsx
      Tests  27 passed (27)
$ npx vitest run src/components/ZeitenImport.test.jsx
      Tests  3 passed (3)
$ npm run build
✓ built in 1.68s
```

Zusätzlich einmalig geprüft (Wegwerf-Test, nicht im Repo): eine mit ExcelJS erzeugte Datei mit
**echten** Datums- und Uhrzeit-Zellen (`hh:mm`) →
`{"Datum":"03.08.2026","Von":"07:30","Bis":"12:00","Start":"03.08.2026 07:30"}` — kein
Zeitzonen-Versatz, keine Tageszahl seit 1900 (die Falle aus dem Stammdaten-Import).

## 5. Nicht geprüft

- **Der echte KI-Aufruf mit einem PDF.** In der Sandbox gibt es keinen API-Key; geprüft ist nur,
  dass die Anfrage an beide Provider die dokumentierte Form hat. Wie gut die KI einen echten
  (gescannten) Stundenzettel liest und wie lange sie braucht, zeigt erst die Abnahme (6.4).
- OpenAI-Pfad mit PDF: Form laut Doku, am Server ist Anthropic eingestellt.
- Bedienung im Browser (Klickstrecke, Handy-Breite) — nur über Komponententests.
- Sehr große Dateien (mehrere tausend Zeilen) auf Dauer/Speicher.

## 6. Abnahme-Checkliste (lokal, Docker)

1. `./test.sh` — erwartet 993 bestanden.
2. Zeiterfassung → **Import**: eine CSV mit `Datum;Von;Bis;Pause;Projekt;Tätigkeit` — Vorschlag
   der Zuordnung stimmt, Prüfbericht zeigt Stundensumme, Import, Einträge stehen in der Liste.
   Dieselbe Datei noch einmal → alles „gibt es schon".
3. Excel mit echten Uhrzeit-Zellen; eine Zeile nur mit Datum + Dauer → wird beanstandet.
4. **PDF:** ein echter Stundenzettel. Hinweis vor dem Senden erscheint; Tabelle und KI-Hinweise
   mit dem PDF vergleichen; „Tabelle als CSV herunterladen" öffnet sich in Excel sauber.
   Im Log: `docker compose logs backend | grep 'KI-AUFRUF.*zeiten-import'` (Dauer, Tokens,
   `stop_reason`).
5. Als Admin: „Laut Spalte in der Datei" mit Name/E-Mail sowie ein fixer Benutzer.
   Als Mitarbeiter: die Auswahl fehlt, Einträge landen bei ihm selbst.
6. ICS-Export aus Outlook/Kalender: Termine kommen als Beginn/Ende/Titel; ganztägige werden
   beanstandet.

## 7. Risiken und Rückweg

| Risiko | Einschätzung | Gegenmaßnahme |
|---|---|---|
| KI verliest Ziffern im PDF | möglich | Hinweis im Assistenten, Vorschau, Stundensumme im Prüfbericht, CSV-Download; Einträge bleiben `veraenderbar` |
| PDF mit Arbeitszeiten geht an US-Anbieter (DSGVO) | bewusst entschieden | Bestätigung vor dem Senden; nichts wird gespeichert; ggf. ins Verarbeitungsverzeichnis aufnehmen |
| PDF-Lesen > 170 s | bei sehr langen PDFs | klare Fehlermeldung „bitte aufteilen"; kein 504 |
| Falscher Massenimport | möglich (Anwenderfehler) | Probelauf + Bericht; Einträge sind `veraenderbar` und löschbar |

Rückweg: Branch nicht mergen bzw. Revert — keine Migration, keine Datenänderung durch das Deploy.

## 8. Mögliche Folgeetappen (nicht beauftragt)

- „Import rückgängig" (Kennzeichnung je Importlauf — braucht eine Spalte/Migration).
- Zuordnungen je Quelle merken (Vorlage „Toggl", „Clockify").
- Option „unbekannte Zeitprojekte beim Import anlegen".
- Excel-Leser von Stammdaten- und Zeiten-Import zusammenlegen.
