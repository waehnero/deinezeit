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

    # Bankdaten
    bank       = inv_settings.get("bank", {})
    if isinstance(bank, str):
        try: bank = json.loads(bank)
        except Exception: bank = {}
    bank_html  = ""
    if bank.get("iban"):
        bank_html = f"""
        <div class="bank-box">
          <strong>Bankverbindung:</strong> &nbsp;
          {bank.get('bank','')} &nbsp;|&nbsp;
          IBAN: {bank['iban']} &nbsp;|&nbsp;
          BIC: {bank.get('bic','')}
        </div>"""

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
        bank_html=bank_html,
        outro=outro,
        watermark=watermark,
        settings=settings,
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
    sender_html = "<br>".join(kw["sender"])
    recip_html  = "<br>".join(kw["recipient"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
{BASE_CSS}
.header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.8cm; }}
.sender-block {{ font-size: 8pt; color: #555; text-align: right; }}
.doc-title {{ margin: 0.5cm 0 0.3cm 0; }}
.address-block {{ display: flex; justify-content: space-between; margin-bottom: 0.6cm; }}
.recipient-box {{ font-size: 9pt; }}
.meta-table {{ font-size: 8.5pt; }}
</style>
</head><body>
{"<div class='watermark'>" + kw['watermark'] + "</div>" if kw['watermark'] else ""}
<div class="header">
  <div>{kw["logo_html"]}</div>
  <div class="sender-block">{sender_html}</div>
</div>
<h1 class="doc-title">{kw["doc_label"]}</h1>
<div class="address-block">
  <div class="recipient-box">{recip_html}</div>
  <table class="meta-table"><tbody>{kw["meta_html"]}</tbody></table>
</div>
{kw["intro"]}
{kw["pos_header"]}
{kw["totals_html"]}
{kw["tax_notes"]}
{kw["bank_html"]}
{kw["outro"]}
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
{kw["bank_html"]}
{kw["outro"]}
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
{kw["bank_html"]}
{kw["outro"]}
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
{kw["bank_html"]}
{kw["outro"]}
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
{kw["bank_html"]}
{kw["outro"]}
</body></html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Öffentliche API
# ─────────────────────────────────────────────────────────────────────────────

def generate_pdf(invoice, positions, settings: dict, inv_settings: dict,
                 sender_contact=None, recipient_contact=None) -> bytes:
    """Gibt PDF-Bytes zurück."""
    template_id = getattr(invoice, "template_id", 1) or 1
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
                           sender_contact=None, recipient_contact=None) -> str:
    """Gibt HTML-String zurück (für Vorschau im Browser)."""
    template_id = getattr(invoice, "template_id", 1) or 1
    return _build_html(
        invoice=invoice,
        positions=positions,
        settings=settings,
        inv_settings=inv_settings,
        sender_contact=sender_contact,
        recipient_contact=recipient_contact,
        template_id=template_id,
    )
