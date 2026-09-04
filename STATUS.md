# STATUS – DeineZeit

> Lebendes Status-/Logbuch. **Oben** der aktuelle Stand (Snapshot, wird
> überschrieben), **unten** ein chronologisches Logbuch (neue Einträge oben
> anhängen). Release-Details stehen im [CHANGELOG.md](CHANGELOG.md), das „Wie/
> Warum/Was-als-Nächstes" hier.

---

## Aktueller Stand (Snapshot)

- **Version:** siehe `frontend/package.json` / [CHANGELOG.md](CHANGELOG.md) (der pre-commit-Hook hebt sie je Branch an)
- **Branch-Modell:** Feature-Branch → PR → CI (pytest ist Pflicht) → Merge auf `main` → Deploy **nach grüner CI** (`deploy.yml`, `workflow_run`)
- **DB-Migrationsstand:** bis `0061_schema_angleichen`; Modelle und Migrationen sind deckungsgleich (`tests/test_migrationen.py` wacht darüber)
- **Tests:** ~930 pytest-Tests, Laufzeit in CI wenige Minuten
- **Lokale Umgebung:** Docker Compose (`docker-compose.local.yml`) → http://localhost; lokale Werte in `.env.local` (nicht im Repo)

### Module / Funktionsumfang

Zeiterfassung (mit Zeitprojekten, Berichten) · Stammdaten (inkl. Artikelstamm, Import) ·
Projektplanung (Kanban/Gantt) · Aufgaben (mit Mail-Import/KI) · Verkauf (Belege, PDF,
E-Rechnung, Zahlungen, Mahnwesen, Monatsabschluss) · Buchhaltung (Eingangsrechnungen,
UVA, BMD-Export) · Datacenter (Dateien via MinIO/WebDAV/OneDrive) · Postecke ·
Benutzerverwaltung mit Rechtegruppen, 2FA/Passkeys · Dashboard.

### Audit September 2026

Vollständiges Software-Audit am 02.09.2026 — Bericht: [docs/AUDIT-2026-09-02.md](docs/AUDIT-2026-09-02.md).
Umgesetzt in Bündeln (K-01 … K-25): Backups bleiben beim Deploy erhalten und enthalten den
Dateispeicher (+ Restore-Anleitung [docs/WIEDERHERSTELLUNG.md](docs/WIEDERHERSTELLUNG.md)),
XSS-Lücke in der Datacenter-Vorschau geschlossen, Konfigurations-Geheimnisse verschlüsselt,
Endpunkte laufen im Threadpool, FastAPI/Starlette/WeasyPrint aktuell, Ortszeit statt UTC,
Setup-Token, CSP (Report-Only). Offen: In-App-Update/Docker-Socket entfernen (K-21),
Testlücken (K-22), Release 2.0.0 (R-01).

### Bekannte Einschränkungen

- **`UVICORN_WORKERS` muss 1 bleiben:** Die Hintergrund-Worker (Mail-Scan, Wiederkehr,
  Fälligkeit, Postecke, Backup, SSL) laufen als Threads im App-Prozess und liefen mit
  mehreren Prozessen doppelt.
- **Doku ist Windows-zentriert** (`.bat`/`.ps1`); Mac-Workflow steht in [CLAUDE.md](CLAUDE.md).
- **Kein Offline-Modus:** Service Worker bewusst abgeschaltet (alter Code im Cache).
- **Nur Deutsch:** Sprachwahl ausgeblendet, i18n nicht durchgezogen.
- **Excel-Import:** nur `.xlsx` (kein `.xls`).

### Nächste Schritte / To-dos

- Bündel G: K-21 (In-App-Update streichen, Docker-Socket raus), K-22 (Tests: Projektplan, Vitest)
- Abschlussprüfung und Release **2.0.0** (Versionsschreibweise mit führenden Nullen ist in npm nicht zulässig)

---

## Logbuch

### 2026-09-02 … 09-03 – Software-Audit und Korrekturbündel A–F
- Prüfbericht `docs/AUDIT-2026-09-02.md` (45 Befunde, Korrekturplan K-01…K-26).
- Umgesetzt: K-01, A (K-22a, K-02…K-06, Migration 0060), B (K-07…K-09, Migration 0061),
  C (K-10…K-12), D (K-13, K-15, K-17, K-18), E (K-14, K-16, K-19, K-20), F (K-23, K-24, K-25).
- CI-Laufzeit des pytest-Jobs von 84 Minuten auf wenige Minuten (MinIO-Retry in Tests).

### 2026-06-27 – CI-Gate für Tests (Schritt 2)
- `ci.yml`: neuer Job „Backend: Tests (pytest)" mit Postgres-Service-Container;
  setzt `DATABASE_URL`/`TEST_DATABASE_URL`/`SECRET_KEY` und installiert pango/
  cairo (für WeasyPrint-Import). Läuft bei jedem Push und PR.
- YAML-Syntax geprüft (valide, 4 Jobs in Reihenfolge).
- `BRANCH-SCHUTZ.md` erstellt: Anleitung für Oliver, um in den GitHub-Settings
  direktes Pushen auf `main` zu sperren und grüne Tests als Merge-Pflicht zu
  setzen (Feature-Branch + PR-Workflow).
- Offen festgehalten: `deploy.yml` deployt noch ohne Test-Kopplung (Folgepunkt).
- CLAUDE.md (CI-Abschnitt) aktualisiert.

### 2026-06-27 – Teststrategie + pytest-Fundament (Schritt 1)
- `TESTSTRATEGIE.md` erstellt und mit Oliver abgestimmt; Reihenfolge angenommen
  (Backend zuerst, dann CI-Gate, dann Module, dann Frontend).
- Backend-Testgerüst angelegt: `backend/tests/conftest.py` (PostgreSQL-Test-DB,
  TestClient mit überschriebenem `get_db`, Fixtures `test_user`/`admin_user`/
  `auth_client`), `test_health.py`, `test_auth.py` (Vorlage), `tests/README.md`.
- `backend/requirements-dev.txt`, `backend/pytest.ini`, und `./test.sh`
  (Wegwerf-Test-DB im laufenden Container) hinzugefügt.
- CLAUDE.md um Test-Abschnitt + Regel „neues Modul ⇒ neuer Test" ergänzt.
- Statisch verifiziert: Python-/Bash-Syntax ok, URL-Ableitung der Test-DB ok,
  MinIO-Startup ist in try/except gekapselt (Tests laufen ohne MinIO).
- **Offen / nächster Schritt:** `./test.sh` einmal lokal am Mac ausführen und
  grün bestätigen; danach Schritt 2 (CI-Gate + Branch-Schutz).

### 2026-06-27 – Bestandsaufnahme & Projekt-Doku angelegt
- Bestandsaufnahme des Repos durchgeführt (Stack, Struktur, Workflow, CI/CD,
  Versionierung). Ordner ist die Git-Repo-Wurzel, `main` synchron mit Remote.
- **CLAUDE.md** neu erstellt: Tech-Stack, Ordnerstruktur, lokale Mac-Befehle,
  Git-/Versionierungs-Workflow, CI/CD, Konventionen.
- **STATUS.md** (diese Datei) neu erstellt: Snapshot + Logbuch.
- Festgehalten: Mac als lokale Plattform; Versionierung läuft automatisch über
  `auto-version.yml` → nicht manuell bumpen.
- **Offen / nächster Schritt:** Snapshot-Felder „Laufende Baustellen" und
  „Nächste Schritte" mit Olivers aktuellen Arbeitszielen befüllen.

<!--
Vorlage für neue Einträge (jeweils oben einfügen):

### JJJJ-MM-TT – Kurztitel
- Was wurde gemacht
- Was ist offen / nächster Schritt
-->
