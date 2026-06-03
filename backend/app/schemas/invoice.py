from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal


# ── Position ──────────────────────────────────────────────────────────────────

class InvoicePositionBase(BaseModel):
    sort_order: int = 0
    pos_type: str = "item"
    description: str
    detail: Optional[str] = None
    quantity: Decimal = Decimal("1")
    unit: Optional[str] = None
    unit_price: Decimal = Decimal("0")
    discount_pct: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    article_id: Optional[UUID] = None
    time_entry_id: Optional[UUID] = None

class InvoicePositionCreate(InvoicePositionBase):
    pass

class InvoicePositionUpdate(InvoicePositionBase):
    pass

class InvoicePositionResponse(InvoicePositionBase):
    id: UUID
    invoice_id: UUID
    line_total: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


# ── Anhang ────────────────────────────────────────────────────────────────────

class InvoiceAttachmentCreate(BaseModel):
    attach_type: str                        # upload | datacenter | external
    filename: Optional[str] = None
    datacenter_id: Optional[UUID] = None
    url: Optional[str] = None

class InvoiceAttachmentResponse(BaseModel):
    id: UUID
    invoice_id: UUID
    attach_type: str
    filename: Optional[str] = None
    file_path: Optional[str] = None
    datacenter_id: Optional[UUID] = None
    url: Optional[str] = None
    mime_type: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Rechnung ──────────────────────────────────────────────────────────────────

class InvoiceCreate(BaseModel):
    doc_type: str = "rechnung"              # rechnung | angebot | gutschrift | lieferschein
    contact_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    related_invoice_id: Optional[UUID] = None
    title: Optional[str] = None
    date: date
    due_date: Optional[date] = None
    delivery_date: Optional[date] = None
    reference: Optional[str] = None
    intro_text: Optional[str] = None
    outro_text: Optional[str] = None
    notes: Optional[str] = None
    tax_mode: str = "per_position"
    currency: str = "EUR"
    template_id: int = 1
    positions: List[InvoicePositionCreate] = []
    # Wiederkehrend
    is_recurring_template: bool = False
    recurring_interval: Optional[str] = None
    recurring_next: Optional[date] = None
    recurring_action: Optional[str] = None
    recurring_end: Optional[date] = None

class InvoiceUpdate(InvoiceCreate):
    pass

class InvoiceResponse(BaseModel):
    id: UUID
    doc_type: str
    number: str
    year: int
    sequence: int
    contact_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    related_invoice_id: Optional[UUID] = None
    title: Optional[str] = None
    date: date
    due_date: Optional[date] = None
    delivery_date: Optional[date] = None
    reference: Optional[str] = None
    intro_text: Optional[str] = None
    outro_text: Optional[str] = None
    notes: Optional[str] = None
    tax_mode: str
    subtotal: Decimal
    tax_total: Decimal
    total: Decimal
    currency: str
    status: str
    cancel_mode: Optional[str] = None
    paid_at: Optional[date] = None
    paid_amount: Optional[Decimal] = None
    template_id: int
    is_recurring_template: bool
    recurring_interval: Optional[str] = None
    recurring_next: Optional[date] = None
    recurring_action: Optional[str] = None
    recurring_end: Optional[date] = None
    recurring_source_id: Optional[UUID] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    positions: List[InvoicePositionResponse] = []
    attachments: List[InvoiceAttachmentResponse] = []

    class Config:
        from_attributes = True

class InvoiceListItem(BaseModel):
    id: UUID
    doc_type: str
    number: str
    date: date
    due_date: Optional[date] = None
    contact_id: Optional[UUID] = None
    title: Optional[str] = None
    total: Decimal
    currency: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Aktionen ──────────────────────────────────────────────────────────────────

class InvoiceCancelRequest(BaseModel):
    cancel_mode: str = "with_credit"        # status_only | with_credit

class InvoiceMarkPaidRequest(BaseModel):
    paid_at: date
    paid_amount: Optional[Decimal] = None

class InvoiceConvertRequest(BaseModel):
    """Angebot → Rechnung umwandeln"""
    pass


# ── Rechnungsbuch ─────────────────────────────────────────────────────────────

class InvoiceBookFilter(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    period: Optional[str] = None            # month | quarter | year
    period_value: Optional[str] = None      # z.B. "2026-01", "2026-Q1", "2026"
    contact_id: Optional[UUID] = None
    doc_type: Optional[str] = None
    status: Optional[str] = None


# ── Einstellungen ─────────────────────────────────────────────────────────────

class InvoiceSettingsUpdate(BaseModel):
    key: str
    value: Any


# ── Nummernkreis-Info ─────────────────────────────────────────────────────────

class NextNumberResponse(BaseModel):
    doc_type: str
    year: int
    next_sequence: int
    preview: str                            # "RE-2026-001"
