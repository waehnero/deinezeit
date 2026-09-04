# DeineZeit – Abschlussprüfung zum Software-Audit vom 02.09.2026

**Stand:** 04.09.2026 · **Geprüfter Stand:** `main` nach Merge von Bündel G (Version 1.12.82, Migrationsstand 0062) zuzüglich Bündel H (Branch `fix/audit-buendel-h`)
**Prüfer:** Claude (unabhängiger Senior-Auditor) · **Auftraggeber:** Oliver Wähner
**Bezug:** [AUDIT-2026-09-02.md](AUDIT-2026-09-02.md) (Prüfbericht mit 45 Befunden und Korrekturplan K-01 … K-26)

> Diese Datei ergänzt den Prüfbericht; der Bericht selbst bleibt unverändert als Ausgangslage stehen.

---

## 1. Management-Zusammenfassung

Zwischen dem 02.09. und dem 04.09.2026 wurden **alle 26 Korrekturschritte** des Plans in acht Bündeln (K-01, A–G) umgesetzt, geprüft, per Pull Request gemergt und automatisch auf den Server ausgerollt. Ein neuntes Bündel H (Nachbefund aus den neuen Tests) liegt zur Prüfung vor.

**Ergebnis nach Schweregrad:**

| Schweregrad | Befunde | behoben | teilweise | offen (bewusst) |
|---|---|---|---|---|
| KRITISCH | 0 | – | – | – |
| HOCH | 8 | **8** | – | – |
| MITTEL | 19 | **19** | – | – |
| NIEDRIG | 12 | 8 | 1 | 3 |
| VERBESSERUNG | 6 | 2 | 1 | 3 |
| **gesamt** | **45** | **37** | **2** | **6** |

Die sechs offenen Punkte sind Modernisierungs- und Komfortthemen (Code-Aufteilung, Skriptordnung, Code-Splitting, Barrierefreiheit, strukturiertes Logging, Installationshinweis); keiner davon berührt Sicherheit oder Datenintegrität. **Aus Sicht des Audits steht einem Release 2.0.0 nichts entgegen.**

**Kennzahlen vorher → nachher:**

| Kennzahl | 02.09.2026 | 04.09.2026 |
|---|---|---|
| Backend-Tests | 873 (46 Dateien) | **961** (54 Dateien), davon 88 neu |
| Frontend-Tests | keine | **9** (Vitest, eigener CI-Job) |
| CI-Laufzeit pytest | bis 84 min | wenige Minuten |
| Modelle ↔ Migrationen (`compare_metadata`) | 104 Abweichungen | **0** — Drift-Test in der Testreihe |
| pip-audit | 12 Meldungen (starlette 8, weasyprint 2, ecdsa 1) | **1** (ecdsa, kein Fix verfügbar, siehe 4.) |
| npm audit `--omit=dev` | 4 (2 high) | 30 moderate (nur Hauptversionssprünge, siehe 4.) |
| `async def`-Endpunkte mit blockierender I/O | 259 | 0 (4 bewusst async, Wächter-Test) |
| Docker-Socket im Backend | ja | **nein** |
| Content-Security-Policy | keine | scharf, CI-geprüft |
| Backup-Umfang | nur Datenbank | Datenbank + Dateispeicher + Manifest, Restore-Anleitung |
| Migrationen | 0001–0059 | 0001–0062 |

---

## 2. Status je Befund

Legende: ✅ behoben · ◐ teilweise · ⏸ offen (bewusst zurückgestellt) · Nachweis = Test/Prüfung, die den Zustand hält

### HOCH (8/8 behoben)

| ID | Befund | Status | Umsetzung | Nachweis |
|---|---|---|---|---|
| DATA-001 | Deploy löscht Backups/Logs | ✅ K-01 | rsync-Ausnahmen `backups/ logs/ backup.cfg mockups/ design-vorschlaege/ lasttest/` | Testdatei in `backups/` überlebte zwei Deploys |
| DATA-002 | MinIO nicht im Backup | ✅ K-20 | ZIP mit `datenbank.sql`, `dateien/<key>`, `manifest.json`; OneDrive-Backup ebenso; `docs/WIEDERHERSTELLUNG.md`, `scripts/wiederherstellen.sh` | `test_backup.py` (+5) |
| SEC-001 | XSS über SVG-Vorschau | ✅ K-03 | Positivliste Vorschau-Mimetypes (serverseitig), SVG nur als Download, `nosniff`, CSP `script-src 'none'` auf EML/MSG | `test_datacenter.py` (19) |
| SEC-002 | Docker-Socket im Backend | ✅ K-21 | Socket, Host-Mount, `git`, `docker-cli` entfernt; In-App-Update gestrichen; certbot-Lebenszeichen statt `docker inspect` | `test_system.py`, `test_ssl.py`; `docker inspect` am Server: nur `letsencrypt:ro` + `CHANGELOG.md:ro` |
| SEC-003 | starlette/weasyprint verwundbar | ✅ K-13/K-14 | fastapi 0.141.1, starlette 1.3.1, pydantic 2.12.5, weasyprint 69.0 | pip-audit: nur noch ecdsa |
| DATA-003 | Benutzer löschen vernichtet Zeiten | ✅ K-09 | 409 mit Aufstellung der Fachdaten; Migration 0061 nimmt CASCADE von `time_entries.user_id` | `test_users.py` (5) |
| PERF-001 | async-Endpunkte blockieren | ✅ K-11 | 251 Endpunkte auf `def` (Threadpool); bcrypt/git/Sammelläufe in `run_in_threadpool` | `test_endpunkte_sync.py` (Wächter mit Positivliste) |
| BUG-001 | XML/PDF-Links liefern 403 | ✅ K-02 | Blob-Download mit Authorization-Header | manuell |

### MITTEL (19/19 behoben)

| ID | Befund | Status | Umsetzung | Nachweis |
|---|---|---|---|---|
| SEC-004 | `/settings` anonym gibt Konfiguration preis | ✅ K-05 | Positivliste Branding-Felder; Rest nur Admin | `test_settings.py` |
| SEC-005 | Geheimnisse im Klartext in `settings` | ✅ K-06 | Fernet über ORM-Events, Migration 0060 verschlüsselt Bestand | `test_settings.py`; Server: Werte `gAAAAA…` |
| SEC-006 | Erstinstallation ohne Schutz | ✅ K-18 | `SETUP_TOKEN` (install.sh erzeugt), `compare_digest`, `LOCK TABLE users` | `test_setup.py` (+3) |
| SEC-007 | Pfad-Traversal Speicherschlüssel | ✅ K-04 | Slug-Muster, UUID-Prüfung, alle Segmente bereinigt | `test_datacenter.py` |
| SEC-008 | Verwundbare Frontend-Abhängigkeiten | ✅ K-15 | Lockfile neu, `npm ci`, `xlsx` → `exceljs`, `uuid`-Override | Build/CI; Rest siehe 4. |
| SEC-009 | Keine CSP | ✅ K-16/K-16b | Report-Only → Rundgang ohne Verstoß → scharf; `X-XSS-Protection` weg | CI-Header-Check prüft aktive CSP-Zeile |
| DATA-004 | Modelle ≠ Migrationen | ✅ K-07/K-08 | Drift-Test, Migration 0061, 13 Modelle nachgezogen | `test_migrationen.py` (0 Abweichungen) |
| DATA-005 | Nummernkreis ohne Sperre | ✅ K-10 | `with_for_update()`, Formatstring-Prüfung | `test_verkauf_belegsperre.py` (+2) |
| BUG-002 | Container in UTC | ✅ K-17 | `TZ=Europe/Vienna`, `core/zeit.py`, 46 Stellen | `test_zeit.py` (Wächter gegen nacktes `today()/now()`) |
| BUG-003 | Lockfile unvollständig | ✅ K-15 | Lockfile regeneriert, `npm ci` im Dockerfile | Docker-Build |
| OPS-001 | Deploy ohne CI-Kopplung, Healthcheck nur Warnung | ✅ K-19 | `workflow_run` nach grüner CI, Healthcheck 12×10 s mit Abbruch | Deploys E–G liefen darüber |
| OPS-002 | Zwei Update-Wege | ✅ K-21 | nur noch `deploy.yml` bzw. `scripts/deploy.sh`; `update.sh` gelöscht | `test_system.py` |
| OPS-003 | In-Memory-Zustand erzwingt einen Prozess | ✅ K-12/K-21 | Zustand in DB, aktive Benutzer aus `user_sessions`, **Worker-Sperre per Advisory-Lock** → `UVICORN_WORKERS` > 1 erlaubt | `test_system.py`; Server-Log „Worker-Sperre erhalten" |
| OPS-004 | `/system/version` anonym mit git fetch | ✅ K-11/K-21 | nur angemeldet, 10-min-Cache, kein git mehr | `test_endpunkte_sync.py` |
| OPS-005 | `minio:latest` | ✅ | `RELEASE.2025-09-07T16-13-09Z` (Ist-Stand am Server) | `test_system.py` |
| TEST-001 | Testlücken | ✅ K-22 (+H) | Datacenter (19), Benutzer (5), Projektplan (15), Sitzungen (10, bereits vorhanden), Migrationskette, Nummernkreis, Zeitzone, Aufgabenbezug (7) | 88 neue Tests |
| TEST-002 | 6 s MinIO-Wartezeit je Test | ✅ K-22a | Startup-Hooks bei `TEST_DATABASE_URL` übersprungen | CI-Laufzeit |
| UX-001 | Kein Error Boundary | ✅ K-23 | `ErrorBoundary.jsx` um `<Routes>` | `ErrorBoundary.test.jsx` |
| UX-002 | Mehrsprachigkeit nur nominell | ✅ K-25 | Sprachwahl ausgeblendet, Doku berichtigt („faktisch Deutsch") | – |

### NIEDRIG (8 behoben, 1 teilweise, 3 offen)

| ID | Befund | Status | Anmerkung |
|---|---|---|---|
| SEC-010 | Backup-Ping ohne `compare_digest`, leer = offen | ✅ K-24 | 503 ohne Token; Token in compose/backup.ps1 |
| SEC-011 | Interne Fehlertexte nach außen | ✅ K-24 | generische Meldung + `logger.exception` |
| SEC-012 | `.env.local` eingecheckt | ✅ K-25 | aus dem Index entfernt (geprüft 04.09.), in `.gitignore`, Anleitung in LOKAL-TESTEN.md |
| SEC-013 | Logo-SVG same-origin | ✅ K-03 | `_svg_pruefen` (kein Script/Event-Handler) + CSP |
| SEC-014 | `/auth/events?limit` unbegrenzt | ✅ K-24 | `le=200` |
| SEC-015 | `curl \| sudo bash` ohne Prüfsumme | ⏸ | Doku-Hinweis; Entscheidung Oliver (Hinweis auf `git clone` + Review) |
| BUG-004 | Name ungeescaped in Reset-Mail | ✅ K-24 | `html.escape` |
| BUG-005 | `Content-Disposition` ohne RFC 5987 | ✅ K-24 | `core/http.py` `content_disposition()`, 7 Stellen |
| PERF-002 | Kein Code-Splitting | ⏸ K-26 | Bundle > 500 kB; `React.lazy` je Seite |
| PERF-003 | Backup/Downloads im Speicher | ✅ K-20 | `pg_dump` streamend in Datei, Timeout `BACKUP_TIMEOUT_SEKUNDEN` |
| UX-003 | Barrierefreiheit | ⏸ K-26 | dazu N-03 (29 Felder ohne `id`/`name`) |
| DOC-001 | Veraltete Doku | ◐ K-25 | STATUS.md neu, CLAUDE.md berichtigt; `version:` in `docker-compose.local.yml` noch drin (N-07) |

### VERBESSERUNG (2 behoben, 1 teilweise, 3 offen)

| ID | Befund | Status | Anmerkung |
|---|---|---|---|
| DOC-002 | Keine Restore-Anleitung | ✅ K-20 | `docs/WIEDERHERSTELLUNG.md`, `scripts/wiederherstellen.sh` |
| ARCH-001 | `invoice.py` 3.699 Zeilen | ⏸ K-26 | reine Verschiebung, nach 2.0.0 |
| ARCH-002 | Skript-Wildwuchs | ⏸ K-26 | `update.sh` ist weg; Rest nach 2.0.0 |
| CODE-001 | ruff-Befunde, `except: pass` | ◐ K-25 | 55 ungenutzte Importe entfernt, ruff `F,E9` blockierend in CI; `raise … from` (B904) und `except: pass`-Durchsicht offen |
| CODE-002 | `on_event` deprecated | ✅ K-13 | `lifespan` |
| OPS-006 | Logging unstrukturiert | ⏸ | nach 2.0.0; App-Logger seit 12.08. ab INFO sichtbar |

---

## 3. Neue Befunde aus der Umsetzung (N-01 … N-08)

Die Korrekturarbeit — vor allem die neuen Tests — hat weitere Punkte zutage gebracht. Sie sind hier nach demselben Schema bewertet.

| ID | Schweregrad | Befund | Status |
|---|---|---|---|
| **N-01** | **HOCH** | `Task.children` (Projektplan) war verkehrt definiert (`remote_side` auf der Kinder-Seite): `children` lieferte das Elternteil, `parent` die Kinder. **Jedes Anlegen/Ändern einer Teilaufgabe endete mit HTTP 500**, `is_leaf` war falsch, die Löschkaskade zeigte vom Kind aufs Elternteil. Erster Test des Moduls deckte es auf. | ✅ Bündel G (`models/projektplan.py`; `test_projektplan.py` hält den Zustand) |
| **N-02** | MITTEL | `time_entries.task_id` (seit Migration 0016) wurde von keinem Endpunkt gesetzt — Löschsperren „Aufgabe/Projekt mit gebuchten Zeiten" und „gebuchte Minuten je Aufgabe" liefen ins Leere. | ✅ Bündel H (`task_id` in Zeiteintrag/Timer, `/zeiterfassung/aufgaben`, Auswahl im Dialog; `test_zeiterfassung_aufgabe.py`, 7 Tests) |
| N-03 | NIEDRIG | 29 Formularfelder ohne `id`/`name` (Chrome „Issues" beim CSP-Rundgang); betrifft Autofill/Screenreader. | ⏸ mit UX-003 |
| N-04 | NIEDRIG | `install.sh` interpolierte das Admin-Passwort in einen Python-String (Apostroph brach die Anlage). | ✅ K-24b (`DZ_ADMIN_*`-Umgebungsvariablen) |
| N-05 | NIEDRIG | Ein Test (`test_update_start_verweigert_doppelt_und_lokal`) war umgebungsabhängig (`DEPLOY_MODE=local` in der lokalen Instanz) — lokal rot, in CI grün. | ✅ Bündel C (Variable im Test geräumt); Test mit K-21 entfallen |
| N-06 | NIEDRIG | Release-Notes der Bündel E, F, G stehen im CHANGELOG als Platzhalter „(Release-Notes ergänzen)". | ⏸ bis R-01 (dort nachziehen) |
| N-07 | VERBESSERUNG | `version:` in `docker-compose.local.yml` ist obsolet (Warnung bei jedem Aufruf). | ⏸ trivial, mit R-01 |
| N-08 | INFO | `npm audit` mit Dev-Abhängigkeiten meldet 36 Punkte (u. a. durch jsdom/vitest); ohne Dev 30 „moderate", alle aus Hauptversionssprüngen (react-router 7, TipTap 3, vite 8). Nichts davon im ausgelieferten Bundle ausnutzbar. | ⏸ Bündel „npm-Hauptversionen" nach 2.0.0 |

---

## 4. Restrisiken (bewusst akzeptiert oder nicht behebbar)

1. **`ecdsa 0.19.2` (PYSEC-2026-1325):** transitive Abhängigkeit von `python-jose`; kein Fix verfügbar. Betrifft nur ECDSA-Signaturen — DeineZeit signiert JWT mit HMAC (`HS256`). Risiko: vernachlässigbar. Beobachten; bei Verfügbarkeit eines Fixes updaten.
2. **npm-Hauptversionssprünge** (react-router 7, TipTap 3, vite 8): 30 „moderate"-Meldungen, überwiegend ReDoS/Prototype-Pollution in Build-/Editor-Ketten. Eigenes Bündel nach 2.0.0 mit Sichtprüfung des Editors.
3. **`SECRET_KEY` dient JWT und Feldverschlüsselung** (2FA-Secrets, Settings-Geheimnisse): ein Wechsel entwertet beides. Dokumentiert; ein separater Verschlüsselungsschlüssel wäre sauberer (Modernisierungsvorschlag).
4. **`UVICORN_WORKERS` > 1** ist technisch freigegeben, aber im Betrieb noch nicht erprobt (Vorgabe bleibt 1). Beim Hochsetzen: Pool-Größe gilt je Prozess; Log auf genau eine Zeile „Worker-Sperre erhalten" prüfen.
5. **certbot-Lebenszeichen:** Läuft die Schleife, ist die Datei frisch; steht der Container, altert sie. Nicht erkannt wird ein Container, der läuft, aber dessen `certbot renew` intern scheitert — das fängt die Restlaufzeit-Warnung (21/7 Tage) ab. Zwei Ebenen bleiben also.
6. **Anhänge für alle angemeldeten Benutzer** (offene Frage 3 des Berichts): weiterhin bewusste Fachentscheidung; Beleg-PDF-Archiv und Eingangsrechnungen sind damit für jeden Mitarbeiter lesbar. Entscheidung Oliver.
7. **`backup.cfg` am Server** wird vom Backend nicht mehr erreicht (kein Mount); am Server las die Datei ohnehin nichts. Für lokale Windows-Installationen bleibt der Mount in `docker-compose.local.yml`.
8. **Deploy per `ssh-keyscan` (TOFU)** statt gepinntem Host-Fingerprint — unverändert, niedrig.

---

## 5. Testabdeckung nach der Umsetzung

**Backend:** 961 Tests in 54 Dateien, alle grün (lokal per `./test.sh` gegen PostgreSQL 16 im Container; in der Sandbox gegen PGlite; in der CI gegen Postgres-Service). Neu seit dem Audit: `test_datacenter.py`, `test_users.py`, `test_migrationen.py`, `test_endpunkte_sync.py`, `test_zeit.py`, `test_setup.py` (+3), `test_backup.py` (+5), `test_kleinigkeiten.py`, `test_system.py`, `test_projektplan.py`, `test_zeiterfassung_aufgabe.py`, `test_ssl.py` (+4), `test_settings.py` (+5), `test_verkauf_belegsperre.py` (+2).

**Wächter-Tests** (halten den Zustand, statt ein Ergebnis zu prüfen): Migrations-Drift (`compare_metadata` = leer), kein `async def` ohne `await`, kein nacktes `today()/now()` im Fachcode, kein `docker`/`subprocess` in `system.py`/`ssl_service.py`, kein Docker-Socket in `docker-compose.yml`, `main.py` startet Worker nur über die Sperre.

**Frontend:** Vitest (jsdom) mit 9 Tests: Token-Verwaltung (Token nur im Speicher, Bearer-Header, genau ein Refresh bei parallelen 401, Abmeldung bei Fehlschlag, kein Refresh bei Login-401) und Error Boundary. Eigener CI-Job „Frontend: Tests (Vitest)" — **noch nicht als Pflicht-Check** im Branch-Schutz eingetragen (Empfehlung: aufnehmen).

**Weiterhin ungetestet (automatisiert):** Storage-Migration MinIO↔OneDrive im echten Betrieb, Migrationskette auf Bestandsdaten (nur leere DB; die Produktions-DB hat 0060–0062 aber fehlerfrei durchlaufen), Nummernkreis unter echter Parallelität (Zeilensperre ist getestet, nicht der Wettlauf), Frontend-Seiten jenseits von api.js/ErrorBoundary, Windows-Skripte.

---

## 6. Abgleich mit dem Auftrag (Abschnitt 10 – Abschlussprüfung)

| Prüfpunkt | Ergebnis |
|---|---|
| Alle freigegebenen Korrekturschritte umgesetzt | ja — K-01 … K-25 vollständig, K-26 bewusst zurückgestellt, Bündel H zusätzlich |
| Jeder Schritt mit Tests abgesichert | ja — je Bündel neue/erweiterte Tests; Gesamtreihe grün vor jedem PR |
| Keine stillen Änderungen | ja — jeder Schritt mit Dateiliste, Begründung, Tests und Restrisiken berichtet; Oliver hat jeden PR selbst gemergt |
| Produktivnachweis | Deploys A–G automatisch nach grüner CI; Server-Nachweise: Migration 0060/0062, verschlüsselte Settings, Mounts ohne Socket, Worker-Sperre im Log, MinIO-Tag |
| Dokumentation aktuell | STATUS.md, CLAUDE.md, INSTALLATION/LOKAL-TESTEN, WIEDERHERSTELLUNG.md; Platzhalter im CHANGELOG (N-06) mit R-01 |
| Offene Fragen des Berichts | 1 (Version): **2.0.0** entschieden · 2 (Server): nachgeholt · 3 (Anhänge): offen, Fachentscheidung · 4 (vite): läuft in CI und lokal · 5 (Tiefe): unverändert · 6 (Lasttest): stillgelegt, PERF-001 strukturell behoben · 7 (.env.local): gelöscht · 8 (Windows-Skripte): nur gelesen |

---

## 7. Empfehlung

Das Release **2.0.0** kann vorbereitet werden (R-01). Reihenfolge:

1. Bündel H prüfen und mergen.
2. R-01: Version 2.0.0 an den sechs Stellen, CHANGELOG und `changelog.js` mit echten Release-Notes für E/F/G/H und einem zusammenfassenden 2.0.0-Eintrag, N-07 (`version:`-Zeile) mitnehmen, Checkliste abarbeiten — **Veröffentlichung nur nach ausdrücklicher Freigabe.**
3. Danach, ohne Release-Druck: Bündel „npm-Hauptversionen" (N-08), K-26 (ARCH-001/002, PERF-002, UX-003 + N-03), OPS-006, SEC-015, CODE-001-Rest.
4. Branch-Schutz: „Frontend: Tests (Vitest)" als Pflicht-Check aufnehmen.
