# Windows-Skripte für die lokale Entwicklung

Doppelklick auf die `.bat`-Datei startet das gleichnamige PowerShell-Skript. Alle
Skripte wechseln selbst in das Repo-Wurzelverzeichnis (zwei Ebenen höher) — sie
funktionieren also nur, solange dieser Ordner `scripts\windows\` im Repo liegt.

| Skript | Wofür |
|---|---|
| `start-lokal.bat` / `.ps1` | DeineZeit lokal starten (Docker Desktop muss laufen): baut die Container, richtet die Datenbank ein, legt beim ersten Mal den Admin an, öffnet http://localhost. Braucht eine `.env.local` im Wurzelverzeichnis (siehe `LOKAL-TESTEN.md`). |
| `stopp-lokal.bat` / `.ps1` | Container stoppen, Daten bleiben erhalten. |
| `reset-lokal.bat` | Alles zurücksetzen — löscht **alle lokalen Testdaten** (`down -v`). |
| `neu-bauen.bat` / `.ps1` | Frontend und Backend ohne Cache neu bauen, Migrationen ausführen. |
| `migriere-kontakte.bat` / `.ps1` | Einmalige Altdaten-Migration Kunden/Lieferanten → Kontakte (historisch, `migrate_kontakte.py` im Backend-Container). |
| `bump-version.ps1` | Version + Changelog von Hand anheben — Windows-Pendant zu `scripts/bump_version.py`; am Mac das Python-Skript verwenden. |
| `git-einrichten.ps1` | Einmalig: Git-Repository und Hooks einrichten. |
| `sicherheits-check.ps1` | Vor einem Deployment: `.env`, `.gitignore`, pip-audit, bandit, Dockerfile und nginx-Header prüfen. |

**Nicht hier, sondern im Wurzelverzeichnis** liegen die Backup-Skripte
(`backup*.ps1`, `backup*.bat`, `wiederherstellen.*`, `backup.cfg`,
`backup-uri-handler.vbs`): Bestehende Windows-Installationen und die
Aufgabenplanung verweisen mit absoluten Pfaden darauf, und
`docker-compose.local.yml` mountet `./backup.cfg`. Sie dürfen nicht verschoben werden.
