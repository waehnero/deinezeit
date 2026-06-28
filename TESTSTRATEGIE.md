# Teststrategie – DeineZeit (Entwurf zur Freigabe)

> **Status: Vorschlag – noch nicht umgesetzt.** Diese Notiz beschreibt, *wie*
> wir automatisierte Tests einführen, bevor Code entsteht. Oliver entscheidet
> über Architektur und Reihenfolge; nach Freigabe baut Claude Schritt 1.

---

## Ziel

Automatisierte Tests, die **gezielt laufen, bevor Erweiterungen und Anpassungen
in den `main`-Code übernommen werden**. Grundsatz: **Jedes neue Modul und jede
Änderung bringt sofort eigene Tests mit**, damit die Weiterentwicklung
mitgetestet bleibt und nichts „außen vor" gerät.

Heute gibt es **keine** automatisierten Tests; „Testen" heißt manuell lokal mit
Docker. Die CI prüft bisher nur Sicherheit (pip-audit, bandit) und Docker-Build.

---

## Warum das Backend zuerst

Die Geschäftslogik liegt im Backend (Auth/2FA/Passkeys, Rechnungen, Buchhaltung,
Zeiterfassung, Datacenter). Fehler dort sind am teuersten. Die Codestruktur ist
bereits gut testbar:

- `get_db` ist eine FastAPI-Dependency → im Test per `app.dependency_overrides`
  durch eine **Wegwerf-Test-DB** ersetzbar.
- `security.py` kapselt Hashing/Token sauber (`get_password_hash`,
  `create_access_token`, …) → gut für Unit-Tests.
- Es gibt einen `/api/health`-Endpoint → idealer erster Smoke-Test.
- `auth.py` (login → `/me`) ist die natürliche Vorlage für den ersten
  Integrationstest.

---

## Tooling

**Backend (zuerst):**
- **pytest** – Test-Runner
- **httpx** + FastAPI `TestClient` – API-Integrationstests (httpx ist schon
  Dependency)
- **eigene Test-Datenbank** – PostgreSQL im Container (gleiche DB wie produktiv,
  damit Tests realistisch sind), pro Lauf frisch aufgesetzt und am Ende verworfen
- Fixtures in `conftest.py`: Test-DB-Session, Test-Client mit überschriebener
  `get_db`-Dependency, Hilfs-Fixture „eingeloggter Benutzer" (Token)

**Frontend (spätere Etappe):**
- **Vitest** + **React Testing Library** (passt zu Vite, kein neuer Build-Stack)

---

## Ordnerstruktur (Vorschlag)

```
backend/
├── app/
└── tests/
    ├── conftest.py            # Fixtures: Test-DB, Client, Auth-Helfer
    ├── test_health.py         # Smoke-Test (erster, einfachster Test)
    ├── test_auth.py           # Login, /me, falsches Passwort, Token nötig
    └── test_<modul>.py        # je Fachmodul eine Datei (gleiches Schema)
```

Pro Domäne **eine** Testdatei mit gleichem Namen wie das Modul
(`test_zeiterfassung.py`, `test_invoice.py`, …) – spiegelt den bestehenden
Domänen-Schnitt (`api/`, `models/`, `schemas/`, `services/`).

---

## Lokal testen (Mac/Docker)

Ein Skript **`./test.sh`** (Pendant zu `check.sh`/`start-arbeit.sh`), das die
Tests in einem Wegwerf-Container gegen eine frische Test-DB laufen lässt – damit
vor jedem Push lokal geprüft werden kann:

```bash
./test.sh          # baut Test-Umgebung, führt pytest aus, räumt auf
```

(Genauer Mechanismus – eigener compose-Service vs. `exec` im laufenden Backend –
wird in Schritt 1 festgelegt.)

---

## Workflow: Tests als Schutz für `main`

Heute geht jeder Commit direkt auf `main` und löst **sofort Deployment** aus
(`deploy.yml`). Damit „Tests bevor etwas in den Master kommt" wirkt, braucht es
einen Schritt **vor** `main`. Vorschlag (zur Entscheidung):

1. Entwicklung auf **Feature-Branch** (`feature/...`).
2. **Pull Request** nach `main`.
3. CI führt **Tests** aus → müssen **grün** sein (Pflicht-Gate / „required check").
4. Erst dann **Merge** nach `main` → Deployment.

> Alternativen, falls der PR-Schritt zu viel ändert: (a) Tests laufen in CI und
> melden nur rot/grün, `main` bleibt direkt bespielbar (weniger Schutz); oder
> (b) eigener `develop`-Branch zum Sammeln/Testen, `main` nur für Releases.
> **Diese Entscheidung steht noch aus.**

Die **Regel „neue Module ⇒ neue Tests"** wird zusätzlich in [CLAUDE.md](CLAUDE.md)
verankert, damit sie bei jeder künftigen Arbeit automatisch gilt.

---

## Vorgeschlagene Reihenfolge

1. **Backend-Fundament:** `pytest` + `conftest.py` + Test-DB + `test_health.py`
   (Smoke) und `test_auth.py` (Login/`/me`) als kopierbare Vorlage. **`./test.sh`**
   zum lokalen Ausführen.
2. **CI-Gate scharf schalten:** Tests in `ci.yml` ergänzen; Branch-/Merge-Schutz
   nach Olivers Entscheidung oben.
3. **Tests je bestehendem Modul** nachziehen (zeiterfassung, invoice, …) – nach
   dem Vorlagen-Schema.
4. **Frontend-Tests** (Vitest) als eigene Etappe.

---

## Offene Entscheidungen für Oliver

- **Branch-Workflow:** Feature-Branch + PR-Gate, oder CI-nur, oder `develop`-Branch?
- **Lokaler Testlauf:** `./test.sh` gewünscht (ja/nein)?
- **Reihenfolge:** mit Schritt 1 (Backend-Fundament) starten?
