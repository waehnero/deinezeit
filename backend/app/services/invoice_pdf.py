"""
Rechnungs-PDF-Generator — 5 Vorlagen
=====================================
Vorlage 1: Klassisch         — zweispaltig, Logo rechts, seriös
Vorlage 2: Modern            — farbiger Header-Block, minimalistische Typografie
Vorlage 3: Kompakt           — einspaltig, dichtes Layout, ideal für kurze Rechnungen
Vorlage 4: Elegant           — Linie statt Farbfläche, viel Weißraum
Vorlage 5: Farbenfroh        — primärfarbe aus Firmeneinstellungen, auffällig

Alle Vorlagen:
  - Logo aus Settings (logo_header_url / logo_url)
  - Absender aus company_contact
  - Bankdaten aus invoice_settings[bank]
  - MwSt.-Aufschlüsselung nach Steuersatz
  - Kleinunternehmer / Reverse-Charge-Hinweis
  - Druckoptimiert (A4, cm-Abstände)
"""
import io
import os
import re
import base64
import json
from decimal import Decimal
from datetime import date
from typing import Optional

from weasyprint import HTML as WeasyprintHTML

STATIC_DIR = "/app/static"


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────

def _logo_b64(settings: dict) -> str:
    url = settings.get("logo_header_url") or settings.get("logo_url") or ""
    if not url:
        return ""
    path = url.replace("/api/static", STATIC_DIR)
    if not os.path.exists(path):
        return ""
    ext  = os.path.splitext(path)[1].lower().lstrip(".")
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "svg": "image/svg+xml", "webp": "image/webp"}.get(ext, "image/png")
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return f"data:{mime};base64,{data}"


def _addr_lines(contact_record, settings: dict) -> list[str]:
    """Gibt Adresszeilen der eigenen Firma zurück."""
    lines = []
    name = settings.get("company_name", "")
    if contact_record:
        d = contact_record.data or {}
        name = contact_record.display_name or name
        lines.append(f"<strong>{name}</strong>")
        if d.get("adresse"):   lines.append(d["adresse"])
        plz  = d.get("plz", "")
        ort  = d.get("ort", "")
        if plz or ort:         lines.append(f"{plz} {ort}".strip())
        if d.get("land"):      lines.append(d["land"])
        if d.get("uid"):       lines.append(f"UID: {d['uid']}")
        if d.get("email"):     lines.append(d["email"])
        if d.get("telefon"):   lines.append(d["telefon"])
        if d.get("webseite"):  lines.append(d["webseite"])
    elif name:
        lines.append(f"<strong>{name}</strong>")
    return lines


def _recipient_lines(contact_record) -> list[str]:
    """Gibt Empfängeradresse zurück."""
    if not contact_record:
        return []
    d = contact_record.data or {}
    lines = []
    lines.append(f"<strong>{contact_record.display_name or ''}</strong>")
    if d.get("ansprechperson"): lines.append(d["ansprechperson"])
    if d.get("adresse"):        lines.append(d["adresse"])
    plz = d.get("plz", ""); ort = d.get("ort", "")
    if plz or ort:              lines.append(f"{plz} {ort}".strip())
    if d.get("land"):           lines.append(d["land"])
    if d.get("uid"):            lines.append(f"UID: {d['uid']}")
    return lines


def _footer_html(sender_contact, bank_settings: dict) -> str:
    """
    Gemeinsame Fußzeile für alle Vorlagen.
    Datenquelle ist primär der verknüpfte Firmen-Kontakt (Stammdaten-Felder werden
    über den Feldnamen erkannt), Fallback für die Bankdaten sind die Belegeinstellungen:
      - IBAN / BIC (SWIFT) / Bank*      → "Bankverbindung: …, IBAN …, BIC …"
      - UID* / Firmenbuch*              → "UID-Nr.: …, Firmenbuch-Nr.: …"
      - *gericht* (z.B. Handelsgericht, Gerichtsstand) → "Handelsgericht Salzburg, …"
      - Fußzeile* / Footer*             → freier Text (z.B. Eigentumsvorbehalt)
    """
    d = (sender_contact.data or {}) if sender_contact is not None else {}
    items = [(k.lower(), str(v).strip()) for k, v in d.items() if str(v or "").strip()]

    def _first(pred):
        return next((v for k, v in items if pred(k)), "")

    # Bankverbindung: bevorzugt aus dem Kontakt, sonst Belegeinstellungen
    iban = _first(lambda k: "iban" in k)
    bic  = _first(lambda k: "bic" in k or "swift" in k)
    bank = _first(lambda k: "bank" in k and "iban" not in k and "bic" not in k)
    if not iban:
        iban = str(bank_settings.get("iban", "") or "").strip()
        bic  = bic  or str(bank_settings.get("bic", "") or "").strip()
        bank = bank or str(bank_settings.get("bank", "") or "").strip()

    lines = []
    if iban:
        seg = [f"Bankverbindung: {bank}" if bank else "Bankverbindung"]
        seg.append(f"IBAN {iban}")
        if bic:
            seg.append(f"BIC {bic}")
        lines.append(", ".join(seg))

    legal = []
    uid = _first(lambda k: "uid" in k)
    if uid:
        legal.append(f"UID-Nr.: {uid}")
    firmenbuch = _first(lambda k: "firmenbuch" in k)
    if firmenbuch:
        legal.append(f"Firmenbuch-Nr.: {firmenbuch}")
    if legal:
        lines.append(", ".join(legal))

    # Gerichts-Angaben: Feldname wird als Label mit ausgegeben ("handelsgericht" → "Handelsgericht Salzburg")
    gericht = [f"{k.replace('_', ' ').title()} {v}" for k, v in items if "gericht" in k]
    if gericht:
        lines.append(", ".join(gericht))

    # Freie Fußzeilen-Texte (z.B. Eigentumsvorbehalt)
    lines += [v for k, v in items if "fusszeile" in k or "fussnote" in k or "footer" in k]

    if not lines:
        return ""
    return '<div class="page-footer">' + "<br>".join(lines) + "</div>"


def _fmt_date(d) -> str:
    if not d:
        return "—"
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except Exception:
            return d
    return d.strftime("%d.%m.%Y")


def _fmt_euro(n) -> str:
    try:
        return f"{float(n):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "—"


_MONATE = ["Jänner", "Februar", "März", "April", "Mai", "Juni",
           "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _fmt_date_long(d) -> str:
    """'2026-06-26' → '26. Juni 2026' (österreichische Langform)."""
    if not d:
        return "—"
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except Exception:
            return d
    return f"{d.day}. {_MONATE[d.month - 1]} {d.year}"


def _fmt_amount(n, currency: str = "EUR") -> str:
    """'2350' → '2.350,00 EUR' (Betrag mit Währungs-Kürzel statt Symbol)."""
    try:
        return f"{float(n):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + f" {currency}"
    except Exception:
        return "—"


def _tax_breakdown(positions, tax_mode: str) -> list[dict]:
    """Berechnet MwSt.-Aufschlüsselung nach Steuersatz."""
    if tax_mode == "kleinunternehmer":
        return []
    buckets: dict[str, Decimal] = {}
    for p in positions:
        rate = p.tax_rate
        if rate is None:
            key = "RC"
        else:
            key = str(int(rate)) if rate == int(rate) else str(rate)
        net = p.line_total or Decimal("0")
        buckets[key] = buckets.get(key, Decimal("0")) + net
    result = []
    for rate_key, net in sorted(buckets.items()):
        if rate_key == "RC":
            tax = Decimal("0")
            label = "Reverse Charge (0 %)"
        else:
            pct = Decimal(rate_key)
            tax = (net * pct / 100).quantize(Decimal("0.01"))
            label = f"MwSt. {rate_key} %"
        result.append({"label": label, "net": net, "tax": tax})
    return result


def _positions_html(positions, tax_mode: str) -> str:
    rows = ""
    for p in positions:
        if p.pos_type == "text":
            rows += f'<tr class="pos-text"><td colspan="5">{p.description}</td></tr>'
            continue
        qty   = float(p.quantity or 0)
        price = float(p.unit_price or 0)
        disc  = p.discount_pct
        tax_r = p.tax_rate
        total = float(p.line_total or 0)
        tax_cell = ""
        if tax_mode != "kleinunternehmer":
            tax_cell = "RC" if tax_r is None else f"{int(tax_r) if tax_r == int(tax_r) else tax_r} %"

        detail_row = ""
        if p.detail:
            detail_row = f'<tr class="pos-detail"><td colspan="5"><span>{p.detail}</span></td></tr>'

        disc_str = f'<br><small>- {float(disc):.0f}% Rabatt</small>' if disc else ""
        rows += f"""
        <tr class="pos-row">
          <td class="pos-desc">{p.description}{disc_str}</td>
          <td class="pos-num">{qty:g}</td>
          <td class="pos-num">{p.unit or ''}</td>
          <td class="pos-num">{_fmt_euro(price)}</td>
          {'<td class="pos-num">' + tax_cell + '</td>' if tax_mode != 'kleinunternehmer' else ''}
          <td class="pos-num pos-total">{_fmt_euro(total)}</td>
        </tr>
        {detail_row}
        """
    return rows


DOC_TYPE_LABELS = {
    "rechnung":     "RECHNUNG",
    "angebot":      "ANGEBOT",
    "gutschrift":   "GUTSCHRIFT",
    "lieferschein": "LIEFERSCHEIN",
}

STATUS_WATERMARKS = {
    "entwurf":   "ENTWURF",
    "storniert": "STORNIERT",
    "bezahlt":   "BEZAHLT",
}


# ─────────────────────────────────────────────────────────────────────────────
# CSS-Basis (gemeinsam für alle Vorlagen)
# ─────────────────────────────────────────────────────────────────────────────

BASE_CSS = """
@page {
  size: A4;
  margin: 1.8cm 1.6cm 2cm 1.8cm;
  @bottom-center {
    content: "Seite " counter(page) " von " counter(pages);
    font-size: 8pt; color: #999;
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 9pt; color: #222; line-height: 1.4; }
h1 { font-size: 18pt; font-weight: 700; letter-spacing: 0.02em; }
h2 { font-size: 10pt; font-weight: 600; }
.logo { max-height: 55px; max-width: 200px; object-fit: contain; }
.watermark {
  position: fixed; top: 40%; left: 50%; transform: translate(-50%, -50%) rotate(-30deg);
  font-size: 72pt; font-weight: 900; opacity: 0.06; color: #000;
  white-space: nowrap; pointer-events: none; z-index: 0;
}
table.positions { width: 100%; border-collapse: collapse; margin: 0.5cm 0; }
table.positions th {
  font-size: 8pt; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 5px 6px; border-bottom: 1.5px solid #333;
}
table.positions td { padding: 5px 6px; vertical-align: top; }
.pos-num { text-align: right; white-space: nowrap; }
.pos-total { font-weight: 600; }
.pos-text td { color: #555; font-style: italic; padding-top: 8px; padding-bottom: 2px; }
.pos-detail td span { font-size: 8pt; color: #777; }
tr.pos-row:nth-child(odd) { background: #fafafa; }
table.totals { width: 100%; border-collapse: collapse; margin-top: 0.3cm; }
table.totals td { padding: 3px 6px; }
table.totals .label { color: #555; text-align: right; width: 70%; }
table.totals .amount { text-align: right; font-weight: 500; white-space: nowrap; }
table.totals .grand-total td { font-size: 11pt; font-weight: 700; border-top: 1.5px solid #333; padding-top: 6px; }
.bank-box { margin-top: 0.6cm; font-size: 8pt; color: #555; border-top: 1px solid #ddd; padding-top: 0.3cm; }
.page-footer {
  margin-top: 1.2cm; padding-top: 0.25cm; border-top: 0.5pt solid #ccc;
  font-size: 6.8pt; color: #999; line-height: 1.6;
}
.notes-box { margin-top: 0.5cm; font-size: 8pt; color: #777; font-style: italic; }
.tax-note { margin-top: 0.3cm; font-size: 8pt; color: #777; }
.footer-text { margin-top: 0.4cm; font-size: 8pt; color: #555; }
"""


# ─────────────────────────────────────────────────────────────────────────────
# Vorlage-Builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_html(invoice, positions, settings: dict, inv_settings: dict,
                sender_contact, recipient_contact, template_id: int) -> str:
    """Gibt vollständiges HTML-Dokument zurück."""

    # Custom-CSS aus Einstellungen anhängen
    custom_css = inv_settings.get("custom_template_css", "") or ""
    if isinstance(custom_css, str) and custom_css.startswith('"'):
        custom_css = custom_css.strip('"')

    logo_src   = _logo_b64(settings)
    logo_html  = f'<img class="logo" src="{logo_src}" alt="Logo">' if logo_src else \
                 f'<span style="font-size:14pt;font-weight:bold;">{settings.get("company_name","")}</span>'

    sender     = _addr_lines(sender_contact, settings)
    recipient  = _recipient_lines(recipient_contact)
    doc_label  = DOC_TYPE_LABELS.get(invoice.doc_type, invoice.doc_type.upper())
    watermark  = STATUS_WATERMARKS.get(invoice.status, "")

    tax_mode   = invoice.tax_mode
    breakdown  = _tax_breakdown(positions, tax_mode)
    pos_html   = _positions_html(positions, tax_mode)

    # Fußzeile (alle Vorlagen): Bankverbindung, UID, Firmenbuch, Gericht etc.
    # primär aus dem verknüpften Firmen-Kontakt, Bank-Fallback aus Belegeinstellungen
    bank       = inv_settings.get("bank", {})
    if isinstance(bank, str):
        try: bank = json.loads(bank)
        except Exception: bank = {}
    footer_html = _footer_html(sender_contact, bank)

    # MwSt.-Hinweise
    tax_notes = ""
    if tax_mode == "kleinunternehmer":
        txt = inv_settings.get("kleinunternehmer_text", "Gemäß § 6 Abs. 1 Z 27 UStG wird keine Umsatzsteuer berechnet.")
        if isinstance(txt, str) and txt.startswith('"'): txt = txt.strip('"')
        tax_notes = f'<div class="tax-note">{txt}</div>'
    elif any(b["label"].startswith("Reverse") for b in breakdown):
        txt = inv_settings.get("reverse_charge_text", "Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge)")
        if isinstance(txt, str) and txt.startswith('"'): txt = txt.strip('"')
        tax_notes = f'<div class="tax-note">{txt}</div>'

    # Summen
    totals_html = _totals_html(invoice, breakdown, tax_mode)

    # Intro/Outro
    intro = f'<p style="margin-bottom:0.3cm;">{invoice.intro_text}</p>' if invoice.intro_text else ""
    outro = f'<p class="footer-text">{invoice.outro_text}</p>' if invoice.outro_text else ""

    # Positionen-Header
    tax_th = '<th class="pos-num">MwSt.</th>' if tax_mode != "kleinunternehmer" else ""
    pos_header = f"""
    <table class="positions">
      <thead><tr>
        <th style="text-align:left;">Beschreibung</th>
        <th class="pos-num">Menge</th>
        <th class="pos-num">Einheit</th>
        <th class="pos-num">Preis</th>
        {tax_th}
        <th class="pos-num">Gesamt</th>
      </tr></thead>
      <tbody>{pos_html}</tbody>
    </table>"""

    # Referenz-Zeile
    meta_rows = []
    if invoice.number:     meta_rows.append(("Nummer",        invoice.number))
    if invoice.date:       meta_rows.append(("Datum",         _fmt_date(invoice.date)))
    if invoice.due_date:   meta_rows.append(("Zahlungsziel",  _fmt_date(invoice.due_date)))
    if invoice.delivery_date: meta_rows.append(("Lieferdatum", _fmt_date(invoice.delivery_date)))
    if invoice.reference:  meta_rows.append(("Referenz",      invoice.reference))

    meta_html = "".join(
        f'<tr><td style="color:#777;padding-right:1cm;">{k}</td>'
        f'<td style="font-weight:500;">{v}</td></tr>'
        for k, v in meta_rows
    )

    # Vorlage wählen
    builders = {1: _t1, 2: _t2, 3: _t3, 4: _t4, 5: _t5}
    builder  = builders.get(template_id, _t1)

    return builder(
        logo_html=logo_html,
        doc_label=doc_label,
        sender=sender,
        recipient=recipient,
        meta_html=meta_html,
        intro=intro,
        pos_header=pos_header,
        totals_html=totals_html,
        tax_notes=tax_notes,
        footer_html=footer_html,
        outro=outro,
        watermark=watermark,
        settings=settings,
        custom_css=custom_css,
        # Rohdaten für Vorlagen mit eigenem Layout (z.B. Klassisch)
        invoice=invoice,
        positions=positions,
        breakdown=breakdown,
        tax_mode=tax_mode,
        bank=bank,
        sender_contact=sender_contact,
        recipient_contact=recipient_contact,
    )


def _totals_html(invoice, breakdown, tax_mode: str) -> str:
    rows = ""
    rows += f'<tr><td class="label">Nettobetrag</td><td class="amount">{_fmt_euro(invoice.subtotal)}</td></tr>'
    if tax_mode != "kleinunternehmer":
        for b in breakdown:
            rows += f'<tr><td class="label">{b["label"]}</td><td class="amount">{_fmt_euro(b["tax"])}</td></tr>'
    rows += f'<tr class="grand-total"><td class="label" style="font-weight:700;">Gesamtbetrag</td><td class="amount">{_fmt_euro(invoice.total)}</td></tr>'
    return f'<table class="totals"><tbody>{rows}</tbody></table>'


# ─────────────────────────────────────────────────────────────────────────────
# Vorlage 1 — Klassisch
# ─────────────────────────────────────────────────────────────────────────────
def _t1(**kw) -> str:
    """Klassisch — nachgebaut nach dem WWInterface-Briefpapier:
    oranger Kopfbalken, Logo rechts, Rücksendezeile, Kontaktblock rechts,
    Ort/Datum, Titel, Meta-Block, Tabelle mit EUR-Beträgen, Fußzeile."""
    settings  = kw["settings"]
    invoice   = kw["invoice"]
    positions = kw["positions"]
    breakdown = kw["breakdown"]
    tax_mode  = kw["tax_mode"]
    primary   = settings.get("primary_color") or "#ef7d00"
    currency  = getattr(invoice, "currency", "EUR") or "EUR"

    sd = (kw.get("sender_contact").data or {}) if kw.get("sender_contact") is not None else {}
    rc = kw.get("recipient_contact")

    # Rücksendezeile: Name – Straße – PLZ Ort (aus den Absenderzeilen, ohne HTML)
    plain_sender = [re.sub(r"<[^>]+>", "", l) for l in kw["sender"]]
    ruecksende   = " – ".join([p for p in plain_sender[:3] if p])

    recip_html = "<br>".join(kw["recipient"])
    sender_html = "<br>".join(kw["sender"])

    # Ort, Datum (Langform)
    ort       = sd.get("ort", "")
    datum     = _fmt_date_long(invoice.date)
    ort_datum = f"{ort}, {datum}" if ort else datum

    # Titel: "Rechnung – <Belegtitel>"
    label_cap = kw["doc_label"].capitalize()
    title     = f"{label_cap} – {invoice.title}" if getattr(invoice, "title", None) else label_cap

    # Meta-Block mit fetten Labels
    nr_labels = {"rechnung": "Rechnungs-Nr.:", "angebot": "Angebots-Nr.:",
                 "gutschrift": "Gutschrift-Nr.:", "lieferschein": "Lieferschein-Nr.:",
                 "auftragsbestaetigung": "Auftrags-Nr.:"}
    meta_rows = [(nr_labels.get(invoice.doc_type, "Beleg-Nr.:"), invoice.number or "")]
    if getattr(invoice, "reference", None):
        meta_rows.append(("Referenz:", invoice.reference))
    if rc is not None and (rc.display_name or ""):
        meta_rows.append(("Kunde:", rc.display_name))
        rc_uid = (rc.data or {}).get("uid", "")
        if rc_uid:
            meta_rows.append(("USt.-ID:", rc_uid))
    meta_rows.append(("Leistungsdatum:", _fmt_date_long(getattr(invoice, "delivery_date", None) or invoice.date)))
    if getattr(invoice, "due_date", None):
        meta_rows.append(("Zahlungsziel:", _fmt_date_long(invoice.due_date)))
    meta_html = "".join(
        f'<tr><td class="m-label">{k}</td><td class="m-value">{v}</td></tr>'
        for k, v in meta_rows
    )

    # Positionen: BEZEICHNUNG | ANZAHL | EINZELPREIS | [MWST.] | PREIS
    # MwSt.-Spalte nur wenn gemischte Steuersätze (sonst reicht die Summenzeile)
    item_rates = {p.tax_rate for p in positions if getattr(p, "pos_type", "item") != "text"}
    show_tax   = tax_mode != "kleinunternehmer" and len(item_rates) > 1
    ncols      = 5 if show_tax else 4
    rows = ""
    for p in positions:
        if getattr(p, "pos_type", "item") == "text":
            rows += f'<tr class="grp"><td colspan="{ncols}">{p.description}</td></tr>'
            continue
        qty    = float(p.quantity or 0)
        anzahl = f"{qty:g} {p.unit or ''}".strip()
        disc   = f'<br><small class="disc">- {float(p.discount_pct):.0f}% Rabatt</small>' if p.discount_pct else ""
        tax_td = ""
        if show_tax:
            r = p.tax_rate
            tax_td = f'<td class="num">{"RC" if r is None else f"{int(r) if r == int(r) else r} %"}</td>'
        rows += f"""
        <tr class="item">
          <td>{p.description}{disc}</td>
          <td class="num">{anzahl}</td>
          <td class="num">{_fmt_amount(p.unit_price, currency)}</td>
          {tax_td}
          <td class="num total">{_fmt_amount(p.line_total, currency)}</td>
        </tr>"""
        if getattr(p, "detail", None):
            rows += f'<tr class="detail"><td colspan="{ncols}">{p.detail}</td></tr>'

    tax_th = '<th class="num">MWST.</th>' if show_tax else ""
    positions_html = f"""
    <table class="pos-k">
      <thead><tr>
        <th style="text-align:left;">BEZEICHNUNG</th>
        <th class="num">ANZAHL</th>
        <th class="num">EINZELPREIS</th>
        {tax_th}
        <th class="num">PREIS</th>
      </tr></thead>
      <tbody>
        {rows}
        <tr class="zwischensumme">
          <td colspan="{ncols - 1}" style="font-weight:600;">Zwischensumme</td>
          <td class="num" style="font-weight:600;">{_fmt_amount(invoice.subtotal, currency)}</td>
        </tr>
      </tbody>
    </table>"""

    # Summenblock: Nettosumme / MwSt. je Satz / Gesamtsumme
    sum_rows = f'<tr><td class="s-label">Nettosumme</td><td class="s-val">{_fmt_amount(invoice.subtotal, currency)}</td></tr>'
    if tax_mode != "kleinunternehmer":
        for b in breakdown:
            lbl = b["label"]
            m = re.match(r"MwSt\. (\S+) %", lbl)
            if m:
                lbl = f"{float(m.group(1)):.2f}".replace(".", ",") + " % MwSt."
            sum_rows += f'<tr><td class="s-label">{lbl}</td><td class="s-val">{_fmt_amount(b["tax"], currency)}</td></tr>'
    sum_rows += f'<tr class="grand"><td class="s-label">Gesamtsumme</td><td class="s-val">{_fmt_amount(invoice.total, currency)}</td></tr>'
    totals_html = f'<table class="sum-k"><tbody>{sum_rows}</tbody></table>'

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
{BASE_CSS}
@page {{
  @bottom-center {{ content: none; }}
  @bottom-right {{
    content: "Seite " counter(page) " von " counter(pages);
    font-size: 7.5pt; color: #999;
  }}
}}
.top-band {{ background: {primary}; height: 1.1cm; margin: -1.8cm -1.6cm 0 -1.8cm; }}
.logo-row {{ text-align: right; margin: 0.6cm 0 0.9cm 0; }}
.logo-row .logo {{ max-height: 65px; max-width: 240px; }}
.addr-row {{ display: flex; justify-content: space-between; margin-bottom: 0.2cm; }}
.ruecksende {{ font-size: 6.8pt; color: #777; text-decoration: underline; margin-bottom: 0.35cm; }}
.recipient {{ font-size: 9.5pt; line-height: 1.5; }}
.contact-block {{ font-size: 8pt; color: #666; line-height: 1.55; max-width: 6cm; }}
.contact-block strong {{ color: #333; }}
.ort-datum {{ text-align: right; font-weight: 700; font-size: 9.5pt; margin: 0.5cm 0 0.5cm 0; }}
.doc-title {{ font-size: 14pt; font-weight: 700; margin-bottom: 0.7cm; }}
.meta-k {{ font-size: 9pt; margin-bottom: 0.9cm; border-collapse: collapse; }}
.meta-k .m-label {{ font-weight: 700; padding: 1.5px 1cm 1.5px 0; white-space: nowrap; }}
.meta-k .m-value {{ font-weight: 600; }}
table.pos-k {{ width: 100%; border-collapse: collapse; margin: 0.4cm 0 0.2cm 0; }}
table.pos-k th {{
  font-size: 8pt; font-weight: 700; letter-spacing: 0.04em;
  padding: 6px 6px; border-bottom: 1.5px solid #333;
}}
table.pos-k td {{ padding: 6px 6px; vertical-align: top; }}
table.pos-k .num {{ text-align: right; white-space: nowrap; }}
table.pos-k .total {{ font-weight: 600; }}
table.pos-k tr.grp td {{ font-weight: 700; padding-top: 10px; }}
table.pos-k tr.detail td {{ font-size: 7pt; color: #888; letter-spacing: 0.03em; padding-top: 0; padding-bottom: 8px; }}
table.pos-k .disc {{ color: #888; font-weight: 400; }}
table.pos-k tr.zwischensumme td {{ border-top: 1px solid #333; border-bottom: 1px solid #333; padding: 6px; }}
table.sum-k {{ width: 45%; margin-left: auto; margin-top: 0.9cm; border-collapse: collapse; font-size: 9.5pt; }}
table.sum-k td {{ padding: 3.5px 6px; }}
table.sum-k .s-label {{ text-align: left; }}
table.sum-k .s-val {{ text-align: right; white-space: nowrap; }}
table.sum-k tr.grand td {{ font-weight: 700; border-top: 1.5px solid #333; border-bottom: 3px double #333; }}
.pay-text {{ margin-top: 0.8cm; font-size: 9pt; }}
.pay-text .footer-text {{ font-size: 9pt; color: #222; margin-top: 0.2cm; }}
{kw["custom_css"]}
</style>
</head><body>
{"<div class='watermark'>" + kw['watermark'] + "</div>" if kw['watermark'] else ""}
<div class="top-band"></div>
<div class="logo-row">{kw["logo_html"]}</div>
<div class="addr-row">
  <div>
    <div class="ruecksende">{ruecksende}</div>
    <div class="recipient">{recip_html}</div>
  </div>
  <div class="contact-block">{sender_html}</div>
</div>
<div class="ort-datum">{ort_datum}</div>
<h1 class="doc-title">{title}</h1>
<table class="meta-k"><tbody>{meta_html}</tbody></table>
{kw["intro"]}
{positions_html}
{totals_html}
{kw["tax_notes"]}
<div class="pay-text">{kw["outro"]}</div>
{kw["footer_html"]}
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Vorlage 2 — Modern
# ─────────────────────────────────────────────────────────────────────────────
def _t2(**kw) -> str:
    sender_html = "&nbsp;&nbsp;|&nbsp;&nbsp;".join(kw["sender"])
    recip_html  = "<br>".join(kw["recipient"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
{BASE_CSS}
{kw["custom_css"]}
.top-bar {{
  background: #1a1a2e; color: #fff; padding: 0.5cm 0.6cm;
  display: flex; justify-content: space-between; align-items: center;
  margin: -1.8cm -1.6cm 0.7cm -1.8cm;
}}
.top-bar .logo img, .top-bar .logo span {{ filter: brightness(0) invert(1); }}
.top-bar .sender-mini {{ font-size: 7.5pt; color: #ccc; text-align: right; }}
.doc-label {{ font-size: 22pt; font-weight: 900; color: #1a1a2e; letter-spacing: -0.02em; margin-bottom: 0.3cm; }}
.cols {{ display: flex; justify-content: space-between; margin-bottom: 0.5cm; }}
.meta-table {{ font-size: 8.5pt; }}
</style>
</head><body>
{"<div class='watermark'>" + kw['watermark'] + "</div>" if kw['watermark'] else ""}
<div class="top-bar">
  <div class="logo">{kw["logo_html"]}</div>
  <div class="sender-mini">{sender_html}</div>
</div>
<div class="doc-label">{kw["doc_label"]}</div>
<div class="cols">
  <div style="font-size:9pt;">{recip_html}</div>
  <table class="meta-table"><tbody>{kw["meta_html"]}</tbody></table>
</div>
{kw["intro"]}
{kw["pos_header"]}
{kw["totals_html"]}
{kw["tax_notes"]}
{kw["outro"]}
{kw["footer_html"]}
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Vorlage 3 — Kompakt
# ─────────────────────────────────────────────────────────────────────────────
def _t3(**kw) -> str:
    sender_html = "<br>".join(kw["sender"])
    recip_html  = "<br>".join(kw["recipient"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
{BASE_CSS}
{kw["custom_css"]}
body {{ font-size: 8.5pt; }}
.top {{ display: flex; justify-content: space-between; border-bottom: 2px solid #000; padding-bottom: 0.3cm; margin-bottom: 0.4cm; }}
.doc-label {{ font-size: 15pt; font-weight: 900; }}
.two-col {{ display: flex; gap: 1cm; margin-bottom: 0.4cm; font-size: 8pt; }}
.meta-table td {{ padding: 2px 4px; }}
</style>
</head><body>
{"<div class='watermark'>" + kw['watermark'] + "</div>" if kw['watermark'] else ""}
<div class="top">
  <div>{kw["logo_html"]}<br><div class="doc-label">{kw["doc_label"]}</div></div>
  <div style="font-size:7.5pt;text-align:right;">{sender_html}</div>
</div>
<div class="two-col">
  <div style="flex:1;">{recip_html}</div>
  <div><table class="meta-table"><tbody>{kw["meta_html"]}</tbody></table></div>
</div>
{kw["intro"]}
{kw["pos_header"]}
{kw["totals_html"]}
{kw["tax_notes"]}
{kw["outro"]}
{kw["footer_html"]}
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Vorlage 4 — Elegant
# ─────────────────────────────────────────────────────────────────────────────
def _t4(**kw) -> str:
    sender_html = "<br>".join(kw["sender"])
    recip_html  = "<br>".join(kw["recipient"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
{BASE_CSS}
{kw["custom_css"]}
body {{ font-family: Georgia, 'Times New Roman', serif; font-size: 9.5pt; }}
table.positions th, table.positions td {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 8.5pt; }}
.header {{ border-bottom: 3px solid #c8a96e; padding-bottom: 0.4cm; margin-bottom: 0.6cm; display:flex; justify-content:space-between; align-items:flex-end; }}
.doc-title {{ font-size: 20pt; font-weight: 400; letter-spacing: 0.15em; text-transform: uppercase; color: #333; margin-bottom: 0.5cm; }}
.address-cols {{ display: flex; justify-content: space-between; margin-bottom: 0.6cm; }}
.meta-table td {{ padding: 2px 6px; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; font-size: 8pt; }}
.label {{ color: #888; }}
</style>
</head><body>
{"<div class='watermark'>" + kw['watermark'] + "</div>" if kw['watermark'] else ""}
<div class="header">
  <div>{kw["logo_html"]}</div>
  <div style="font-size:8pt;text-align:right;">{sender_html}</div>
</div>
<div class="doc-title">{kw["doc_label"]}</div>
<div class="address-cols">
  <div style="font-size:9pt;">{recip_html}</div>
  <table class="meta-table"><tbody>{kw["meta_html"]}</tbody></table>
</div>
{kw["intro"]}
{kw["pos_header"]}
{kw["totals_html"]}
{kw["tax_notes"]}
{kw["outro"]}
{kw["footer_html"]}
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Vorlage 5 — Farbenfroh
# ─────────────────────────────────────────────────────────────────────────────
def _t5(**kw) -> str:
    sender_html  = "<br>".join(kw["sender"])
    recip_html   = "<br>".join(kw["recipient"])
    primary      = kw["settings"].get("primary_color", "#2563eb") or "#2563eb"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
{BASE_CSS}
{kw["custom_css"]}
:root {{ --primary: {primary}; }}
.header-band {{
  background: var(--primary); color: #fff;
  padding: 0.5cm 0.6cm; display: flex; justify-content: space-between; align-items: center;
  margin: -1.8cm -1.6cm 0cm -1.8cm;
}}
.header-band img {{ filter: brightness(0) invert(1); max-height: 45px; }}
.header-band .name {{ font-size: 10pt; font-weight: 700; }}
.sub-band {{
  background: color-mix(in srgb, var(--primary) 15%, white);
  padding: 0.25cm 0.6cm; display: flex; justify-content: flex-end; gap: 1cm;
  margin: 0 -1.6cm 0.5cm -1.8cm; font-size: 7.5pt; color: #444;
}}
.doc-label {{ font-size: 18pt; font-weight: 900; color: var(--primary); margin-bottom: 0.4cm; }}
.two-col {{ display: flex; justify-content: space-between; margin-bottom: 0.5cm; }}
table.positions th {{ background: var(--primary); color: #fff; border-bottom: none; }}
tr.pos-row:nth-child(odd) {{ background: color-mix(in srgb, var(--primary) 5%, white); }}
table.totals .grand-total td {{ color: var(--primary); }}
.meta-table td {{ padding: 2px 5px; font-size: 8pt; }}
</style>
</head><body>
{"<div class='watermark'>" + kw['watermark'] + "</div>" if kw['watermark'] else ""}
<div class="header-band">
  <div>{kw["logo_html"]}</div>
  <div style="text-align:right;font-size:8pt;">{sender_html}</div>
</div>
<div style="margin-top:0.5cm;"></div>
<div class="doc-label">{kw["doc_label"]}</div>
<div class="two-col">
  <div style="font-size:9pt;">{recip_html}</div>
  <table class="meta-table"><tbody>{kw["meta_html"]}</tbody></table>
</div>
{kw["intro"]}
{kw["pos_header"]}
{kw["totals_html"]}
{kw["tax_notes"]}
{kw["outro"]}
{kw["footer_html"]}
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Öffentliche API
# ─────────────────────────────────────────────────────────────────────────────

def generate_pdf(invoice, positions, settings: dict, inv_settings: dict,
                 sender_contact=None, recipient_contact=None) -> bytes:
    """Gibt PDF-Bytes zurück."""
    # Vorlage: zuerst aus inv_settings (globale Einstellung), dann aus Rechnung, Fallback 1
    default_tpl = inv_settings.get("default_template", 1)
    try: default_tpl = int(default_tpl)
    except Exception: default_tpl = 1
    template_id = default_tpl or getattr(invoice, "template_id", 1) or 1
    html = _build_html(
        invoice=invoice,
        positions=positions,
        settings=settings,
        inv_settings=inv_settings,
        sender_contact=sender_contact,
        recipient_contact=recipient_contact,
        template_id=template_id,
    )
    buf = io.BytesIO()
    WeasyprintHTML(string=html, base_url="/").write_pdf(buf)
    return buf.getvalue()


def generate_html_preview(invoice, positions, settings: dict, inv_settings: dict,
                           sender_contact=None, recipient_contact=None,
                           template_id: Optional[int] = None) -> str:
    """Gibt HTML-String zurück (für Vorschau im Browser).
    template_id: optionaler Override — sonst globale Einstellung / Rechnung / Fallback 1."""
    if template_id is None:
        default_tpl = inv_settings.get("default_template", 1)
        try: default_tpl = int(default_tpl)
        except Exception: default_tpl = 1
        template_id = default_tpl or getattr(invoice, "template_id", 1) or 1
    html = _build_html(
        invoice=invoice,
        positions=positions,
        settings=settings,
        inv_settings=inv_settings,
        sender_contact=sender_contact,
        recipient_contact=recipient_contact,
        template_id=template_id,
    )
    # Browser-Vorschau: Die @page-Ränder gelten nur beim PDF-Druck (WeasyPrint).
    # Für die Anzeige im Browser wird ein A4-Blatt mit denselben Rändern simuliert.
    preview_css = """
<style>
  html { background: #ebebeb; }
  body {
    width: 21cm; min-height: 29.7cm;
    margin: 0.8cm auto;
    padding: 1.8cm 1.6cm 2cm 1.8cm;
    background: #fff;
    box-shadow: 0 2px 14px rgba(0,0,0,0.18);
  }
</style>
"""
    return html.replace("</head>", preview_css + "</head>", 1)
