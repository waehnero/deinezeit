# Release 2.0.0 – Checkliste

**Datum:** 04.09.2026 · **Anlass:** Abschluss des Software-Audits vom 02.09.2026
(Bericht: [AUDIT-2026-09-02.md](AUDIT-2026-09-02.md), Abschlussprüfung: [AUDIT-2026-09-02-ABSCHLUSS.md](AUDIT-2026-09-02-ABSCHLUSS.md))
**Versionsschreibweise:** `2.0.0` (semver; „2.00.00" wäre in npm ungültig — Entscheidung 03.09.2026)

> Nichts aus dieser Liste wird ohne ausdrückliche Freigabe ausgeführt. Der Deploy
> läuft wie bei jedem Merge automatisch nach grüner CI; Tag und GitHub-Release
> legt Oliver von Hand an.

---

## 1. Was dieses Release enthält

Ausschließlich die Ergebnisse des Audits (Bündel K-01, A–H) — keine neuen Fachfunktionen
über die Audit-Korrekturen hinaus. Zusammenfassung siehe [CHANGELOG.md](../CHANGELOG.md), Eintrag 2.0.0.

Technischer Umfang gegenüber 1.12.75 (Stand vor dem Audit): 3 Migrationen (0060–0062),
88 neue Backend-Tests, Vitest-Grundgerüst, kein In-App-Update mehr, CSP scharf.

## 2. Vorbedingungen (vor dem Merge)

- [ ] `main` enthält Bündel H (PR grün, gemergt, Deploy erfolgreich) — ✅ 04.09.2026
- [ ] Release-Branch `release/2.0.0` aus aktuellem `main`
- [ ] Version `2.0.0` an allen sechs Stellen (`frontend/package.json`, `frontend/package-lock.json` (Wurzelpaket),
      `backend/app/core/config.py`, `docker-compose.yml`, `docker-compose.local.yml`, `frontend/src/data/changelog.js`) + `CHANGELOG.md`
- [ ] Release-Notes: 2.0.0-Eintrag und echte Texte für die Bündel A–H (keine Platzhalter mehr auf der Anmeldeseite)
- [ ] `./test.sh` grün (961), `cd frontend && npm test` grün (9), `docker compose -f docker-compose.local.yml up -d --build` startet
- [ ] Anmeldeseite lokal zeigt „2.0.0" im Änderungsprotokoll; Einstellungen → System zeigt v2.0.0
- [ ] **Backup vor dem Deploy:** Einstellungen → Backup → „Backup herunterladen" (ZIP mit `manifest.json`) sicher ablegen
- [ ] Normal committen: Der pre-commit-Hook bumpt nicht (Version weicht schon von `main` ab) und prüft nur, dass alle sechs Stellen übereinstimmen

## 3. Deploy

- [ ] PR `release/2.0.0` → `main`, Pflicht-Checks grün, mergen
- [ ] GitHub Actions: „CI – Qualitätsprüfung" grün → „Deploy" grün (Healthcheck bestanden)

## 4. Nachweis am Server (`/opt/deinezeit`)

```bash
cd /opt/deinezeit && set -a && . ./.env && set +a
docker compose ps                                         # alle Container Up, backend healthy
curl -s https://localhost/api/health -k                   # {"status":"ok","version":"2.0.0"}
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -c "SELECT version_num FROM alembic_version;"   # 0062
docker compose logs backend 2>&1 | grep -c "Worker-Sperre erhalten"                                       # 1
docker inspect deinezeit_backend --format '{{range .Mounts}}{{.Destination}} {{end}}'                    # kein docker.sock
```

Im Browser (dz.wwinterface.online):
- [ ] Anmeldung, Dashboard, Zeiterfassung (Nachtragen mit Aufgabe), Verkauf (Beleg-PDF), Datacenter (PDF-Vorschau)
- [ ] Einstellungen → System: v2.0.0, kein Update-Knopf, HTTPS-Karte ohne Warnung
- [ ] Browser-Konsole ohne „Refused to …" (CSP)

## 5. Tag und GitHub-Release (Oliver, von Hand)

```bash
# lokal, auf main nach dem Merge
git checkout main && git pull
git tag -a v2.0.0 -m "DeineZeit 2.0.0 – Abschluss Software-Audit 09/2026"
git push origin v2.0.0
```

GitHub → Releases → „Draft a new release" → Tag `v2.0.0` → Text aus `CHANGELOG.md` (Eintrag 2.0.0) →
Anhang: keine (Docker-Images werden am Server gebaut).

## 6. Rückweg (falls nötig)

Kein Schemabruch zwischen 1.12.84 und 2.0.0 — das Release ändert nur Versionsnummern und Changelog.
Ein Rückweg auf einen älteren Stand ist deshalb ein gewöhnlicher Rollback:

1. `git revert` des Release-Merges auf `main` → CI → Deploy (empfohlen), **oder**
2. am Server `git checkout <commit>` + `sudo bash scripts/deploy.sh` (manueller Pfad).

Migrationen: 0062 ist reine Datenbereinigung (`downgrade` ist ein No-op); 0061 hat einen
`downgrade`-Pfad (stellt die Löschkaskaden wieder her). 0060 lässt beim `downgrade` die Geheimnisse
**verschlüsselt** liegen — ein Programmstand vor 1.12.77 könnte sie nicht lesen (SMTP, Cloud, KI
wären dann ohne Zugangsdaten). Ein Rollback auf einen Stand vor Bündel A (1.12.77) ist deshalb
nicht vorgesehen; innerhalb 1.12.77 … 2.0.0 ist jeder Stand austauschbar.

## 7. Nach dem Release

- [ ] Branch-Schutz `main`: „Frontend: Tests (Vitest)" als Pflicht-Check ergänzen
- [ ] Verwaisten Lasttest-Container aufräumen: `docker rm -f deinezeit-locust` (lokal)
- [ ] Offene Punkte aus der Abschlussprüfung einplanen (Abschnitt 7 dort): npm-Hauptversionen, K-26, OPS-006, SEC-015
- [ ] Fachentscheidung offene Frage 3 (Anhänge für alle angemeldeten Benutzer)
