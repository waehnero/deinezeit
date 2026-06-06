import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (Column, String, Boolean, DateTime, Integer, Date,
                        Text, ForeignKey, Numeric, UniqueConstraint)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base


class Invoice(Base):
    """
    Rechnung, Angebot, Gutschrift oder Lieferschein.
    doc_type: rechnung | angebot | gutschrift | lieferschein
    """
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Typ & Nummer
    doc_type = Column(String(20), nullable=False)           # rechnung | angebot | gutschrift | lieferschein
    number = Column(String(50), nullable=False, unique=True)
    year = Column(Integer, nullable=False)
    sequence = Column(Integer, nullable=False)

    # Bezüge
    contact_id = Column(UUID(as_uuid=True), nullable=True)          # entity_records.id
    project_id = Column(UUID(as_uuid=True), nullable=True)          # entity_records.id
    related_invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)

    # Inhalte
    title = Column(String(300), nullable=True)
    date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    delivery_date = Column(Date, nullable=True)
    reference = Column(String(200), nullable=True)
    intro_text = Column(Text, nullable=True)
    outro_text = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # MwSt.-Modus: per_position | single_rate | kleinunternehmer
    tax_mode = Column(String(30), nullable=False, default="per_position")

    # Berechnete Beträge (gecacht)
    subtotal = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    tax_total = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    total = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    currency = Column(String(3), nullable=False, default="EUR")

    # Status: entwurf | gesendet | offen | bezahlt | ueberfaellig | storniert | angenommen | abgelehnt
    status = Column(String(30), nullable=False, default="entwurf")
    cancel_mode = Column(String(20), nullable=True)         # status_only | with_credit
    paid_at = Column(Date, nullable=True)
    paid_amount = Column(Numeric(12, 2), nullable=True)

    # PDF-Vorlage (1–5)
    template_id = Column(Integer, nullable=False, default=1)

    # Wiederkehrend
    is_recurring_template = Column(Boolean, nullable=False, default=False)
    recurring_interval = Column(String(20), nullable=True)  # weekly | monthly | quarterly | yearly
    recurring_next = Column(Date, nullable=True)
    recurring_action = Column(String(20), nullable=True)    # remind | create | create_and_send
    recurring_end = Column(Date, nullable=True)
    recurring_source_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)

    # Audit
    created_by = Column(String(200), nullable=True)
    updated_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    positions = relationship("InvoicePosition", back_populates="invoice",
                             cascade="all, delete-orphan", order_by="InvoicePosition.sort_order")
    attachments = relationship("InvoiceAttachment", back_populates="invoice",
                               cascade="all, delete-orphan")
    related_invoice = relationship("Invoice", foreign_keys=[related_invoice_id], remote_side="Invoice.id")
    recurring_instances = relationship("Invoice", foreign_keys=[recurring_source_id], remote_side="Invoice.id")


class InvoicePosition(Base):
    """
    Eine Position in einer Rechnung.
    pos_type: item | text | time_entry | discount | subtotal
    """
    __tablename__ = "invoice_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)

    article_id = Column(UUID(as_uuid=True), nullable=True)          # entity_records.id (Artikel)
    time_entry_id = Column(UUID(as_uuid=True), nullable=True)       # time_entries.id

    pos_type = Column(String(20), nullable=False, default="item")
    description = Column(Text, nullable=False)
    detail = Column(Text, nullable=True)
    quantity = Column(Numeric(10, 4), nullable=False, default=Decimal("1"))
    unit = Column(String(30), nullable=True)
    unit_price = Column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    discount_pct = Column(Numeric(5, 2), nullable=True)
    tax_rate = Column(Numeric(5, 2), nullable=True)                  # None = reverse charge
    line_total = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="positions")


class InvoiceAttachment(Base):
    """
    Anhang zu einer Rechnung.
    attach_type: upload | datacenter | external
    """
    __tablename__ = "invoice_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    attach_type = Column(String(20), nullable=False)
    filename = Column(String(300), nullable=True)
    file_path = Column(String(500), nullable=True)
    datacenter_id = Column(UUID(as_uuid=True), nullable=True)
    url = Column(String(1000), nullable=True)
    mime_type = Column(String(100), nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="attachments")


class InvoiceNumberSequence(Base):
    """Zähler für automatische Nummerierung pro Typ und Jahr."""
    __tablename__ = "invoice_number_sequences"
    __table_args__ = (UniqueConstraint("doc_type", "year", name="uq_invoice_seq_type_year"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_type = Column(String(20), nullable=False)
    year = Column(Integer, nullable=False)
    last_sequence = Column(Integer, nullable=False, default=0)


class InvoiceSettings(Base):
    """Key-Value-Store für Rechnungseinstellungen (Bankdaten, Texte, Steuersätze)."""
    __tablename__ = "invoice_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
