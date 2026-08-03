# Modul „Verkauf" — Vollständige Funktionsprüfung

**Stand:** 31.07.2026 · **Branch bei Prüfung:** `feature/postecke-instagram`
**Geprüft:** `api/invoice.py`, `api/accounting.py`, `models/invoice.py`,
`models/accounting.py`, `schemas/invoice.py`, `services/invoice_pdf.py`,
`services/invoice_snapshot.py`, `services/invoice_archive.py`,
`services/recurring_service.py`, `alembic/0011`–`0013`, `0026`,
`pages/InvoicePage.jsx`, `pages/InvoiceFormPage.jsx`, `pages/InvoiceBookPage.jsx`,
`services/api.js`, `backend/tests/*`

> **Umsetzungsstand**
>
> | Etappe | Branch | Status |
> |---|---|---|
> | 1 — Reparieren | `fix/verkauf-kritische-fehler` | ✅ umgesetzt (A-1, A-2, A-3, A-4, A-12, A-13 + Tests) |
> | 2a — Belegsperre & Nummernkreis | `feature/verkauf-belegsperre` | ✅ umgesetzt (A-7, A-8, A-9, A-10, A-11, A-17a, B-4 + Tests) |
> | 2b — Leistungsdatum & Steuer | `feature/verkauf-leistungsdatum-steuer` | ✅ umgesetzt (B-1, B-2, A-5, A-6, A-15 teilweise + Tests) |
> | 3a — Zahlungen & offene Posten | `feature/verkauf-zahlungen` | ✅ umgesetzt (C-2, C-3, A-17b + Tests) |
> | 3b — Mahnwesen & Skonto | offen | C-1, C-9 |
> | 4a — Erlöskonto & UVA | `feature/verkauf-uva` | ✅ umgesetzt (A-16, C-7 + Tests) |
> | 4b — Periodenabschluss & Übergabepaket | `feature/verkauf-monatsabschluss` | ✅ umgesetzt (C-6, C-8, B-5, Übergabe-Historie + Tests) |
> | Sammelbranch Kleinigkeiten | `fix/verkauf-kleinigkeiten` | ✅ umgesetzt (A-14, A-17e/f/g, B-3) |
> | Positionstypen & Gliederung | `feature/verkauf-positionstypen` | ✅ umgesetzt (A-15 + Umsortieren) |
> | 5 — E-Rechnung & Komfort | — | offen |
>
> **Entscheidungen aus Etappe 2a** (Oliver): Gesperrt wird alles, was auf dem
> Beleg gedruckt wird oder die Buchung bestimmt — änderbar bleiben nur interne
> Notiz und Projektzuordnung. Belegnummer fällt beim Finalisieren. Protokoll
> mit Ansicht am Beleg, erst ab dem Finalisieren.
>
> **Entscheidungen aus Etappe 2b:** Steuersätze als gepflegte Liste mit eigenem
> USt-Code (BMD-Codes sind kanzleiabhängig). Rundung je Steuersatz; bei
> Altbelegen bleibt die gespeicherte Summe maßgeblich und die Restdifferenz
> wird der größten Steuerzeile zugeschlagen. Leistungsdatum ist Pflicht erst
> beim Ausstellen, nicht schon beim Speichern des Entwurfs.
>
> **Weiterhin offen:** Zeiteinträge können ohne `contact_id` entstehen (nur
> Name); der Namens-Rückfall fängt das ab, sauber ist es nicht. Die
> Positionstypen `discount` und `subtotal` (A-15) sind nach wie vor nicht
> umgesetzt — nur Textzeilen rechnen jetzt korrekt mit null. Und: 42 bekannte
> Schwachstellen in sieben Python-Paketen (pip-audit) warten auf ein
> Abhängigkeits-Update.

> **Der folgende Befund-Teil beschreibt den Zustand bei der Prüfung (31.07.2026),
> also VOR Etappe 1.** Er bleibt bewusst unverändert als Referenz stehen.
> Ziel der Prüfung: Ist das Modul so weit, dass am Monatsende ein sauberes,
> prüfungsfestes Paket an den Steuerberater übergeben werden kann?
>
> **Kurzantwort: Nein — noch nicht.** Zwei Funktionen sind aktuell komplett
> defekt (darunter der BMD-Export selbst), und für einen Monatsabschluss fehlen
> mehrere Bausteine, die jede Vergleichssoftware hat.

---

## Inhalt

- [0. Management-Zusammenfassung](#0-management-zusammenfassung)
- [1. Was heute funktioniert](#1-was-heute-funktioniert)
- [2. Teil A — Defekte Funktionen (Bugs)](#2-teil-a--defekte-funktionen-bugs)
- [3. Teil B — Rechtliche Lücken (§ 11 UStG / § 131 BAO / GoBD)](#3-teil-b--rechtliche-lücken)
- [4. Teil C — Fehlende Funktionen im Vergleich zur Standardsoftware](#4-teil-c--fehlende-funktionen-im-vergleich-zur-standardsoftware)
- [5. Teil D — Der Monatsabschluss-Workflow](#5-teil-d--der-monatsabschluss-workflow)
- [6. Teil E — Vorschlag zur Priorisierung](#6-teil-e--vorschlag-zur-priorisierung)

---

## 0. Management-Zusammenfassung

| Bereich | Bewertung | Kernproblem |
|---|---|---|
| Belegerfassung (Angebot → AB → Rechnung) | 🟢 gut | Kette ist vorhanden und sauber gebaut |
| PDF-Erzeugung & Versand | 🟢 gut | 5 Vorlagen, E-Mail-Templates, Archivierung |
| Wiederkehrende Rechnungen | 🟡 teilweise | nur „Entwurf erzeugen"; 2 von 3 Modi tot |
| Zeiterfassung → Rechnung | 🔴 **defekt** | Endpunkt ist abgeschnitten, liefert `null` |
| Buchhaltungs-Export (BMD) | 🔴 **defekt** | wirft AttributeError → HTTP 500 |
| Zahlungsverwaltung | 🔴 fehlt | keine Teilzahlungen, keine OP-Liste, kein Mahnwesen |
| Unveränderbarkeit / Revisionssicherheit | 🔴 fehlt | finalisierte Rechnungen sind frei editierbar |
| Monatsabschluss | 🔴 fehlt | kein Periodenabschluss, keine UVA, kein Übergabepaket |
| E-Rechnung (ebInterface/Peppol) | 🔴 fehlt | kein strukturiertes Format |

**Die drei wichtigsten Baustellen:**

1. **A-1 und A-2 sind Totalausfälle** — der BMD-Export (dein Weg zum
   Steuerberater!) und die Zeiteintrags-Übernahme funktionieren derzeit gar
   nicht. Das sind keine Feature-Wünsche, das sind kaputte Funktionen.
2. **Finalisierte Rechnungen können nachträglich beliebig geändert werden**
   (A-7). Das ist der schwerwiegendste konzeptionelle Mangel — jede
   Vergleichssoftware sperrt den Beleg beim Finalisieren. Ohne diese Sperre ist
   das Modul im Prüfungsfall angreifbar.
3. **Der Monatsabschluss existiert als Konzept nicht.** Es gibt keinen
   Zeitpunkt, an dem ein Monat „zu" ist. Genau das ist aber der Vorgang, den du
   laut Zielsetzung abbilden willst.

---

## 1. Was heute funktioniert

Damit klar ist, worauf aufgebaut wird — das ist bereits solide:

- **Belegarten:** Rechnung, Angebot, Auftragsbestätigung, Gutschrift,
  Lieferschein — jeweils eigener Nummernkreis pro Jahr, Format konfigurierbar
  (`RE-{year}-{seq:03d}`), Zählerstand über die Einstellungen korrigierbar.
- **Belegkette:** Angebot → AB (`convert-to-ab`) → Rechnung
  (`convert-to-invoice`), mit `related_invoice_id` als Verkettung.
- **Storno:** wahlweise nur Statuswechsel oder mit automatisch erzeugter
  Gutschrift (Positionen mit negativer Menge).
- **Empfänger-Snapshot** (`recipient_snapshot`, Migration 0026): beim
  Finalisieren werden die Empfängerdaten eingefroren. Das ist sauber gelöst und
  genau richtig — spätere Stammdaten-Änderungen oder eine DSGVO-Anonymisierung
  verändern den Beleg nicht mehr. **Das ist der beste Teil des Moduls.**
- **PDF:** 5 Vorlagen, MwSt.-Aufschlüsselung nach Satz,
  Kleinunternehmer-/Reverse-Charge-Hinweis, Fußzeile aus dem Firmen-Kontakt,
  Status-Wasserzeichen.
- **E-Mail:** Versand mit PDF-Anhang, Vorlagen je Belegart mit Platzhaltern
  (`{nummer}`, `{betrag}`, `{faellig}` …), CC, Zusatzanhänge aus dem Datacenter
  oder lokal, Massenversand.
- **PDF-Archivierung ins Datacenter** unter dem Kontakt, Ordner je Belegart,
  Auslöser parametrierbar (`archive_triggers`).
- **Wiederkehrende Rechnungen:** Vorlage + Hintergrund-Thread, korrekte
  Monatsend-Logik (31.01. + 1 M = 28.02.), Nachhol-Schleife, Enddatum.
- **Verträge** an wiederkehrenden Belegen (max. 10), Ablage im Datacenter unter
  „Verträge" beim Kunden.
- **Duplizieren** mit selektiven Optionen (Positionen / Texte / Kontakt / Anhänge).
- **Verkaufsbuch** mit Zeitraum-Filter, Summen, CSV- und PDF-Export.
- **Kontenplan** mit österreichischem EKR vorbefüllt, Standard-Erlöskonto setzbar.
- **Sperren gegen Manipulation der Zeiterfassung:** abgerechnete Zeiteinträge
  können nicht mehr geändert werden (`_is_billed` in `zeiterfassung.py`). Sehr gut.

---

## 2. Teil A — Defekte Funktionen (Bugs)

### 🔴 A-1 · BMD-Export stürzt immer ab (HTTP 500)

**Datei:** `backend/app/api/accounting.py`, Zeile 234

```python
erloes_konto = pos.account_nr or default_erloes
```

`InvoicePosition` hat **kein Attribut `account_nr`**. Die Spalte wurde zwar in
Migration `0013_buchhaltung.py` (Zeile 140) in der Datenbank angelegt:

```python
op.add_column('invoice_positions', sa.Column('account_nr', sa.String(20), nullable=True))
```

… aber **nie in das SQLAlchemy-Modell** `backend/app/models/invoice.py`
aufgenommen. Nachgeprüft — die Spaltenliste des Modells lautet:

```
id, invoice_id, sort_order, article_id, time_entry_id, pos_type, description,
detail, quantity, unit, unit_price, discount_pct, tax_rate, line_total, created_at
```

**Auswirkung:** Sobald mindestens eine Rechnung im gewählten Zeitraum liegt,
wirft `pos.account_nr` einen `AttributeError`. Der Button „BMD Export" im
Verkaufsbuch zeigt nur „BMD-Export-Fehler". **Der Weg zum Steuerberater ist
damit aktuell zu.** Das fällt nur deshalb nicht in den Tests auf, weil es
für den BMD-Export überhaupt keinen Test gibt.

---

### 🔴 A-2 · Zeiteinträge können nicht in Rechnungen übernommen werden

**Datei:** `backend/app/api/invoice.py`, Zeile 1489–1510 (Dateiende)

Die Funktion `get_unbilled_time_entries` **bricht mitten im Code ab**:

```python
    from app.models.zeiterfassung import TimeEntry
    from sqlalchemy import not_, or_ as _or_


    # Bereits verrechnete Einträge      ← Datei endet hier, ohne Zeilenumbruch
```

Kein `return`, keine Query. Nachgeprüft: der Zustand ist **so im Git committed**
(MD5 von `HEAD` identisch mit der Arbeitskopie), also kein lokaler Unfall.

**Auswirkung:** Der Endpunkt ist syntaktisch gültig und liefert `null`. Im
Frontend (`InvoiceFormPage.jsx`, Zeile 130) läuft `setEntries(res.data)` → dann
`entries.filter(...)` in Zeile 141 → **TypeError, der Dialog „Zeiteinträge
übernehmen" bricht die Seite ab.** Die zentrale Verbindung zwischen
Zeiterfassung und Verkauf ist damit tot.

---

### 🔴 A-3 · Gutschriften bekommen im BMD-Export das falsche Vorzeichen

Beim Storno erzeugt `cancel_invoice` die Gutschriftspositionen mit
**negativer Menge** (`invoice.py` Zeile 793) → `line_total` ist negativ.

Im Export wird zusätzlich gedreht (`accounting.py` Zeile 246):

```python
sign = -1 if inv.doc_type == "gutschrift" else 1
```

**Zweimal negativ = positiv.** Die Gutschrift würde als **Umsatz** exportiert
statt als Umsatzminderung. Beim Steuerberater bedeutet das zu hohe Erlöse und
zu hohe Umsatzsteuer.

---

### 🔴 A-4 · Gutschriften werden standardmäßig gar nicht exportiert

`accounting.py`, Zeile 174:

```python
doc_type: Optional[str] = Query("rechnung")
```

Wählt man im Verkaufsbuch „Alle Typen", sendet das Frontend **keinen**
`doc_type` — dann greift der Server-Default `"rechnung"`. Gutschriften fehlen
also im Export, außer man wählt sie explizit einzeln aus (und bekommt dann nur
sie, mit falschem Vorzeichen, siehe A-3).

Für die Buchhaltung braucht es genau eine Auswahl: **alle buchungsrelevanten
Belege** (Rechnung + Gutschrift), niemals Angebote/AB/Lieferscheine.
Aktuell könnte man versehentlich Angebote exportieren — die sind kein Umsatz.

---

### 🟠 A-5 · Steuersatz 13 % wird als 20 % gebucht

`accounting.py`, Zeile 132–137:

```python
BMD_UST_CODES = {"20": "U20", "10": "U10", "0": "U00", None: "URC"}
...
ust_code = BMD_UST_CODES.get(rate_key, "U20")   # Fallback!
```

Österreich hat einen **13-%-Satz** (Beherbergung, Kultur, Ab-Hof-Verkauf,
lebende Tiere …) und für Jungholz/Mittelberg 19 %. Beide fallen auf den
Default `"U20"` — **falscher USt-Code im Buchungssatz**.

Passend dazu bietet das Positions-Dropdown im Formular
(`InvoiceFormPage.jsx`, Zeile 576) nur 20 / 10 / 0 / RC an — 13 % lässt sich
gar nicht erfassen. Die Steuersätze gehören konfigurierbar in die
Belegeinstellungen, nicht hartcodiert an zwei Stellen.

---

### 🟠 A-6 · Netto + MwSt. ≠ Brutto auf dem PDF möglich

Es gibt **drei verschiedene Rundungswege** für dieselbe Rechnung:

| Ort | Datei | Methode |
|---|---|---|
| Gespeicherte Summen | `invoice.py` `_calc_totals` | rundet **je Position** |
| MwSt.-Zeilen im PDF | `invoice_pdf.py` `_tax_breakdown` | rundet **je Steuersatz** |
| BMD-Buchungszeilen | `accounting.py` | rundet **je Position**, gruppiert danach |

Der Summenblock im PDF zeigt `invoice.subtotal` und `invoice.total` (Weg 1),
die MwSt.-Zeilen dazwischen aber Weg 2. Bei mehreren Positionen mit
Nachkommastellen ergibt sich **Netto + MwSt. ≠ Gesamtsumme auf dem gedruckten
Beleg** — Cent-Differenz, aber auf einer Kundenrechnung. Korrekt (und in allen
Vergleichsprogrammen so umgesetzt) ist ausschließlich: **je Steuersatz
summieren, dann einmal runden.**

---

### 🔴 A-7 · Finalisierte Rechnungen bleiben voll editierbar

`invoice.py`, Zeile 690:

```python
if inv.status == "storniert":
    raise HTTPException(400, "Stornierte Rechnungen können nicht bearbeitet werden")
```

Das ist die **einzige** Sperre. Eine Rechnung mit Status `gesendet`, `offen`
oder sogar `bezahlt` kann per `PUT` komplett überschrieben werden — Betrag,
Positionen, Datum, Empfänger. Zeile 705 löscht sogar alle Positionen und legt
sie neu an.

**Auswirkung:** Der Kunde hat die Rechnung als PDF, in der Datenbank steht
etwas anderes. Kein Protokoll, keine Nachvollziehbarkeit. Das widerspricht der
Aufbewahrungs- und Unveränderbarkeitspflicht (§ 131 BAO / § 132 BAO, in
Deutschland GoBD) und ist der einzige Punkt dieser Analyse, den ich als
**echtes Risiko** einstufen würde.

Der Snapshot-Mechanismus (`recipient_snapshot`) schützt bereits die
Empfängerdaten — der gleiche Gedanke fehlt für Positionen und Beträge.

**So machen es die Vergleichsprogramme:** Beim Finalisieren wird der Beleg
schreibgeschützt. Korrekturen laufen ausschließlich über Storno + neue Rechnung
oder Gutschrift. sevDesk, lexware, BMD und myfactory handhaben das ausnahmslos so.

---

### 🟠 A-8 · `mark-paid` umgeht die Statusmaschine komplett

`invoice.py`, Zeile 812–831: keine Prüfung auf `doc_type`, keine Prüfung des
Ausgangsstatus. Damit lässt sich ein **Entwurf** oder ein **Angebot** als
„bezahlt" markieren. Ein einmal gesetzter Zahlungseingang kann außerdem nicht
mehr korrigiert werden (`"bezahlt": []` in der Übergangstabelle Zeile 862) —
ein Tippfehler im Zahldatum ist unumkehrbar.

---

### 🟠 A-9 · Belegart lässt sich nachträglich ändern

`InvoiceUpdate` erbt von `InvoiceCreate` und enthält damit `doc_type`
(`schemas/invoice.py`, Zeile 89). `update_invoice` schreibt alle Felder blind
durch (Zeile 695). Eine Rechnung `RE-2026-001` kann so zum „Angebot" werden —
**Belegart und Nummernkreis passen dann nicht mehr zusammen**, und der Beleg
verschwindet aus der Rechnungsliste.

Dasselbe gilt für `year`: ändert man das Belegdatum aufs Folgejahr, bleiben
`number` und `year` auf dem alten Stand.

---

### 🟠 A-10 · Nummernlücken durch Nummernvergabe an Entwürfe

`create_invoice` zieht die Nummer **sofort beim Anlegen** (Zeile 180) — also
schon für den Entwurf. `delete_invoice` erlaubt das Löschen von Entwürfen
(Zeile 728). Ergebnis: **Lücke im Nummernkreis**, die niemand erklären kann.

§ 11 Abs. 1 Z 3 UStG verlangt eine fortlaufende Nummer, § 131 BAO die
lückenlose Aufzeichnung. Jeder Nummernkreis muss für sich fortlaufend sein.
Der übliche Weg: **Nummer erst beim Finalisieren vergeben**, Entwürfe laufen
unter einer Vorschau-/Entwurfskennung.

---

### 🟠 A-11 · Zählerstand rückwärts setzbar → Nummernkollision

`update_number_sequence` (Zeile 300) akzeptiert jeden Wert ≥ 0. Setzt ein Admin
den Zähler zurück, erzeugt die nächste Rechnung eine bereits vergebene Nummer →
`UNIQUE`-Verletzung auf `invoices.number` → HTTP 500 ohne verständliche
Meldung. Es sollte nur Erhöhen erlaubt sein (mit Hinweis auf die entstehende Lücke).

---

### 🟠 A-12 · Kontaktname im Verkaufsbuch bleibt leer

`invoice.py`, Zeile 460–461:

```python
contact_name = d.get("name") or d.get("firma") or d.get("vorname", "")
```

Überall sonst im Modul wird `rec.display_name` verwendet (z. B. Zeile 147, 1274,
Zeile 217 in `accounting.py`). Die Keys `name` / `firma` existieren in den
Stammdaten-Feldern nicht → **die Spalte „Kontakt" im Verkaufsbuch ist leer.**

---

### 🟡 A-13 · Ausgewählte PDF-Vorlage wird ignoriert

In den Einstellungen kann eine Standard-Vorlage gewählt werden
(`SettingsPage.jsx`, Zeile 1739/1761: `default_template`). Das Belegformular
sendet aber hart:

```javascript
tax_mode: taxMode, template_id: 1,        // InvoiceFormPage.jsx, Zeile 295
```

**Die Vorlagen 2–5 sind über die Oberfläche nie erreichbar.** Die
Vorschau-Funktion (`/template-preview/{id}`) zeigt sie, benutzen kann man sie
nicht. Beim Bearbeiten eines Belegs wird die gespeicherte Vorlage sogar
auf 1 zurückgesetzt.

---

### 🟡 A-14 · MwSt.-Modus „Ein Satz für alle" ohne Wirkung

`tax_mode = "single_rate"` ist im Dropdown wählbar
(`InvoiceFormPage.jsx`, Zeile 439), wird aber weder in `_calc_totals` noch in
`invoice_pdf.py` ausgewertet — es verhält sich exakt wie `per_position`. Der
Nutzer wählt etwas aus, das nichts tut.

Ergänzend: `template_preview` setzt `tax_mode="normal"` (Zeile 408) — ein Wert,
den es im Modell gar nicht gibt.

---

### 🟡 A-15 · Positionstypen `text`, `discount`, `subtotal` sind nicht implementiert

Das Modell kennt `pos_type: item | text | time_entry | discount | subtotal`.
Tatsächlich:

- `_calc_totals` behandelt **alle** Typen gleich → eine `discount`-Zeile würde
  als normale Position addiert statt abgezogen.
- `_tax_breakdown` im PDF zählt **Textzeilen mit in die Steuergruppen** →
  eine Textzeile ohne Steuersatz landet im Bucket „RC" und erzeugt eine
  **falsche Zeile „Reverse Charge (0 %)"** samt Reverse-Charge-Hinweis auf dem
  PDF. Der BMD-Export überspringt Textzeilen dagegen korrekt (Zeile 226).
- Das Formular bietet gar keine Auswahl des Positionstyps an — Zwischensummen,
  Textblöcke und Rabattzeilen sind nicht erfassbar.

---

### 🟡 A-16 · Erlöskonto vom Artikel wird nie übernommen

Migration 0013 legt das Stammdaten-Feld `erloes_konto` beim Artikel an, und der
Changelog verspricht: *„Erlöskonto pro Artikel festlegbar — wird automatisch auf
Rechnungspositionen übernommen"*. Tatsächlich:

- `ArticleSearch.onSelect` (`InvoiceFormPage.jsx`, Zeile 103) überträgt nur
  `article_id`, `description`, `unit_price`, `unit`, `detail` — **nicht** `erloes_konto`.
- `InvoicePositionBase` (Schema) hat kein Feld dafür.
- `account_nr` ist im Modell nicht vorhanden (siehe A-1).

Ergebnis: **Alle Umsätze landen im BMD-Export auf dem einen Standard-Erlöskonto
4000.** Eine Trennung nach Erlösarten (Waren 20 %, Dienstleistung, EU, Drittland)
— genau das, was der Steuerberater braucht — ist nicht möglich.

---

### 🟡 A-17 · Weitere kleinere Punkte

| # | Punkt | Fundstelle |
|---|---|---|
| a | Stornierte Belege sind löschbar → Aufbewahrungspflicht verletzt | `invoice.py` 728 |
| b | Status `ueberfaellig` wird **nirgends automatisch gesetzt** — überfällige Rechnungen bleiben ewig „offen" | keine |
| c | `recurring_action` (`remind` / `create_and_send`) wird gespeichert, aber **nie ausgewertet**; das Frontend sendet immer `create` | `recurring_service.py` |
| d | N+1-Query: Verkaufsbuch lädt den Kontakt je Beleg einzeln in der Schleife | `invoice.py` 458 |
| e | `/book/pdf` fällt bei WeasyPrint-Fehler still auf HTML zurück — der Browser lädt dann „belegbuch.pdf", das HTML ist | `invoice.py` 610 |
| f | `bulk-send-email` committet **einmal am Ende**; ein Fehler in der Mitte kann Statusänderungen vorheriger Belege mitreißen | `invoice.py` 1449 |
| g | Der Wiederkehr-Worker schläft **erst 1 h**, bevor er das erste Mal prüft — nach einem Neustart am Monatsersten verzögert sich der Lauf | `recurring_service.py` 136 |
| h | Angebote haben kein Gültigkeitsdatum; `due_date` wird im Formular nur bei `doc_type=rechnung` angezeigt | `InvoiceFormPage.jsx` 425 |
| i | Kein Test für `accounting.py` — daher ist A-1 nie aufgefallen. Laut CLAUDE.md gilt: neues Modul ⇒ neuer Test | `backend/tests/` |

---

## 3. Teil B — Rechtliche Lücken

### 🔴 B-1 · Liefer-/Leistungsdatum ist nicht erfassbar

`delivery_date` existiert im Modell, im Schema **und** im PDF
(`invoice_pdf.py`, Zeile 383 und 478) — aber es gibt **kein Eingabefeld im
Belegformular**. Nachgeprüft: `grep delivery_date frontend/src/` findet nichts.

Vorlage 1 zeigt die Zeile nur, wenn gesetzt → sie erscheint nie.
Vorlagen 2–5 setzen ersatzweise das Belegdatum ein — das ist inhaltlich falsch,
sobald Leistung und Rechnungslegung auseinanderfallen (also fast immer).

**Das Liefer-/Leistungsdatum ist eine Pflichtangabe nach § 11 Abs. 1 Z 4 UStG.**
Fehlt sie, verliert der Kunde den Vorsteuerabzug. Das ist die dringendste
inhaltliche Lücke.

### 🟠 B-2 · Kein Leistungszeitraum (von–bis)

Bei Zeitabrechnung und Wartungsverträgen braucht es „Leistungszeitraum
01.07.–31.07.2026" statt eines Einzeldatums. Nicht im Modell vorhanden.
Sämtliche Vergleichsprogramme haben beides.

### 🟠 B-3 · UID des Leistungsempfängers wird nicht geprüft

Ab einem Rechnungsbetrag über **10.000 € brutto** ist die UID des Empfängers
Pflichtangabe (§ 11 Abs. 1 Z 2 UStG). Bei innergemeinschaftlichen Lieferungen
und Reverse Charge immer. Das PDF druckt die UID, wenn sie im Kontakt steht —
es gibt aber **keine Warnung, wenn sie fehlt**, und keine Format- oder
VIES-Prüfung. sevDesk und lexware validieren beim Speichern.

### 🔴 B-4 · Kein Änderungsprotokoll

Es gibt nur `created_by` / `updated_by` / `updated_at` — also immer nur den
**letzten** Zugriff. Wer wann welchen Betrag geändert hat, ist nicht
rekonstruierbar. In Kombination mit A-7 (Belege frei editierbar) bedeutet das:
**es gibt keine Nachvollziehbarkeit.**

### 🔴 B-5 · Keine Festschreibung / Periodensperre

Es gibt keinen Mechanismus, einen Monat abzuschließen. Nach der Übergabe an den
Steuerberater kann jederzeit noch eine Rechnung mit Datum im übergebenen Monat
angelegt oder geändert werden — ohne dass irgendetwas warnt. Das ist der
Kernpunkt für dein eigentliches Ziel (siehe Teil D).

---

## 4. Teil C — Fehlende Funktionen im Vergleich zur Standardsoftware

Legende: ✅ vorhanden · ⚠️ rudimentär · ❌ fehlt

| # | Funktion | DeineZeit | sevDesk | lexware | BMD | myfactory | Troi |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|
| C-1 | **Mahnwesen** (Stufen, Gebühren, Verzugszinsen) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-2 | **Teilzahlungen / Zahlungsjournal** | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-3 | **OP-Liste mit Fälligkeitsstaffel** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-4 | **Bankabgleich** (CAMT.053 / MT940) | ❌ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| C-5 | **E-Rechnung** (ebInterface / XRechnung / ZUGFeRD / Peppol) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-6 | **Periodenabschluss / Festschreibung** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-7 | **UVA-Auswertung** | ❌ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| C-8 | Weitere Exportformate (DATEV, RZL, BMD-MTF) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-9 | **Skonto / Zahlungsbedingungen** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-10 | **Anzahlungs-/Teil-/Schlussrechnung** | ❌ | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| C-11 | Sammelrechnung / Rechnungslauf | ❌ | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| C-12 | Preislisten / Kundenpreise / Staffeln | ❌ | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| C-13 | Lieferschein → Rechnung, Teillieferung | ❌ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ |
| C-14 | Fremdwährung mit Kurs | ⚠️ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-15 | Auswertungen (Umsatz je Kunde/Artikel/Monat) | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| C-16 | Projektabrechnung Budget vs. verrechnet | ❌ | ❌ | ⚠️ | ✅ | ✅ | ✅ |
| C-17 | Angebotsverfolgung / Pipeline | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ✅ |
| C-18 | Zahlungslink / Kundenportal | ❌ | ✅ | ✅ | ⚠️ | ✅ | ⚠️ |

### Die sieben wichtigsten Lücken im Detail

#### C-1 · Mahnwesen — fehlt vollständig

`grep -i "mahnung\|mahnwesen\|zahlungserinnerung"` findet **null Treffer** im
gesamten Repository. Es gibt keinen Weg, eine überfällige Rechnung anzumahnen.
Verschärfend: Status `ueberfaellig` wird nie automatisch gesetzt (A-17b), du
siehst also nicht einmal, *welche* Rechnungen überfällig sind.

**Was fehlt:** Mahnstufen (Zahlungserinnerung → 1./2./3. Mahnung), Mahnfristen,
Mahngebühren, Verzugszinsen (in AT: 9,2 Prozentpunkte über Basiszinssatz bei
B2B), Mahnsperre je Kunde, Sammelmahnung über mehrere Rechnungen, eigenes
Mahn-PDF, Mahnhistorie.

#### C-2 / C-3 · Zahlungen und offene Posten

Aktuell gibt es nur `paid_at` + `paid_amount` — **ein einziger Zahlungseingang
pro Rechnung**, als Feld direkt auf der Rechnung. Damit ist nicht abbildbar:

- Teilzahlung (Kunde zahlt 500 von 1.200 €)
- Ratenzahlung
- Überzahlung / Rundungsdifferenz
- Skontoabzug
- Zahlungsdatum korrigieren (siehe A-8)

Nötig wäre eine eigene Tabelle `invoice_payments` (Rechnung, Datum, Betrag,
Zahlungsart, Verwendungszweck, Notiz) und daraus abgeleitet der Offene-Posten-
Betrag. Darauf baut dann die **OP-Liste** auf: alle unbezahlten Rechnungen mit
Fälligkeitsstaffel (nicht fällig / 1–30 / 31–60 / 61–90 / > 90 Tage), je Kunde
summiert. Das ist die Standardauswertung, die jeder Steuerberater und jede Bank
sehen will — und dein tägliches Steuerungsinstrument.

#### C-5 · E-Rechnung

Kein strukturiertes Rechnungsformat vorhanden — es gibt ausschließlich PDF.

**Rechtliche Lage (Stand 07/2026):**

- **Österreich B2G:** seit 01.01.2014 verpflichtend; seit 01.01.2025 müssen
  Lieferanten des Bundes über **e-Rechnung.gv.at** in **ebInterface 5.0** oder
  **Peppol BIS 3.0** einreichen. → **Wenn du je an eine Bundesstelle
  fakturierst, geht das mit DeineZeit heute nicht.**
- **Österreich B2B:** noch keine Pflicht.
- **Deutschland:** Empfangspflicht seit 01.01.2025, Ausstellungspflicht gestaffelt.
  Relevant, sobald du an deutsche Firmenkunden fakturierst.
- **EU (ViDA, RL 2025/516):** ab 01.07.2030 verpflichtend für
  innergemeinschaftliche B2B-Lieferungen.

ebInterface, XRechnung und Peppol BIS 3.0 basieren alle auf **EN 16931** — man
baut also einmal ein Mapping und bedient damit alle Formate. Der richtige
Zeitpunkt dafür ist, wenn Belegdaten sauber und vollständig sind (also nach
B-1/B-2, denn EN 16931 verlangt das Leistungsdatum zwingend).

#### C-6 · Periodenabschluss — siehe Teil D

#### C-7 · UVA-Auswertung

Es gibt keine Umsatzsteuer-Auswertung. Für die Voranmeldung braucht man
Nettoumsätze und Steuerbeträge **je Steuersatz** für den Zeitraum, plus die
Sonderfälle: innergemeinschaftliche Lieferungen (Kz. 017), Reverse Charge
(Kz. 021 / 057), steuerfreie Umsätze, Ausfuhr (Kz. 011). Aktuell liefert das
Verkaufsbuch nur eine einzige Summe „MwSt." über alles.

#### C-9 · Skonto

„2 % Skonto bei Zahlung binnen 10 Tagen, 30 Tage netto" ist nicht abbildbar —
weder als Text auf dem Beleg noch rechnerisch beim Zahlungseingang.

#### C-10 · Anzahlungs- und Teilrechnungen

Für Projektgeschäft essenziell (Troi kann das, und ihr nutzt Troi genau dafür):
Anzahlungsrechnung → Teilrechnungen nach Baufortschritt → Schlussrechnung mit
Abzug der bereits fakturierten Beträge. Umsatzsteuerlich heikel, weil die
Anzahlung bereits USt-pflichtig ist und in der Schlussrechnung korrekt
abgesetzt werden muss. Fehlt vollständig.

---

## 5. Teil D — Der Monatsabschluss-Workflow

Das ist dein eigentliches Ziel. Heute existiert davon **kein einziger Schritt**
als Funktion. So sieht der Ablauf in den Vergleichsprogrammen aus:

```
1. PRÜFEN     → Gibt es im Monat noch Entwürfe? Lücken im Nummernkreis?
                Belege ohne Kontakt/UID/Leistungsdatum? Positionen ohne Erlöskonto?
                → Prüfliste, die den Abschluss blockiert, solange etwas offen ist.

2. ABSTIMMEN  → Summen je Steuersatz, Umsatz gesamt, OP-Stand zum Monatsletzten.
                → UVA-Vorschau.

3. FESTSCHREIBEN → Monat wird gesperrt. Ab jetzt: kein neuer Beleg mit Datum in
                   diesem Monat, keine Änderung an bestehenden Belegen.
                   Nur Admin kann mit Begründung wieder öffnen (protokolliert).

4. ÜBERGEBEN  → Ein Paket, ein Klick:
                   ├── buchungen.csv        (BMD-Buchungsjournal)
                   ├── verkaufsbuch.pdf     (Belegjournal des Monats)
                   ├── ust_uebersicht.pdf   (Summen je Steuersatz / UVA)
                   ├── offene_posten.pdf
                   └── belege/RE-2026-0xx.pdf … (alle Original-PDFs)
                → als ZIP, dazu ein Protokoll: wer, wann, welcher Zeitraum,
                  Prüfsumme/Hash über den Inhalt.

5. NACHWEIS   → Übergabe-Historie: welcher Monat wurde wann in welcher Fassung
                übergeben. Damit ist bei Rückfragen belegbar, was der
                Steuerberater tatsächlich bekommen hat.
```

Bemerkenswert: **Schritt 4 ist zu großen Teilen schon da** — die
PDF-Archivierung ins Datacenter legt bereits alle Belege beim Kunden ab. Es
fehlt die Klammer: die Prüfung davor, die Sperre, und das Zusammenpacken.

Für BMD ist das ZIP-Paket aus `buchungen.csv` + Originalbelegen genau das
etablierte Übergabeformat.

---

## 6. Teil E — Vorschlag zur Priorisierung

Kein Vorgriff auf deine Entscheidung — das ist mein Vorschlag zur Reihenfolge,
begründet nach „was blockiert was".

### Etappe 1 — Reparieren (nichts Neues, nur heilen)

*Branch-Vorschlag: `fix/verkauf-kritische-fehler`*

| # | Was | Aufwand |
|---|---|---|
| A-1 | `account_nr` ins Modell `InvoicePosition` aufnehmen | S |
| A-2 | `get_unbilled_time_entries` zu Ende schreiben | M |
| A-3 | Doppelte Negation bei Gutschriften beheben | S |
| A-4 | Export auf Rechnung **+** Gutschrift umstellen, Angebote ausschließen | S |
| A-12 | `display_name` statt `data["name"]` im Verkaufsbuch | S |
| A-13 | `default_template` im Formular verwenden | S |
| — | **Tests:** `test_verkauf_buchhaltung.py` (BMD-Export) und Test für die Zeiteintrags-Übernahme | M |

Ohne diese Etappe ist alles andere sinnlos — der Export funktioniert nicht.

### Etappe 2 — Rechtssicherheit

*Branch-Vorschlag: `feature/verkauf-belegsperre`*

| # | Was | Aufwand |
|---|---|---|
| B-1 | Feld „Liefer-/Leistungsdatum" ins Formular (Pflicht bei Rechnung) | S |
| B-2 | Leistungszeitraum von–bis | M |
| A-7 | **Finalisierte Belege sperren** — Änderung nur über Storno/Gutschrift | M |
| A-9 | `doc_type` aus `InvoiceUpdate` entfernen | S |
| A-10 | Nummer erst beim Finalisieren vergeben | M |
| A-11 | Zähler nur erhöhbar | S |
| B-4 | Änderungsprotokoll `invoice_audit_log` | M |
| A-5 | Steuersätze konfigurierbar (inkl. 13 %) | M |
| A-6 | Rundung vereinheitlichen: je Steuersatz | M |

A-7 ist der wichtigste Punkt dieser Analyse.

### Etappe 3 — Zahlungen & Mahnwesen

*Branch-Vorschlag: `feature/verkauf-zahlungen`*

| # | Was | Aufwand |
|---|---|---|
| C-2 | Tabelle `invoice_payments`, Teilzahlungen, Zahlungsjournal | L |
| A-17b | Automatischer Wechsel auf `ueberfaellig` (im bestehenden Worker) | S |
| C-3 | OP-Liste mit Fälligkeitsstaffel | M |
| C-1 | Mahnwesen mit Stufen, Gebühren, Mahn-PDF, Historie | L |
| C-9 | Skonto & Zahlungsbedingungen | M |

### Etappe 4 — Monatsabschluss (dein Zielbild)

*Branch-Vorschlag: `feature/verkauf-monatsabschluss`*

| # | Was | Aufwand |
|---|---|---|
| C-6 | Periodenabschluss + Sperre + Wiederöffnen mit Protokoll | L |
| C-7 | UVA-Auswertung je Steuersatz inkl. IG/RC/Ausfuhr | M |
| A-16 | Erlöskonto Artikel → Position durchreichen, Konto je Position wählbar | M |
| C-8 | Export-Paket als ZIP (CSV + Journal + USt + OP + Beleg-PDFs) | M |
| — | Übergabe-Historie mit Prüfsumme | M |

### Etappe 5 — E-Rechnung & Komfort

| # | Was |
|---|---|
| C-5 | EN 16931-Mapping → ebInterface 5.0, XRechnung, ZUGFeRD; später Peppol |
| C-4 | Bankabgleich CAMT.053 |
| C-10 | Anzahlungs-/Teil-/Schlussrechnung |
| C-15 | Umsatzauswertungen |
| A-14/15 | `single_rate` umsetzen oder entfernen; Positionstypen implementieren |

---

## Anhang · Fundstellen-Verzeichnis

| ID | Datei | Zeile |
|---|---|---|
| A-1 | `backend/app/api/accounting.py` | 234 |
| A-1 | `backend/app/models/invoice.py` | 89–116 (Modell ohne `account_nr`) |
| A-1 | `backend/alembic/versions/0013_buchhaltung.py` | 138–141 |
| A-2 | `backend/app/api/invoice.py` | 1489–1510 (Dateiende) |
| A-2 | `frontend/src/pages/InvoiceFormPage.jsx` | 129–141 |
| A-3 | `backend/app/api/accounting.py` | 246 · `invoice.py` 793 |
| A-4 | `backend/app/api/accounting.py` | 174 |
| A-5 | `backend/app/api/accounting.py` | 132–137, 231 |
| A-5 | `frontend/src/pages/InvoiceFormPage.jsx` | 574–578 |
| A-6 | `invoice.py` 84–89 · `invoice_pdf.py` 187–210, 534–542 |
| A-7 | `backend/app/api/invoice.py` | 680–716 |
| A-8 | `backend/app/api/invoice.py` | 812–831, 856–864 |
| A-9 | `backend/app/schemas/invoice.py` | 89 · `invoice.py` 694–696 |
| A-10 | `backend/app/api/invoice.py` | 180, 719–731 |
| A-11 | `backend/app/api/invoice.py` | 299–309 |
| A-12 | `backend/app/api/invoice.py` | 457–461 |
| A-13 | `frontend/src/pages/InvoiceFormPage.jsx` | 295 · `SettingsPage.jsx` 1739 |
| A-14 | `frontend/src/pages/InvoiceFormPage.jsx` | 437–441 · `invoice.py` 408 |
| A-15 | `backend/app/api/invoice.py` | 75–89 · `invoice_pdf.py` 191–199 |
| A-16 | `frontend/src/pages/InvoiceFormPage.jsx` | 102–104 |
| B-1 | `backend/app/services/invoice_pdf.py` | 383, 478 (Frontend: kein Feld) |
</content>
</invoke>
