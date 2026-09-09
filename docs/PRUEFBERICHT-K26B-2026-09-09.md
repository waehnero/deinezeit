# Prüfbericht – Bündel K-26b: Frontend (Version 2.0.4)

**Datum:** 09.09.2026 · **Anlass:** Audit-Befunde PERF-002 (Bundle > 500 kB), UX-003/N-03
(Formularfelder ohne `id`/`name`, fehlende Beschriftungen), Nebenbefunde aus den Abnahmen
der Bündel npm und K-26a (Wortlaut „Neue Angebot", Logo-URL mit doppeltem `?v=`) ·
**Freigabe:** Oliver, 09.09.2026 („weiter" nach K-26a2) · **Lokale Abnahme:** 09.09.2026 (Abschnitt 9) · **Branch (Vorschlag):** `fix/audit-k26b-frontend`

> Stand bei Abgabe: Änderungen im Working Tree, nichts committet. Backend unberührt
> (außer Versionsnummer). Vitest 14/14 und Produktions-Build grün, geprüft in einer
> frischen Arbeitskopie. Sichtprüfung im Browser folgt nach dem Deploy (Abschnitt 7).

---

## 1. Zusammenfassung

Vier Punkte, alle im Frontend:

1. **Seiten laden verzögert** (`React.lazy`): Das Hauptbundle schrumpft von **1.766 kB auf 269 kB**
   (gzip 479 → 82 kB); jede Seite wird erst beim Aufruf geholt. Dazu ein Schutz für den
   Deploy-Fall ohne Service Worker (einmaliger Reload, wenn eine alte Sitzung eine nicht mehr
   vorhandene Datei anfordert) und eine Chunk-Gruppierung, damit Rolldown nicht 50 einzelne
   Icon-Dateien erzeugt.
2. **39 Formularfelder** in `<form>`-Blöcken haben jetzt `id` + `name`, 36 davon ein verknüpftes
   `<label htmlFor>`. `autoComplete` hatten die Anmelde-, Setup- und Passwortseiten bereits
   (`email`/`username`, `current-password`, `new-password`, `one-time-code`); neu nur im Profil (`name`, `email`, `new-password`).
3. **55 Schaltflächen ohne Beschriftung** haben ein `aria-label`: 22 aus dem vorhandenen `title`,
   27 Schließen-Kreuze („Schließen"), 6 von Hand (Liste aktualisieren, Position entfernen,
   Weitere Aktionen, Video entfernen).
4. **Wortlaut** „Neue Angebot" → „Neues Angebot" / „Neuer Lieferschein"; **Logo-Adressen** ohne
   doppelten `?v=`-Parameter und ohne neuen Bild-Request pro Render.

Neu: 5 Vitest-Tests (`lazySeite`, `mitCacheBuster`); Frontend-Tests damit 14.

## 2. Ausgangslage

| Messgröße (Stand 2.0.3) | Wert |
|---|---|
| Hauptbundle `index-*.js` | 1.765,83 kB (gzip 478,79 kB) — Vite-Warnung „> 500 kB" seit Monaten |
| Dateien in `dist/assets` | 4 (index.js, index.css, exceljs, bundle) |
| Formularfelder in `<form>` ohne `id`/`name` (statisch gezählt) | 39 (Chrome-Issues auf dem CSP-Rundgang: 29 — die Differenz sind nicht besuchte Dialoge) |
| `aria-label` im gesamten Frontend | 8 (bei 624 `<button>`) |
| Vitest | 2 Dateien, 9 Tests |

## 3. Umfang der Änderungen

### 3.1 Verzögertes Laden (`frontend/src/main.jsx`, `utils/lazySeite.js`, `vite.config.js`)

- 29 Seiten hinter der Anmeldung: `import X from './pages/X'` → `const X = lazySeite(() => import('./pages/X'))`.
  Eager bleiben `LoginPage`, `SetupPage`, `ForgotPasswordPage`, `ResetPasswordPage` (klein, vor der Anmeldung nötig).
- `<Suspense fallback={<AuthSpinner />}>` um die inneren `<Routes>` im `Layout` — derselbe Spinner
  wie beim Warten auf die Sitzung, kein neues Element.
- **`utils/lazySeite.js`**: Wrapper um `React.lazy`. Nach einem Deploy tragen die Dateien neue
  Hash-Namen; eine noch offene Browser-Sitzung fordert beim nächsten Seitenwechsel eine Datei an,
  die es nicht mehr gibt (`Failed to fetch dynamically imported module`). Der Wrapper lädt die
  Seite dann **genau einmal** neu (Merker in `sessionStorage`), danach hat der Browser das neue
  `index.html`. Schlägt der Import auch dann fehl, geht der Fehler an die ErrorBoundary. Ohne
  diesen Schutz hätte jeder Deploy bei allen offenen Sitzungen die Fehlerseite ausgelöst — das
  ist die eigentliche Voraussetzung dafür, dass Lazy-Loading in einer App ohne Service Worker
  überhaupt vertretbar ist.
- **`vite.config.js`**: `build.rolldownOptions.output.codeSplitting.groups` — alle
  `lucide-react`-Icons in eine Datei (`icons`, 41 kB), React-Kern (`react`, `react-dom`,
  `react-router`, `scheduler`) in eine zweite (`react`, 174 kB). Ohne die Gruppen legte Rolldown
  für jedes von mehreren Seiten geteilte Icon eine eigene 200-Byte-Datei an (105 Dateien statt 52).
  `chunkSizeWarningLimit: 1000`, weil die einzige Datei über 500 kB `exceljs` (930 kB) ist, die nur
  beim Excel-Import/-Export per `import()` nachgeladen wird — die Warnung soll bei echten
  Ausreißern wieder anschlagen.
- Nebeneffekt: TipTap (`RichTextEditor`, 393 kB) wird erst mit der ersten Seite geladen, die ihn braucht (Verkauf oder Einstellungen), nicht mehr beim Start.

### 3.2 Formularfelder (N-03)

39 Felder in 11 Dateien, jeweils `id="…" name="…"` (gleicher Wert, sprechend, deutsch), das
zugehörige `<label>` bekam `htmlFor`, wo es unmittelbar davor stand (35 Fälle; der Rest ist
bereits umschließend oder hat kein Label):

| Datei | Felder | Besonderheit |
|---|---|---|
| `LoginPage.jsx` | 4 | `autoComplete` war vorhanden; neu `inputMode="numeric"` am TOTP-Feld, `htmlFor` am Passwort-Label |
| `SetupPage.jsx` | 5 | `autoComplete` war vorhanden |
| `ProfilePage.jsx` | 3 | `name`, `email`, `new-password` |
| `ResetPasswordPage.jsx`, `ForgotPasswordPage.jsx` | 3 | `autoComplete` war vorhanden |
| `UserManagementPage.jsx` | 6 | Anlegen `neu-*`, Bearbeiten `bearbeiten-*` (getrennte Dialoge, keine ID-Kollision); Gruppen-Checkbox `name={`gruppe-${g.id}`}` |
| `FieldBuilder.jsx`, `GridFieldBuilder.jsx` | 14 | Präfix `feld-` / `gfeld-`, damit beide Baukästen nebeneinander eindeutig bleiben |
| `MasterDataOverview.jsx`, `AttachmentExplorer.jsx` | 4 | |

Die übrigen ~370 Felder außerhalb von `<form>` (Filterleisten, Tabellenzellen, Dialoge ohne
`<form>`) lösen den Chrome-Befund nicht aus und sind bewusst nicht angefasst — das wäre ein
eigener, deutlich größerer Durchgang mit vielen Feldern in Schleifen.

### 3.3 Beschriftungen (`aria-label`)

| Quelle | Anzahl | Regel |
|---|---|---|
| Buttons mit `title`, ohne `aria-label` | 22 | `aria-label` = `title` (Literal oder Ausdruck 1:1 übernommen) |
| Schließen-Kreuze (`<X/>`/`<XIcon/>` als einziger Inhalt, `onClick={onClose \| schliessen \| onAbbrechen}`) | 27 | `aria-label="Schließen"` |
| Von Hand | 11 | `InvoicePage` Aktualisieren, `InvoiceFormPage` 2× Position entfernen, `ProjektplanPage` 2× Weitere Aktionen, `PosteckePage` Video entfernen; nach der lokalen Abnahme: 4× Passwort/Wert anzeigen (Login, Setup, Profil, Einstellungen), Menü-Button im mobilen Kopf (`Layout`, mit `aria-expanded`) |

Der Durchgang war skriptgestützt mit anschließender Sichtung der Trefferliste; Buttons, die
Text über `{t('…')}` oder bedingt rendern, wurden ausgelassen (Falschtreffer).

### 3.4 Wortlaut und Logo-URL

- `InvoiceFormPage.jsx`: neue Tabelle `DOC_TYPE_NEU` (Neue Rechnung, Neues Angebot, Neue
  Auftragsbestätigung, Neue Gutschrift, Neuer Lieferschein) statt `'Neue ' + Label`.
- `SettingsContext.jsx`: `mitCacheBuster(url)` — hängt `?v=<Zeit>` nur an, wenn die Adresse noch
  keinen Parameter hat. Das Backend liefert Logo-Adressen bereits mit `?v=<Upload-Zeit>`; der
  zusätzliche Frontend-Buster erzeugte `…?v=1785821496?v=1788931966742` **und** bei jedem Render
  eine neue Adresse, also einen neuen Bild-Request (die `ERR_ABORTED`-Einträge aus der K-26a-Abnahme).
  Verwendet für das Favicon-`<link>` und die drei Vorschaubilder in `SettingsPage.jsx`.

### 3.5 Sonstiges

`CLAUDE.md`: Konvention „neue Seite über `lazySeite` einbinden". Version 2.0.4 mit drei
kundentauglichen Changelog-Zeilen. Lockfile-Wurzel nachgezogen.

## 4. Prüfungen und Ergebnisse

Frische Arbeitskopie (`npm ci` aus dem Lockfile), Vite 8 / Vitest 5.

| # | Prüfung | Ergebnis |
|---|---|---|
| 4.1 | `npm run build` | grün, 1,2 s; **52 Dateien**; `index` 268,7 kB, `react` 173,6 kB, `icons` 40,8 kB, `SettingsPage` 129,9 kB, `RichTextEditor` 393,3 kB, `exceljs` 929,6 kB (nur bei Excel), größte Seite sonst `MasterDataDetail` 68,6 kB; keine Warnung mehr ✅ |
| 4.2 | Vergleich Hauptbundle | 1.765,8 kB → 268,7 kB (−85 %); Erstaufruf lädt jetzt index + react + icons + CSS ≈ 553 kB statt 1.836 kB ✅ |
| 4.3 | `npx vitest run` | **4 Dateien, 14 Tests bestanden** (neu: `lazySeite.test.js` 2, `SettingsContext.test.js` 3) ✅ |
| 4.4 | `lazySeite`-Verhalten | Test: Modul wird durchgereicht und Merker gelöscht; erster Importfehler → genau ein `location.reload()`, Merker gesetzt, Promise bleibt offen; zweiter Fehler → kein Reload, Fehler geht nach oben ✅ |
| 4.5 | `mitCacheBuster` | Adresse mit `?v=` bleibt identisch; ohne Parameter genau ein `?v=<Zahl>`; leer/null unverändert ✅ |
| 4.6 | Doppelte `id` je Datei nach dem Durchgang | keine ✅ |
| 4.7 | Zählung nach dem Durchgang | Felder in `<form>` ohne `id`/`name`: **0**; `aria-label` gesamt: 68 (vorher 8) ✅ |
| 4.8 | Doppelte `autoComplete`-Props (in der lokalen Abnahme aufgefallen: mein Wert stand vor dem vorhandenen und wurde überschrieben) | 12 Duplikate entfernt, vorhandene Werte behalten; Vitest 14/14, Build 51 Dateien ✅ |

**Nicht geprüft (kein Browser in der Prüfumgebung):** das tatsächliche Nachladen der Seiten,
der Reload-Schutz nach einem echten Deploy, Passwort-Manager-Verhalten auf der Anmeldeseite,
Bildschirmleser. Siehe Abschnitt 7.

## 5. Risiken

| # | Risiko | Einschätzung | Absicherung |
|---|---|---|---|
| R1 | Seitenwechsel direkt nach einem Deploy scheitert (alte Sitzung, neue Dateinamen) | **war vorher kein Thema, ist es jetzt** — durch `lazySeite` auf einen einmaligen Reload reduziert | Test 4.4; nach dem Deploy in einer *vorher* geöffneten Sitzung navigieren (7.) |
| R2 | Spinner-Flackern beim ersten Aufruf einer Seite | gering; Dateien 5–70 kB, im LAN/DSL < 100 ms | Sichtprüfung |
| R3 | Rolldown-`codeSplitting.groups` ist Vite-8-spezifisch | Build grün; bei einem späteren Vite-Wechsel Option prüfen | Kommentar in `vite.config.js` |
| R4 | `autoComplete="username"` auf dem E-Mail-Feld ändert Passwort-Manager-Verhalten | gewollt (Standard für Anmeldeformulare); Passkey-Anmeldung unberührt | Anmeldung mit Passwort + Face ID prüfen |
| R5 | `aria-label` aus `title` bei Buttons, die auch Text haben (z. B. „Testen" mit langem Hinweis) | Screenreader liest den längeren Hinweis statt des Textes — akzeptabel, nicht falsch | — |
| R6 | `id`-Kollision, wenn zwei Dialoge gleichzeitig offen sind | geprüft: getrennte Präfixe (`neu-`/`bearbeiten-`, `feld-`/`gfeld-`) | 4.6 |

Rückweg: Revert des Merge-Commits; keine Migration, keine Datenänderung, Backend unberührt.

## 6. Bewusst nicht enthalten

- ~370 Eingabefelder außerhalb von `<form>` (Filter, Tabellen, Baukästen in Schleifen).
- Icon-Buttons mit bedingtem Text (Speichern/Laden) — haben Text, brauchen kein Label.
- Weitere Bundle-Optimierung (React 19, kleinere Alternativen zu exceljs) — außerhalb der Freigabe.
- Optionale K-26-Punkte OPS-006 (request_id-Logging), SEC-015, CODE-001-Rest — eigenes Bündel.

## 7. Abnahme durch Oliver (lokal) und am Server

```bash
git checkout main && git pull
git checkout -b fix/audit-k26b-frontend
cd frontend && npm ci && npm test && cd ..        # erwartet: 14 bestanden
docker compose -f docker-compose.local.yml up -d --build
./test.sh                                          # Backend unberührt, sicherheitshalber
```

- [ ] `npm test`: 14/14; Docker-Build grün
- [ ] Anmeldung mit Passwort (Browser bietet gespeicherte Zugangsdaten an) und mit Face ID/Passkey
- [ ] Netzwerk-Tab: beim Anmelden nur `index`, `react`, `icons`, CSS; beim Wechsel auf Verkauf erscheint `InvoicePage-*.js`, auf Einstellungen `SettingsPage-*.js` + `RichTextEditor-*.js`
- [ ] Beleg → „Neu erstellen" → Angebot: Überschrift „Neues Angebot"; Lieferschein: „Neuer Lieferschein"
- [ ] Einstellungen → Allgemein (Logo): Netzwerk-Tab zeigt Logo-Adressen mit genau einem `?v=` und keinen `ERR_ABORTED`
- [ ] Konsole ohne Fehler

**Nach dem Merge/Deploy** (mache ich über den eingebauten Browser): Version 2.0.4, Netzwerkprotokoll
je Seite, Konsole. **Zusätzlich R1:** eine Browser-Sitzung, die *vor* dem Deploy offen war, nach
dem Deploy auf eine noch nicht besuchte Seite navigieren → genau ein automatischer Reload, dann
die Seite; keine Fehlerseite.

## 8. Abgleich mit dem Plan

| Vorgabe K-26 (Frontend) | Ergebnis |
|---|---|
| `React.lazy` je Seite (Bundle > 500 kB) | ✅ 1.766 → 269 kB, Warnung weg |
| 29 Formularfelder ohne id/name (N-03) | ✅ 39 gefunden und versorgt |
| `aria-label`-Durchgang (UX-003) | ✅ 55 Beschriftungen |
| Wortlaut „Neue Angebot" | ✅ |
| Logo-URL doppeltes `?v=` | ✅ inkl. Ursache (Request pro Render) |
| Optional OPS-006 / SEC-015 / CODE-001-Rest | ⏸ nächstes Bündel oder mit dem Tiefen-Audit |

## 9. Lokale Abnahme (09.09.2026, Docker lokal, eingebauter Browser)

Oliver hat das Frontend-Image neu gebaut und sich angemeldet; ich habe navigiert und DOM, Netzwerk
und Konsole ausgelesen.

| Prüfung | Ergebnis |
|---|---|
| Anmeldeseite lädt | `index`, `rolldown-runtime`, `icons`, `react`, CSS — kein Seiten-Chunk ✅ |
| Anmeldeformular | `id`/`name`/`autoComplete` gesetzt, Labels verknüpft ✅ |
| Nach Anmeldung | `DashboardPage-*.js` + `PageHeader`, `VoiceEntryDialog`, dnd-kit nachgeladen ✅ |
| Wechsel auf Verkauf | `InvoicePage-*.js`, `Fab`, `RichTextEditor` erst jetzt ✅ |
| Neu erstellen → Angebot | Überschrift **„Neues Angebot"**, `InvoiceFormPage-*.js` nachgeladen; Button „Position entfernen" mit `aria-label` ✅ |
| Dokumenttyp Lieferschein | Überschrift **„Neuer Lieferschein"** ✅ |
| Einstellungen | `SettingsPage`, `MailImportVerwaltung`, `UserManagementPage` nachgeladen; kein doppeltes `?v=` (lokal ist kein Logo hinterlegt — Adressprüfung am Server nachholen) ✅ |
| Konsole | keine Fehler aus der Anwendung. Die Meldung „Failed to register a ServiceWorker" stammt aus dem eingebauten Browser (erlaubt keine Service Worker auf `http://localhost`), nicht aus dem Build; die 401 sind fehlgeschlagene Anmeldeversuche vor dem Login ✅ |
| Nacharbeit aus der Abnahme | 12 doppelte `autoComplete`-Props entfernt, Passwort-Label verknüpft, 4 Auge-Schaltflächen und der mobile Menü-Button beschriftet; Vitest 14/14, Build grün |

**Offen für den Server:** R1 (Sitzung von vor dem Deploy → genau ein Reload), Logo-Adressen mit genau
einem `?v=`, Passwort-Manager-Angebot beim Login in Olivers Browser.
