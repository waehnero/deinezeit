# Backend-Tests

Automatisierte Tests für das DeineZeit-Backend (pytest).

## Ausführen (Mac/Docker)

Lokale Umgebung starten, dann im Projekt-Wurzelverzeichnis:

```bash
./test.sh                      # alle Tests
./test.sh tests/test_auth.py   # gezielt eine Datei
```

`test.sh` legt eine separate Wegwerf-Test-DB an (`<DB_NAME>_test`), führt pytest
im backend-Container aus und löscht die Test-DB danach wieder. Die normale
Entwicklungs-DB wird nicht berührt.

## Aufbau

- `conftest.py` – gemeinsame Fixtures:
  - `db_session` – frische Test-DB pro Test (Tabellen werden an- und abgebaut)
  - `client` – FastAPI-TestClient mit Test-DB (get_db überschrieben)
  - `test_user` / `admin_user` – angelegte Benutzer
  - `auth_client` – wie `client`, aber bereits eingeloggt (Bearer-Token gesetzt)
- `test_health.py` – Smoke-Test
- `test_auth.py` – Login/`/me`/Fehlerfälle, zugleich **Vorlage** für neue Module

## Neues Modul = neuer Test

Für jedes neue oder geänderte Modul `xy` eine `tests/test_xy.py` nach dem Muster
von `test_auth.py` anlegen und die vorhandenen Fixtures wiederverwenden. So
bleibt jede Weiterentwicklung abgesichert.
