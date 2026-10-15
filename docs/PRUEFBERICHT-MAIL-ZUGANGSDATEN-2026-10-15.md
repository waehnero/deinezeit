# Prüfbericht – Mail-Import: zentrale Zugangsdaten binden (Version 2.1.2)

**Datum:** 15.10.2026 · **Anlass:** Sicherheitsbefund „Zentrale Mailzugangsdaten können an
einen frei wählbaren IMAP-Server gesendet werden" (Bestandsaufnahme zu Commit
`1a5787e49216c953650980eed285aba80ae22667`) · **Branch:** `fix/mail-zentrale-zugangsdaten`
(Basis `main` @ `b7371c3`) · **Migration:** `0063_mail_zentrale_zugangsdaten_binden`

---

## 1. Zusammenfassung

1. **Befund bestätigt** — automatisiert, mit erfundenen Zugangsdaten und simulierter
   IMAP-Verbindung (`tests/test_mailimport_befund.py`). Am unveränderten Stand meldete sich das
   Backend **zweimal** (Verbindungstest und manueller Scan) mit dem zentralen SMTP-Benutzer und
   -Passwort beim Server `mail.angreifer.invalid` an, den ein Mitarbeiter ohne Adminrechte
   eingetragen hatte. Nach der Behebung: 0 Anmeldungen.
2. **Zentrale Zugangsdaten nur noch an zentralen Konten.** `use_central_credentials` ist nur an
   globalen, vom Admin verwalteten Konten zulässig. Persönliche Konten arbeiten ausschließlich
   mit eigenen Zugangsdaten — sie funktionieren unverändert weiter.
3. **Bindung an ein bestätigtes Ziel.** Beim Anlegen/Ändern durch den Admin (oder per „Ziel
   bestätigen") hält der Server fest, wohin die zentralen Zugangsdaten gehen dürfen: Server,
   Port, TLS-Art, Anmeldeidentität, bei Microsoft 365 die Mailbox. Weicht der aktuelle Stand
   davon ab, wird **nicht verbunden** — auch dann nicht, wenn das Ziel an der API vorbei in der
   Datenbank geändert wurde.
4. **Freigabe zentraler Konten.** Der Admin gibt ein zentrales Konto für alle oder für
   bestimmte Rechtegruppen frei (vorhandenes Gruppenmodell, kein Parallelmodell). Nicht
   freigegebene Benutzer sehen weder das Konto noch seine Vorschläge und können nicht scannen.
5. **Microsoft Graph:** Die zentralen Anwendungsrechte gelten nur für die gebundene Mailbox;
   Mailbox/Tenant werden syntaktisch geprüft, alle URL-Bestandteile kodiert (kein Umbiegen auf
   andere Graph-Endpunkte).
6. **Verschlüsselung Pflicht.** IMAP nur noch über TLS (993) oder STARTTLS (143, Pflicht — kein
   Klartext-Rückfall). Zertifikat **und** Hostname werden geprüft (vorher prüfte
   `imaplib.IMAP4_SSL` mangels Kontext **gar nicht**). Firmen-CAs für interne Server kann der
   Admin hinterlegen.
7. **Kein Zugriff aufs interne Netz.** Loopback, private Netze, Link-Local inkl.
   Cloud-Metadaten (169.254.169.254), CGNAT, ULA/Site-Local, IPv4-gemappte/-eingebettete
   IPv6-Formen werden abgewiesen — für **alle** aufgelösten Adressen; verbunden wird mit genau
   der geprüften Adresse (kein DNS-Rebinding). Interne Mailserver gibt der Admin ausdrücklich
   frei (Hostname, IP oder Netz; ohne Portangabe nur 143/993).
8. **Gleiche Regeln überall:** Anlegen, Ändern, Verbindungstest, manueller Scan,
   Hintergrund-Scan und Outlook-Flagge laufen durch dieselben Prüfungen im Service
   (`mail_ingest._imap_connect` / `_graph_token`).
9. **Keine Geheimnisse in Antworten, Fehlern, Logs.** Fehlertexte werden um bekannte
   Geheimnisse bereinigt; Konfigurationsänderungen werden mit Feldnamen, nie mit Werten
   protokolliert.

## 2. Ausgangslage

| Stelle (Stand `1a5787e` bzw. `b7371c3`) | Problem |
|---|---|
| `schemas/mailimport.py` | `use_central_credentials`, `imap_host`, `imap_port`, `imap_ssl` frei übertragbar, auch für persönliche Konten |
| `api/mailimport.py` `create_account`/`update_account` | keine Prüfung, ob ein Nicht-Admin zentrale Zugangsdaten anfordert |
| `services/mail_ingest.py` `_imap_credentials` | liefert SMTP-Benutzer/-Passwort für **jedes** Konto mit gesetztem Schalter |
| `_imap_connect` | `IMAP4_SSL` ohne Kontext ⇒ **keine Zertifikatsprüfung**; `imap_ssl=False` ⇒ Klartext |
| `_graph_credentials` | zentrale App-Rechte mit **frei gewählter** `graph_mailbox` |
| Graph-URLs | Mailbox/Ordner/ID unkodiert im Pfad |
| `_scanner_loop` | Fehler per `print`, ungefilterter Fehlertext in `last_error` |
| Globale Konten | für **alle** Benutzer mit Aufgabenrechten nutzbar, keine Freigabe möglich |

## 3. Umfang

| Datei | Änderung |
|---|---|
| `backend/app/services/mail_sicherheit.py` | **neu** – Bindung, Sperrgründe, TLS-Kontext, Zielprüfung (DNS/IPv4/IPv6), Bereinigung von Fehlertexten |
| `backend/app/services/mail_ingest.py` | Zugangsdaten mit Bindungsprüfung, `_imap_oeffnen` (gepinnte IP, TLS/STARTTLS), Graph-URL-Kodierung, `fehlertext()`, `auto_scan_durchlauf()` (Hintergrund-Scan testbar, Logging statt `print`) |
| `backend/app/api/mailimport.py` | Feld-Whitelist, Regeln für Anlegen/Ändern, Freigabeprüfung (Konten, Scan, Vorschläge), `POST …/zentral-bestaetigen`, `GET/PUT /mail-import/sicherheit`, Protokollierung |
| `backend/app/schemas/mailimport.py` | Feldlängen/Portbereich, Freigabefelder, `zentral_sperrgrund`, Sicherheits-Schemas |
| `backend/app/models/mailimport.py` | Spalten `zentral_bindung`, `freigabe_alle`, `freigabe_gruppen` |
| `backend/alembic/versions/0063_…` | **neu** – Spalten + Bestandsübernahme (s. Abschnitt 5) |
| `frontend/src/components/MailImportVerwaltung.jsx` | zentrale Option nur bei globalen Konten, Freigabe nach Gruppen, Sperrhinweis + „Ziel bestätigen", TLS/STARTTLS-Auswahl, neue Karte „Sicherheit der Mailverbindungen" |
| `frontend/src/pages/SettingsPage.jsx`, `services/api.js` | Einbindung der neuen Karte bzw. Endpunkte |
| Tests | `test_mailimport_befund.py`, `test_mailimport_sicherheit.py`, `test_mailimport_migration.py` (neu), `test_mailimport.py` (4 Tests angepasst, die das alte Verhalten festschrieben), `MailImportVerwaltung.test.jsx` (neu) |
| Version | 2.1.1 → 2.1.2 über `scripts/bump_version.py` (6 Dateien + Changelog) |

**Bewusst nicht angefasst:** der SMTP-Versand (`services/email.py`, nur vom Admin
konfiguriert), die KI-Einstellungen, die Dashboard-Kennzahl „offene Mail-Vorschläge"
(zählt weiterhin alle offenen Vorschläge als Zahl — zeigt keine Inhalte), die übrigen Module.

## 4. Sicherheitsmodell

```
Mitarbeiter ── wählt ──▶ freigegebenes zentrales Konto (id)
                              │  Server bestimmt: Host, Port, TLS, Identität, Mailbox
                              ▼
               zentral_sperrgrund(): global? gebunden? Bindung == aktueller Stand?
                              │ nein → 403 / übersprungen (Hintergrund) – vor jeder Verbindung
                              ▼ ja
               ziel_adressen(): DNS → alle Adressen öffentlich oder vom Admin freigegeben?
                              ▼
               TLS/STARTTLS mit Zertifikats- + Hostnamenprüfung (gepinnte IP)
                              ▼
               LOGIN mit zentralen Zugangsdaten
```

- **Wer darf was:** Persönliche Konten – nur Besitzer, nur eigene Zugangsdaten. Globale Konten
  – anlegen/ändern/bestätigen/Verbindungstest nur Admin; verwenden (Liste, Scan, Vorschläge)
  Admin + Freigegebene.
- **Bindung wird neu gesetzt**, wenn der Admin das Ziel ändert (Host, Port, TLS, Mailbox,
  Protokoll, Einschalten der zentralen Nutzung) oder ausdrücklich bestätigt. Abschalten der
  zentralen Nutzung löscht die Bindung.
- **Wechsel der zentralen Anmeldeidentität** (SMTP-Benutzer bzw. Tenant/Client in
  Einstellungen → System → E-Mail) sperrt alle gebundenen Konten, bis der Admin sie bestätigt.
  Ein reiner **Passwortwechsel** bei gleicher Identität sperrt nicht.

## 5. Bestehende Installationen (Migration 0063)

| Bestand | Ergebnis | Begründung |
|---|---|---|
| Globales Konto (jede Art) | `freigabe_alle = true` | Bisher durfte jeder mit Aufgabenrechten es nutzen — gleicher Kreis, keine Erweiterung |
| Globales IMAP-Konto mit zentralen Daten, Host + SMTP-Benutzer vorhanden | Ziel als bestätigt übernommen (`quelle: migration_0063`), TLS-Art: SSL bzw. **STARTTLS statt Klartext** | Ziel hat der Admin eingetragen; nur er konnte globale Konten ändern |
| Globales Graph-Konto mit zentralen Daten, Tenant/Client/Mailbox bestimmbar | Mailbox (Konto bzw. Absenderadresse) als bestätigt übernommen | wie oben |
| Globales Konto mit zentralen Daten, Ziel unvollständig | **gesperrt** bis „Ziel bestätigen" | nicht eindeutig |
| Persönliches Konto mit zentralen Daten | **gesperrt**, `last_error` mit verständlichem Hinweis | Ziel von einem Mitarbeiter gewählt, nie autorisiert |
| Persönliches Konto mit eigenen Daten | unverändert | – |

Rückweg (`alembic downgrade 0062`) entfernt die Spalten — damit wäre der Befund wieder offen.

## 6. Administrative Schritte nach dem Einspielen

1. **Einstellungen → KI & Mail-Import → Globale Mail-Konten** öffnen. Steht bei einem Konto
   ein gelber Hinweis „Zentrale Zugangsdaten gesperrt …", Konto bearbeiten, Server/Port bzw.
   Mailbox kontrollieren und **„Ziel bestätigen"** drücken.
2. Je zentralem Konto die **Freigabe** prüfen: Nach dem Update steht sie auf „Alle Benutzer
   mit Zugriff auf Aufgaben" (bisheriges Verhalten). Bei Bedarf auf Gruppen einschränken.
3. **Interne Mailserver** (z. B. Exchange im Firmennetz, 10.x/192.168.x) unter **„Sicherheit
   der Mailverbindungen"** freigeben — sonst werden sie ab jetzt abgewiesen. Hat der Server ein
   Zertifikat einer eigenen Firmen-CA, das CA-Zertifikat (PEM) dort hinterlegen. Sonderports
   als `host:port`.
4. Konten, die bisher **unverschlüsselt** (Port 143 ohne SSL) liefen, verwenden jetzt STARTTLS.
   Unterstützt der Server das nicht, schlägt die Verbindung fehl — dann TLS am Mailserver
   aktivieren; einen Klartextweg gibt es bewusst nicht mehr.
5. Mitarbeiter mit gesperrtem **persönlichem** Konto (Hinweis im Profil) tragen eigene
   Zugangsdaten ein oder nutzen ein freigegebenes zentrales Konto.

### Möglicher Credential-Wechsel

Ob das zentrale SMTP-Passwort bzw. das Microsoft-Client-Secret tatsächlich abgeflossen ist,
lässt sich aus der Anwendung nicht feststellen. Hinweise darauf liefern:
- `mail_accounts`-Zeilen mit `owner_user_id IS NOT NULL AND use_central_credentials = true`
  (nach der Migration erkennbar am Hinweistext in `last_error`) — `imap_host` zeigt, wohin die
  Daten gingen; `last_scan_at` ungefähr, wann zuletzt.
- Graph: Anmelde-/Zugriffsprotokolle der App-Registrierung in Entra ID (Mailbox-Zugriffe auf
  andere Postfächer als das zentrale).

Gibt es solche Konten mit fremdem Server, **SMTP-Passwort beim Mailanbieter ändern** und in
Einstellungen → System → E-Mail neu eintragen; bei Graph ein **neues Client-Secret** erzeugen,
das alte widerrufen. Ein Passwortwechsel bei gleichem Benutzer erfordert keine
Neubestätigung; wechselt der Benutzer, müssen die zentralen Konten bestätigt werden (Schritt 1).

## 7. Prüfungen (tatsächlich ausgeführt)

Umgebung: Cloud-Arbeitskopie, Python 3.12.3, PostgreSQL 16 (lokal, Wegwerf-DB), Node 22.22.0.
Alle Zugangsdaten erfunden; IMAP simuliert bzw. Wegwerf-TLS-Server auf 127.0.0.1; Graph nie
aufgerufen; DNS simuliert.

| Prüfung | Ergebnis |
|---|---|
| Regressionstest am **unveränderten** Stand | **1 failed** – „Zentrale Zugangsdaten wurden 2x an einen vom Mitarbeiter gewählten Server übertragen: ['mail.angreifer.invalid']" |
| Derselbe Test nach der Behebung | passed |
| `pytest tests/test_mailimport*.py tests/test_migrationen.py` | **81 passed** |
| Vollständige Backend-Testreihe `python -m pytest` (Endstand) | **1054 passed**, 0 failed (9:02 min) — vorher auf `main`: 22 Mail-Tests grün, Gesamtzahl +56 |
| `ruff check --select F,E9,B904 --ignore F841 app/ alembic/env.py` (CI-Pflicht) | All checks passed |
| `bandit -ll` auf die drei geänderten Module | keine Meldungen |
| Frontend `npm ci`, `npm run build` | ok |
| Frontend `vitest run` | **7 Dateien, 33 Tests passed** (3 neu) |
| Unabhängige Prüfung durch separaten Prüfer (las nur den Diff) | kein Umgehungsweg; 9 kleinere Punkte, behoben: generische Fehlermeldung ohne interne IP, Flag-Fehler bereinigt, `fec0::/10` gesperrt, IPv6 in Klammern, alle geprüften Adressen der Reihe nach, Port-Beschränkung interner Ziele (+ `host:port`), `null` im Update, Socket-Schließen bei TLS-Fehler |

Abgedeckte Fälle (Auftrag „Tests und Validierung"): Umleitung durch Nicht-Admin (Anlegen,
IMAP + Graph) · nachträgliche Änderung (persönlich, global, an der API vorbei) · freigegebene
Mitarbeiter (Gruppe, alle) · nicht freigegebene Benutzer (Liste, Scan, Vorschläge annehmen/
verwerfen) · persönliche Konten (TLS + STARTTLS) · Verbindungstest/manueller/Hintergrund-Scan
mit identischen Regeln · Graph-Mailboxbindung inkl. Outlook-Flagge · TLS: selbstsigniert,
falscher Hostname (echter Handshake) → Abbruch vor LOGIN; Firmen-CA → Erfolg; STARTTLS fehlt →
kein Klartext · interne Adressen (IPv4/IPv6/gemischte DNS-Antworten/IP-Literale) · Admin-
Freigaben inkl. Port · Migration mit sechs Altfällen + Rückweg · keine Geheimnisse in
Antworten/Fehlern/Logs.

## 8. Nicht geprüft

- Kein Lauf gegen echte Mailanbieter oder Microsoft 365 (bewusst, laut Auftrag).
- Kein Lauf im Docker-Image/auf dem Server; die CI baut die Images.
- Bestandsübernahme gegen die **Produktionsdaten**: Migration nur gegen konstruierte Altfälle
  getestet. Beim Einspielen Abschnitt 6 abarbeiten.
- Oberfläche nur über Vitest/jsdom, nicht im Browser angesehen.

## 9. Risiken und Rückweg

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Interne Mailserver ohne Freigabe | Scan schlägt fehl („nicht erreichbar oder nicht freigegeben") | Abschnitt 6, Schritt 3 |
| Server ohne STARTTLS/mit selbstsigniertem Zertifikat | Verbindung scheitert | TLS am Server einrichten bzw. Firmen-CA hinterlegen |
| Wechsel des zentralen SMTP-Benutzers | zentrale Konten gesperrt | „Ziel bestätigen" |
| Rückweg nötig | – | Vorherige Version deployen + `alembic downgrade 0062` (öffnet den Befund wieder) |

## 10. Abnahme-Checkliste

- [ ] CI grün (pytest, Vitest, ruff, Docker-Build)
- [ ] Nach Deploy: Einstellungen → KI & Mail-Import öffnen, Sperrhinweise abarbeiten
- [ ] Freigaben der zentralen Konten kontrollieren
- [ ] Interne Mailserver/Firmen-CA eintragen (falls vorhanden)
- [ ] Ein zentrales Konto „Verbindung testen" + „Jetzt scannen"
- [ ] Als Mitarbeiter: persönliches Konto – Option „Zentrale Zugangsdaten" ist nicht mehr da
- [ ] Credential-Wechsel entscheiden (Abschnitt 6)
