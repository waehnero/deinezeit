"""
Eingangsrechnungen (Kreditoren).

Gegenstück zum Verkaufsbeleg — mit einem entscheidenden Unterschied: Eine
Eingangsrechnung wird nicht erzeugt, sondern **abgeschrieben**. Was drauf
steht, gilt. Deshalb wird der Steuerbetrag erfasst und nicht gerechnet, und
deshalb gibt es keine Positionen: Die Rechnung existiert bereits als PDF, sie
muss nur gebucht und für die Vorsteuer ausgewertet werden.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (Index, Column, String, Boolean, DateTime, Integer, Date,
                        Text, ForeignKey, Numeric)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


# Steuerarten und ihre Bedeutung für die Voranmeldung
TAX_KINDS = ("normal", "reverse_charge", "ig_erwerb", "einfuhr", "ohne_vorsteuer")

TAX_KIND_LABELS = {
    "normal":         "Inland mit Vorsteuer",
    "reverse_charge": "Reverse Charge (§ 19)",
    "ig_erwerb":      "Innergemeinschaftlicher Erwerb",
    "einfuhr":        "Einfuhr (Drittland)",
    "ohne_vorsteuer": "Ohne Vorsteuerabzug",
}


class PurchaseInvoice(Base):
    """Eine Lieferantenrechnung."""
    __tablename__ = "purchase_invoices"
    # Indizes/Constraints mit den Namen aus den Migrationen (Audit DATA-004):
    # Modelle und Produktionsschema müssen deckungsgleich sein, damit die
    # Tests dasselbe Schema prüfen wie der Betrieb (tests/test_migrationen.py).
    __table_args__ = (
        Index('ix_purchase_invoices_date', 'date'),
        Index('ix_purchase_invoices_status', 'status'),
        Index('ix_purchase_invoices_supplier', 'supplier_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Eigene laufende Nummer für die Ablage. Die Nummer des Lieferanten taugt
    # dafür nicht: Sie ist über alle Lieferanten hinweg nicht eindeutig.
    internal_number = Column(String(50), nullable=True, unique=True)
    year = Column(Integer, nullable=True)
    sequence = Column(Integer, nullable=True)

    supplier_id = Column(UUID(as_uuid=True), nullable=True)      # entity_records.id
    # Eingefroren wie der Empfänger-Snapshot beim Verkaufsbeleg: Eine spätere
    # Umbenennung oder Anonymisierung darf einen gebuchten Beleg nicht ändern.
    supplier_name = Column(String(300), nullable=True)
    supplier_number = Column(String(100), nullable=True)         # Rechnungs-Nr. des Lieferanten
    supplier_uid = Column(String(50), nullable=True)

    date = Column(Date, nullable=False)                          # Rechnungsdatum
    delivery_date = Column(Date, nullable=True)                  # Leistungsdatum
    due_date = Column(Date, nullable=True)

    tax_kind = Column(String(20), nullable=False, default="normal")
    # Getrennt von tax_kind: Ob die Vorsteuer abziehbar ist, entscheidet
    # § 12 UStG (PKW, Repräsentation …) — das ist unabhängig davon, ob es sich
    # um einen Inlandsbezug oder einen innergemeinschaftlichen Erwerb handelt.
    vat_deductible = Column(Boolean, nullable=False, default=True)
    vat_note = Column(String(300), nullable=True)                # Begründung, wenn nicht abziehbar

    account_nr = Column(String(20), nullable=True)               # Aufwandskonto
    title = Column(String(300), nullable=True)
    note = Column(Text, nullable=True)

    net_total = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    tax_total = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    gross_total = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    currency = Column(String(3), nullable=False, default="EUR")

    status = Column(String(20), nullable=False, default="offen")
    paid_at = Column(Date, nullable=True)
    paid_amount = Column(Numeric(12, 2), nullable=True)

    # Original im Objektspeicher — nach § 132 BAO sieben Jahre aufzubewahren.
    file_key = Column(String(500), nullable=True)
    file_name = Column(String(300), nullable=True)
    file_mimetype = Column(String(100), nullable=True)
    # Speicher, in dem das Original liegt — im Mischbetrieb unverzichtbar.
    # NULL = unbekannt, dann gilt der aktive Speicher.
    file_provider = Column(String(20), nullable=True)

    created_by = Column(String(200), nullable=True)
    updated_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    taxes = relationship("PurchaseInvoiceTax", back_populates="invoice",
                         cascade="all, delete-orphan",
                         order_by="PurchaseInvoiceTax.sort_order")
    payments = relationship("PurchasePayment", back_populates="invoice",
                            cascade="all, delete-orphan",
                            order_by="PurchasePayment.paid_at")


class PurchaseInvoiceTax(Base):
    """
    Eine Steuerzeile: Nettobetrag und Steuerbetrag zu einem Satz.

    Der Steuerbetrag wird **erfasst, nicht gerechnet**. Auf der Rechnung des
    Lieferanten steht ein bestimmter Betrag; weicht er um einen Cent von
    unserer Rundung ab, gilt trotzdem seiner — sonst stimmt die Buchung nicht
    mit dem Beleg überein, und genau das prüft eine Betriebsprüfung.
    """
    __tablename__ = "purchase_invoice_taxes"
    # Indizes/Constraints mit den Namen aus den Migrationen (Audit DATA-004):
    # Modelle und Produktionsschema müssen deckungsgleich sein, damit die
    # Tests dasselbe Schema prüfen wie der Betrieb (tests/test_migrationen.py).
    __table_args__ = (
        Index('ix_purchase_invoice_taxes_beleg', 'purchase_invoice_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_invoice_id = Column(UUID(as_uuid=True),
                                 ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
                                 nullable=False)
    tax_rate = Column(Numeric(5, 2), nullable=True)      # None = kein Satz (Reverse Charge)
    net_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    tax_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    sort_order = Column(Integer, nullable=False, default=0)

    invoice = relationship("PurchaseInvoice", back_populates="taxes")


class PurchasePayment(Base):
    """Ein Zahlungsausgang. Aufbau wie ``InvoicePayment`` auf der Verkaufsseite."""
    __tablename__ = "purchase_payments"
    # Indizes/Constraints mit den Namen aus den Migrationen (Audit DATA-004):
    # Modelle und Produktionsschema müssen deckungsgleich sein, damit die
    # Tests dasselbe Schema prüfen wie der Betrieb (tests/test_migrationen.py).
    __table_args__ = (
        Index('ix_purchase_payments_beleg', 'purchase_invoice_id'),
        Index('ix_purchase_payments_datum', 'paid_at'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_invoice_id = Column(UUID(as_uuid=True),
                                 ForeignKey("purchase_invoices.id", ondelete="CASCADE"),
                                 nullable=False)
    paid_at = Column(Date, nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    # bank | bar | karte | lastschrift | verrechnung | sonstige
    method = Column(String(20), nullable=True)
    reference = Column(String(200), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invoice = relationship("PurchaseInvoice", back_populates="payments")
