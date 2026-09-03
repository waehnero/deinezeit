import uuid
from datetime import datetime, timezone
from sqlalchemy import Index, Column, String, BigInteger, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class Attachment(Base):
    __tablename__ = "attachments"
    # Indizes/Constraints mit den Namen aus den Migrationen (Audit DATA-004):
    # Modelle und Produktionsschema müssen deckungsgleich sein, damit die
    # Tests dasselbe Schema prüfen wie der Betrieb (tests/test_migrationen.py).
    __table_args__ = (
        Index('ix_attachments_contact', 'contact_id'),
        Index('ix_attachments_entity', 'entity_type', 'entity_id'),
        Index('ix_attachments_folder', 'folder'),
        Index('ix_attachments_share_token', 'share_token'),
    )

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type   = Column(String(50),  nullable=False)   # kontakt | projekt | zeiterfassung
    entity_id     = Column(UUID(as_uuid=True), nullable=False)
    type          = Column(String(20),  nullable=False)   # file | link

    # Für type=file
    storage_key   = Column(String(500), nullable=True)
    # In welchem Speicher liegt die Datei (minio | nextcloud | seadrive | onedrive).
    # Down-/Vorschau nutzen genau diesen Provider (Mischbetrieb-fähig).
    storage_provider = Column(String(20), nullable=True)
    filename      = Column(String(255), nullable=True)
    filesize      = Column(BigInteger,  nullable=True)
    mimetype      = Column(String(255), nullable=True)

    # Für type=link
    link_url      = Column(Text,        nullable=True)
    link_provider = Column(String(50),  nullable=True)

    # Gemeinsam
    display_name  = Column(String(255), nullable=False)
    description   = Column(Text,        nullable=True)

    # Kontaktbezug (EntityRecord aus Stammdaten, denormalisiert).
    # Wird beim Upload aus dem Ursprungs-Datensatz vererbt, nachträglich änderbar.
    contact_id    = Column(UUID(as_uuid=True), nullable=True)
    contact_name  = Column(String(300), nullable=True)

    # Optionaler Unterordner innerhalb des Kontakt-Ordners (z.B. Belegart
    # "Rechnungen" für automatisch archivierte Verkaufsbelege).
    folder        = Column(String(100), nullable=True)

    # Share-Link
    share_token      = Column(String(64),  nullable=True, unique=True)
    share_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Metadaten
    uploaded_by   = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
