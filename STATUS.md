# STATUS – DeineZeit

> Lebendes Status-/Logbuch. **Oben** der aktuelle Stand (Snapshot, wird
> überschrieben), **unten** ein chronologisches Logbuch (neue Einträge oben
> anhängen). Release-Details stehen im [CHANGELOG.md](CHANGELOG.md), das „Wie/
> Warum/Was-als-Nächstes" hier.

---

## Aktueller Stand (Snapshot)

- **Version:** 1.12.14 (Stand 26.06.2026, siehe CHANGELOG)
- **Branch:** `main`, synchron mit `origin/main` (sauberer Working Tree)
- **Letzter Commit:** `fe65af4 – chore: Version 1.12.14 – Zeiterfassung Datei-Upload repariert`
- **DB-Migrationsstand:** bis `0020_attachment_kontakt`
- **Lokale Umgebung:** Docker Compose (`docker-compose.local.yml`) → http://localhost

### Module / Funktionsumfang

Zeiterfassung · Stammdaten · Projektplanung (Kanban/Gantt, Migration 0016+) ·
Rechnungen (PDF via WeasyPrint) · Buchhaltung · Datacenter (Dateien via MinIO,
nach Modul/Kontakt organisiert) · Benutzerverwaltung mit 2FA/Passkeys ·
PWA-Installation.

### Laufende Baustellen / offene Punkte

- **CI/CD-Pipeline steht und funktioniert (✓):** Kompletter Ablauf scharf:
  lokal `./test.sh` → Feature-Branch + PR → CI-Tests „Backend: Tests (pytest)"
  müssen grün sein (Branch-Schutz-Regel „Schutz main - Tests erforderlich",
  aktiv, Pflicht-Check) → Merge nach `main` → **automatisches Deployment** auf
  den Hetzner-Server (dz.wwinterface.online) via `deploy.yml`. Deploy-Secrets
  (`SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, `DEPLOY_PATH`) sind hinterlegt;
  erstes erfolgreiches Auto-Deployment am 28.06.2026 (Run #130, Commit 28685a8).
- **Kleinere offene Punkte CI/CD:**
  - `deploy.yml`-Healthcheck zeigt noch auf Platzhalter `https://deine-domain.at`
    statt `dz.wwinterface.online` → Healthcheck prüft falsche Adresse (Deploy
    selbst läuft, nur die Abschlussprüfung greift ins Leere). Korrigieren.
  - Warnung „Node.js 20 deprecated" in den Actions (`webfactory/ssh-agent`,
    `actions/checkout`) – unkritisch, bei Gelegenheit Action-Versionen anheben.
- **Abhängigkeits-Updates (offen, Folgeschritt):** pip-audit meldet bekannte
  Schwachstellen in `pillow`, `python-dotenv`, `requests`, `weasyprint`,
  `jinja2`, `starlette`. Bereits erledigt: `python-jose` 3.3.0→3.5.0,
  `python-multipart` 0.0.9→0.0.32. Der pip-audit-CI-Schritt ist vorerst
  **nicht blockierend** (warnt, blockiert Merge nicht). Restliche Updates
  kontrolliert einzeln nachziehen (Achtung: `starlette`/FastAPI-Kopplung,
  `weasyprint` betrifft Rechnungs-PDFs) – jeweils mit den Tests absichern.
- **Schritt 3/4 (offen):** Tests je bestehendem Modul; danach Frontend (Vitest).

### Bekannte Probleme / Risiken

- **Doku ist Windows-zentriert** (`.bat`/`.ps1`, „Doppelklick", Pfad
  `C:\Projekte\deinezeit`); Mac-Workflow ist in [CLAUDE.md](CLAUDE.md) ergänzt,
  aber die Endnutzer-Anleitungen (`LOKAL-TESTEN.md`, `MIGRATION-…`, Handoffs)
  beschreiben weiterhin Windows.
- **Push auf `main` löst automatisches Deployment aus** (`deploy.yml`) — also
  nur nach Freigabe und bestandenem lokalem Test pushen.

### Nächste Schritte / To-dos

- _(offen — von Oliver festzulegen)_

---

## Logbuch

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
