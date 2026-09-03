import uuid
from datetime import datetime, timezone
from sqlalchemy import Index, Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class GdprDeletionLog(Base):
    """
    Löschprotokoll zur Rechenschaftspflicht (Art. 5 Abs. 2 DSGVO).

    Bewusst OHNE personenbezogene Daten: nur die (nach der Anonymisierung
    bedeutungslose) Datensatz-UUID, Zeitpunkt, ausführender Benutzer und
    die betroffenen Kategorien mit Anzahl.
    """
    __tablename__ = "gdpr_deletion_log"
    # Indizes/Constraints mit den Namen aus den Migrationen (Audit DATA-004):
    # Modelle und Produktionsschema müssen deckungsgleich sein, damit die
    # Tests dasselbe Schema prüfen wie der Betrieb (tests/test_migrationen.py).
    __table_args__ = (
        Index('ix_gdpr_deletion_log_record', 'record_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id = Column(UUID(as_uuid=True), nullable=False)
    executed_by = Column(String(200), nullable=True)     # E-Mail des Admins
    executed_at = Column(DateTime(timezone=True), nullable=False,
                         default=lambda: datetime.now(timezone.utc))
    # z.B. {"time_entries": 12, "invoices_snapshotted": 3, "attachments": 2}
    categories = Column(JSONB, nullable=True)
    files_action = Column(String(20), nullable=True)     # deleted | unlinked | none
    note = Column(String(500), nullable=True)
