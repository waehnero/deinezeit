# Prüfbericht – Bündel K-26a: Verkaufsmodul aufgeteilt (Version 2.0.2)

**Datum:** 08.09.2026 · **Anlass:** Audit-Befund ARCH-001 (`invoice.py` mit 3.740 Zeilen),
Korrekturplan K-26 ([AUDIT-2026-09-02.md](AUDIT-2026-09-02.md), Abschlussprüfung Abschnitt 7) ·
**Freigabe:** Oliver, 08.09.2026 („weiter" nach Bündel npm; Aufteilung in K-26a Backend / K-26b Frontend vorgeschlagen, kein Widerspruch) ·
**Branch (Vorschlag):** `fix/audit-k26a-verkauf-aufteilen`

> Stand bei Abgabe: Änderungen im Working Tree, nichts committet. `./test.sh`
> (Backend, 961 Tests) konnte hier nicht laufen — kein PostgreSQL in der
> Prüfumgebung — und ist von Oliver vor dem Push auszuführen (Abschnitt 7).

---

## 1. Zusammenfassung

`backend/app/api/invoice.py` (3.740 Zeilen, 58 Endpunkte) ist in **neun Fachmodule
plus ein Hilfsmodul** zerlegt. Es handelt sich um eine **reine Verschiebung**: Kein
Endpunkt, keine Funktion, keine Zeile Fachlogik wurde geändert. Nachgewiesen durch
einen byteweisen Vergleich der OpenAPI-Beschreibung (identisch) und eine Anfrage an
jeden der 58 Endpunkte gegen alte und neue App (identisches Verhalten).

`app/api/invoice.py` bleibt als **Sammelrouter** bestehen (57 Zeilen): Er registriert die
Teil-Router in der richtigen Reihenfolge und stellt die Hilfsfunktionen weiter unter dem
alten Namen bereit, sodass **`main.py`, sechs Dienste und alle Tests unverändert
funktionieren** (eine Test-Datei angepasst, siehe 3.4).

Der zweite Teil von K-26a — Windows-Skripte nach `scripts/windows/` verschieben — wurde
**bewusst nicht ausgeführt** (Begründung und Entscheidungsvorlage in Abschnitt 6).

## 2. Ausgangslage

| Messgröße (Stand 2.0.1) | Wert |
|---|---|
| `app/api/invoice.py` | 3.740 Zeilen, 58 Endpunkte (50 Pfade), rund 30 Hilfsfunktionen, 11 Modulkonstanten |
| Größtes anderes API-Modul | `projektplan.py` 1.221 Zeilen |
| Von außen genutzte Namen aus `app.api.invoice` | 15 Funktionen/Konstanten/Modelle in 6 Diensten (`dunning`, `dunning_pdf`, `invoice_archive`, `overdue_service`, `period_service`, `recurring_service`) und 3 Testdateien |
| Ruff (F, E9) | grün |

## 3. Umfang der Änderungen

### 3.1 Neue Module (`backend/app/api/`)

| Modul | Zeilen | Endpunkte | Inhalt |
|---|---|---|---|
| `invoice_common.py` | 613 | – | Nummernkreis (`_next_number`, Format), Summen (`_calc_totals`), Zeiteintrags-Status, Änderungsprotokoll (`_audit`), Zahlstand, Pflichtangaben/UID, Finalisieren, Belegsperre, `DOC_TYPE_LABELS_DE`, `_load_pdf_context` |
| `invoice_einstellungen.py` | 238 | 7 | `/settings/*`, `/template-preview/{id}`, `/positions/image`, `/email-templates/{doc_type}` |
| `invoice_buchhaltung.py` | 694 | 10 | Belegbuch `/book/*`, `/uva`, `/uva/pdf`, `/open-items`, `/auswertung/*` |
| `invoice_zahlungen.py` | 266 | 5 | Zahlungseingänge, Skonto |
| `invoice_mahnwesen.py` | 283 | 7 | `/dunning/*`, Mahnhistorie, Mahnsperre |
| `invoice_erechnung.py` | 96 | 2 | Factur-X-Prüfung und XML |
| `invoice_versand.py` | 307 | 2 | `_send_invoice_email`, `/send-email`, `/bulk-send-email` |
| `invoice_anhaenge.py` | 171 | 3 | Vertragsanhang (`/contract/*`) |
| `invoice_status.py` | 777 | 9 | Stornieren, bezahlt, Statuswechsel, Angebot→AB→Rechnung, Abrechnung in Stufen, Duplizieren |
| `invoice_belege.py` | 600 | 13 | Liste, Anlegen, `/templates`, `/next-number`, `/number-sequences`, Detail, Audit, PDF/Vorschau, Ändern, Löschen, `/time-entries/unbilled` |
| `invoice.py` (neu) | 57 | – | Sammelrouter + Re-Exporte |

Summe der Teilmodule 4.045 Zeilen (Original 3.740): Die Differenz sind Modul-Docstrings
und die je Modul wiederholten Import-Blöcke. Jeder Import-Block wurde mit `ruff --fix`
auf das tatsächlich Benötigte reduziert (647 ungenutzte Importe entfernt).

### 3.2 Vorgehen

Skriptgestützt, nicht von Hand: Ein Schneideskript hat das Original nach Zeilenbereichen
in die Module verteilt und geprüft, dass **jede Zeile ab dem alten `router = …` genau
einmal** in einem Modul landet (keine Lücke, keine Dublette). Danach `ruff F821` (nicht
definierte Namen) → alle Treffer waren Hilfsfunktionen aus `invoice_common`; keine
Abhängigkeit zwischen zwei Endpunkt-Modulen. Zuletzt `ruff F401 --fix` für die Importe.

### 3.3 Router-Reihenfolge (der eigentliche Fallstrick)

FastAPI wertet Routen in Registrierungsreihenfolge aus; `GET /{invoice_id}` schluckt
jeden festen Ein-Segment-Pfad, der danach kommt (`/uva`, `/open-items`, `/templates` …
würden zu 422). Der Sammelrouter registriert deshalb in dieser Reihenfolge:
einstellungen → buchhaltung → zahlungen → mahnwesen → erechnung → versand → anhaenge →
status → **belege zuletzt** (dort liegt `GET /{invoice_id}`). Die Reihenfolge ist im
Docstring von `invoice.py` begründet.

Technisches Detail: FastAPI lehnt eine Route mit leerem Pfad (`GET ""` = Belegliste) in
einem Router ohne Präfix ab. Deshalb tragen die **Teil-Router** das Präfix `/invoices`,
der Sammelrouter nur den Tag `Rechnungen`; `main.py` hängt wie bisher `/api` davor.
Ergebnis für den Aufrufer: exakt dieselben Pfade.

### 3.4 Angepasste bestehende Dateien

| Datei | Änderung |
|---|---|
| `app/api/invoice.py` | ersetzt durch Sammelrouter (s. o.) |
| `tests/test_verkauf_kleinigkeiten.py` | ein `monkeypatch` auf `_send_invoice_email` zeigt jetzt auf `app.api.invoice_versand` — dort schlägt der Endpunkt `/bulk-send-email` die Funktion nach. Die beiden Patches in `test_verkauf_erweiterungen.py` bleiben auf `app.api.invoice`, weil dort `recurring_service` aufruft, der weiterhin aus dem Sammelrouter importiert. |
| `CLAUDE.md` | Ordnerstruktur + Konvention „ab ~1.000 Zeilen aufteilen" |
| Version 2.0.2 | `scripts/bump_version.py`, Lockfile-Wurzel nachgezogen, Changelog-Text kundentauglich („für dich ändert sich nichts") |

Nicht angefasst: `main.py`, alle Dienste, Modelle, Schemas, Migrationen, Frontend.

## 4. Prüfungen und Ergebnisse

Prüfumgebung: Python 3.10 mit `requirements.txt` in einem eigenen venv (ohne Datenbank),
App-Import mit Platzhalter-Umgebungsvariablen.

| # | Prüfung | Ergebnis |
|---|---|---|
| 4.1 | Zeilenabdeckung des Schneideskripts | 0 fehlende, 0 doppelte Zeilen (einzige nicht übernommene Zeile: eine Leerzeile 3618) ✅ |
| 4.2 | `ruff check --select F,E9 --ignore F841 app/ alembic/env.py` (CI-Kommando) | All checks passed ✅ |
| 4.3 | `py_compile` aller `invoice*.py` | ✅ |
| 4.4 | `app.openapi()` — alle Pfade unter `/api/invoices`, sortiert als JSON | **byteweise identisch** alt/neu (50 Pfade, 58 Operationen; inkl. Parameter, Schemas, Tags, Rechte-Abhängigkeiten) ✅ |
| 4.5 | Statische Routenauflösung (Regex wie Starlette, Beispielpfad je Route) | alt und neu lösen jede der 58 Routen auf denselben Endpunkt auf ✅ |
| 4.6 | Dynamische Probe mit `TestClient`: je Operation eine Anfrage ohne Anmeldung | alt und neu: 58× **401** (Anfrage kommt bis zur Anmeldeprüfung — kein 404, kein 422 durch verschluckte Pfade) ✅ |
| 4.7 | App-Start (`from app.main import app`) | ohne Fehler ✅ (Warnung `STATIC_DIR` ist umgebungsbedingt, /app nicht beschreibbar) |
| 4.8 | Importe von außen (`from app.api.invoice import …` in Diensten/Tests) | alle 15 Namen im Sammelrouter re-exportiert (Importstellen per grep erhoben, Sammelrouter von `ruff` auf gültige Namen geprüft) ✅ |

**Nicht geprüft:** `./test.sh` (961 Backend-Tests) — kein PostgreSQL in der Prüfumgebung.
Erwartung: grün, weil OpenAPI und Auflösung identisch sind und die Tests über die
HTTP-Schnittstelle bzw. den Sammelrouter arbeiten. Der eine angepasste Test (3.4) ist der
einzige, dessen Ergebnis von der Aufteilung abhängt.

## 5. Risiken

| # | Risiko | Einschätzung | Absicherung |
|---|---|---|---|
| R1 | Verschluckter Pfad durch falsche Router-Reihenfolge | ausgeschlossen durch 4.5 + 4.6 | Reihenfolge im Docstring festgehalten |
| R2 | Ein Dienst importiert einen Namen, der nicht re-exportiert ist | ausgeschlossen durch 4.8 (alle Importstellen gegrept) | — |
| R3 | `monkeypatch` in Tests greift ins Leere (Funktion wird aus anderem Modul nachgeschlagen) | ein Fall gefunden und angepasst (3.4) | `./test.sh` durch Oliver |
| R4 | Merge-Konflikte mit parallelen Verkaufs-Branches | Zeilen sind in neue Dateien gewandert; ein offener Branch, der `invoice.py` ändert, müsste die Änderung im passenden `invoice_*`-Modul neu anbringen | vor dem Merge prüfen, ob ein Feature-Branch `invoice.py` berührt |
| R5 | Neue Verkaufs-Endpunkte landen wieder in `invoice.py` | Konvention in CLAUDE.md | — |

Rückweg: Revert des Merge-Commits; keine Migration, keine Datenänderung.

## 6. Entscheidungsvorlage: Windows-Skripte nach `scripts/windows/`

Im Repo-Wurzelverzeichnis liegen 25 `.ps1`/`.bat`/`.vbs`-Dateien. Ich habe sie **nicht**
verschoben, aus drei Gründen:

1. **Kopplung an den Ort.** Alle Skripte setzen `$PSScriptRoot` bzw. `%~dp0` = Repo-Wurzel
   voraus (`Set-Location $PSScriptRoot`, `docker compose -f docker-compose.local.yml`,
   `.\backend\…`). Jedes verschobene Skript bräuchte eine Pfadkorrektur — 12 Dateien allein
   für die lokale Entwicklung.
2. **Die Backup-Familie hängt an Installationen.** `backup-task-register.ps1` trägt den
   absoluten Pfad von `backup.ps1` in die Windows-Aufgabenplanung ein;
   `docker-compose.local.yml` mountet `./backup.cfg`; das Backend schreibt
   `/opt/deinezeit/backup.cfg`. Ein Umzug bricht bestehende Windows-Einrichtungen still.
3. **Hier nicht testbar.** Es gibt in der Prüfumgebung kein Windows/PowerShell; die
   Änderung ginge ungeprüft in den PR — genau das Muster, das der Prüfbericht ausschließen soll.

Vorschlag: (a) belassen und in `INSTALLATION.md`/`LOKAL-TESTEN.md` eine kurze Tabelle
„Welches Skript wofür" ergänzen, oder (b) nur die 12 Entwickler-Skripte verschieben
(`start-lokal`, `stopp-lokal`, `neu-bauen`, `reset-lokal`, `migriere-kontakte`,
`bump-version`, `git-einrichten`, `sicherheits-check`) mit Pfadkorrektur, Backup-Familie
bleibt — dann bitte mit einem Windows-Test durch dich. **Meine Empfehlung: (a).**

## 7. Abnahme durch Oliver (lokal)

```bash
git checkout -b fix/audit-k26a-verkauf-aufteilen
docker compose -f docker-compose.local.yml up -d --build
./test.sh                                  # erwartet: 961 bestanden
./test.sh tests/test_verkauf_kleinigkeiten.py tests/test_verkauf_erweiterungen.py tests/test_verkauf_belegsperre.py
```

- [ ] `./test.sh` grün (961)
- [ ] Anmeldeseite lokal zeigt 2.0.2 „Aufräumen im Verkaufsmodul"
- [ ] Kurzer Rundgang Verkauf: Liste, Beleg öffnen, PDF, Offene Posten, Mahnlauf, Einstellungen → Parameter (jede Seite trifft einen anderen Teil-Router)
- [ ] Entscheidung zu Abschnitt 6 (a/b)

Danach Commit und PR; Pflicht-Checks „Backend: Tests (pytest)" (enthält den Ruff-Lauf) und
„Frontend: Tests (Vitest)". Abnahme am Server mache ich anschließend wie beim Bündel npm.

## 8. Abgleich mit dem Plan

| Vorgabe K-26 | Ergebnis |
|---|---|
| `invoice.py` in `invoice_*`-Router aufteilen (reine Verschiebung) | ✅ 9 + 1 Module, OpenAPI identisch |
| Skripte in `scripts/windows/` ordnen | ⏸ Entscheidungsvorlage (Abschnitt 6) |
| `React.lazy` je Seite, `aria-label`/N-03, Wortlaut „Neue Angebot" | → K-26b (Frontend) |
| Optional OPS-006, SEC-015, CODE-001-Rest | offen, nach K-26b |
