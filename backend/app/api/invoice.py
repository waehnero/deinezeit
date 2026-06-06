from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, extract
from typing import List, Optional
from uuid import UUID
from datetime import date, datetime, timezone
import io
import json

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.invoice import (Invoice, InvoicePosition, InvoiceAttachment,
                                 InvoiceNumberSequence, InvoiceSettings)
from app.models.settings import Setting
from app.models.masterdata import EntityRecord
from app.services.invoice_pdf import generate_pdf, generate_html_preview
from app.schemas.invoice import (
    InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceListItem,
    InvoiceCancelRequest, InvoiceMarkPaidRequest,
    InvoiceBookFilter, InvoiceSettingsUpdate, NextNumberResponse,
    InvoicePositionResponse, InvoiceAttachmentResponse,
)

router = APIRouter(prefix="/invoices", tags=["Rechnungen"])


# ─────────────────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────────────────────

TYPE_PREFIX = {
    "rechnung":             "RE",
    "angebot":              "AN",
    "auftragsbestaetigung": "AB",
    "gutschrift":           "GS",
    "lieferschein":         "LS",
}

def _next_number(db: Session, doc_type: str, year: int) -> tuple[int, str]:
    """Atomarer Zähler — gibt (sequence, formatted_number) zurück."""
    seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=year).first()
    if not seq:
        seq = InvoiceNumberSequence(doc_type=doc_type, year=year, last_sequence=0)
        db.add(seq)
        db.flush()
    seq.last_sequence += 1
    db.flush()

    # Format aus Einstellungen lesen (Fallback)
    fmt_key = f"number_format_{doc_type}"
    setting = db.query(InvoiceSettings).filter_by(key=fmt_key).first()
    if setting and setting.value:
        fmt = setting.value.strip('"') if isinstance(setting.value, str) else str(setting.value)
    else:
        prefix = TYPE_PREFIX.get(doc_type, "DO")
        fmt = f"{prefix}-{{year}}-{{seq:03d}}"

    number = fmt.format(year=year, seq=seq.last_sequence)
    return seq.last_sequence, number


def _calc_totals(invoice: Invoice) -> None:
    """Positionen neu berechnen und Summen auf Invoice schreiben."""
    from decimal import Decimal
    subtotal = Decimal("0")
    tax_total = Decimal("0")

    for pos in invoice.positions:
        qty = pos.quantity or Decimal("0")
        price = pos.unit_price or Decimal("0")
        base = qty * price
        if pos.discount_pct:
            base = base * (1 - pos.discount_pct / 100)
        base = base.quantize(Decimal("0.01"))
        pos.line_total = base
        subtotal += base
        if invoice.tax_mode != "kleinunternehmer" and pos.tax_rate is not None:
            tax_total += (base * pos.tax_rate / 100).quantize(Decimal("0.01"))

    invoice.subtotal = subtotal
    invoice.tax_total = tax_total
    invoice.total = subtotal + tax_total


# ─────────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[InvoiceListItem])
async def list_invoices(
    doc_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Invoice).filter(Invoice.is_recurring_template == False)
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    if status:
        q = q.filter(Invoice.status == status)
    if contact_id:
        q = q.filter(Invoice.contact_id == contact_id)
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            Invoice.number.ilike(like),
            Invoice.title.ilike(like),
            Invoice.reference.ilike(like),
        ))
    return q.order_by(Invoice.date.desc(), Invoice.number.desc()).offset(skip).limit(limit).all()


@router.post("", response_model=InvoiceResponse)
async def create_invoice(
    body: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.doc_type not in TYPE_PREFIX:
        raise HTTPException(400, f"Ungültiger doc_type: {body.doc_type}")

    year = body.date.year
    sequence, number = _next_number(db, body.doc_type, year)

    data = body.model_dump(exclude={"positions"})
    data["year"] = year
    data["sequence"] = sequence
    data["number"] = number
    data["created_by"] = current_user.email
    data["updated_by"] = current_user.email

    invoice = Invoice(**data)
    db.add(invoice)
    db.flush()

    for i, pos_data in enumerate(body.positions):
        pos = InvoicePosition(invoice_id=invoice.id, **pos_data.model_dump())
        pos.sort_order = i
        db.add(pos)

    db.flush()
    db.refresh(invoice)
    _calc_totals(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/templates", response_model=List[InvoiceListItem])
async def list_recurring_templates(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Invoice).filter(Invoice.is_recurring_template == True)\
             .order_by(Invoice.created_at.desc()).all()


@router.get("/next-number", response_model=NextNumberResponse)
async def get_next_number(
    doc_type: str = Query("rechnung"),
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    y = year or datetime.now().year
    seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
    next_seq = (seq.last_sequence + 1) if seq else 1
    fmt_key = f"number_format_{doc_type}"
    setting = db.query(InvoiceSettings).filter_by(key=fmt_key).first()
    if setting and setting.value:
        fmt = setting.value.strip('"') if isinstance(setting.value, str) else str(setting.value)
    else:
        prefix = TYPE_PREFIX.get(doc_type, "DO")
        fmt = f"{prefix}-{{year}}-{{seq:03d}}"
    preview = fmt.format(year=y, seq=next_seq)
    return {"doc_type": doc_type, "year": y, "next_sequence": next_seq, "preview": preview}

DOC_TYPES_LIST = ["rechnung", "angebot", "auftragsbestaetigung", "gutschrift", "lieferschein"]
DOC_TYPE_DEFAULTS = {
    "rechnung":             "RE-{year}-{seq:03d}",
    "angebot":              "AN-{year}-{seq:03d}",
    "auftragsbestaetigung": "AB-{year}-{seq:03d}",
    "gutschrift":           "GS-{year}-{seq:03d}",
    "lieferschein":         "LS-{year}-{seq:03d}",
}


@router.get("/number-sequences")
async def get_number_sequences(
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Gibt Nummernkreise (Format + aktueller Zähler) für alle Dokumenttypen zurück."""
    y = year or datetime.now().year
    result = []
    for doc_type in DOC_TYPES_LIST:
        seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
        fmt_setting = db.query(InvoiceSettings).filter_by(key=f"number_format_{doc_type}").first()
        fmt = (fmt_setting.value.strip('"') if fmt_setting and fmt_setting.value else None) \
              or DOC_TYPE_DEFAULTS[doc_type]
        last = seq.last_sequence if seq else 0
        # Vorschau nächste Nummer
        preview = fmt.format(year=y, seq=last + 1)
        result.append({
            "doc_type": doc_type,
            "year": y,
            "format": fmt,
            "last_sequence": last,
            "next_sequence": last + 1,
            "next_preview": preview,
        })
    return result


@router.put("/number-sequences/{doc_type}")
async def update_number_sequence(
    doc_type: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Aktualisiert Format und/oder Zählerstand für einen Dokumenttyp.
    Body: { year, format, last_sequence }
    """
    if doc_type not in DOC_TYPES_LIST:
        raise HTTPException(400, f"Ungültiger Dokumenttyp: {doc_type}")

    y = body.get("year", datetime.now().year)

    # Format speichern
    if "format" in body:
        fmt_key = f"number_format_{doc_type}"
        setting = db.query(InvoiceSettings).filter_by(key=fmt_key).first()
        if setting:
            setting.value = body["format"]
        else:
            setting = InvoiceSettings(key=fmt_key, value=body["format"])
            db.add(setting)

    # Zählerstand setzen
    if "last_sequence" in body:
        new_seq = int(body["last_sequence"])
        if new_seq < 0:
            raise HTTPException(400, "Zählerstand darf nicht negativ sein")
        seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
        if seq:
            seq.last_sequence = new_seq
        else:
            seq = InvoiceNumberSequence(doc_type=doc_type, year=y, last_sequence=new_seq)
            db.add(seq)

    db.commit()

    # Aktuellen Stand zurückgeben
    seq = db.query(InvoiceNumberSequence).filter_by(doc_type=doc_type, year=y).first()
    fmt_setting = db.query(InvoiceSettings).filter_by(key=f"number_format_{doc_type}").first()
    fmt = (fmt_setting.value.strip('"') if fmt_setting and fmt_setting.value else None) \
          or DOC_TYPE_DEFAULTS[doc_type]
    last = seq.last_sequence if seq else 0
    return {
        "doc_type": doc_type,
        "year": y,
        "format": fmt,
        "last_sequence": last,
        "next_sequence": last + 1,
        "next_preview": fmt.format(year=y, seq=last + 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Belegbuch
# ─────────────────────────────────────────────────────────────────────────────

def _book_query(db: Session, date_from: Optional[date], date_to: Optional[date],
                doc_type: Optional[str]):
    """Gemeinsame Abfragelogik für Belegbuch-Endpoints."""
    q = db.query(Invoice).filter(Invoice.status != "entwurf")
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    return q.order_by(Invoice.date, Invoice.number)


@router.get("/book/list")
async def get_book_list(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch-Liste mit Summen."""
    from decimal import Decimal
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    total_net = sum(Decimal(str(i.subtotal or 0)) for i in invoices)
    total_tax = sum(Decimal(str(i.tax_total or 0)) for i in invoices)
    total_gross = sum(Decimal(str(i.total or 0)) for i in invoices)

    rows = []
    for inv in invoices:
        contact_name = None
        if inv.contact_id:
            rec = db.query(EntityRecord).filter(EntityRecord.id == inv.contact_id).first()
            if rec:
                d = rec.data or {}
                contact_name = d.get("name") or d.get("firma") or d.get("vorname", "")
        rows.append({
            "id": str(inv.id),
            "number": inv.number,
            "doc_type": inv.doc_type,
            "date": inv.date.isoformat() if inv.date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "title": inv.title,
            "contact_name": contact_name,
            "subtotal": float(inv.subtotal or 0),
            "tax_total": float(inv.tax_total or 0),
            "total": float(inv.total or 0),
            "status": inv.status,
            "currency": inv.currency,
        })

    return {
        "invoices": rows,
        "summary": {
            "count": len(rows),
            "total_net": float(total_net),
            "total_tax": float(total_tax),
            "total_gross": float(total_gross),
        },
    }


@router.get("/book/csv")
async def get_book_csv(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch als CSV-Download."""
    import csv as csv_mod
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    output = io.StringIO()
    writer = csv_mod.writer(output, delimiter=";")
    writer.writerow(["Nummer", "Typ", "Datum", "Fällig", "Titel", "Netto", "MwSt.", "Brutto", "Status"])

    for inv in invoices:
        writer.writerow([
            inv.number,
            inv.doc_type,
            inv.date.strftime("%d.%m.%Y") if inv.date else "",
            inv.due_date.strftime("%d.%m.%Y") if inv.due_date else "",
            inv.title or "",
            str(inv.subtotal or 0).replace(".", ","),
            str(inv.tax_total or 0).replace(".", ","),
            str(inv.total or 0).replace(".", ","),
            inv.status,
        ])

    content = output.getvalue().encode("utf-8-sig")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=belegbuch.csv"},
    )


@router.get("/book/pdf")
async def get_book_pdf(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Belegbuch als PDF-Download."""
    from decimal import Decimal
    invoices = _book_query(db, date_from, date_to, doc_type).all()

    total_net = sum(Decimal(str(i.subtotal or 0)) for i in invoices)
    total_tax = sum(Decimal(str(i.tax_total or 0)) for i in invoices)
    total_gross = sum(Decimal(str(i.total or 0)) for i in invoices)

    def fmt_date(d):
        return d.strftime("%d.%m.%Y") if d else "—"

    def fmt_eur(n):
        return f"{float(n):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")

    period_label = ""
    if date_from and date_to:
        period_label = f"{fmt_date(date_from)} – {fmt_date(date_to)}"
    elif date_from:
        period_label = f"ab {fmt_date(date_from)}"
    elif date_to:
        period_label = f"bis {fmt_date(date_to)}"
    else:
        period_label = "Alle Zeiträume"

    rows_html = ""
    for inv in invoices:
        status_map = {
            "offen": "Offen", "bezahlt": "Bezahlt", "ueberfaellig": "Überfällig",
            "storniert": "Storniert", "gesendet": "Gesendet",
            "angenommen": "Angenommen", "abgelehnt": "Abgelehnt",
        }
        rows_html += f"""
        <tr>
          <td>{inv.number}</td>
          <td>{fmt_date(inv.date)}</td>
          <td>{fmt_date(inv.due_date)}</td>
          <td>{inv.title or '—'}</td>
          <td class="r">{fmt_eur(inv.subtotal or 0)}</td>
          <td class="r">{fmt_eur(inv.tax_total or 0)}</td>
          <td class="r"><b>{fmt_eur(inv.total or 0)}</b></td>
          <td>{status_map.get(inv.status, inv.status)}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11px; margin: 20px; }}
  h1 {{ font-size: 16px; margin-bottom: 4px; }}
  p.sub {{ color: #666; font-size: 10px; margin-bottom: 16px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ background: #f3f4f6; text-align: left; padding: 6px 8px; border-bottom: 2px solid #d1d5db; font-size: 10px; }}
  td {{ padding: 5px 8px; border-bottom: 1px solid #e5e7eb; }}
  .r {{ text-align: right; }}
  tfoot td {{ font-weight: bold; background: #f9fafb; border-top: 2px solid #d1d5db; }}
</style>
</head><body>
<h1>Belegbuch</h1>
<p class="sub">Zeitraum: {period_label} &nbsp;|&nbsp; {len(invoices)} Dokumente</p>
<table>
  <thead><tr>
    <th>Nummer</th><th>Datum</th><th>Fällig</th><th>Titel</th>
    <th class="r">Netto</th><th class="r">MwSt.</th><th class="r">Brutto</th><th>Status</th>
  </tr></thead>
  <tbody>{rows_html}</tbody>
  <tfoot><tr>
    <td colspan="4">Gesamt ({len(invoices)})</td>
    <td class="r">{fmt_eur(total_net)}</td>
    <td class="r">{fmt_eur(total_tax)}</td>
    <td class="r">{fmt_eur(total_gross)}</td>
    <td></td>
  </tr></tfoot>
</table>
</body></html>"""

    try:
        import weasyprint
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
    except Exception:
        # Fallback: HTML als Datei zurückgeben wenn WeasyPrint nicht verfügbar
        return Response(
            content=html.encode("utf-8"),
            media_type="text/html",
            headers={"Content-Disposition": "inline; filename=belegbuch.html"},
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=belegbuch.pdf"},
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")
    return inv


@router.put("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: UUID,
    body: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Rechnungen können nicht bearbeitet werden")

    update_data = body.model_dump(exclude={"positions"})
    for k, v in update_data.items():
        setattr(inv, k, v)
    inv.updated_by = current_user.email

    # Positionen ersetzen
    db.query(InvoicePosition).filter(InvoicePosition.invoice_id == invoice_id).delete()
    for i, pos_data in enumerate(body.positions):
        pos = InvoicePosition(invoice_id=inv.id, **pos_data.model_dump())
        pos.sort_order = i
        db.add(pos)

    db.flush()
    db.refresh(inv)
    _calc_totals(inv)
    db.commit()
    db.refresh(inv)
    return inv


@router.delete("/{invoice_id}", status_code=204)
async def delete_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if inv.status not in ("entwurf", "storniert"):
        raise HTTPException(400, "Nur Entwürfe oder stornierte Dokumente können gelöscht werden")
    db.delete(inv)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Aktionen
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{invoice_id}/cancel", response_model=InvoiceResponse)
async def cancel_invoice(
    invoice_id: UUID,
    body: InvoiceCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Bereits storniert")
    if inv.doc_type != "rechnung":
        raise HTTPException(400, "Nur Rechnungen können storniert werden")

    inv.status = "storniert"
    inv.cancel_mode = body.cancel_mode
    inv.updated_by = current_user.email

    credit_note = None
    if body.cancel_mode == "with_credit":
        year = datetime.now().year
        sequence, number = _next_number(db, "gutschrift", year)
        credit_note = Invoice(
            doc_type="gutschrift",
            number=number,
            year=year,
            sequence=sequence,
            contact_id=inv.contact_id,
            project_id=inv.project_id,
            related_invoice_id=inv.id,
            title=f"Gutschrift zu {inv.number}",
            date=datetime.now().date(),
            tax_mode=inv.tax_mode,
            currency=inv.currency,
            template_id=inv.template_id,
            status="offen",
            created_by=current_user.email,
            updated_by=current_user.email,
        )
        db.add(credit_note)
        db.flush()

        for orig_pos in inv.positions:
            pos = InvoicePosition(
                invoice_id=credit_note.id,
                sort_order=orig_pos.sort_order,
                pos_type=orig_pos.pos_type,
                description=orig_pos.description,
                detail=orig_pos.detail,
                quantity=-orig_pos.quantity,   # negativer Betrag
                unit=orig_pos.unit,
                unit_price=orig_pos.unit_price,
                discount_pct=orig_pos.discount_pct,
                tax_rate=orig_pos.tax_rate,
            )
            db.add(pos)

        db.flush()
        db.refresh(credit_note)
        _calc_totals(credit_note)

    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{invoice_id}/mark-paid", response_model=InvoiceResponse)
async def mark_paid(
    invoice_id: UUID,
    body: InvoiceMarkPaidRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")
    inv.status = "bezahlt"
    inv.paid_at = body.paid_at
    inv.paid_amount = body.paid_amount or inv.total
    inv.updated_by = current_user.email
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{invoice_id}/set-status", response_model=InvoiceResponse)
async def set_status(
    invoice_id: UUID,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Setzt den Status eines Dokuments.
    Erlaubte Übergänge:
      entwurf   → offen | gesendet
      offen     → gesendet | bezahlt
      gesendet  → offen | bezahlt | angenommen | abgelehnt
      angenommen→ (nur via convert-to-invoice weiter)
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Dokument nicht gefunden")
    if inv.status == "storniert":
        raise HTTPException(400, "Stornierte Dokumente können nicht geändert werden")

    new_status = body.get("status")
    allowed = {
        "entwurf":      ["offen", "gesendet"],
        "offen":        ["gesendet", "bezahlt"],
        "gesendet":     ["offen", "bezahlt", "angenommen", "abgelehnt"],
        "angenommen":   ["bezahlt"],
        "abgelehnt":    [],
        "bezahlt":      [],
        "ueberfaellig": ["bezahlt", "gesendet"],
    }
    if new_status not in allowed.get(inv.status, []):
        raise HTTPException(400, f"Statuswechsel von '{inv.status}' nach '{new_status}' nicht erlaubt")

    inv.status = new_status
    inv.updated_by = current_user.email
    db.commit()
    db.refresh(inv)
    return inv


@router.post("/{invoice_id}/convert-to-ab", response_model=InvoiceResponse)
async def convert_to_ab(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Angebot in Auftragsbestätigung umwandeln."""
    offer = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not offer:
        raise HTTPException(404, "Angebot nicht gefunden")
    if offer.doc_type != "angebot":
        raise HTTPException(400, "Nur Angebote können in eine AB umgewandelt werden")

    year = datetime.now().date().year
    sequence, number = _next_number(db, "auftragsbestaetigung", year)

    # Standard-Texte für AB laden
    intro_setting = db.query(InvoiceSettings).filter_by(key="default_intro_auftragsbestaetigung").first()
    outro_setting = db.query(InvoiceSettings).filter_by(key="default_outro_auftragsbestaetigung").first()
    intro = (intro_setting.value.strip('"') if intro_setting and isinstance(intro_setting.value, str) else "") or offer.intro_text or ""
    outro = (outro_setting.value.strip('"') if outro_setting and isinstance(outro_setting.value, str) else "") or offer.outro_text or ""

    ab = Invoice(
        doc_type="auftragsbestaetigung",
        number=number, year=year, sequence=sequence,
        contact_id=offer.contact_id, project_id=offer.project_id,
        related_invoice_id=offer.id,
        title=offer.title, date=datetime.now().date(),
        tax_mode=offer.tax_mode, currency=offer.currency,
        template_id=offer.template_id,
        intro_text=intro, outro_text=outro,
        status="entwurf",
        created_by=current_user.email, updated_by=current_user.email,
    )
    db.add(ab)
    db.flush()
    for orig_pos in offer.positions:
        db.add(InvoicePosition(
            invoice_id=ab.id, sort_order=orig_pos.sort_order,
            pos_type=orig_pos.pos_type, description=orig_pos.description,
            detail=orig_pos.detail, quantity=orig_pos.quantity, unit=orig_pos.unit,
            unit_price=orig_pos.unit_price, discount_pct=orig_pos.discount_pct,
            tax_rate=orig_pos.tax_rate,
        ))
    offer.status = "angenommen"
    db.flush()
    db.refresh(ab)
    _calc_totals(ab)
    db.commit()
    db.refresh(ab)
    return ab


@router.post("/{invoice_id}/convert-to-invoice", response_model=InvoiceResponse)
async def convert_to_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Angebot oder Auftragsbestätigung in Rechnung umwandeln."""
    offer = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not offer:
        raise HTTPException(404, "Dokument nicht gefunden")
    if offer.doc_type not in ("angebot", "auftragsbestaetigung"):
        raise HTTPException(400, "Nur Angebote oder Auftragsbestätigungen können umgewandelt werden")

    year = datetime.now().date().year
    sequence, number = _next_number(db, "rechnung", year)

    invoice = Invoice(
        doc_type="rechnung",
        number=number,
        year=year,
        sequence=sequence,
        contact_id=offer.contact_id,
        project_id=offer.project_id,
        related_invoice_id=offer.id,
        title=offer.title,
        date=datetime.now().date(),
        tax_mode=offer.tax_mode,
        currency=offer.currency,
        template_id=offer.template_id,
        intro_text=offer.intro_text,
        outro_text=offer.outro_text,
        status="entwurf",
        created_by=current_user.email,
        updated_by=current_user.email,
    )
    db.add(invoice)
    db.flush()

    for orig_pos in offer.positions:
        pos = InvoicePosition(
            invoice_id=invoice.id,
            sort_order=orig_pos.sort_order,
            pos_type=orig_pos.pos_type,
            description=orig_pos.description,
            detail=orig_pos.detail,
            quantity=orig_pos.quantity,
            unit=orig_pos.unit,
            unit_price=orig_pos.unit_price,
            discount_pct=orig_pos.discount_pct,
            tax_rate=orig_pos.tax_rate,
        )
        db.add(pos)

    offer.status = "angenommen"
    db.flush()
    db.refresh(invoice)
    _calc_totals(invoice)
    db.commit()
    db.refresh(invoice)
    return invoice


# ─────────────────────────────────────────────────────────────────────────────
# E-Mail-Versand
# ─────────────────────────────────────────────────────────────────────────────

DOC_TYPE_LABELS_DE = {
    "rechnung":             "Rechnung",
    "angebot":              "Angebot",
    "auftragsbestaetigung": "Auftragsbestätigung",
    "gutschrift":           "Gutschrift",
    "lieferschein":         "Lieferschein",
}



def _load_pdf_context(db: Session, invoice: Invoice):
    """Lädt Settings, InvoiceSettings, Sender- und Empfängerkontakt."""
    settings = {r.key: r.value for r in db.query(Setting).all()}
    inv_settings = {r.key: r.value for r in db.query(InvoiceSettings).all()}

    sender_contact = None
    cid = settings.get("company_contact_id")
    if cid:
        try:
            from uuid import UUID as _UUID
            sender_contact = db.query(EntityRecord).filter(EntityRecord.id == _UUID(cid)).first()
        except Exception:
            pass

    recipient_contact = None
    if invoice.contact_id:
        recipient_contact = db.query(EntityRecord).filter(EntityRecord.id == invoice.contact_id).first()

    return settings, inv_settings, sender_contact, recipient_contact


def _send_invoice_email(inv: Invoice, db, settings_d: dict, inv_settings_d: dict,
                         sender_contact, recipient_contact, to_email: str, current_user_email: str,
                         extra_attachments: list = None):
    """Generiert PDF und versendet per E-Mail.
    extra_attachments: Liste von Dicts mit:
      - type='datacenter': {type, id}  → wird aus Storage geladen
      - type='local':      {type, filename, mime_type, data_b64}  → base64-kodiert
    """
    import base64
    from app.services.invoice_pdf import generate_pdf
    from app.services.email_service import send_email
    from app.models.attachment import Attachment
    from app.services import storage_service

    doc_label = DOC_TYPE_LABELS_DE.get(inv.doc_type, inv.doc_type)
    company_name = settings_d.get("company_name", "DeineZeit")

    pdf_bytes = generate_pdf(inv, inv.positions, settings_d, inv_settings_d,
                              sender_contact, recipient_contact)

    filename = f"{inv.number.replace('/', '-')}.pdf"
    subject  = f"{doc_label} {inv.number} von {company_name}"
    body     = (
        f"Sehr geehrte Damen und Herren,\n\n"
        f"anbei erhalten Sie {doc_label} {inv.number}.\n\n"
        f"Mit freundlichen Grüßen\n{company_name}"
    )

    attachments = [{"filename": filename, "data": pdf_bytes, "mime_type": "application/pdf"}]

    for att in (extra_attachments or []):
        try:
            if att.get("type") == "datacenter":
                dc = db.query(Attachment).filter(Attachment.id == att["id"]).first()
                if dc and dc.storage_key:
                    data, mime = storage_service.download_file(dc.storage_key)
                    attachments.append({
                        "filename":  dc.filename or dc.display_name or "anhang",
                        "data":      data,
                        "mime_type": mime or dc.mimetype or "application/octet-stream",
                    })
            elif att.get("type") == "local":
                data = base64.b64decode(att.get("data_b64", ""))
                attachments.append({
                    "filename":  att.get("filename", "anhang"),
                    "data":      data,
                    "mime_type": att.get("mime_type", "application/octet-stream"),
                })
        except Exception:
            pass  # Einzelner fehlerhafter Anhang soll Versand nicht blockieren

    send_email(
        settings=settings_d,
        to_email=to_email,
        subject=subject,
        body_text=body,
        attachments=attachments,
    )

    # Status auf "gesendet" setzen (außer bereits bezahlt/storniert/angenommen/abgelehnt)
    if inv.status not in ("bezahlt", "storniert", "angenommen", "abgelehnt"):
        inv.status = "gesendet"
        inv.updated_by = current_user_email
        db.add(inv)


@router.post("/{invoice_id}/send-email")
async def send_invoice_email(
    invoice_id: UUID,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Versendet einen Beleg per E-Mail.
    Body: { to_email: str (optional — wird sonst aus Kontakt gelesen) }
    """
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Beleg nicht gefunden")

    settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, inv)

    to_email = body.get("to_email", "")
    if not to_email and recipient_contact:
        to_email = (recipient_contact.data or {}).get("email", "")
    if not to_email:
        raise HTTPException(400, "Keine E-Mail-Adresse vorhanden. Bitte im Kontakt hinterlegen.")

    extra_attachments = body.get("extra_attachments", [])

    try:
        _send_invoice_email(inv, db, settings_d, inv_settings_d,
                             sender_contact, recipient_contact, to_email, current_user.email,
                             extra_attachments=extra_attachments)
        db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"E-Mail konnte nicht gesendet werden: {str(e)}")

    return {"ok": True, "to": to_email, "number": inv.number}


@router.post("/bulk-send-email")
async def bulk_send_email(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Versendet mehrere Belege per E-Mail.
    Body: { invoice_ids: [str, ...] }
    """
    from uuid import UUID as _UUID
    ids = [_UUID(i) for i in body.get("invoice_ids", [])]
    if not ids:
        raise HTTPException(400, "Keine Belege angegeben")

    results = []
    for inv_id in ids:
        inv = db.query(Invoice).filter(Invoice.id == inv_id).first()
        if not inv:
            results.append({"id": str(inv_id), "ok": False, "error": "Nicht gefunden"})
            continue

        settings_d, inv_settings_d, sender_contact, recipient_contact = _load_pdf_context(db, inv)

        to_email = (recipient_contact.data or {}).get("email", "") if recipient_contact else ""
        if not to_email:
            results.append({"id": str(inv_id), "number": inv.number, "ok": False,
                             "error": "Keine E-Mail-Adresse im Kontakt"})
            continue

        try:
            _send_invoice_email(inv, db, settings_d, inv_settings_d,
                                 sender_contact, recipient_contact, to_email, current_user.email)
            results.append({"id": str(inv_id), "number": inv.number, "ok": True, "to": to_email})
        except Exception as e:
            results.append({"id": str(inv_id), "number": inv.number, "ok": False, "error": str(e)})

    db.commit()
    sent = sum(1 for r in results if r["ok"])
    return {"sent": sent, "total": len(ids), "results": results}


# ─────────────────────────────────────────────────────────────────────────────
# Zeiteinträge für Rechnung vorschlagen
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/time-entries/unbilled")
async def get_unbilled_time_entries(
    contact_id: Optional[UUID] = Query(None),
    project_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Gibt alle abgeschlossenen, noch nicht verrechneten Zeiteinträge zurück.

    Filterlogik:
    - contact_id: Sucht zuerst per UUID-Spalte. Falls keine Treffer,
      fällt zurück auf Textvergleich mit contact_name (weil ältere
      Einträge contact_id=null haben können).
    - project_id: Analog, mit Fallback auf project_name.
    - search: Freitextsuche über Beschreibung, Kontakt- und Projektname.
    """
    from app.models.zeiterfassung import TimeEntry
    from sqlalchemy import not_, or_ as _or_


    # Bereits verrechnete Einträge ausschließen
    billed_ids = db.query(InvoicePosition.time_entry_id).filter(
        InvoicePosition.time_entry_id.isnot(None)
    ).subquery()

    q = db.query(TimeEntry).filter(
        TimeEntry.ended_at.isnot(None),
        TimeEntry.billable == True,
        _or_(TimeEntry.id.notin_(db.query(billed_ids.c.time_entry_id)), False),
    )
    # Workaround: NOT IN mit Subquery
    billed_entry_ids = [r[0] for r in db.query(InvoicePosition.time_entry_id).filter(
        InvoicePosition.time_entry_id.isnot(None)
    ).all()]
    if billed_entry_ids:
        q = q.filter(not_(TimeEntry.id.in_(billed_entry_ids)))

    # Filter: contact_id
    if contact_id:
        primary = q.filter(TimeEntry.contact_id == contact_id).all()
        if primary:
            entries = primary
        else:
            entries = q.filter(TimeEntry.contact_name.ilike(
                f"%{str(contact_id)}%"
            )).all()
        q = db.query(TimeEntry).filter(TimeEntry.id.in_([e.id for e in entries]))
        if billed_entry_ids:
            q = q.filter(not_(TimeEntry.id.in_(billed_entry_ids)))

    # Filter: project_id
    if project_id:
        primary = q.filter(TimeEntry.project_id == project_id).all()
        if primary:
            q = db.query(TimeEntry).filter(TimeEntry.id.in_([e.id for e in primary]))
        else:
            q = q.filter(TimeEntry.project_name.ilike(f"%{str(project_id)}%"))
        if billed_entry_ids:
            q = q.filter(not_(TimeEntry.id.in_(billed_entry_ids)))

    # Filter: search
    if search:
        q = q.filter(_or_(
            TimeEntry.note.ilike(f"%{search}%"),
            TimeEntry.contact_name.ilike(f"%{search}%"),
            TimeEntry.project_name.ilike(f"%{search}%"),
        ))

    entries = q.order_by(TimeEntry.started_at.desc()).limit(200).all()

    result = []
    for e in entries:
        dur_h = round(e.duration_minutes / 60, 2) if e.duration_minutes else 0
        result.append({
            "id":             str(e.id),
            "started_at":     e.started_at.isoformat() if e.started_at else None,
            "ended_at":       e.ended_at.isoformat() if e.ended_at else None,
            "duration_hours": dur_h,
            "duration_minutes": e.duration_minutes,
            "note":           e.note or "",
            "description":    e.note or "Zeitaufwand",
            "contact_name":   e.contact_name or "",
            "project_name":   e.project_name or "",
            "contact_id":     str(e.contact_id) if e.contact_id else None,
            "project_id":     str(e.project_id) if e.project_id else None,
            "billable":       e.billable,
        })
    return result
