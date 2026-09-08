# Prüfbericht – Bündel „npm-Hauptversionen" (Version 2.0.1)

**Datum:** 08.09.2026 · **Anlass:** Befund N-08 der Abschlussprüfung
([AUDIT-2026-09-02-ABSCHLUSS.md](AUDIT-2026-09-02-ABSCHLUSS.md), Abschnitt 3 und 4) ·
**Freigabe des Bündels:** Oliver, 08.09.2026 · **Branch (Vorschlag):** `fix/npm-hauptversionen`

> Stand bei Abgabe dieses Berichts: Änderungen liegen im Working Tree, nichts
> committet. Die Punkte in Abschnitt 7 sind von Oliver lokal nachzuvollziehen,
> bevor Commit und PR folgen.

---

## 1. Zusammenfassung

Die drei im Audit zurückgestellten Hauptversionssprünge (react-router 6→7, TipTap 2→3,
vite 5→8) sind umgesetzt. `npm audit` meldet **0 Schwachstellen** (vorher 30 „moderate"
ohne Dev-Abhängigkeiten, 36 mit). Produktions-Build und Frontend-Tests (9/9) sind grün,
geprüft aus einer frischen `npm ci`-Installation gegen das eingecheckte Lockfile.
Code-Änderungen beschränken sich auf 37 Dateien: eine Editor-Komponente (fachlich
angepasst) und 36 Dateien mit ausschließlich geändertem Import-Pfad des Routers.

Mitgenommen, weil zwingend bzw. sinnvoll im selben Zug: Node 20 → 22 im Frontend-Build
(Dockerfile, CI) — Node 20 ist seit April 2026 ohne Sicherheitsupdates, Vite 8 verlangt
mindestens 20.19 — und `"type": "module"` in `package.json` (Vite 8 warnt sonst bei jedem
Build wegen der ESM-Konfigurationsdateien).

## 2. Ausgangslage

| Messgröße (Stand 2.0.0) | Wert |
|---|---|
| `npm audit --omit=dev` | 30 moderate (26× TipTap-Kette über `@tiptap/core ≤ 3.30.3`, 2× react-router `GHSA-337j-9hxr-rhxg`, Rest Folgeabhängigkeiten) |
| `npm audit` (mit Dev) | 36 |
| Pakete nach `npm ci` | 696 |
| Node im Build | `node:20-alpine` (Dockerfile), `node-version: 20` (ci.yml) |
| Vitest | 2 Dateien, 9 Tests |

## 3. Umfang der Änderungen

### 3.1 Abhängigkeiten (`frontend/package.json`, `frontend/package-lock.json`)

| Paket | vorher | nachher | Bemerkung |
|---|---|---|---|
| `react-router-dom` | ^6.24.0 | **entfernt** | ersetzt durch `react-router` |
| `react-router` | – (transitiv 6.30) | **^7.18.3** | v8.3 existiert bereits, bewusst nicht genommen (nicht freigegeben, v7 ist sicherheitsseitig sauber) |
| `@tiptap/react`, `@tiptap/starter-kit`, `@tiptap/extension-text-align` | ^2.4.0 | **^3.31.3** | |
| `@tiptap/pm` | – | ^3.31.3 | Peer-Abhängigkeit von `@tiptap/react` 3, muss jetzt explizit stehen |
| `@tiptap/extension-underline` | ^2.4.0 | **entfernt** | in TipTap 3 Teil des StarterKits |
| `@tiptap/extension-link` | ^2.4.0 | **entfernt** | war im Code nie eingebunden; in TipTap 3 im StarterKit, dort abgeschaltet (`link: false`) |
| `@tiptap/extension-text-style`, `@tiptap/extension-color` | ^2.4.0 | **entfernt** | Color war nie eingebunden, TextStyle nur dessen Voraussetzung |
| `vite` | ^5.3.4 | **^8.2.2** | Bundler jetzt Rolldown 1.2.7 statt Rollup/esbuild |
| `@vitejs/plugin-react` | ^4.3.1 | ^6.1.1 | |
| `vite-plugin-pwa` | ^0.20.0 | ^1.3.0 | `selfDestroying` unverändert unterstützt |
| `vitest` | ^2.1.9 | ^5.0.0 | |
| `jsdom` | ^25.0.1 | ^30.0.1 | |
| `"type": "module"` | – | neu | |

Nicht angefasst (bewusst, außerhalb der Freigabe): React 18 (→19), Tailwind 3 (→4),
zustand 4 (→5), i18next 23 (→26), lucide-react 0.395 (→1.x), @simplewebauthn/browser 10 (→14),
@dnd-kit/sortable 8 (→10). Keine davon hat offene Advisories.

### 3.2 Quellcode

**`frontend/src/components/RichTextEditor.jsx`** — einzige fachliche Anpassung, vier Punkte:

1. Imports: `TextAlign` ist in v3 ein benannter Export (`import { TextAlign }`); Underline/TextStyle-Imports entfallen.
2. `StarterKit.configure({ link: false })` — Underline kommt aus dem StarterKit, die dort neu enthaltene Link-Erweiterung bleibt aus (Verhalten wie vorher, keine automatische Verlinkung eingetippter URLs).
3. **`useEditorState`** für den Toolbar-Zustand. TipTap 3 rendert die React-Komponente nicht mehr bei jeder Editor-Transaktion neu (`shouldRerenderOnTransaction` ist jetzt standardmäßig `false`). Ohne diese Änderung hätten die Buttons Fett/Kursiv/Unterstrichen/Ausrichtung/Listen ihren Aktiv-Zustand nicht mehr angezeigt — der Editor hätte funktioniert, die Toolbar aber „tot" gewirkt.
4. `editor.commands.setContent(value, { emitUpdate: false })` statt des alten zweiten Bool-Parameters (Signaturänderung v3).

**36 Dateien unter `frontend/src/`** — nur `from 'react-router-dom'` → `from 'react-router'`
(mechanisch per `sed`, keine weitere Änderung). Verwendete Symbole: `BrowserRouter`, `Routes`,
`Route`, `Navigate`, `Link`, `NavLink`, `useLocation`, `useNavigate` (32×), `useParams`,
`useSearchParams` — alle in v7 aus `react-router` exportiert (geprüft, Abschnitt 5.4).
Keine Loader/Actions/Data-Router im Einsatz, daher keine weiteren v7-Migrationsschritte
(alle v6-„future flags" sind in v7 Standard; die App nutzt keine relativen Splat-Routen).

### 3.3 Build und Betrieb

| Datei | Änderung |
|---|---|
| `frontend/Dockerfile` | `FROM node:20-alpine` → `node:22-alpine` |
| `.github/workflows/ci.yml` | Job „Frontend: Tests (Vitest)": `node-version: 20` → `22` |
| `frontend/vite.config.js` | unverändert (Config, Proxy, PWA-Manifest laufen unter Vite 8 ohne Anpassung) |
| `CLAUDE.md` | Tech-Stack-Zeilen (Vite 8, React Router 7, TipTap 3, Node 22) |
| `STATUS.md` | Punkt „npm-Hauptversionen" als erledigt markiert |
| Version 2.0.1 | per `scripts/bump_version.py` in allen 6 Dateien + `CHANGELOG.md`; Lockfile-Wurzel von Hand nachgezogen (das Skript schreibt sie nicht) |

## 4. Vorgehen

Alle npm-Läufe erfolgten in einer Arbeitskopie außerhalb des Repos (ohne `node_modules`
und `dist`), damit Olivers lokales `frontend/node_modules` unberührt bleibt. Bei den
Hauptversionssprüngen traten Peer-Konflikte (`ERESOLVE`) auf, solange alte und neue
Paketfamilie gemischt waren; gelöst durch vollständiges `npm uninstall` der alten Familie
und Neuinstallation in einem Schritt — **ohne** `--force` oder `--legacy-peer-deps`.
Ins Repo zurück kamen nur `package.json`, `package-lock.json` und die Quelltext-Änderungen.
Die Abnahmeprüfung (Abschnitt 5) lief anschließend noch einmal in einer zweiten, frischen
Kopie **aus dem Repo-Stand** mit `npm ci`, also exakt so, wie es Dockerfile und CI tun.

## 5. Prüfungen und Ergebnisse

### 5.1 Installation aus dem Lockfile

```
$ npm ci --no-audit --no-fund
added 663 packages in 6s
```
→ Lockfile und `package.json` konsistent (`npm ci` bricht sonst ab). 663 statt 696 Pakete.

### 5.2 Produktions-Build (Vite 8 / Rolldown)

```
$ npm run build
✓ 1723 modules transformed.
dist/registerSW.js                       0.13 kB
dist/manifest.webmanifest                0.46 kB
dist/index.html                          1.58 kB │ gzip:   0.78 kB
dist/assets/index-Ctn32c2g.css          70.18 kB │ gzip:  12.78 kB
dist/assets/bundle-CKnbji6g.js           7.00 kB │ gzip:   2.36 kB
dist/assets/exceljs.min-D7YhlfM-.js    929.55 kB │ gzip: 256.42 kB
dist/assets/index-CdYlWS5l.js        1,765.83 kB │ gzip: 478.79 kB
✓ built in 1.64s
(!) Some chunks are larger than 500 kB after minification.
```
→ Grün. Manifest und der selbstzerstörende Service Worker (`registerSW.js`) werden weiter
erzeugt. Die Chunk-Größen-Warnung ist bekannt (PERF-002) und Gegenstand von K-26
(`React.lazy` je Seite); sie ist durch dieses Bündel weder entstanden noch behoben.
Vor der Änderung erschien zusätzlich eine `MODULE_TYPELESS_PACKAGE_JSON`-Warnung bei
jedem Build — durch `"type": "module"` beseitigt (alle `.js`-Dateien im Frontend sind ESM,
kein `require`/`module.exports` vorhanden, geprüft per grep).

### 5.3 Frontend-Tests (Vitest 5, jsdom 30)

```
$ npx vitest run
 ✓ src/services/api.test.js (7 tests)
 ✓ src/components/ErrorBoundary.test.jsx (2 tests)
 Test Files  2 passed (2)
      Tests  9 passed (9)
```
→ Grün, Setup-Datei und `include`-Muster unverändert gültig. (Die Stack-Traces
„Kaputte Komponente 42" in der Ausgabe stammen aus dem ErrorBoundary-Test und sind gewollt.)

### 5.4 Router-Exporte

```
$ node -e "…" → BrowserRouter function · Routes function · Route function · Navigate function ·
Link object · NavLink object · useLocation function · useNavigate function ·
useParams function · useSearchParams function
```
→ Alle zehn im Projekt verwendeten Symbole werden von `react-router` 7.18.3 exportiert.

### 5.5 Schwachstellen

```
$ npm audit --omit=dev   → found 0 vulnerabilities
$ npm audit              → found 0 vulnerabilities
```
→ Ziel des Bündels („ohne moderate") übertroffen; auch mit Dev-Abhängigkeiten sauber.

### 5.6 Nicht geprüft (Sandbox ohne Browser)

- Sichtprüfung des Editors im Browser (Toolbar-Zustand, Ausrichtung, Listen, Laden bestehender HTML-Inhalte aus der Datenbank).
- Seitenwechsel im Browser (Zurück-Taste, `Navigate`-Weiterleitungen, Query-Parameter über `useSearchParams`).
- Docker-Build des Frontend-Images mit `node:22-alpine` (gleiche Schritte wie 5.1/5.2, nur anderes Basis-Image).
- Backend-Tests `./test.sh` — vom Bündel nicht berührt, keine Backend-Datei geändert außer `config.py` (Versionsnummer).

## 6. Risiken und Bewertung

| # | Risiko | Einschätzung | Absicherung |
|---|---|---|---|
| R1 | TipTap 3 liest bestehende Editor-Inhalte (HTML in DB) anders ein, z. B. Ausrichtung oder Unterstreichung geht verloren | niedrig — gleiche Node-/Mark-Namen (`underline`, `textAlign`-Attribut), HTML-Schema unverändert | Sichtprüfung mit einem bestehenden Text (Abschnitt 7) |
| R2 | Toolbar zeigt Aktiv-Zustand nicht (Rendering-Änderung v3) | im Code behandelt (`useEditorState`) | Sichtprüfung |
| R3 | Rolldown erzeugt anderes Chunking/Verhalten als Rollup | niedrig — Build grün, gleiche Einstiege, keine `rollupOptions` in der Config | Docker-Build + Rundgang lokal |
| R4 | Vitest 5.0.0 ist eine frische Hauptversion | niedrig — 9/9 grün, Config-Format unverändert | bei Problemen `vitest@4` pinnen (kein Einfluss aufs ausgelieferte Bundle) |
| R5 | Olivers lokales `node_modules` passt nicht mehr zum Lockfile | sicher, kein Fehler — nur Hinweis | `cd frontend && npm ci` einmal ausführen |
| R6 | Node 22 im Alpine-Image verhält sich anders als Node 20 | sehr niedrig — reiner Build-Container, Laufzeit ist nginx | Docker-Build lokal |

Rückweg: Der Branch enthält keine Migration und keine Datenänderung. Bei Problemen nach dem
Deploy genügt ein Revert des Merge-Commits; ein zweiter Deploy stellt 2.0.0 wieder her.

## 7. Abnahme durch Oliver (lokal)

```bash
git checkout -b fix/npm-hauptversionen
cd frontend && npm ci && npm test && cd ..
docker compose -f docker-compose.local.yml up -d --build
```

- [ ] `npm test` lokal: 9/9
- [ ] Docker-Build des Frontends läuft mit `node:22-alpine` durch, http://localhost erreichbar
- [ ] Anmeldeseite zeigt 2.0.1 mit dem Eintrag „Technik-Update im Hintergrund"
- [ ] Editor (einzige Einsatzstelle: Einstellungen → E-Mail-Vorlage, Feld „E-Mail-Text"): Fett/Kursiv/Unterstrichen, drei Ausrichtungen, beide Listen, Trennlinie — Buttons leuchten bei gesetztem Format auf, Speichern und Wieder-Öffnen erhält die Formatierung
- [ ] Ein **bestehender** Text mit Unterstreichung/Ausrichtung aus der Datenbank wird unverändert angezeigt (R1)
- [ ] Navigation: Dashboard → Verkauf → Beleg öffnen (`useParams`) → Zurück-Taste; Seite mit Parametern in der URL (`useSearchParams`: Verkauf-Liste, Bericht Projektzeiten) neu laden; Abmelden → Weiterleitung zur Anmeldung (`Navigate`)
- [ ] Browser-Konsole ohne Fehler und ohne „Refused to …" (CSP unverändert)
- [ ] `./test.sh` (optional, Backend unberührt)

Danach normal committen (der Hook bumpt nicht mehr, Version steht bereits auf 2.0.1) und
PR öffnen; Pflicht-Checks: „Backend: Tests (pytest)" und „Frontend: Tests (Vitest)".

## 8. Abgleich mit dem Plan nach 2.0.0

| Vorgabe | Ergebnis |
|---|---|
| react-router 6→7, TipTap 2→3, vite 5→8 (+ passende Plugins) | ✅ |
| `npm audit --omit=dev` ohne moderate | ✅ 0 (auch mit Dev 0) |
| Vitest/Build grün | ✅ 9/9, Build 1,6 s |
| Sichtprüfung Editor und Routing | ⏳ Oliver, Abschnitt 7 |
| Ein Branch, ein PR | ⏳ `fix/npm-hauptversionen` |

Nächstes Bündel laut Plan: **K-26** (invoice.py aufteilen, Skripte ordnen, `React.lazy`
je Seite gegen die 1,7-MB-Warnung aus 5.2, `aria-label`/N-03).

## 9. Abnahme am Server (08.09.2026, nach Merge und Deploy)

Durchgeführt über den eingebauten Browser auf https://dz.wwinterface.online (Anmeldung durch Oliver).

| Prüfpunkt | Ergebnis |
|---|---|
| `/api/health` | `{"status":"ok","version":"2.0.1"}` ✅ |
| Anmeldeseite | Fußzeile v2.0.1; Reiter „Updates" zeigt den Eintrag vom 08.09. mit beiden Texten ✅ |
| Dashboard | lädt vollständig, Kachel „Version 2.0.1" ✅ |
| Editor (Einstellungen → Parameter → E-Mail-Vorlagen → Rechnung) | bestehende Vorlage mit Fettdruck korrekt geladen (R1); Cursor im fetten Wort → Button „Fett" leuchtet (R2); Unterstrichen, Zentriert und Nummerierte Liste setzen das Format und leuchten auf ✅ — Änderungen nicht gespeichert |
| `useParams` | Verkauf → RE-2026-002 öffnet „Rechnung bearbeiten" ✅ |
| Zurück-Taste | zurück zur Verkaufsliste, Filter „Rechnungen" erhalten ✅ |
| `useSearchParams` | `/invoices/new?type=angebot` → Formular startet als Angebot (AN-2026-002) ✅ |
| `Navigate`-Weiterleitung | `/masterdata/projekte` → Zeitprojekte ✅ |
| Abmelden | Weiterleitung zur Anmeldeseite ✅ |
| Browser-Konsole | keine Einträge über den gesamten Rundgang (keine Fehler, kein „Refused to …") ✅ |

Nebenbefund (nicht dieses Bündel, Wortlaut): Überschrift „Neue Angebot" beim neuen Beleg vom Typ Angebot – Artikel passt nicht zum Dokumenttyp. Vermerk für K-26/aria-Durchgang.

**Ergebnis: Bündel npm abgenommen, keine Auffälligkeiten.**
