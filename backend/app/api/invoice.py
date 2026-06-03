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
    "rechnung": "RE",
    "angebot": "AN",
    "gutschrift": "GS",
    "lieferschein": "LS",
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


@router.post("/{invoice_id}/convert-to-invoice", response_model=InvoiceResponse)
async def convert_to_invoice(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Angebot in Rechnung umwandeln."""
    offer = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not offer:
        raise HTTPException(404, "Angebot nicht gefunden")
    if offer.doc_type != "angebot":
        raise HTTPException(400, "Nur Angebote können umgewandelt werden")

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

    billed_ids = db.query(InvoicePosition.time_entry_id).filter(
        InvoicePosition.time_entry_id.isnot(None)
    ).subquery()

    base_q = db.query(TimeEntry).filter(
        TimeEntry.ended_at.isnot(None),
        ~TimeEntry.id.in_(billed_ids),
    )

    # Kontakt-Filter: UUID wenn vorhanden, sonst contact_name
    if contact_id:
        # Versuche zunächst UUID-Match
        uuid_matches = base_q.filter(TimeEntry.contact_id == contact_id).count()
        if uuid_matches > 0:
            base_q = base_q.filter(TimeEntry.contact_id == contact_id)
        else:
            # Fallback: alle Einträge zeigen (contact_name ist ggf. im Picker sichtbar)
            pass  # kein weiterer Filter — Benutzer kann im Picker nach Kontakt suchen

    # Projekt-Filter
    if project_id:
        proj_uuid_matches = base_q.filter(TimeEntry.project_id == project_id).count()
        if proj_uuid_matches > 0:
            base_q = base_q.filter(TimeEntry.project_id == project_id)

    # Freitextsuche
    if search:
        like = f"%{search}%"
        base_q = base_q.filter(_or_(
            TimeEntry.contact_name.ilike(like),
            TimeEntry.project_name.ilike(like),
        ))

    entries = base_q.order_by(TimeEntry.started_at.desc()).limit(500).all()
    result = []
    for e in entries:
        duration_h = round((e.duration_minutes or 0) / 60, 4)
        result.append({
            "id": str(e.id),
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "duration_hours": duration_h,
            "description": e.data.get("beschreibung", "") if e.data else "",
            "project": e.project_name or "",
            "contact": e.contact_name or "",
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Rechnungsbuch
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/book/list")
async def invoice_book(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    doc_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(Invoice).filter(Invoice.is_recurring_template == False)
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    if contact_id:
        q = q.filter(Invoice.contact_id == contact_id)
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    if status:
        q = q.filter(Invoice.status == status)
    invoices = q.order_by(Invoice.date.asc(), Invoice.number.asc()).all()

    from decimal import Decimal
    total_net = sum(i.subtotal or Decimal("0") for i in invoices)
    total_tax = sum(i.tax_total or Decimal("0") for i in invoices)
    total_gross = sum(i.total or Decimal("0") for i in invoices)

    return {
        "invoices": [
            {
                "id": str(i.id),
                "number": i.number,
                "doc_type": i.doc_type,
                "date": i.date.isoformat(),
                "due_date": i.due_date.isoformat() if i.due_date else None,
                "contact_id": str(i.contact_id) if i.contact_id else None,
                "title": i.title,
                "subtotal": float(i.subtotal),
                "tax_total": float(i.tax_total),
                "total": float(i.total),
                "currency": i.currency,
                "status": i.status,
            }
            for i in invoices
        ],
        "summary": {
            "count": len(invoices),
            "total_net": float(total_net),
            "total_tax": float(total_tax),
            "total_gross": float(total_gross),
        },
    }


@router.get("/book/csv")
async def invoice_book_csv(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    doc_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    import csv, io
    q = db.query(Invoice).filter(Invoice.is_recurring_template == False)
    if date_from:
        q = q.filter(Invoice.date >= date_from)
    if date_to:
        q = q.filter(Invoice.date <= date_to)
    if contact_id:
        q = q.filter(Invoice.contact_id == contact_id)
    if doc_type:
        q = q.filter(Invoice.doc_type == doc_type)
    invoices = q.order_by(Invoice.date.asc()).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["Nummer", "Typ", "Datum", "Fällig", "Titel", "Netto", "MwSt", "Brutto", "Währung", "Status"])
    for i in invoices:
        writer.writerow([
            i.number, i.doc_type, i.date, i.due_date or "",
            i.title or "", float(i.subtotal), float(i.tax_total), float(i.total),
            i.currency, i.status,
        ])

    output.seek(0)
    filename = f"rechnungsbuch_{date_from or 'alle'}_{date_to or 'alle'}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Einstellungen
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/settings/all")
async def get_invoice_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    rows = db.query(InvoiceSettings).all()
    return {r.key: r.value for r in rows}



@router.put("/settings/{key}")
async def update_invoice_setting(
    key: str,
    body: InvoiceSettingsUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    setting = db.query(InvoiceSettings).filter_by(key=key).first()
    if setting:
        setting.value = body.value
    else:
        setting = InvoiceSettings(key=key, value=body.value)
        db.add(setting)
    db.commit()
    return {"key": key, "value": body.value}


# ─────────────────────────────────────────────────────────────────────────────
# PDF-Endpunkte
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Muster-Vorschau für Template-Auswahl (kein echtes Dokument nötig)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/template-preview/{template_id}")
async def template_preview(
    template_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from fastapi.responses import HTMLResponse
    from app.services.invoice_pdf import generate_html_preview
    from decimal import Decimal
    from datetime import date as _date
    import types

    settings_d = {r.key: r.value for r in db.query(Setting).all()}
    inv_settings_d = {r.key: r.value for r in db.query(InvoiceSettings).all()}
    # Vorlage aus Parameter erzwingen
    inv_settings_d["default_template"] = template_id

    sender_contact = None
    cid = settings_d.get("company_contact_id")
    if cid:
        try:
            from uuid import UUID as _UUID
            sender_contact = db.query(EntityRecord).filter(EntityRecord.id == _UUID(cid)).first()
        except Exception:
            pass

    # Muster-Rechnung als einfaches Objekt
    inv = types.SimpleNamespace(
        doc_type="rechnung",
        number="RE-2026-001",
        date=_date.today(),
        due_date=_date(2026, 7, 31),
        delivery_date=None,
        reference="Muster-001",
        title="Musterrechnung — Vorschau",
        intro_text="Wir erlauben uns, folgende Leistungen in Rechnung zu stellen:",
        outro_text="Wir bitten um Überweisung des Betrages innerhalb von 30 Tagen. Vielen Dank!",
        tax_mode="per_position",
        subtotal=Decimal("1680.00"),
        tax_total=Decimal("336.00"),
        total=Decimal("2016.00"),
        currency="EUR",
        status="entwurf",
        template_id=template_id,
        contact_id=None,
    )

    # Muster-Positionen
    class FakePos:
        def __init__(self, desc, qty, price, tax, detail=None, unit="Stk"):
            self.pos_type = "item"
            self.description = desc
            self.detail = detail
            self.quantity = Decimal(str(qty))
            self.unit = unit
            self.unit_price = Decimal(str(price))
            self.discount_pct = None
            self.tax_rate = Decimal(str(tax))
            self.line_total = (self.quantity * self.unit_price).quantize(Decimal("0.01"))

    positions = [
        FakePos("Webentwicklung — Frontend", 8, 120, 20, "React-Komponenten und UI-Implementierung", "h"),
        FakePos("Webentwicklung — Backend", 6, 120, 20, "REST-API, Datenbank-Design", "h"),
        FakePos("Projektmanagement & Meetings", 2, 90, 20, unit="h"),
        FakePos("Server-Konfiguration (Pauschal)", 1, 480, 20),
    ]

    html = generate_html_preview(inv, positions, settings_d, inv_settings_d, sender_contact, None)
    return HTMLResponse(content=html)


@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(404, "Rechnung nicht gefunden")

    settings, inv_settings, sender, recipient = _load_pdf_context(db, inv)
    pdf_bytes = generate_pdf(inv, inv.positions, settings, inv_settings, sender, recipient)

    filename = f"{inv.number.replace('/', '-')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{invoice_id}/preview")
async def preview_invoice_html(
    invoice_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from fastapi.responses import HTMLResponse
  