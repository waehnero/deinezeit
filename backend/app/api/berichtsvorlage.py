"""
Vorlage des Projektzeitberichts (HTML für Vorschau und PDF).

Aus ``api/reports.py`` herausgelöst, als der Bericht ein neues Aussehen bekam:
Layout und Abfragelogik in einer Datei zu führen hieß, für jede Änderung an
der Darstellung im Endpunkt zu suchen — und umgekehrt.

Zwei Dinge, die man beim Ändern wissen muss:

1. **Dasselbe HTML dient zwei Zwecken.** Die Vorschau öffnet es im Browser,
   das PDF entsteht daraus mit WeasyPrint. Deshalb gibt es einen
   ``@media screen``-Block, der die Seite als weißes Blatt auf grauem Grund
   zeigt — im Druck greift er nicht. Wer nur für den Bildschirm gestaltet,
   bekommt ein PDF mit grauem Rand; wer nur fürs Papier gestaltet, bekommt
   eine Vorschau, die über die ganze Fensterbreite läuft (so war es bis
   01.09.2026).

2. **WeasyPrint ist kein Browser.** Verlässlich sind Tabellen, Blockelemente,
   Ränder und einfache Flex-Layouts; ``position: sticky``, ``gap`` in Grids
   und moderne Farbfunktionen sind es nicht. Neue Gestaltungsideen bitte im
   PDF gegenprüfen, nicht nur in der Vorschau.
"""
from collections import defaultdict
from datetime import datetime
from typing import Callable


# Fallback-Markenfarbe: dasselbe Orange wie in den Rechnungsvorlagen
STANDARD_FARBE = "#ef7d00"


def _hell(hexfarbe: str, anteil: float) -> str:
    """Markenfarbe mit Weiß mischen — für Flächen hinter dunklem Text.

    Eine eigene Berechnung statt ``rgba()``: Die Kopfzeile der Tabelle liegt im
    PDF auf Weiß, und WeisePrint rendert halbtransparente Hintergründe je nach
    Version unterschiedlich. Ein fertig gemischter Hex-Wert sieht überall gleich
    aus.
    """
    hexfarbe = (hexfarbe or STANDARD_FARBE).lstrip("#")
    if len(hexfarbe) != 6:
        hexfarbe = STANDARD_FARBE.lstrip("#")
    r, g, b = (int(hexfarbe[i:i + 2], 16) for i in (0, 2, 4))
    misch = lambda w: round(w + (255 - w) * anteil)  # noqa: E731
    return f"#{misch(r):02x}{misch(g):02x}{misch(b):02x}"


def bericht_html(
    entries: list,
    group_by: str,                 # "aufgabe" (= Zeitprojekt) | "benutzer" | "kontakt"
    settings: dict,
    filters: dict,
    current_user_name: str,
    logo_html: str,
    fmt_minutes: Callable[[int], str],
    fmt_dt: Callable[[datetime], str],
    runde: Callable[[object], int],
    empfaenger_html: str = "",
) -> str:
    """Vollständiges HTML des Projektzeitberichts.

    Die Formatier- und Rundungsfunktionen kommen von außen (aus reports.py),
    damit Bericht und Auswertung nachweislich dieselbe Rechnung verwenden.
    """
    farbe      = settings.get("brand_color") or settings.get("primary_color") or STANDARD_FARBE
    farbe_hell = _hell(farbe, 0.88)
    farbe_mittel = _hell(farbe, 0.55)

    # ── Gruppieren ────────────────────────────────────────────────────────────
    gruppen: dict = defaultdict(list)
    for e in entries:
        if group_by == "benutzer":
            schluessel = getattr(e.user, "full_name", "") or "Unbekannt"
        elif group_by == "kontakt":
            schluessel = (e.contact_name or "").strip() or "(ohne Kunde)"
        else:
            schluessel = e.project_name or "(ohne Zeitprojekt)"
        gruppen[schluessel].append(e)
    gruppen = dict(sorted(gruppen.items()))

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    zusammenfassung = []
    summe_verr = 0
    summe_nicht = 0
    for name, eintraege in gruppen.items():
        verr  = sum(runde(e) for e in eintraege if e.billable)
        nicht = sum(runde(e) for e in eintraege if not e.billable)
        summe_verr  += verr
        summe_nicht += nicht
        zusammenfassung.append((name, verr, nicht, verr + nicht))
    summe_gesamt = summe_verr + summe_nicht

    gruppen_spalte = {"benutzer": "Benutzer", "kontakt": "Kunde"}.get(group_by, "Zeitprojekt")
    # Zweite Spalte der Detailtabelle: das, wonach NICHT gruppiert wurde.
    # Nach Kunde gruppiert ist das Zeitprojekt die nützlichere Angabe — der
    # Kunde steht bereits in der Überschrift des Abschnitts.
    detail_spalte  = "Benutzer" if group_by == "aufgabe" else "Zeitprojekt"

    # ── Kopfzeile: Zeitraum + Filter als Marken ──────────────────────────────
    zeitraum = f"{filters.get('date_from', '')} – {filters.get('date_to', '')}"
    marken = []
    for beschriftung, wert in (
        # Der Kontakt entfällt hier, wenn er schon als Empfängerblock oben
        # steht — zweimal derselbe Name in zwei Zeilen liest sich wie ein Fehler.
        ("Kontakt",      "" if empfaenger_html else filters.get("contact_name")),
        ("Zeitprojekt",  filters.get("project_name")),
        ("Benutzer",     filters.get("user_name")),
        ("Verrechenbar", filters.get("billable_label")),
    ):
        if wert:
            marken.append(
                f'<span class="marke"><span class="marke-k">{beschriftung}</span>{wert}</span>'
            )
    marken_html = "".join(marken) or '<span class="marke marke-leer">Keine weiteren Filter</span>'

    # ── Zusammenfassungs-Zeilen ──────────────────────────────────────────────
    anteil = lambda m: round(m * 100 / summe_gesamt) if summe_gesamt else 0  # noqa: E731
    zusammenfassung_html = "".join(
        f"<tr>"
        f"<td class='name'>{name}</td>"
        f"<td class='zahl'>{fmt_minutes(verr)}</td>"
        f"<td class='zahl grau'>{fmt_minutes(nicht)}</td>"
        f"<td class='zahl stark'>{fmt_minutes(gesamt)}</td>"
        f"<td class='balken-zelle'>"
        f"  <span class='balken'><span style='width:{anteil(gesamt)}%'></span></span>"
        f"  <span class='prozent'>{anteil(gesamt)}%</span>"
        f"</td>"
        f"</tr>"
        for name, verr, nicht, gesamt in zusammenfassung
    )

    # ── Detail-Abschnitte ────────────────────────────────────────────────────
    def zeilen(eintraege) -> str:
        html = ""
        for e in sorted(eintraege, key=lambda x: x.started_at):
            zweitspalte = (
                (getattr(e.user, "full_name", "") or "—") if group_by == "aufgabe"
                else (e.project_name or "(ohne Zeitprojekt)")
            )
            notiz = (e.note or "").replace("\n", "<br>") or "<span class='leer'>—</span>"
            verr_marke = ('<span class="ja">verrechenbar</span>' if e.billable
                          else '<span class="nein">nicht verr.</span>')
            html += (
                f"<tr>"
                f"<td class='wer'>{zweitspalte}</td>"
                f"<td class='notiz'>{notiz}</td>"
                f"<td class='zeit'>{fmt_dt(e.started_at)}</td>"
                f"<td class='zeit'>{fmt_dt(e.ended_at)}</td>"
                f"<td class='zahl grau'>{fmt_minutes(e.pause_minutes or 0)}</td>"
                f"<td class='zahl stark'>{fmt_minutes(runde(e))}</td>"
                f"<td class='verr'>{verr_marke}</td>"
                f"</tr>"
            )
        return html

    abschnitte_html = ""
    for name, eintraege in gruppen.items():
        gruppen_summe = sum(runde(e) for e in eintraege)
        abschnitte_html += f"""
<section class="gruppe">
  <div class="gruppe-kopf">
    <h3>{name}</h3>
    <span class="gruppe-summe">{fmt_minutes(gruppen_summe)}</span>
  </div>
  <table class="detail">
    <thead><tr>
      <th class="wer">{detail_spalte}</th>
      <th class="notiz">Notiz</th>
      <th class="zeit">Beginn</th>
      <th class="zeit">Ende</th>
      <th class="zahl">Pause</th>
      <th class="zahl">Dauer</th>
      <th class="verr">Status</th>
    </tr></thead>
    <tbody>{zeilen(eintraege)}</tbody>
  </table>
</section>
"""

    # Anschriftfeld nur, wenn der Bericht genau einen Kunden betrifft
    empfaenger_block = (
        f'<div class="empfaenger"><p class="empf-titel">Bericht für</p>{empfaenger_html}</div>'
        if empfaenger_html else ""
    )

    erstellt = datetime.now().strftime("%d.%m.%Y %H:%M")
    rundung_hinweis = filters.get("rounding_label", "")

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<title>Projektzeitbericht {zeitraum}</title>
<style>
  @page {{
    size: A4;
    margin: 16mm 14mm 18mm 14mm;
    @bottom-left   {{ content: "{current_user_name}"; font-size: 7.5pt; color: #9aa0a6; font-family: Helvetica, Arial, sans-serif; }}
    @bottom-center {{ content: "Seite " counter(page) " von " counter(pages); font-size: 7.5pt; color: #9aa0a6; font-family: Helvetica, Arial, sans-serif; }}
    @bottom-right  {{ content: "{erstellt}"; font-size: 7.5pt; color: #9aa0a6; font-family: Helvetica, Arial, sans-serif; }}
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: Helvetica, Arial, sans-serif;
    font-size: 8.8pt;
    line-height: 1.5;
    color: #1f2430;
  }}

  /* Bildschirm-Vorschau: die Seite als Blatt zeigen, nicht als Fensterbreite.
     Im PDF greift dieser Block nicht — dort setzt @page die Ränder. */
  @media screen {{
    body {{
      background: #eceef1;
      padding: 28px 16px 48px;
    }}
    .blatt {{
      width: 210mm;
      max-width: 100%;
      margin: 0 auto;
      background: #fff;
      padding: 16mm 14mm 18mm;
      border-radius: 6px;
      box-shadow: 0 10px 40px rgba(0,0,0,.14);
    }}
    .bildschirm-fuss {{ display: block; }}
  }}
  .bildschirm-fuss {{ display: none; }}

  /* ── Kopf ──────────────────────────────────────────────────────────────
     Links das Firmenlogo, rechts der Titel des Berichts. Die eigene Adresse
     steht bewusst NICHT im Kopf (Beschluss 01.09.2026): Der Bericht geht an
     den Kunden, und dessen Anschrift steht darunter — die eigene daneben
     macht den Kopf voll, ohne etwas zu klären. Wer sie braucht, findet sie
     auf der Rechnung. */
  .kopf {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 14mm; }}
  .kopf .titelblock {{ text-align: right; }}
  .kopf h1 {{
    font-size: 19pt; font-weight: 700; letter-spacing: -.2pt; color: #12161f;
  }}
  .kopf .zeitraum {{
    font-size: 9.5pt; color: {farbe}; font-weight: 600; margin-top: 1mm;
  }}
  .kopf .firma {{ font-size: 8pt; color: #6b7280; line-height: 1.55; }}
  .logo {{ display: block; max-height: 56px; max-width: 260px; object-fit: contain; margin-bottom: 2.5mm; }}
  .logo-text {{ display: block; font-size: 13pt; font-weight: 700; color: #1f2430; margin-bottom: 1.5mm; }}

  .trennlinie {{ height: 2.5px; background: {farbe}; margin: 4mm 0 0; border-radius: 2px; }}

  /* ── Empfänger (Kunde) ─────────────────────────────────────────────── */
  .empfaenger {{
    margin-top: 6mm; padding-left: 3mm; border-left: 3px solid {farbe_mittel};
    font-size: 9pt; line-height: 1.5;
  }}
  .empf-titel {{
    font-size: 7pt; text-transform: uppercase; letter-spacing: .5pt;
    color: #9aa0a6; font-weight: 700; margin-bottom: .8mm;
  }}
  .empf-name {{ font-weight: 700; font-size: 10pt; color: #12161f; }}
  .empfaenger div {{ color: #4b5563; }}

  /* ── Filtermarken ──────────────────────────────────────────────────── */
  .marken {{ margin: 4mm 0 7mm; }}
  .marke {{
    display: inline-block; font-size: 7.8pt; color: #374151;
    background: #f3f4f6; border-radius: 20px; padding: 1.6mm 3mm;
    margin: 0 1.6mm 1.6mm 0;
  }}
  .marke-k {{ color: #9aa0a6; margin-right: 1.6mm; }}
  .marke-leer {{ color: #9aa0a6; background: transparent; padding-left: 0; }}

  /* ── Kennzahlen ────────────────────────────────────────────────────── */
  .kennzahlen {{ display: flex; gap: 4mm; margin-bottom: 7mm; }}
  .kennzahl {{
    flex: 1; border: 1px solid #e5e7eb; border-radius: 5px; padding: 3mm 4mm;
  }}
  .kennzahl.haupt {{ background: {farbe_hell}; border-color: {farbe_mittel}; }}
  .kennzahl .titel {{
    font-size: 7pt; text-transform: uppercase; letter-spacing: .5pt;
    color: #6b7280; font-weight: 700;
  }}
  .kennzahl .wert {{ font-size: 16pt; font-weight: 700; line-height: 1.25; color: #12161f; }}
  .kennzahl.haupt .wert {{ color: {farbe}; }}
  .kennzahl .zusatz {{ font-size: 7.4pt; color: #9aa0a6; }}

  /* ── Überschriften ─────────────────────────────────────────────────── */
  h2 {{
    font-size: 11pt; font-weight: 700; color: #12161f;
    margin: 0 0 3mm; padding-bottom: 1.5mm; border-bottom: 1px solid #e5e7eb;
  }}

  /* ── Tabellen ──────────────────────────────────────────────────────── */
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    font-size: 7pt; text-transform: uppercase; letter-spacing: .45pt;
    color: #6b7280; font-weight: 700; text-align: left;
    padding: 2mm 2.5mm; background: #f7f8fa; border-bottom: 1px solid #e5e7eb;
  }}
  td {{ padding: 2mm 2.5mm; border-bottom: 1px solid #f0f1f3; vertical-align: top; }}
  .zahl {{ text-align: right; white-space: nowrap; }}
  .stark {{ font-weight: 700; }}
  .grau {{ color: #9aa0a6; }}
  .leer {{ color: #d1d5db; }}
  .name {{ font-weight: 600; }}

  /* Zusammenfassung */
  table.zusammenfassung {{ margin-bottom: 8mm; }}
  table.zusammenfassung tfoot td {{
    border-top: 1.5px solid #1f2430; border-bottom: 0;
    font-weight: 700; padding-top: 2.5mm;
  }}
  .balken-zelle {{ width: 26mm; }}
  .balken {{
    display: block; height: 4px; background: #eceef1; border-radius: 2px;
    overflow: hidden; margin-top: 2mm;
  }}
  .balken span {{ display: block; height: 4px; background: {farbe}; border-radius: 2px; }}
  .prozent {{ font-size: 7pt; color: #9aa0a6; }}

  /* Detail-Abschnitte */
  /* Ein Abschnitt soll nicht mitten in der Tabelle umbrechen. Beide
     Schreibweisen, weil WeasyPrint je nach Version die alte oder die neue
     Eigenschaft auswertet. */
  .gruppe {{ margin-bottom: 7mm; break-inside: avoid; page-break-inside: avoid; }}
  .gruppe-kopf {{
    display: flex; justify-content: space-between; align-items: baseline;
    border-left: 3px solid {farbe}; padding: 0 0 1.5mm 3mm; margin-bottom: 2mm;
  }}
  .gruppe-kopf h3 {{ font-size: 10pt; font-weight: 700; color: #12161f; }}
  .gruppe-summe {{ font-size: 10pt; font-weight: 700; color: {farbe}; }}
  table.detail th, table.detail td {{ font-size: 8.2pt; }}
  table.detail .zeit {{ white-space: nowrap; color: #4b5563; }}
  table.detail .wer {{ font-weight: 600; }}
  table.detail .notiz {{ color: #4b5563; }}
  table.detail tbody tr:nth-child(even) td {{ background: #fafbfc; }}
  .verr {{ white-space: nowrap; }}
  .ja, .nein {{
    display: inline-block; font-size: 7pt; font-weight: 700; border-radius: 20px;
    padding: .8mm 2.2mm;
  }}
  .ja   {{ background: #e8f6ed; color: #1a7f47; }}
  .nein {{ background: #f3f4f6; color: #6b7280; }}

  .fusszeile {{
    margin-top: 6mm; padding-top: 2.5mm; border-top: 1px solid #e5e7eb;
    font-size: 7.2pt; color: #9aa0a6; display: flex; justify-content: space-between;
  }}
</style>
</head>
<body>
<div class="blatt">

  <header class="kopf">
    <div class="firma">{logo_html}</div>
    <div class="titelblock">
      <h1>Projektzeitbericht</h1>
      <p class="zeitraum">{zeitraum}</p>
    </div>
  </header>
  <div class="trennlinie"></div>

  {empfaenger_block}

  <div class="marken">{marken_html}</div>

  <div class="kennzahlen">
    <div class="kennzahl haupt">
      <p class="titel">Gesamt</p>
      <p class="wert">{fmt_minutes(summe_gesamt)}</p>
      <p class="zusatz">{len(entries)} {'Eintrag' if len(entries) == 1 else 'Einträge'}{rundung_hinweis}</p>
    </div>
    <div class="kennzahl">
      <p class="titel">Verrechenbar</p>
      <p class="wert">{fmt_minutes(summe_verr)}</p>
      <p class="zusatz">{anteil(summe_verr)} % der Gesamtzeit</p>
    </div>
    <div class="kennzahl">
      <p class="titel">Nicht verrechenbar</p>
      <p class="wert">{fmt_minutes(summe_nicht)}</p>
      <p class="zusatz">{anteil(summe_nicht)} % der Gesamtzeit</p>
    </div>
  </div>

  <h2>Zusammenfassung</h2>
  <table class="zusammenfassung">
    <thead><tr>
      <th>{gruppen_spalte}</th>
      <th class="zahl">Verrechenbar</th>
      <th class="zahl">Nicht verrechenbar</th>
      <th class="zahl">Gesamt</th>
      <th class="balken-zelle">Anteil</th>
    </tr></thead>
    <tbody>{zusammenfassung_html}</tbody>
    <tfoot><tr>
      <td>Gesamt</td>
      <td class="zahl">{fmt_minutes(summe_verr)}</td>
      <td class="zahl">{fmt_minutes(summe_nicht)}</td>
      <td class="zahl">{fmt_minutes(summe_gesamt)}</td>
      <td></td>
    </tr></tfoot>
  </table>

  <h2>Einzelne Projektzeiten</h2>
  {abschnitte_html}

  <!-- Nur am Bildschirm: im PDF steht dasselbe in der Seitenfußzeile -->
  <div class="fusszeile bildschirm-fuss">
    <span>Ersteller: {current_user_name}</span>
    <span>Erstellt am {erstellt}</span>
  </div>

</div>
</body>
</html>"""
