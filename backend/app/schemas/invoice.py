from pydantic import BaseModel, Field
from typing import Optional, List, Any
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal


# ── Position ──────────────────────────────────────────────────────────────────

class InvoicePositionBase(BaseModel):
    sort_order: int = 0
    # item | text | time_entry | discount | subtotal | heading
    # | advance_deduction (Abzug einer bereits gestellten Anzahlung; wird
    #   serverseitig gerechnet und beim Speichern verworfen)
    pos_type: str = "item"
    description: str
    detail: Optional[str] = None
    quantity: Decimal = Decimal("1")
    unit: Optional[str] = None
    unit_price: Decimal = Decimal("0")
    discount_pct: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    account_nr: Optional[str] = None        # Erlöskonto, leer = Standard-Erlöskonto
    image_key: Optional[str] = None         # Objektspeicher-Schlüssel des Bildes
    image_size: Optional[str] = None        # klein | mittel | gross
    image_provider: Optional[str] = None    # Speicher der Datei; leer = aktiver
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
    delivery_date_to: Optional[date] = None
    valid_until: Optional[date] = None      # Bindefrist (Angebot)
    reference: Optional[str] = None
    intro_text: Optional[str] = None
    outro_text: Optional[str] = None
    notes: Optional[str] = None
    tax_mode: str = "per_position"
    currency: str = "EUR"
    template_id: int = 1
    # Zahlungsbedingung: "skonto_percent % bei Zahlung binnen skonto_days Tagen"
    skonto_percent: Optional[Decimal] = None
    skonto_days: Optional[int] = None
    # Abrechnung in Stufen: anzahlung | teil | schluss (None = normale Rechnung)
    billing_stage: Optional[str] = None
    chain_id: Optional[UUID] = None
    positions: List[InvoicePositionCreate] = []
    # Wiederkehrend
    is_recurring_template: bool = False
    recurring_interval: Optional[str] = None
    recurring_next: Optional[date] = None
    recurring_action: Optional[str] = None
    recurring_end: Optional[date] = None

class InvoiceUpdate(BaseModel):
    """
    Beleg bearbeiten.

    Bewusst OHNE ``doc_type``: Die Belegart bestimmt den Nummernkreis. Ließe
    sie sich nachträglich ändern, würde aus RE-2026-001 ein „Angebot" mit
    Rechnungsnummer. Für eine andere Belegart wird ein neuer Beleg angelegt.
    """
    contact_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    related_invoice_id: Optional[UUID] = None
    title: Optional[str] = None
    date: date
    due_date: Optional[date] = None
    delivery_date: Optional[date] = None
    delivery_date_to: Optional[date] = None
    valid_until: Optional[date] = None      # Bindefrist (Angebot)
    reference: Optional[str] = None
    intro_text: Optional[str] = None
    outro_text: Optional[str] = None
    notes: Optional[str] = None
    tax_mode: str = "per_position"
    currency: str = "EUR"
    template_id: int = 1
    # Zahlungsbedingung: "skonto_percent % bei Zahlung binnen skonto_days Tagen"
    skonto_percent: Optional[Decimal] = None
    skonto_days: Optional[int] = None
    # Die Abrechnungsstufe bleibt änderbar, solange der Beleg Entwurf ist:
    # Aus einer versehentlich gewöhnlichen Rechnung soll eine Teilrechnung
    # werden können, ohne sie neu anzulegen.
    billing_stage: Optional[str] = None
    chain_id: Optional[UUID] = None
    positions: List[InvoicePositionCreate] = []
    is_recurring_template: bool = False
    recurring_interval: Optional[str] = None
    recurring_next: Optional[date] = None
    recurring_action: Optional[str] = None
    recurring_end: Optional[date] = None

class InvoiceResponse(BaseModel):
    id: UUID
    doc_type: str
    # Entwürfe haben noch keine Nummer — sie fällt beim Finalisieren
    number: Optional[str] = None
    year: Optional[int] = None
    sequence: Optional[int] = None
    contact_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    related_invoice_id: Optional[UUID] = None
    recipient_snapshot: Optional[dict] = None
    title: Optional[str] = None
    date: date
    due_date: Optional[date] = None
    delivery_date: Optional[date] = None
    delivery_date_to: Optional[date] = None
    valid_until: Optional[date] = None      # Bindefrist (Angebot)
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
    skonto_percent: Optional[Decimal] = None
    skonto_days: Optional[int] = None
    dunning_blocked: bool = False
    dunning_block_reason: Optional[str] = None
    dunning_level: int = 0
    dunning_last_at: Optional[date] = None
    # Abrechnung in Stufen
    billing_stage: Optional[str] = None
    chain_id: Optional[UUID] = None
    advance_percent: Optional[Decimal] = None
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
    number: Optional[str] = None            # None = Entwurf, Nummer noch nicht vergeben
    date: date
    due_date: Optional[date] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    title: Optional[str] = None
    total: Decimal
    currency: str
    status: str
    created_at: datetime
    is_recurring_template: bool = False
    recurring_source_id: Optional[UUID] = None    # gesetzt = automatisch aus Vorlage erzeugt
    valid_until: Optional[date] = None            # Bindefrist (Angebot)
    expired: bool = False                         # abgeleitet, kein Status
    billing_stage: Optional[str] = None           # anzahlung | teil | schluss
    chain_id: Optional[UUID] = None               # Kopf des Abrechnungsstrangs

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


# ── Abrechnung in Stufen (C-10) ───────────────────────────────────────────────

# ``date`` ist in diesem Modul zugleich Typ und übliches Feldname. Solange das
# Feld keinen Vorgabewert hat (``date: date``), ist das harmlos. Bekommt es
# einen (``date: Optional[date] = None``), landet der Name im Namensraum der
# Klasse — und Pydantic löst die Typangaben anschließend gegen genau diesen
# Namensraum auf. Aus ``Optional[date]`` wird dann stillschweigend
# ``Optional[None]``: Das Feld nimmt nur noch ``null`` an und weist jedes
# Datum mit 422 ab. Betroffen sind ALLE Datumsfelder der Klasse, nicht nur das
# auslösende. Ein eigener Name für den Typ umgeht das.
Belegdatum = date


class AnzahlungRequest(BaseModel):
    """
    Anzahlung aus einem Angebot oder einer Auftragsbestätigung anfordern.

    Entweder Prozentsatz **oder** Betrag. Der Prozentsatz wird sofort in einen
    Betrag umgerechnet und nur zur Anzeige mitgeführt: Ändert sich das Angebot
    später, soll auf der bereits gestellten Anzahlungsrechnung weiterhin das
    stehen, was der Kunde bekommen hat.
    """
    percent: Optional[Decimal] = None
    amount: Optional[Decimal] = None        # Nettobetrag
    description: Optional[str] = None
    date: Optional[Belegdatum] = None
    due_date: Optional[Belegdatum] = None


class SchlussrechnungRequest(BaseModel):
    """
    Schlussrechnung eines Strangs erzeugen.

    ``from_invoice_id`` ist der Beleg, aus dem die Positionen der
    Gesamtleistung übernommen werden — üblicherweise das Angebot. Fehlt er,
    entsteht die Schlussrechnung leer und wird von Hand gefüllt.
    """
    from_invoice_id: Optional[UUID] = None
    date: Optional[Belegdatum] = None
    due_date: Optional[Belegdatum] = None


class AbzugZeile(BaseModel):
    tax_rate: Optional[Decimal] = None
    net_amount: Decimal
    tax_amount: Decimal


class StrangBeleg(BaseModel):
    id: UUID
    doc_type: str
    number: Optional[str] = None
    billing_stage: Optional[str] = None
    stage_label: str
    date: date
    title: Optional[str] = None
    subtotal: Decimal
    total: Decimal
    status: str
    open_amount: Decimal = Decimal("0")
    deducted: bool = False              # wird in der Schlussrechnung abgezogen


class StrangResponse(BaseModel):
    """Übersicht über ein Bauvorhaben: alle Belege und der Stand der Abrechnung."""
    chain_id: Optional[UUID] = None
    belege: List[StrangBeleg] = []
    abzug: List[AbzugZeile] = []
    abzug_netto: Decimal = Decimal("0")
    abzug_brutto: Decimal = Decimal("0")
    hat_schlussrechnung: bool = False
    hinweise: List[str] = []

class InvoiceDuplicateRequest(BaseModel):
    """Steuert, welche Bestandteile beim Duplizieren übernommen werden."""
    positions: bool = True          # Positionszeilen
    texts: bool = True              # Einleitungs-/Schlusstext + Notizen
    contact: bool = True            # Kontakt, Projekt, Titel, Referenz
    attachments: bool = False       # Datei-Anhänge


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


# ── Zahlungen ─────────────────────────────────────────────────────────────────

class InvoicePaymentCreate(BaseModel):
    paid_at: date
    amount: Decimal
    method: Optional[str] = None       # bank | bar | karte | lastschrift | verrechnung | sonstige
    reference: Optional[str] = None
    note: Optional[str] = None

class InvoicePaymentResponse(BaseModel):
    id: UUID
    invoice_id: UUID
    paid_at: date
    amount: Decimal
    payment_type: str = "zahlung"      # zahlung | skonto
    method: Optional[str] = None
    reference: Optional[str] = None
    note: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class InvoicePaymentState(BaseModel):
    """Zahlstand eines Belegs — nach jeder Zahlungsänderung zurückgegeben."""
    invoice_id: UUID
    status: str
    total: Decimal
    paid_total: Decimal
    open_amount: Decimal               # negativ = überzahlt
    overpaid: bool
    payments: List[InvoicePaymentResponse] = []


# ── Offene Posten ─────────────────────────────────────────────────────────────

class OpenItem(BaseModel):
    id: UUID
    number: Optional[str] = None
    doc_type: str
    date: date
    due_date: Optional[date] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    title: Optional[str] = None
    total: Decimal
    paid_total: Decimal
    open_amount: Decimal
    status: str
    days_overdue: int                  # 0 = noch nicht fällig
    bucket: str                        # nicht_faellig | b1_30 | b31_60 | b61_90 | b90_plus

class OpenItemsByContact(BaseModel):
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    open_amount: Decimal
    count: int

class OpenItemsResponse(BaseModel):
    items: List[OpenItem] = []
    by_contact: List[OpenItemsByContact] = []
    buckets: dict                      # {"nicht_faellig": 0.0, "b1_30": …}
    total_open: Decimal
    count: int


# ── Umsatzsteuer-Voranmeldung ─────────────────────────────────────────────────

class UvaZeile(BaseModel):
    kennzahl: str                      # "022", "029", "006" … leer = nicht zugeordnet
    bezeichnung: str
    satz: Optional[Decimal] = None     # None = Reverse Charge
    bemessungsgrundlage: Decimal
    steuer: Decimal
    zugeordnet: bool                   # False → Kennzahl fehlt, muss gepflegt werden

class UvaResponse(BaseModel):
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    country: str = "AT"                # Steuerland der Firma
    country_supported: bool = True     # False → Formular für dieses Land fehlt
    zeilen: List[UvaZeile] = []
    kz_000: Decimal                    # Gesamtbetrag der Bemessungsgrundlage
    steuer_gesamt: Decimal
    beleg_anzahl: int
    hinweise: List[str] = []


# ── Mahnwesen ─────────────────────────────────────────────────────────────────

class DunningLevelConfig(BaseModel):
    """Eine Mahnstufe aus den Verkaufseinstellungen."""
    level: int
    label: str
    days_after: int = 0        # Stufe 1: Tage nach Fälligkeit, sonst nach der Vorstufe
    grace_days: int = 0        # im Schreiben gesetzte Nachfrist
    fee: Decimal = Decimal("0")
    interest: bool = False
    text: Optional[str] = None

class DunningCandidate(BaseModel):
    invoice_id: UUID
    number: Optional[str] = None
    date: date
    due_date: Optional[date] = None
    title: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    total: Decimal
    open_amount: Decimal
    days_overdue: int
    current_level: int
    last_dunned_at: Optional[date] = None
    next_level: Optional[int] = None
    next_label: Optional[str] = None
    fee: Decimal = Decimal("0")
    interest: Decimal = Decimal("0")
    interest_rate: Optional[Decimal] = None
    dunnable: bool
    reason: Optional[str] = None       # gesetzt, wenn nicht mahnbar

class DunningRunResponse(BaseModel):
    stichtag: date
    items: List[DunningCandidate] = []
    dunnable_count: int = 0
    levels: List[DunningLevelConfig] = []
    interest_hint: Optional[str] = None

class DunningCreateRequest(BaseModel):
    """
    Mahnung erzeugen. Ohne ``level`` wird die nächste fällige Stufe genommen.

    ``force`` übergeht die Wartezeit — nicht aber eine Mahnsperre. Die Sperre
    ist eine bewusste Entscheidung und darf nicht versehentlich fallen.
    """
    level: Optional[int] = None
    dunned_at: Optional[date] = None
    force: bool = False
    send_email: bool = False

class DunningEntry(BaseModel):
    id: UUID
    invoice_id: UUID
    level: int
    label: Optional[str] = None
    dunned_at: date
    due_date: Optional[date] = None
    open_amount: Decimal
    fee: Decimal
    interest: Decimal
    interest_rate: Optional[Decimal] = None
    interest_days: Optional[int] = None
    batch_id: Optional[UUID] = None
    sent_at: Optional[datetime] = None
    sent_to: Optional[str] = None
    note: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class DunningBlockRequest(BaseModel):
    blocked: bool
    reason: Optional[str] = None

class DunningBatchRequest(BaseModel):
    """Sammelmahnlauf über eine Auswahl von Belegen."""
    invoice_ids: List[UUID] = []
    dunned_at: Optional[date] = None
    force: bool = False


# ── Skonto ────────────────────────────────────────────────────────────────────

class SkontoZeile(BaseModel):
    satz: Optional[Decimal] = None     # None = Reverse Charge
    brutto: Decimal
    netto: Decimal                     # Entgeltminderung
    steuer: Decimal                    # Steuerberichtigung § 16 UStG

class SkontoVorschau(BaseModel):
    invoice_id: UUID
    skonto_percent: Optional[Decimal] = None
    skonto_days: Optional[int] = None
    frist_ende: Optional[date] = None
    in_frist: bool = False
    betrag: Decimal = Decimal("0")     # Skonto laut Vereinbarung
    open_amount: Decimal = Decimal("0")
    zeilen: List[SkontoZeile] = []
    hinweis: Optional[str] = None

class SkontoRequest(BaseModel):
    """
    Restbetrag als Skonto ausbuchen.

    ``paid_at`` ist das Datum des Zahlungseingangs — daran hängt die
    Umsatzsteuer-Berichtigung, nicht am Rechnungsdatum.
    """
    paid_at: date
    amount: Optional[Decimal] = None   # ohne Angabe: der offene Restbetrag
    note: Optional[str] = None


# ── Änderungsprotokoll ────────────────────────────────────────────────────────

class InvoiceAuditEntry(BaseModel):
    id: UUID
    action: str
    changes: Optional[dict] = None
    note: Optional[str] = None
    changed_by: Optional[str] = None
    changed_at: datetime

    class Config:
        from_attributes = True


# ── E-Rechnung (C-5) ──────────────────────────────────────────────────────────

class ERechnungPruefung(BaseModel):
    """
    Ob und was einer E-Rechnung dieses Belegs noch fehlt.

    ``aktiv`` und ``moeglich`` sind zwei verschiedene Fragen: Die E-Rechnung
    kann eingeschaltet und der Beleg trotzdem unvollständig sein — und
    umgekehrt.
    """
    aktiv: bool = False
    moeglich: bool = False
    fehlende_angaben: List[str] = []
    format: str = ""
