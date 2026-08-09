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
    # Nummer, Jahr und laufende Nummer werden erst beim Finalisieren vergeben
    # (Beleg verlässt 'entwurf'). Entwürfe bleiben nummernlos, damit ein
    # verworfener Entwurf keine Lücke im Nummernkreis hinterlässt
    # (§ 11 Abs. 1 Z 3 UStG / § 131 BAO). NULL ist vom UNIQUE-Index ausgenommen.
    number = Column(String(50), nullable=True, unique=True)
    year = Column(Integer, nullable=True)
    sequence = Column(Integer, nullable=True)

    # Bezüge
    contact_id = Column(UUID(as_uuid=True), nullable=True)          # entity_records.id
    project_id = Column(UUID(as_uuid=True), nullable=True)          # entity_records.id
    related_invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)

    # Eingefrorene Empfängerdaten (DSGVO / Belegaufbewahrung):
    # {"display_name": ..., "data": {...}, "frozen_at": ..., "source": ...}
    # Wird beim Finalisieren gesetzt (Status verlässt 'entwurf'). PDF/Vorschau
    # rendern ab dann aus dem Snapshot statt live aus den Stammdaten.
    recipient_snapshot = Column(JSONB, nullable=True)

    # Inhalte
    title = Column(String(300), nullable=True)
    date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=True)
    # Liefer-/Leistungsdatum (Pflichtangabe § 11 Abs. 1 Z 4 UStG). Ist
    # delivery_date_to gesetzt, handelt es sich um einen Leistungszeitraum
    # von delivery_date bis delivery_date_to — nötig für Zeitabrechnung
    # und Wartungsverträge.
    delivery_date = Column(Date, nullable=True)
    delivery_date_to = Column(Date, nullable=True)
    # Bindefrist des Angebots. Ob es abgelaufen ist, wird aus dem Datum
    # abgeleitet und nicht als Status gespeichert: „abgelaufen" und „abgelehnt"
    # sind zwei verschiedene Dinge, und der Unterschied wird für die
    # Angebotsverfolgung gebraucht.
    valid_until = Column(Date, nullable=True)
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

    # Status: entwurf | gesendet | offen | teilbezahlt | bezahlt | ueberfaellig
    #         | storniert | angenommen | abgelehnt
    status = Column(String(30), nullable=False, default="entwurf")
    cancel_mode = Column(String(20), nullable=True)         # status_only | with_credit
    # Abgeleitet aus invoice_payments: Datum der letzten Zahlung und Summe
    # aller Zahlungen. Bewusst als Zwischenspeicher am Beleg belassen, damit
    # PDF, Export und DSGVO-Auswertung unverändert weiterarbeiten.
    paid_at = Column(Date, nullable=True)
    paid_amount = Column(Numeric(12, 2), nullable=True)

    # Skonto-Bedingung: "skonto_percent % bei Zahlung binnen skonto_days Tagen".
    # Am Beleg gespeichert und nicht nur als Einstellung, weil die Bedingung
    # Teil der Vereinbarung mit dem Kunden ist — sie darf sich nicht rückwirkend
    # ändern, wenn die Vorgabe später angepasst wird.
    skonto_percent = Column(Numeric(5, 2), nullable=True)
    skonto_days = Column(Integer, nullable=True)

    # Mahnwesen. Stufe und Datum sind Zwischenspeicher aus invoice_dunnings,
    # damit Listen und Mahnlauf nicht je Beleg die Historie laden müssen.
    dunning_blocked = Column(Boolean, nullable=False, default=False)
    dunning_block_reason = Column(String(300), nullable=True)
    dunning_level = Column(Integer, nullable=False, default=0)
    dunning_last_at = Column(Date, nullable=True)

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
    payments = relationship("InvoicePayment", back_populates="invoice",
                            cascade="all, delete-orphan",
                            order_by="InvoicePayment.paid_at")
    dunnings = relationship("InvoiceDunning", back_populates="invoice",
                            cascade="all, delete-orphan",
                            order_by="InvoiceDunning.level")
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

    # Erlöskonto dieser Position (überschreibt das Standard-Erlöskonto beim
    # Buchhaltungs-Export). Die Spalte existiert seit Migration 0013, fehlte
    # aber im Modell — dadurch scheiterte der BMD-Export mit AttributeError.
    account_nr = Column(String(20), nullable=True)

    # Bild zur Position. Der Speicher-Schlüssel steht hier und nicht in einer
    # eigenen Tabelle, weil Positionen beim Speichern gelöscht und neu angelegt
    # werden — sie haben keine dauerhafte Kennung, an der ein Anhang hinge.
    image_key = Column(String(500), nullable=True)
    image_size = Column(String(10), nullable=True)      # klein | mittel | gross
    # In welchem Speicher die Datei liegt (minio | onedrive | webdav …).
    # Ohne diese Angabe wird im Mischbetrieb am falschen Ort gesucht: Nach
    # einem Wechsel auf OneDrive liegen ältere Bilder weiter in MinIO.
    # NULL = unbekannt, dann gilt der aktive Speicher (bisheriges Verhalten).
    image_provider = Column(String(20), nullable=True)

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


class InvoicePayment(Base):
    """
    Ein Zahlungseingang zu einem Beleg.

    Ersetzt die früheren Einzelfelder ``paid_at``/``paid_amount``, mit denen
    genau eine Zahlung abbildbar war — Teilzahlung, Ratenzahlung, Überzahlung
    und selbst die Korrektur eines Tippfehlers im Zahldatum waren unmöglich.
    """
    __tablename__ = "invoice_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True),
                        ForeignKey("invoices.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    paid_at = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    # zahlung | skonto
    #
    # Ein gewährter Skonto schließt den Beleg wie eine Zahlung, ist aber keine:
    # Er mindert das Entgelt und zieht eine Umsatzsteuer-Berichtigung nach
    # § 16 UStG nach sich — und zwar im Monat der Zahlung, nicht im Monat der
    # Rechnung. Buchhaltung und UVA müssen ihn deshalb erkennen können.
    payment_type = Column(String(20), nullable=False, default="zahlung")
    # bank | bar | karte | lastschrift | verrechnung | sonstige
    method = Column(String(20), nullable=True)
    reference = Column(String(200), nullable=True)   # Verwendungszweck, Beleg-Nr. der Bank
    note = Column(String(500), nullable=True)
    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="payments")


class InvoiceDunning(Base):
    """
    Eine verschickte Mahnung zu einem Beleg.

    **Alle Beträge sind eingefroren.** Offener Betrag, Gebühr und Zinsen halten
    den Stand zum Mahnzeitpunkt fest — eine Woche später eintreffende
    Teilzahlung darf nicht rückwirkend verändern, was im Schreiben stand.

    Gebühr und Zinsen sind Schadenersatz und **nicht umsatzsteuerbar**. Sie
    stehen deshalb bewusst hier und nicht als Belegposition: Eine Position
    landete im Erlös, in der UVA und im Buchungsjournal und würde die
    Umsatzsteuer verfälschen.
    """
    __tablename__ = "invoice_dunnings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True),
                        ForeignKey("invoices.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    level = Column(Integer, nullable=False)              # 1 = Zahlungserinnerung, 2 = 1. Mahnung …
    label = Column(String(100), nullable=True)           # Bezeichnung der Stufe zum Zeitpunkt
    dunned_at = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=True)               # gesetzte Nachfrist
    open_amount = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    fee = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    interest = Column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    interest_rate = Column(Numeric(6, 3), nullable=True)  # verwendeter Jahreszinssatz
    interest_days = Column(Integer, nullable=True)
    # Sammelmahnung: mehrere Belege eines Kunden auf einem Schreiben teilen
    # sich eine batch_id.
    batch_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    sent_to = Column(String(300), nullable=True)
    note = Column(String(500), nullable=True)
    created_by = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    invoice = relationship("Invoice", back_populates="dunnings")


class InvoiceAuditLog(Base):
    """
    Änderungsprotokoll je Beleg (Nachvollziehbarkeit / § 131 BAO).

    Eine Zeile je Vorgang. Die einzelnen Feldänderungen liegen als JSONB in
    ``changes`` im Format ``{"feld": {"alt": ..., "neu": ...}, ...}``.
    Aufbau bewusst analog zu :class:`GdprDeletionLog`.

    Protokolliert wird ab dem Finalisieren — an einem Entwurf wird
    naturgemäß laufend gearbeitet, das erzeugt nur Rauschen.
    """
    __tablename__ = "invoice_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True),
                        ForeignKey("invoices.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    # finalisiert | status | bezahlt | zahlung | skonto | mahnung | storniert
    # | bearbeitet | nummer | archiviert
    action = Column(String(30), nullable=False)
    changes = Column(JSONB, nullable=True)
    note = Column(String(500), nullable=True)
    changed_by = Column(String(200), nullable=True)
    changed_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))


class InvoiceSettings(Base):
    """Key-Value-Store für Rechnungseinstellungen (Bankdaten, Texte, Steuersätze)."""
    __tablename__ = "invoice_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(JSONB, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
