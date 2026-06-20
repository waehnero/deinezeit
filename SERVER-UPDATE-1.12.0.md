# Server-Update auf v1.12.0 – Schritt für Schritt

Neues Projektplanungs-Modul. Lokal ist alles committet und nach GitHub
gepusht (Commit `v1.12.0`). Diese Anleitung beschreibt das Update **auf dem
Server**.

> Geschätzte Dauer: wenige Minuten. Plane ein kleines Wartungsfenster ein.

---

## 0. Vorbereitung (lokal, bereits erledigt)

- [x] Version auf `1.12.0` gesetzt (package.json, config.py, beide compose-Dateien)
- [x] CHANGELOG.md mit `1.12.0`-Eintrag
- [x] committet und nach `origin/main` gepusht

Du musst lokal also **nichts mehr tun**.

---

## 1. Backup ziehen (WICHTIG, vor jedem Update)

Auf dem Server, im Projektverzeichnis (z. B. `/opt/deinezeit`):

```
docker compose exec -T db pg_dump -U deinezeit deinezeit > backup_vor_1.12.0.sql
```

So hast du den Stand vor dem Update gesichert, falls etwas schiefgeht.

---

## 2. Code aktualisieren & Container neu bauen

```
git pull
docker compose up -d --build
```

Beim Start führt der Backend-Container automatisch die Datenbank-Migrationen
aus (`alembic upgrade head`) – das legt die neuen Tabellen für das
Projektmodul an (Migrationen **0016–0019**).

> Falls ihr ein `update.sh` nutzt: stattdessen einfach `sh update.sh`
> ausführen – es macht git pull + build in einem.

---

## 3. Migration prüfen

```
docker compose exec -T backend alembic current
```

Erwartet: **`0019 (head)`**.

Tabellen-Kontrolle (optional):

```
docker compose exec -T db psql -U deinezeit -c "\dt planning_*"
```

Erwartet: `planning_projects`, `planning_tasks`,
`planning_task_dependencies`, `planning_milestones`,
`planning_task_fields`, `planning_checklist_items`.

---

## 4. „Projektzeiten" umbenennen (optional, nur wenn gewünscht)

Diese Umbenennung der Stammdaten ist eine reine Datenänderung und **nicht**
in einer Migration enthalten. Nur ausführen, wenn der Stammdaten-Bereich
auch auf dem Server „Projektzeiten" heißen soll:

```
docker compose exec -T db psql -U deinezeit -f /opt/deinezeit/sql/umbenennung-projektzeiten.sql
```

Oder direkt als Einzeiler:

```
docker compose exec -T db psql -U deinezeit -c "UPDATE entity_types SET name='Projektzeiten', slug='projektzeiten' WHERE slug='projekte';"
```

Erwartet: `UPDATE 1`.

> Hinweis: Der Frontend-Code referenziert den neuen Slug `projektzeiten`
> bereits (Projektsuche in der Zeiterfassung). Wenn du diese Umbenennung
> auf dem Server NICHT machst, bleibt der Slug `projekte` – dann findet die
> Projektsuche in der Zeiterfassung nichts mehr. Also: entweder umbenennen
> (empfohlen, konsistent mit dem Code) oder den Code-Slug zurück auf
> `projekte` stellen.

---

## 5. Kontrolle in der App

1. App im Browser öffnen, **Cmd/Strg + Shift + R** (Cache leeren).
2. Einstellungen → System → **Installierte Version: v1.12.0**.
3. Links im Menü erscheint **„Projekte"** – ein Testprojekt mit Aufgabe anlegen.
4. Zeitschiene/Gantt, Checkliste und Kontakt-Zuweisung kurz testen.

---

## 6. Wenn etwas schiefgeht – Rückweg

**Migration zurückrollen** (entfernt die neuen Tabellen samt Planungsdaten):

```
docker compose exec -T backend alembic downgrade 0015
```

**Komplettes Backup zurückspielen** (Stand vor dem Update):

```
cat backup_vor_1.12.0.sql | docker compose exec -T db psql -U deinezeit deinezeit
```

Danach auf den vorherigen Git-Stand zurück:

```
git log --oneline -5        # Commit VOR v1.12.0 finden
git checkout <commit-davor>
docker compose up -d --build
```

---

## Checkliste

- [ ] Backup gezogen (Schritt 1)
- [ ] git pull + build (Schritt 2)
- [ ] alembic current zeigt 0019 (Schritt 3)
- [ ] „Projektzeiten" umbenannt – falls gewünscht (Schritt 4)
- [ ] Version v1.12.0 sichtbar, Modul „Projekte" funktioniert (Schritt 5)
