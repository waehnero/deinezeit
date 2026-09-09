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

> **Entscheidung Oliver (09.09.2026): (b).** Umsetzung als Nachtrag K-26a2, siehe Abschnitt 10.

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

## 9. Abnahme am Server (09.09.2026, nach Merge und Deploy)

`./test.sh` lokal durch Oliver: **961 bestanden**. Rundgang über den eingebauten Browser auf
https://dz.wwinterface.online (Anmeldung durch Oliver); die Server-Antworten wurden aus dem
Netzwerkprotokoll des Browsers abgelesen.

| Teil-Router | Aufgerufene Endpunkte (alle **200**) |
|---|---|
| `/api/health` | `{"status":"ok","version":"2.0.2"}` |
| `invoice_belege` | `GET /invoices`, `?doc_type=rechnung`, `/next-number`, `/number-sequences?year=2026`, `GET /{id}`, `/{id}/audit`, `/{id}/preview` |
| `invoice_einstellungen` | `/settings/all`, `/email-templates/rechnung` |
| `invoice_buchhaltung` | `/open-items`, `/book/list`, `/uva`, `/auswertung/umsatz-jahr`, `/umsatz-kunden`, `/umsatz-artikel`, `/angebotsquote` |
| `invoice_zahlungen` | `/{id}/payments`, `/{id}/skonto?paid_at=…` |
| `invoice_mahnwesen` | `/dunning/run`, `/{id}/dunning` |
| `invoice_erechnung` | `/{id}/erechnung/pruefen` |
| `invoice_versand`, `invoice_anhaenge`, `invoice_status` | nur schreibende Aktionen (Versand, Storno, Umwandlung, Anhang) — am Produktivsystem bewusst nicht ausgelöst; Auflösung durch 4.4–4.6 und die Backend-Tests abgedeckt |

Seiten: Verkauf (Liste, Reiter Rechnungen/Wiederkehrend, Zahlungen-Dialog), Beleg RE-2026-002
(Vorschau, Änderungsprotokoll), Offene Posten, Mahnlauf, Verkaufsbuch, Auswertungen,
Einstellungen → Parameter (Belegnummern, E-Mail-Vorlagen) — alle mit Inhalt, Konsole ohne Einträge.

Nebenbefund (nicht dieses Bündel): Die Logo-Bilder werden mit doppeltem Cache-Parameter
angefordert (`logo_header.png?v=1785821496?v=1788931966742`); ein Teil dieser Anfragen wird vom
Browser mit `ERR_ABORTED` verworfen, weil das Layout sie beim Neu-Rendern erneut stellt.
Funktional folgenlos (die Wiederholung liefert 200), aber unsauber — Vermerk für K-26b.

**Ergebnis: K-26a abgenommen, keine Auffälligkeiten.**

## 10. Nachtrag K-26a2: Entwickler-Skripte nach `scripts/windows/` (09.09.2026, Version 2.0.3)

Umgesetzt nach Olivers Entscheidung für Variante (b). **Branch-Vorschlag:** `fix/audit-k26a2-windows-skripte`.

### 10.1 Verschoben (12 Dateien, Inhalt bis auf die Pfadkorrektur unverändert)

`start-lokal.bat/.ps1`, `stopp-lokal.bat/.ps1`, `reset-lokal.bat`, `neu-bauen.bat/.ps1`,
`migriere-kontakte.bat/.ps1`, `bump-version.ps1`, `git-einrichten.ps1`, `sicherheits-check.ps1`
→ `scripts/windows/`. Git erkennt das als Umbenennung (Inhalt > 90 % gleich), die Historie bleibt.

**Nicht verschoben** (Begründung Abschnitt 6): `backup*.ps1/.bat`, `backup.cfg`,
`backup-uri-handler.vbs`, `wiederherstellen.*`, sowie die Mac-Skripte `check.sh`, `test.sh`,
`start-arbeit.sh`, `frontend-neu-bauen.sh`, `install.sh` (in CLAUDE.md als Einstiegspunkte
an der Wurzel dokumentiert).

### 10.2 Pfadkorrekturen je Skript

Jedes Skript nahm bisher `$PSScriptRoot` bzw. `%~dp0` als Repo-Wurzel an. Jetzt:

| Skript | Änderung |
|---|---|
| `start-lokal.ps1`, `neu-bauen.ps1`, `migriere-kontakte.ps1` | `Set-Location $PSScriptRoot` → `Set-Location (Join-Path $PSScriptRoot "..\..")` |
| `stopp-lokal.ps1` | `$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path`, `Set-Location $Root`; `.watcher-pid` wird unter `$Root` gesucht (dort legt `backup-watcher.ps1` sie ab) |
| `reset-lokal.bat` | `cd /d "%~dp0"` → `cd /d "%~dp0..\.."` |
| `bump-version.ps1` | `$Root = $PSScriptRoot` → `Resolve-Path (Join-Path $PSScriptRoot "..\..")`; `git add` des Skripts selbst auf `scripts/windows/bump-version.ps1`; Aufrufbeispiel im Kopf |
| `git-einrichten.ps1`, `sicherheits-check.ps1` | hatten **kein** `Set-Location` und verließen sich auf das aktuelle Verzeichnis — jetzt explizit `Set-Location (Join-Path $PSScriptRoot "..\..")` nach dem Kopfkommentar; Aufrufhinweise auf `.\scripts\windows\…` |
| `*.bat`-Starter | unverändert (`%~dp0<name>.ps1` zeigt weiter auf die Datei daneben) |

Zeilenenden (CRLF) und die UTF-8-BOM von `bump-version.ps1` sind erhalten (`.gitattributes`
gilt per Muster `*.ps1`/`*.bat`, unabhängig vom Ordner).

### 10.3 Doku und Verweise

| Datei | Änderung |
|---|---|
| `scripts/windows/README.md` (neu) | Tabelle „Welches Skript wofür" + Hinweis, warum die Backup-Familie an der Wurzel bleibt |
| `LOKAL-TESTEN.md` | 5 Stellen: „im Ordner `scripts\windows`" bzw. voller Pfad |
| `MIGRATION-0016-PROJEKTPLAN.md` | `scripts\windows\neu-bauen.bat` |
| `docker-compose.local.yml` | Kopfkommentar (Windows-Pfad + Mac-Befehl) |
| `CLAUDE.md` | Ordnerbaum (`scripts/windows/`), Hinweis zu Windows-Pendants und Backup-Familie, `bump-version.ps1`-Pfad |
| Version 2.0.3 | `bump_version.py`, Lockfile-Wurzel nachgezogen; Changelog kundentauglich |

Nicht angepasst: Einträge in `CHANGELOG.md`/`changelog.js` (Historie), `AUDIT-*.md`
(Befundtext), `auto-version.yml` (deaktiviert, Kommentar).

### 10.4 Prüfung

| # | Prüfung | Ergebnis |
|---|---|---|
| 1 | Alle Verweise auf die 12 Dateinamen im Repo (`grep`, ohne node_modules/dist/.git/Changelog/Audit) | nur noch die Windows-Skripte untereinander (gleicher Ordner) und die angepassten Doku-Stellen ✅ |
| 2 | Kein Skript außerhalb der 12 verweist auf einen alten Pfad | `backup*.ps1`, `wiederherstellen.ps1` nennen `start-lokal.bat` nur in Hinweistexten an den Benutzer — nicht als Aufruf ✅ (Texte bewusst nicht geändert; sie sagen „starte DeineZeit", der Ort steht in LOKAL-TESTEN.md) |
| 3 | CI/Deploy | `ci.yml` und `deploy.yml` referenzieren keine der 12 Dateien; rsync-Ausnahmen betreffen nur `backup.cfg` ✅ |
| 4 | Zeilenenden/BOM nach dem Bearbeiten | `file`: CRLF erhalten, BOM bei `bump-version.ps1` erhalten ✅ |
| 5 | **PowerShell-Lauf** | ⚠️ **nicht möglich** — kein Windows/PowerShell in der Prüfumgebung. Abnahme unter Windows durch Oliver (10.5). |

Nebenbefund `bump-version.ps1` (unverändert gelassen, historisch): Das Skript macht am Ende
`git commit` + `git push` auf den aktuellen Branch und zieht `package-lock.json` nicht nach —
beides passt nicht mehr zum heutigen Ablauf (pre-commit-Hook, geschütztes `main`). Kandidat
zum Streichen oder Angleichen, aber nicht Teil dieses Bündels.

### 10.5 Abnahme (Windows, durch Oliver)

- [ ] `scripts\windows\start-lokal.bat` doppelklicken → Container starten, Browser öffnet http://localhost
- [ ] `scripts\windows\stopp-lokal.bat` → Container stoppen, keine Fehlermeldung zu `.watcher-pid`
- [ ] `scripts\windows\neu-bauen.bat` → Build läuft durch
- [ ] optional `reset-lokal.bat` (löscht Testdaten!) und `sicherheits-check.ps1`

Ohne Windows-Rechner: PR trotzdem mergbar (Backend/Frontend unberührt, CI grün erwartet);
die Skripte dann beim nächsten Windows-Einsatz prüfen und Rückmeldung in diesen Bericht.
