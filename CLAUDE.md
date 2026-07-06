# CLAUDE.md – DeineZeit

> Arbeitsanweisung für Claude in diesem Repo. Oliver ist für Architektur und
> Funktionsgestaltung zuständig; Claude programmiert nach seinen Vorgaben.
> **Kommunikation auf Deutsch.** Nichts ungefragt committen oder pushen.

---

## Was ist DeineZeit?

Selbst-gehostete WebApp für **Zeiterfassung, Stammdaten, Projektplanung,
Rechnungen, Buchhaltung und einen Datei-„Datacenter"-Bereich**. Läuft komplett
in Docker (Backend, Frontend, PostgreSQL, MinIO, nginx, certbot) und wird per
GitHub Actions auf einen eigenen Linux-Server deployed. PWA-fähig (installierbar
über „Zum Home-Bildschirm").

- **Repo:** https://github.com/waehnero/deinezeit (Branch: `main`)
- **Aktuelle Version:** siehe [STATUS.md](STATUS.md) / [CHANGELOG.md](CHANGELOG.md)

---

## Tech-Stack

**Backend** (`backend/`)
- Python 3.12, **FastAPI** 0.111 + Uvicorn
- **SQLAlchemy** 2.0 + **Alembic** (Migrationen), PostgreSQL 16
- Auth: JWT (python-jose), Passwörter (passlib/bcrypt), 2FA/TOTP (pyotp),
  **WebAuthn/Passkeys** (webauthn / @simplewebauthn im Frontend)
- Rate-Limiting: slowapi
- PDF-Erzeugung: WeasyPrint + Jinja2 (Rechnungen)
- Objektspeicher: **MinIO** (S3-kompatibel) für Datei-Uploads
- E-Mail-Vorschau: extract-msg

**Frontend** (`frontend/`)
- **React 18** + **Vite 5**, React Router 6
- State: **Zustand**; Formulare: react-hook-form
- UI: **Tailwind CSS 3**, lucide-react Icons, react-hot-toast
- i18n: i18next (mehrsprachig)
- Editor: TipTap; Drag&Drop: @dnd-kit (Kanban/Gantt); CSV: papaparse
- **PWA:** vite-plugin-pwa (Service Worker, Manifest)

**Infrastruktur**
- Docker Compose; nginx als Reverse-Proxy; certbot für SSL (Let's Encrypt)
- CI/CD: GitHub Actions (siehe unten)

---

## Ordnerstruktur

```
deinezeit/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI-App, Router-Registrierung, CORS, Rate-Limit
│   │   ├── api/               # Endpunkte: auth, users, masterdata, zeiterfassung,
│   │   │                      #   reports, settings, datacenter, system, invoice,
│   │   │                      #   accounting, projektplan, deps
│   │   ├── core/              # config.py (Settings/Env), security.py
│   │   ├── db/                # DB-Session / Base
│   │   ├── models/            # SQLAlchemy-Modelle (ein Modul je Domäne)
│   │   ├── schemas/           # Pydantic-Schemas
│   │   └── services/          # auth, email, invoice_pdf, masterdata, storage (MinIO)
│   ├── alembic/versions/      # Migrationen 0001..0020 (durchnummeriert)
│   ├── Dockerfile
│   └── entrypoint.sh          # führt `alembic upgrade head` aus, startet uvicorn
├── frontend/
│   ├── src/
│   │   ├── pages/             # Seiten (Dashboard, Zeiterfassung, Projektplan, …)
│   │   ├── components/        # KanbanBoard, GanttChart, RichTextEditor, Layout, …
│   │   ├── services/api.js    # axios-Client
│   │   ├── contexts/  data/  i18n/  utils/
│   ├── Dockerfile             # Multi-Stage: node build → nginx
│   └── nginx.conf
├── nginx/                     # Reverse-Proxy-Konfig (conf.d/app.conf prod, local.conf lokal)
├── sql/                       # manuelle SQL-Hilfen (Einzelfälle)
├── scripts/                   # auto_version.py, deploy.sh
├── .github/workflows/         # ci.yml, deploy.yml, auto-version.yml
├── docker-compose.yml         # PRODUKTION (db, minio, backend, frontend, nginx, certbot)
├── docker-compose.local.yml   # LOKAL (http://localhost, MinIO-Console :9001)
├── check.sh                   # Lese-Statuscheck (ändert nichts)
├── start-arbeit.sh            # zieht sauber den neuesten Stand (nur wenn working tree clean)
├── frontend-neu-bauen.sh      # Frontend ohne Cache neu bauen (für Service-Worker-Änderungen)
└── CHANGELOG.md               # release-orientierte Änderungshistorie
```

---

## Lokal entwickeln (macOS — dieser Rechner)

Voraussetzung: **Docker Desktop für Mac** läuft (Wal-Symbol aktiv). Alles läuft
in Containern; lokale Python-/Node-Installationen sind nicht nötig.

```bash
# 1. Vor jeder Aufgabe: sauberen, aktuellen Stand holen
./start-arbeit.sh          # macht git pull NUR wenn working tree clean ist

# 2. Lokal starten / neu bauen  → http://localhost
docker compose -f docker-compose.local.yml up -d --build

# 3. Status / Logs
docker compose -f docker-compose.local.yml ps
docker compose -f docker-compose.local.yml logs -f backend

# 4. Stoppen
docker compose -f docker-compose.local.yml down

# Nur Frontend ohne Cache neu bauen (z.B. nach Service-Worker-/PWA-Änderungen)
./frontend-neu-bauen.sh
# danach im Browser http://localhost/sw-reset.html aufrufen (alten SW löschen)
```

> **MinIO-Console** lokal: http://localhost:9001 (Login `minioadmin` /
> `minioadmin123`, sofern in `.env` nicht überschrieben).

**„Bin ich richtig?"-Check** (reine Leseprüfung — Ordner, Branch, uncommittete
Änderungen, Sync mit GitHub, Versionskonsistenz):

```bash
./check.sh
```

> Die `.bat`/`.ps1`-Skripte (`start-lokal.bat`, `neu-bauen.bat`,
> `bump-version.ps1`, …) sind die **Windows-Pendants**. Am Mac stattdessen die
> oben genannten `docker compose`-Befehle bzw. `.sh`-Skripte verwenden.

### Datenbank / Migrationen

Migrationen laufen beim Backend-Start automatisch (`entrypoint.sh` →
`alembic upgrade head`). Manuell im laufenden Container:

```bash
docker compose -f docker-compose.local.yml exec backend alembic upgrade head
# Neue Migration erzeugen (nach Modell-Änderung):
docker compose -f docker-compose.local.yml exec backend \
  alembic revision --autogenerate -m "kurze beschreibung"
```

> Migrationen sind **durchnummeriert** (`0001_…` … `0020_…`). Neue Migration mit
> der nächsten Nummer + sprechendem Namen anlegen, Reihenfolge nicht brechen.

---

## Konfiguration (.env)

`.env` ist **nicht** eingecheckt (steht in `.gitignore`). Vorlage:
`.env.example`. Pflichtfelder (von CI geprüft): `DB_USER`, `DB_PASSWORD`,
`DB_NAME`, `SECRET_KEY`, `FRONTEND_URL`, `DOMAIN`, `APP_ENV`. Niemals echte
Secrets committen — die CI bricht sonst ab.

---

## Git-Workflow & Versionierung

### 🧭 Merkzettel: So entwickle ich ein Modul/Feature weiter

> **Pro Modul/Feature eine eigene Unterhaltung** im Projekt „deinezeit" starten
> (Kontext bleibt erhalten, jede Unterhaltung bleibt fokussiert). Einstieg z. B.:
> „Wir arbeiten am Modul X, leg einen Feature-Branch an."

1. **Sauberen Stand holen:** `./start-arbeit.sh`
2. **Feature-Branch anlegen** (nicht direkt auf `main`):
   `git checkout -b feature/kurzname`
3. **Entwickeln + lokal testen:**
   - `docker compose -f docker-compose.local.yml up -d --build` → http://localhost
   - `./test.sh` (müssen grün sein)
   - **Regel: neues/geändertes Modul ⇒ neuer Test** (`backend/tests/test_<modul>.py`,
     Schema wie `test_auth.py`).
4. **Hochladen** (GitHub Desktop: „Publish branch" / ⌘P) → **Pull Request öffnen**.
5. **Mergen** — geht erst, wenn die Pflicht-Tests grün sind (Branch-Schutz
   blockiert sonst). **Nach dem Merge deployt es automatisch** auf
   dz.wwinterface.online (`deploy.yml`).

> `main` ist geschützt: direktes Pushen ist gesperrt, Merge nur über PR mit
> grünem Check „Backend: Tests (pytest)". Deploy-Ziel-Domain steckt in der
> GitHub-Variable `DOMAIN` (umstellbar ohne Code-Änderung). Der Sicherheits-Job
> (pip-audit/bandit) **warnt nur** und blockiert den Merge nicht.

---

1. **Vor der Arbeit:** `./start-arbeit.sh` (holt sauberen Stand).
2. Entwickeln → **lokal testen** (`docker compose -f docker-compose.local.yml up -d --build`).
3. **Erst nach Olivers Freigabe** committen/pushen. Claude pusht nie ungefragt.

**Versionierung läuft automatisch beim Committen** (per pre-commit-Hook). Auf
einem Feature-Branch hebt der Hook `.githooks/pre-commit` beim **ersten** Commit
die Patch-Version **einmal pro Branch** an (`scripts/bump_version.py`) und nimmt
alle 6 Versions-Dateien in den Commit auf — inkl. Changelog-Eintrag. So bleibt
die im Login-Fenster angezeigte Version/Changelog-Liste automatisch aktuell,
ohne direkten Push auf das geschützte `main`. Der Bump landet über den PR in
`main`; danach deployt es und die neue Version ist live.

**Einmalig aktivieren** (Hook einschalten — sonst passiert nichts):

```bash
git config core.hooksPath .githooks
```

- Titel/Changelog-Text werden aus dem Branch-Namen abgeleitet; bei Bedarf
  vorher gezielt setzen: `python3 scripts/bump_version.py --title "…" --update "…"`.
- Änderungen an changelog.js/CHANGELOG.md im selben Branch verfeinern den Text
  (es wird pro Branch nur **einmal** hochgezählt).
- Bump ausnahmsweise überspringen: `git commit --no-verify`.

> **Hinweis:** Die alte GitHub-Action `auto-version.yml` (Post-Push-Bump auf
> `main`) ist **deaktiviert** — sie scheiterte am Branch-Schutz (direkter Push
> auf `main` gesperrt). Nicht reaktivieren, solange kein Bot-Bypass existiert.
> `bump-version.ps1` ist das Windows-Pendant zu `bump_version.py`.

> Hinweis: GitHub Desktop u. ä. hinterlassen manchmal eine verwaiste
> `.git/index.lock`. `check.sh` räumt sie auf, wenn kein git-Prozess läuft.

---

## CI/CD (GitHub Actions)

- **`ci.yml`** — bei jedem Push/PR: Backend-Sicherheit (pip-audit, bandit),
  **Backend-Tests (pytest gegen Postgres-Service)**, Docker-Images bauen,
  `.env.example`-Vollständigkeit & Secret-/nginx-Header-Checks.
- **`auto-version.yml`** — **deaktiviert** (scheiterte am Branch-Schutz). Der
  Versions-Bump passiert jetzt lokal beim Committen per pre-commit-Hook (s. o.).
- **`deploy.yml`** — bei Push auf `main`: per SSH/rsync auf den Server,
  `docker compose build` + `alembic upgrade head` + Neustart + Healthcheck.
  Nötige Secrets: `SSH_HOST`, `SSH_USER`, `SSH_PRIVATE_KEY`, `DEPLOY_PATH`.

### Automatisierte Tests (Backend)

Es gibt **pytest-Tests** im Backend (`backend/tests/`). Lokal ausführen (Mac):

```bash
./test.sh                      # alle Tests gegen eine Wegwerf-Test-DB
./test.sh tests/test_auth.py   # gezielt
```

Fixtures in `backend/tests/conftest.py` (Test-DB, Client, `auth_client`);
`test_auth.py` dient als Vorlage. Details: `backend/tests/README.md`.

> **Regel: Neues Modul ⇒ neuer Test.** Jede neue oder geänderte Domäne bringt
> eine eigene `tests/test_<modul>.py` mit (gleiches Schema wie `test_auth.py`),
> damit die Weiterentwicklung mitgetestet bleibt.

> Frontend-Tests (Vitest) sind noch nicht eingerichtet (geplante Etappe).
> Über die Backend-Tests hinaus heißt „testen" weiterhin auch: lokal mit Docker
> hochfahren und manuell prüfen.

---

## Konventionen

- **Sprache:** Code-Kommentare, Commit-Messages, UI-Texte und Changelog auf
  **Deutsch**. Benutzersichtbare Texte im Frontend über i18next.
- **Domänen-Schnitt:** pro Fachbereich je ein Modul in `api/`, `models/`,
  `schemas/`, `services/` (gleicher Name, z. B. `invoice.py`). Neue Features
  diesem Muster folgend ergänzen.
- **API-Präfix:** alle Router unter `/api` (siehe `main.py`).
- **Migrationen:** durchnummeriert; nie nachträglich umnummerieren.
- **Zeilenenden** (`.gitattributes`): `.sh` = LF, `.bat/.ps1/.cmd` = CRLF.
- **Doku:** nutzerorientierte Anleitungen sind bewusst einfach gehalten und
  überwiegend für Windows-Endnutzer geschrieben — beim Erweitern Ton beibehalten.

---

## Was Claude NICHT tut

- Nicht ungefragt committen oder nach `origin/main` pushen (löst Deploy aus!).
- Version nicht von Hand in den Dateien ändern — der pre-commit-Hook bumpt
  automatisch (einmal pro Branch). Bei Bedarf `scripts/bump_version.py` nutzen.
- Keine Secrets / `.env`-Inhalte committen.
- Migrationen nicht umnummerieren oder bestehende verändern.
- Keine destruktiven Aktionen am Server/an der DB ohne ausdrückliche Freigabe.
