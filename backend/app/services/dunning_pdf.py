"""
Mahnschreiben als PDF.

Bewusst **kein** Ableger der Belegvorlagen: Ein Mahnschreiben ist ein Brief,
keine Rechnung. Es hat keine Positionen, keine Steueraufschlüsselung und keine
Belegnummer aus dem Rechnungsnummernkreis — es listet Forderungen auf. Es die
fünf Belegvorlagen mitschleppen zu lassen, hieße fünf Layouts zu pflegen, von
denen vier nie zum Einsatz kommen.

Übernommen wird dagegen das Briefpapier: Kopfbalken, Logo, Adressfeld und
Fußzeile stammen aus denselben Bausteinen wie Vorlage 1, damit die Post an den
Kunden einheitlich aussieht.

Bei einer Sammelmahnung (mehrere Belege desselben Kunden, gleiche ``batch_id``)
stehen alle betroffenen Rechnungen auf einem Schreiben.
"""
import io
import json
import re
from decimal import Decimal

from weasyprint import HTML as WeasyprintHTML

from app.services.invoice_pdf import (BASE_CSS, _logo_b64, _addr_lines,
                                      _recipient_lines, _footer_html,
                                      _fmt_date_long, _fmt_amount, _fmt_date)
from app.services import dunning as dunning_service


def _kontext(db, invoice):
    """Absender, Empfänger und Einstellungen — wie bei der Belegerzeugung."""
    from app.api.invoice import _load_pdf_context
    return _load_pdf_context(db, invoice)


def _geschwister(db, eintrag):
    """
    Alle Mahnungen desselben Laufs (Sammelmahnung), sonst nur diese eine.

    Sortiert nach Belegdatum, damit die älteste Forderung oben steht — das ist
    die Reihenfolge, in der ein Kunde die Liste erwartet.
    """
    from app.models.invoice import Invoice, InvoiceDunning
    if not eintrag.batch_id:
        return [eintrag]
    zeilen = (db.query(InvoiceDunning)
              .join(Invoice, Invoice.id == InvoiceDunning.invoice_id)
              .filter(InvoiceDunning.batch_id == eintrag.batch_id)
              .order_by(Invoice.date.asc()).all())
    return zeilen or [eintrag]


def baue_html(db, eintrag) -> tuple:
    """
    Gibt ``(html, dateiname)`` zurück.

    Von der PDF-Erzeugung getrennt, damit sich der Inhalt prüfen lässt, ohne
    WeasyPrint zu bemühen — Tests über den Text sind schneller und sagen bei
    einem Fehler mehr aus als ein Bytevergleich.
    """
    from app.models.invoice import Invoice

    zeilen = _geschwister(db, eintrag)
    belege = {z.invoice_id: db.query(Invoice).filter(Invoice.id == z.invoice_id).first()
              for z in zeilen}
    leitbeleg = belege[eintrag.invoice_id]

    settings, inv_settings, sender_contact, recipient_contact = _kontext(db, leitbeleg)
    stufen = {s["level"]: s for s in dunning_service.get_levels(db)}
    stufe = stufen.get(eintrag.level, {})

    primary = settings.get("primary_color") or "#ef7d00"
    waehrung = leitbeleg.currency or "EUR"
    logo_src = _logo_b64(settings)
    logo_html = (f'<img class="logo" src="{logo_src}" alt="Logo">' if logo_src else
                 f'<span style="font-size:14pt;font-weight:bold;">'
                 f'{settings.get("company_name", "")}</span>')

    sender = _addr_lines(sender_contact, settings)
    empfaenger = _recipient_lines(recipient_contact)
    plain_sender = [re.sub(r"<[^>]+>", "", z) for z in sender]
    ruecksende = " – ".join([p for p in plain_sender[:3] if p])

    sd = (sender_contact.data or {}) if sender_contact is not None else {}
    ort = sd.get("ort", "")
    datum = _fmt_date_long(eintrag.dunned_at)
    ort_datum = f"{ort}, {datum}" if ort else datum

    bank = inv_settings.get("bank", {})
    if isinstance(bank, str):
        try:
            bank = json.loads(bank)
        except Exception:
            bank = {}
    footer_html = _footer_html(sender_contact, bank)

    # ── Forderungstabelle ────────────────────────────────────────────────────
    zeilen_html, summe = "", Decimal("0")
    for z in zeilen:
        beleg = belege.get(z.invoice_id)
        gesamt = dunning_service.gesamtforderung(z)
        summe += gesamt
        zusatz = []
        if z.fee:
            zusatz.append(f"Mahnspesen {_fmt_amount(z.fee, waehrung)}")
        if z.interest:
            satz = f"{float(z.interest_rate):.2f} %".replace(".", ",") if z.interest_rate else ""
            tage = f"{z.interest_days} Tage" if z.interest_days else ""
            detail = ", ".join([t for t in (satz, tage) if t])
            zusatz.append(f"Verzugszinsen {_fmt_amount(z.interest, waehrung)}"
                          + (f" ({detail})" if detail else ""))
        zeilen_html += f"""
        <tr class="item">
          <td>{beleg.number or "—"}</td>
          <td>{_fmt_date(beleg.date)}</td>
          <td>{_fmt_date(beleg.due_date) if beleg.due_date else "—"}</td>
          <td class="num">{_fmt_amount(z.open_amount, waehrung)}</td>
          <td class="num total">{_fmt_amount(gesamt, waehrung)}</td>
        </tr>"""
        if zusatz:
            zeilen_html += (f'<tr class="detail"><td colspan="5">'
                            f'{" · ".join(zusatz)}</td></tr>')

    titel = eintrag.label or f"Mahnung (Stufe {eintrag.level})"
    einleitung = stufe.get("text") or ""
    frist_satz = (f"Wir ersuchen Sie, den Gesamtbetrag von "
                  f"<b>{_fmt_amount(summe, waehrung)}</b> bis spätestens "
                  f"<b>{_fmt_date_long(eintrag.due_date)}</b> auf das unten "
                  f"angeführte Konto zu überweisen."
                  if eintrag.due_date else
                  f"Wir ersuchen Sie, den Gesamtbetrag von "
                  f"<b>{_fmt_amount(summe, waehrung)}</b> umgehend zu überweisen.")

    # Der Hinweis steht auf jedem Schreiben: Eine Überschneidung mit einer
    # bereits getätigten Zahlung ist der häufigste Grund für eine unberechtigte
    # Mahnung — und der Satz kostet nichts.
    schluss = ("Sollte sich Ihre Zahlung mit diesem Schreiben überschnitten "
               "haben, betrachten Sie es bitte als gegenstandslos.")

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
{BASE_CSS}
@page {{
  @bottom-center {{ content: none; }}
  @bottom-right {{ content: "Seite " counter(page) " von " counter(pages);
                   font-size: 7.5pt; color: #999; }}
}}
.top-band {{ background: {primary}; height: 1.1cm; margin: -1.8cm -1.6cm 0 -1.8cm; }}
.logo-row {{ text-align: right; margin: 0.6cm 0 0.9cm 0; }}
.logo-row .logo {{ max-height: 65px; max-width: 240px; }}
.addr-row {{ display: flex; justify-content: space-between; margin-bottom: 0.2cm; }}
.ruecksende {{ font-size: 6.8pt; color: #777; text-decoration: underline; margin-bottom: 0.35cm; }}
.recipient {{ font-size: 9.5pt; line-height: 1.5; }}
.contact-block {{ font-size: 8pt; color: #666; line-height: 1.55; max-width: 6cm; }}
.ort-datum {{ text-align: right; font-weight: 700; font-size: 9.5pt; margin: 0.5cm 0; }}
.doc-title {{ font-size: 14pt; font-weight: 700; margin-bottom: 0.5cm; }}
.brieftext {{ font-size: 9.5pt; line-height: 1.55; margin-bottom: 0.5cm; }}
table.mahn {{ width: 100%; border-collapse: collapse; margin: 0.5cm 0 0.2cm 0; }}
table.mahn th {{ font-size: 8pt; font-weight: 700; text-align: left;
                 padding: 6px; border-bottom: 1.5px solid #333; }}
table.mahn td {{ padding: 6px; vertical-align: top; }}
table.mahn .num {{ text-align: right; white-space: nowrap; }}
table.mahn .total {{ font-weight: 600; }}
table.mahn tr.detail td {{ font-size: 7.5pt; color: #888; padding-top: 0; }}
table.summe {{ width: 45%; margin-left: auto; margin-top: 0.4cm;
               border-collapse: collapse; font-size: 9.5pt; }}
table.summe td {{ padding: 3.5px 6px; }}
table.summe .s-val {{ text-align: right; white-space: nowrap; }}
table.summe tr.grand td {{ font-weight: 700; border-top: 1.5px solid #333;
                           border-bottom: 3px double #333; }}
.hinweis {{ margin-top: 0.8cm; font-size: 8.5pt; color: #555; }}
</style>
</head><body>
<div class="top-band"></div>
<div class="logo-row">{logo_html}</div>
<div class="addr-row">
  <div>
    <div class="ruecksende">{ruecksende}</div>
    <div class="recipient">{"<br>".join(empfaenger)}</div>
  </div>
  <div class="contact-block">{"<br>".join(sender)}</div>
</div>
<div class="ort-datum">{ort_datum}</div>
<h1 class="doc-title">{titel}</h1>
<div class="brieftext">{einleitung}</div>
<table class="mahn">
  <thead><tr>
    <th>Rechnung</th><th>Datum</th><th>fällig am</th>
    <th class="num">offen</th><th class="num">Forderung</th>
  </tr></thead>
  <tbody>{zeilen_html}</tbody>
</table>
<table class="summe"><tbody>
  <tr class="grand"><td>Gesamtforderung</td>
      <td class="s-val">{_fmt_amount(summe, waehrung)}</td></tr>
</tbody></table>
<div class="brieftext" style="margin-top:0.8cm;">{frist_satz}</div>
<div class="hinweis">{schluss}</div>
{footer_html}
</body></html>"""

    kennung = leitbeleg.number or str(leitbeleg.id)[:8]
    return html, f"Mahnung_{kennung}_Stufe{eintrag.level}.pdf"


def generate_dunning_pdf(db, eintrag) -> tuple:
    """Gibt ``(pdf_bytes, dateiname)`` zurück."""
    html, dateiname = baue_html(db, eintrag)
    puffer = io.BytesIO()
    WeasyprintHTML(string=html, base_url="/").write_pdf(puffer)
    return puffer.getvalue(), dateiname
