# Modul „Projekte" aktivieren (Migration 0016)

Diese Anleitung aktiviert das neue **Projekt-Aufzeichnungstool** in deiner
lokalen DeineZeit-Installation. Der Code liegt bereits im Projekt – es fehlen
nur die neuen Datenbank-Tabellen.

> Geschätzte Dauer: ein paar Minuten (Container-Neubau).

---

## Schritt 1 – Neu bauen (macht die Migration automatisch)

Doppelklick auf:

```
neu-bauen.bat
```

Dieses Skript erledigt alles in einem Rutsch:

1. stoppt die Container
2. baut Frontend + Backend neu
3. wartet, bis die Datenbank bereit ist
4. **führt `alembic upgrade head` aus** → legt die neuen Tabellen an
   (`planning_projects`, `planning_tasks`, `planning_task_dependencies`,
   `planning_milestones`) und ergänzt `time_entries` um `task_id`
5. wartet, bis die Webseite erreichbar ist

Wenn am Ende **„Fertig! DeineZeit laeuft unter http://localhost"** steht,
ist die Migration durch.

> Den Hinweis „Naechster Schritt: migriere-kontakte.bat" kannst du hier
> ignorieren – der betrifft ein anderes Thema.

---

## Schritt 2 – App öffnen und testen

1. http://localhost öffnen und einloggen.
2. Links im Menü erscheint jetzt der neue Punkt **„Projekte"**.
3. Test:
   - Auf **„Neues Projekt"** tippen, einen Namen vergeben (z. B.
     „Wohnhaus Mariahilf"), anlegen.
   - Im Projekt unten auf **„Aufgabe"** tippen, ein paar Aufgaben erfassen
     (mit „Speichern & weiter" geht es schnell hintereinander).
   - Bei einer Aufgabe auf das **+** rechts → Teilaufgabe anlegen.
   - Eine Aufgabe antippen → im Detail **„Zu Detailprojekt machen"** testen.

---

## Schritt 3 – Rückmeldung an Claude

Sag kurz Bescheid:

- Erscheint der Menüpunkt **„Projekte"**? (ja/nein)
- Kannst du Projekt + Aufgaben + Teilaufgaben anlegen? (ja/nein)
- Kommt **irgendeine Fehlermeldung**? → bitte den genauen Text kopieren.

Danach baue ich die nächste Stufe: **Kanban-Board**, **Gantt mit kritischem
Pfad** und den **„Zeit starten"-Button** (Anbindung an die bestehende
Zeiterfassung).

---

## Falls etwas schiefgeht

**Die Migration meldet einen Fehler / „Projekte" fehlt trotz Neubau**
Migration manuell nachholen (im Projektordner, Konsole):

```
docker compose -f docker-compose.local.yml exec -T backend alembic upgrade head
```

**Prüfen, welche Migration aktiv ist:**

```
docker compose -f docker-compose.local.yml exec -T backend alembic current
```

→ sollte `0016` anzeigen.

**Tabellen prüfen (optional):**

```
docker compose -f docker-compose.local.yml exec -T db psql -U deinezeit -c "\dt planning_*"
```

→ sollte die vier `planning_*`-Tabellen listen.

**Zurückrollen (nur im Notfall):**

```
docker compose -f docker-compose.local.yml exec -T backend alembic downgrade 0015
```

> Achtung: `downgrade` löscht die neuen Tabellen samt erfasster Planungsdaten.
