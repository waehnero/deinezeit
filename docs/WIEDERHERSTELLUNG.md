# DeineZeit – Sicherung und Wiederherstellung

> Anleitung für den Ernstfall: Server weg, Datenbank kaputt, versehentlich
> gelöscht. Alles hier gilt für die Linux-Server-Installation unter
> `/opt/deinezeit`. Befehle sind **am Server** auszuführen, sofern nicht anders
> angegeben.

---

## Was ein Backup enthält

Seit September 2026 ist ein Backup ein **ZIP-Archiv** (vorher nur ein
SQL-Dump — die Dateien des Objektspeichers waren nicht gesichert):

| Im Archiv | Inhalt |
|---|---|
| `datenbank.sql` | vollständiger PostgreSQL-Dump (Benutzer, Stammdaten, Zeiten, Belege, Einstellungen) |
| `dateien/…` | jede Datei aus dem Objektspeicher (MinIO): Anhänge, PDF-Archiv der Belege, Positions- und Stammdatenbilder, Postecke-Medien |
| `manifest.json` | Zeitpunkt, App-Version, Migrationsstand, Dateiliste, Fehler beim Einsammeln |

**Nicht** im Archiv:
- die Datei **`.env`** (Passwörter, `SECRET_KEY`, `SETUP_TOKEN`) — bitte getrennt und sicher aufbewahren. Ohne den ursprünglichen `SECRET_KEY` sind verschlüsselte Werte (2FA-Secrets, SMTP-/Cloud-Passwörter) nicht lesbar und müssen neu eingerichtet werden.
- das **HTTPS-Zertifikat** (wird bei einer Neuinstallation neu ausgestellt)
- das **Logo** unter `backend/static/` (in den Einstellungen neu hochladen)
- Dateien in **WebDAV/OneDrive** (Mischbetrieb): die liegen extern und stehen nur im Manifest (`externe_anhaenge`)

## Backups erzeugen

- **Von Hand:** Einstellungen → System → „Backup herunterladen" (Administrator).
- **Automatisch:** Einstellungen → Backup → Ziel „OneDrive" und Uhrzeit; das Backend lädt täglich ein Archiv hoch und löscht ältere als `backup_keep_days`.
- **Vor jedem Update:** `scripts/deploy.sh` (manueller Modus) legt `backups/pre-update_*.sql` an — nur die Datenbank.

Große Installationen: `BACKUP_TIMEOUT_SEKUNDEN` in der `.env` erhöht das Zeitlimit für `pg_dump` (Vorgabe 600). Das OneDrive-Backup lädt in einem Stück hoch; ab etwa 200 MB Archivgröße ist der Download von Hand der verlässlichere Weg.

## Wiederherstellung — kompletter Bestand

Voraussetzung: eine laufende Installation (frisch per `install.sh` oder die bestehende).

```bash
# am Server
cd /opt/deinezeit
sudo bash scripts/wiederherstellen.sh /pfad/deinezeit_backup_2026-09-03_02-00.zip
```

Das Skript:
1. sichert den aktuellen Stand nach `backups/vor-wiederherstellung_*.sql`,
2. hält das Backend an (nginx zeigt die Wartungsseite),
3. ersetzt die Datenbank vollständig durch `datenbank.sql`,
4. schreibt alle Dateien aus `dateien/` in den Objektspeicher,
5. zieht Migrationen nach, falls das Archiv älter ist als der Code,
6. startet das Backend.

Danach müssen sich alle Benutzer neu anmelden. Stichprobe: einen Beleg öffnen, einen Anhang herunterladen, ein Positionsbild ansehen.

## Wiederherstellung — nur die Datenbank (z. B. `pre-update_*.sql`)

```bash
# am Server
cd /opt/deinezeit && source .env
docker compose stop backend
docker compose exec -T db psql -U "$DB_USER" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid <> pg_backend_pid();" \
  -c "DROP DATABASE \"$DB_NAME\";" -c "CREATE DATABASE \"$DB_NAME\" OWNER \"$DB_USER\";"
docker compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" < backups/pre-update_JJJJMMTT_HHMMSS.sql
docker compose run --rm backend alembic upgrade head
docker compose up -d backend
```

## Eine Migration zurücknehmen

Nur, wenn ein Update wegen einer Migration zurückgedreht werden muss und der alte Code wieder laufen soll:

```bash
# am Server
docker compose run --rm backend alembic downgrade 0061      # Ziel = letzte Migration des alten Standes
```

Hinweis: Migration 0060 (Verschlüsselung der Einstellungs-Geheimnisse) entschlüsselt beim Downgrade **nicht** — SMTP-/Cloud-Passwörter wären mit altem Code neu einzutragen.

## Neuer Server von Null

1. `install.sh` wie in `INSTALLATION.md` (Domain, Zertifikat, erster Admin).
2. **`.env` aus der alten Installation einspielen** — mindestens `SECRET_KEY`, sonst 2FA und verschlüsselte Passwörter neu einrichten. Danach `docker compose up -d --force-recreate`.
3. `scripts/wiederherstellen.sh <archiv>`.
4. Logo in den Einstellungen neu hochladen; OneDrive/WebDAV-Anbindung prüfen.

## Was regelmäßig geprüft gehört

- Einstellungen → Backup: „Letztes Backup" ist nicht älter als ein Tag.
- Einmal im Quartal: ein Archiv auf einer lokalen Docker-Instanz (`docker-compose.local.yml`) einspielen und hineinschauen. Ein Backup, das nie zurückgespielt wurde, ist ein Hoffnungswert.
- `manifest.json` → `fehler` ist leer. Steht dort etwas, konnte eine Datei nicht gelesen werden.

## Windows-Skripte (`backup.ps1`, `wiederherstellen.ps1`)

Sie sichern nur die Datenbank der **lokalen Windows-Instanz** per `pg_dump` und sind kein Ersatz für das Archiv des Servers.
