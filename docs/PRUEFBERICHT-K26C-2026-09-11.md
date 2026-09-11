# Prüfbericht – Bündel K-26c: Rest aus dem Audit (Version 2.0.5)

**Datum:** 11.09.2026 · **Anlass:** Audit-Befunde OPS-006 (Logging ohne Anfragekennung), CODE-001-Rest
(`raise` ohne `from`, `except: pass`), SEC-015 (`curl | sudo bash` ohne Prüfmöglichkeit) ·
**Freigabe:** Oliver, 11.09.2026 („weiter") · **Branch (Vorschlag):** `fix/audit-k26c-rest`

> Stand bei Abgabe: Änderungen im Working Tree, nichts committet. Fährt mit: K-26b-Abschnitt 10,
> STATUS.md und die Fachentscheidung zu Audit-Frage 3 (Anhänge für alle: ja) im Abschlussbericht
> und als Kommentar in `main.py`. Kein Frontend-Code, keine Migration, keine Schema-Änderung.

---

## 1. Zusammenfassung

1. **Anfragekennung im Log (OPS-006).** Neue Middleware `core/request_id.py`: nginx erzeugt je
   Anfrage `$request_id`, reicht sie als `X-Request-ID` weiter, das Backend hängt sie an **jede**
   Logzeile unterhalb von `app` (`[…]` nach dem Modulnamen) und gibt sie in der Antwort zurück.
   nginx-Zugriffslog schreibt dieselbe Kennung als `rid=`. Dazu zwei Zugriffszeilen aus dem
   Backend, die es vorher nicht gab: jede **5xx-Antwort** (WARNING) und jede Anfrage **über 5 s**
   (INFO), jeweils mit Methode, Pfad, Status, Dauer.
2. **Fehlerketten vollständig (CODE-001).** 53 `raise … from e` in 20 Dateien; 18 unbenannte
   `except`-Blöcke dafür benannt. ruff-Regel **B904 jetzt in CI blockierend.** Von 35
   `except: pass` vier in Logzeilen umgewandelt (Backup-Aufräumen, Löschen WebDAV/OneDrive,
   Changelog-Abruf); die übrigen 31 sind Aufräum-Beiwerk (`logout`, alte Logodateien, Parsen
   optionaler Werte) und bleiben bewusst.
3. **Installationsanleitung (SEC-015).** Hinweis, was `curl | sudo bash` bedeutet, und der
   Weg über `git clone` + Lesen + `sudo bash install.sh` (das Skript nutzt einen vorhandenen
   Projektordner, lädt also nichts erneut).
4. **Nebenbei:** `bump_version.py` zieht jetzt die Wurzel von `package-lock.json` mit (war seit
   dem npm-Bündel bei jedem Bump Handarbeit). `CLAUDE.md` bekommt eine Logging-Konvention.

Neu: 6 Backend-Tests (`tests/test_request_id.py`).

## 2. Ausgangslage

| Messgröße (Stand 2.0.4) | Wert |
|---|---|
| Logzeilen mit Anfragekennung | 0 — Zusammengehörigkeit nur über Zeitstempel erratbar |
| Zugriffslog nginx ↔ Backend abgleichbar | nein |
| `raise` in `except` ohne `from` (ruff B904) | 53 in 20 Dateien |
| `except …: pass` | 35 |
| ruff in CI | `F,E9` blockierend (seit K-25) |
| Hinweis zur Prüfbarkeit von `install.sh` | keiner |

## 3. Umfang der Änderungen

### 3.1 `backend/app/core/request_id.py` (neu) + `main.py` + nginx

- **Middleware** als reines ASGI-Middleware (kein `BaseHTTPMiddleware`: das puffert
  Streaming-Antworten und kostet spürbar Zeit). Liest `X-Request-ID`, akzeptiert nur
  `[A-Za-z0-9_.-]{1,64}` — alles andere (leer, Leerzeichen, Sonderzeichen, überlang) wird durch
  eine eigene 16-stellige Hex-Kennung ersetzt, damit niemand über den Header Text ins Log schreibt.
  Kennung liegt in einer `ContextVar`, wird im `finally` zurückgesetzt (Test 4.4 prüft, dass nach
  der Anfrage wieder `-` steht — wichtig bei Thread-Wiederverwendung).
- **Reihenfolge:** `add_middleware` **nach** CORS aufgerufen = äußerste Schicht; die Kennung
  steht damit, bevor CORS und Rate-Limit Meldungen schreiben. `expose_headers=["X-Request-ID"]`,
  damit das Frontend die Kennung lesen könnte (noch ungenutzt).
- **Unbehandelte Ausnahme:** eine ERROR-Zeile mit Kennung, Methode, Pfad; der Traceback selbst
  kommt weiter von Uvicorn (ohne Kennung) — die Zeile davor ist die Brücke.
- **Logging-Filter** setzt `record.request_id` (`-` außerhalb einer Anfrage: Start, Worker-Threads).
  Formatzeile: `%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s`.
- **nginx:** `log_format mit_kennung` (Standardfelder + `rid=$request_id rt=$request_time`) in
  `nginx.conf`; `proxy_set_header X-Request-ID $request_id;` im `/api/`-Block von `app.conf`
  **und** `local.conf`. `$request_id` ist ein eingebautes nginx-Feld (32 Hex, je Anfrage).

### 3.2 CODE-001-Rest

Skriptgestützt über die ruff-Trefferliste (AST-basiert, kein Regex-Raten): am `raise`-Ende
` from <name>` ergänzt; wo der `except` keinen Namen hatte, `as e` (bzw. `as fehler`, falls `e`
im Block schon vorkam — trat nicht auf). Ergebnis: `ruff --select F,E9,B904` ohne Befund,
`ast.parse` über alle 118 Python-Dateien unter `app/` grün. Verhalten unverändert: `from e` ändert nur die
`__cause__`-Verkettung, also was im Traceback als „The above exception was the direct cause“
erscheint.

`except: pass` → Logzeile (4):

| Stelle | neu |
|---|---|
| `backup_service.py` Aufräumen alter Backups | `logger.warning(…, exc_info=True)` — sonst füllt sich der Speicher unbemerkt |
| `storage_service.py` WebDAV `delete` | `logger.warning("WebDAV: Löschen von %s fehlgeschlagen")` — verwaiste Datei auffindbar |
| `storage_service.py` OneDrive `delete` | analog |
| `system.py` Changelog von GitHub | `logger.debug` (reines Komfort-Feature) |

### 3.3 `INSTALLATION.md`

Kasten unter dem Einzeiler: was der Befehl tut, Alternative `git clone` → `less install.sh` →
`sudo bash install.sh`. Geprüft gegen `install.sh` `setup_application()`: liegt
`docker-compose.yml` neben dem Skript, kopiert es diesen Stand nach `/opt/deinezeit` statt zu
klonen — die Aussage „nichts wird erneut geladen“ stimmt also.

### 3.4 Sonstiges

`scripts/auto_version.py::_update_package_lock` (aufgerufen aus `update_package_json`), Neuschreiben
des Lockfiles ist byteidentisch (Test 4.6). `CLAUDE.md` Konventionen: Logging/`raise from`/`except: pass`.
`.github/workflows/ci.yml`: `--select F,E9,B904`. Version 2.0.5, drei Changelog-Zeilen.

## 4. Prüfungen und Ergebnisse

Die Backend-Testreihe braucht PostgreSQL und läuft bei Oliver über `./test.sh`. In der
Prüfumgebung (Python 3.10, venv mit FastAPI 0.141) wurde die Middleware **isoliert** gegen eine
Minimal-App geprüft — dieselbe Testdatei, die auch im Repo liegt, plus zwei Zusatzfälle.

| # | Prüfung | Ergebnis |
|---|---|---|
| 4.1 | `tests/test_request_id.py` (6 Tests) gegen Minimal-App | 6/6 ✅ |
| 4.2 | Zusatz: 500er-Route → ERROR-Zeile „Unbehandelter Fehler“ mit Kennung im Logger `app.zugriff` | ✅ |
| 4.3 | Zusatz: Formatzeile enthält `app.probe [feedface]: drin` bei Header `X-Request-ID: feedface` | ✅ |
| 4.4 | Nach der Anfrage ist die Kennung wieder `-` (kein Leck zwischen Anfragen) | ✅ |
| 4.5 | `ruff check --select F,E9,B904 --ignore F841 app/ alembic/env.py` | All checks passed ✅ |
| 4.6 | `ast.parse` über `app/**/*.py`; Lockfile-Neuschreiben byteidentisch | ✅ |
| 4.7 | nginx-Konfiguration | **nicht prüfbar** in der Umgebung (kein nginx/Docker) → `nginx -t` läuft beim lokalen `docker compose up` implizit; siehe 7. |

**Nicht geprüft:** vollständige Backend-Testreihe (`./test.sh`), nginx-Syntax, echtes Zugriffslog.

## 5. Risiken

| # | Risiko | Einschätzung | Absicherung |
|---|---|---|---|
| R1 | nginx startet nicht wegen Tippfehler in `log_format` | mittel-schwer, aber sofort sichtbar: `docker compose up` lokal zeigt es, bevor es zum Server geht | 7. Schritt 2 |
| R2 | Log wird lauter (5xx- und Langsam-Zeilen) | gewollt; im Normalbetrieb ~0 Zeilen | Beobachten nach Deploy |
| R3 | Ein `except`, das jetzt `e` bindet, überschattet eine Variable `e` außerhalb | Skript hat auf `\be\b` im Block geprüft; Python-3-`except as` löscht `e` am Blockende ohnehin | 4.6 + `./test.sh` |
| R4 | Neue WARNING-Zeilen beim Löschen zeigen bisher unsichtbare Fehler | das ist der Zweck — kein Verhaltensänderung, nur Sichtbarkeit | — |
| R5 | `X-Request-ID` von außen gesetzt (Direktzugriff am Backend-Port) | nur gefiltert übernommen; Port 8000 ist ohnehin nicht öffentlich | Zeichenfilter, Test 4.1 |

Rückweg: Revert des Merge-Commits; keine Migration, keine Daten.

## 6. Bewusst nicht enthalten

- JSON-Logs (zweiter Teil von OPS-006) — ohne Log-Sammler kein Nutzen, eher Lesbarkeitsverlust.
- Kennung in Uvicorns eigenem Zugriffs-/Fehlerlog — eigener Handler; nginx-Log deckt den Zugriff ab.
- Restliche 31 `except: pass` — gesichtet, Beiwerk.
- Anzeige der Kennung im Frontend (Fehlermeldung „Bitte diese Nummer melden“) — sinnvoll, aber eigenes kleines UX-Thema.

## 7. Abnahme durch Oliver (lokal) und am Server

```bash
git checkout main && git pull
git checkout -b fix/audit-k26c-rest
docker compose -f docker-compose.local.yml up -d --build      # nginx -t implizit: nginx-Container muss laufen
docker compose -f docker-compose.local.yml ps nginx            # Status "running"
./test.sh                                                      # erwartet: bisherige + 6 neue Tests grün
```

- [ ] nginx-Container läuft (kein Neustart-Loop); `docker compose … logs nginx | tail` ohne `emerg`
- [ ] `./test.sh` grün
- [ ] `curl -si http://localhost/api/health | grep -i x-request-id` → 32-stellige Hex-Kennung (von nginx)
- [ ] `docker compose … logs nginx | tail -3` zeigt `rid=<dieselbe Kennung>`
- [ ] `docker compose … logs backend | tail` — Zeilen tragen `[…]` nach dem Modulnamen

**Nach dem Merge/Deploy** (mache ich über den eingebauten Browser): Version 2.0.5, `X-Request-ID`
im Antwort-Header, Konsole. **Zusätzlich K-26b R1:** vor dem Deploy geöffnete Sitzung → nach dem
Deploy auf eine noch nicht besuchte Seite navigieren → genau ein Reload, keine Fehlerseite.

## 8. Abgleich mit dem Plan

| Vorgabe | Ergebnis |
|---|---|
| OPS-006 `request_id`-Middleware | ✅ inkl. nginx-Abgleich und 5xx/Langsam-Zeilen |
| CODE-001-Rest `raise from` | ✅ 53/53, B904 in CI |
| CODE-001 `except: pass`-Durchsicht | ✅ 35 gesichtet, 4 geändert, Rest begründet |
| SEC-015 Doku-Hinweis | ✅ |
| Doku K-26b/Frage 3 fährt mit | ✅ |

## 9. Abnahme am Server (11.09.2026, dz.wwinterface.online, Version 2.0.5)

Merge und Deploy #228 durch. Oliver hat sich im eingebauten Browser angemeldet; ich habe navigiert
und DOM, Netzwerk und Konsole ausgelesen.

| Prüfung | Ergebnis |
|---|---|
| Version | Dashboard zeigt **2.0.5**, `/api/health` liefert `2.0.5` ✅ |
| `X-Request-ID` | jede API-Antwort trägt eine 32-stellige Hex-Kennung (z. B. `e37e0a69…`), also die von nginx erzeugte; zwei Aufrufe → zwei verschiedene Kennungen ✅ |
| Seiten nachgeladen | `BuchhaltungPage`, `PosteckePage`, `SettingsPage`, `UserManagementPage` je beim Aufruf ✅ |
| Konsole | keine Fehler aus der Anwendung (401 = Aufrufe vor dem Login bzw. meine Testaufrufe ohne Token; der eine 404 ist der R1-Fall unten) ✅ |
| Serverlog (`rid=` / `[…]`) | am Server selbst nicht eingesehen — Oliver prüft bei Gelegenheit `docker compose logs nginx backend \| tail` |

### 9.1 K-26b R1 live beobachtet — Reload-Schutz funktioniert

Der Browser-Tab war **vor** dem Deploy geöffnet (Anmeldeseite mit dem 2.0.4-Bundle
`index-AN7OGThw.js`), Oliver hat sich darin nach dem Deploy angemeldet. Klick auf **Buchhaltung**
(noch nie besucht) ergab im Netzwerkprotokoll genau die vorhergesagte Kette:

```
GET /assets/BuchhaltungPage-Z27sADVv.js   → 404            (alter Hash, Datei weg)
GET /buchhaltung                          → 200            (genau EIN location.reload())
GET /assets/index-BaH437MR.js             → 200            (neues Bundle)
POST /api/auth/refresh                    → 200            (Sitzung überlebt)
GET /assets/BuchhaltungPage-BsLxZESz.js   → 200            (neuer Hash)
```

`performance.navigation.type = "reload"`, Merker `deinezeit.chunk-neu-geladen` danach gelöscht,
Seite „Buchhaltung" sichtbar, Benutzer angemeldet. Oliver hat denselben Fall parallel in seinem
eigenen Browser gesehen („passt"). **R1 damit abgeschlossen** — ohne `lazySeite` hätte dieser Klick
die Fehlerseite gezeigt.

**Bündel K-26c abgeschlossen. Aus dem Audit vom 02.–04.09.2026 ist damit nichts mehr offen;**
als Nächstes steht nur noch das Tiefen-Audit ab ~25.09.2026 an.
