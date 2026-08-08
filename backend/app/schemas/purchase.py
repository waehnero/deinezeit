from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal


# ── Steuerzeilen ──────────────────────────────────────────────────────────────

class PurchaseTaxLine(BaseModel):
    """
    Netto und Steuer zu einem Satz.

    ``tax_amount`` wird erfasst, nicht gerechnet — maßgeblich ist der Betrag
    auf der Rechnung des Lieferanten. ``tax_rate = None`` steht für „kein
    Satz ausgewiesen" (Reverse Charge).
    """
    tax_rate: Optional[Decimal] = None
    net_amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")


class PurchaseTaxLineResponse(PurchaseTaxLine):
    id: UUID

    class Config:
        from_attributes = True


# ── Beleg ─────────────────────────────────────────────────────────────────────

class PurchaseInvoiceBase(BaseModel):
    supplier_id: Optional[UUID] = None
    supplier_number: Optional[str] = None       # Rechnungs-Nr. des Lieferanten
    date: date
    delivery_date: Optional[date] = None
    due_date: Optional[date] = None
    tax_kind: str = "normal"                    # normal | reverse_charge | ig_erwerb | einfuhr | ohne_vorsteuer
    vat_deductible: bool = True
    vat_note: Optional[str] = None
    account_nr: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    currency: str = "EUR"
    taxes: List[PurchaseTaxLine] = []


class PurchaseInvoiceCreate(PurchaseInvoiceBase):
    pass


class PurchaseInvoiceUpdate(PurchaseInvoiceBase):
    pass


class PurchaseInvoiceResponse(BaseModel):
    id: UUID
    internal_number: Optional[str] = None
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    supplier_number: Optional[str] = None
    supplier_uid: Optional[str] = None
    date: date
    delivery_date: Optional[date] = None
    due_date: Optional[date] = None
    tax_kind: str
    vat_deductible: bool
    vat_note: Optional[str] = None
    account_nr: Optional[str] = None
    title: Optional[str] = None
    note: Optional[str] = None
    net_total: Decimal
    tax_total: Decimal
    gross_total: Decimal
    currency: str
    status: str
    paid_at: Optional[date] = None
    paid_amount: Optional[Decimal] = None
    file_key: Optional[str] = None
    file_name: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    taxes: List[PurchaseTaxLineResponse] = []

    class Config:
        from_attributes = True


class PurchaseInvoiceListItem(BaseModel):
    id: UUID
    internal_number: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_number: Optional[str] = None
    date: date
    due_date: Optional[date] = None
    title: Optional[str] = None
    tax_kind: str
    net_total: Decimal
    tax_total: Decimal
    gross_total: Decimal
    currency: str
    status: str
    has_file: bool = False
    open_amount: Decimal = Decimal("0")

    class Config:
        from_attributes = True


# ── Zahlungen ─────────────────────────────────────────────────────────────────

class PurchasePaymentCreate(BaseModel):
    paid_at: date
    amount: Decimal
    method: Optional[str] = None
    reference: Optional[str] = None
    note: Optional[str] = None


class PurchasePaymentResponse(BaseModel):
    id: UUID
    purchase_invoice_id: UUID
    paid_at: date
    amount: Decimal
    method: Optional[str] = None
    reference: Optional[str] = None
    note: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PurchasePaymentState(BaseModel):
    purchase_invoice_id: UUID
    status: str
    gross_total: Decimal
    paid_total: Decimal
    open_amount: Decimal
    overpaid: bool = False
    payments: List[PurchasePaymentResponse] = []


# ── Offene Posten (Kreditoren) ────────────────────────────────────────────────

class PurchaseOpenItem(BaseModel):
    id: UUID
    internal_number: Optional[str] = None
    supplier_number: Optional[str] = None
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    date: date
    due_date: Optional[date] = None
    title: Optional[str] = None
    gross_total: Decimal
    paid_total: Decimal
    open_amount: Decimal
    status: str
    days_overdue: int = 0
    bucket: str


class PurchaseOpenItemsBySupplier(BaseModel):
    supplier_id: Optional[UUID] = None
    supplier_name: Optional[str] = None
    open_amount: Decimal
    count: int


class PurchaseOpenItemsResponse(BaseModel):
    items: List[PurchaseOpenItem] = []
    by_supplier: List[PurchaseOpenItemsBySupplier] = []
    buckets: dict = {}
    total_open: Decimal
    count: int


# ── Vorsteuer-Auswertung ──────────────────────────────────────────────────────

class VorsteuerZeile(BaseModel):
    schluessel: str
    kennzahl: str
    bezeichnung: str
    betrag: Decimal
    grundlage: Decimal
    art: str                      # vorsteuer | steuerschuld
    zugeordnet: bool


class VorsteuerResponse(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    zeilen: List[VorsteuerZeile] = []
    vorsteuer_gesamt: Decimal
    schuld_gesamt: Decimal
    nicht_abziehbar: Decimal
    beleg_anzahl: int
    hinweise: List[str] = []
