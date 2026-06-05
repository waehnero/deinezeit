import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.db.base import Base


class TimeEntryField(Base):
    """
    Definition eines Custom-Feldes für Zeiteinträge.
    Gleiche Logik wie FieldDefinition bei Stammdaten —
    ermöglicht jederzeit neue Felder hinzuzufügen.
    """
    __tablename__ = "time_entry_fields"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    key = Column(String(100), nullable=False, unique=True)
    field_type = Column(String(30), nullable=False)     # text, number, date, dropdown, checkbox, textarea, url
    is_required = Column(Boolean, default=False)
    show_in_list = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    col_span = Column(Integer, default=12)              # 3=25%, 4=33%, 6=50%, 9=75%, 12=100%
    options = Column(JSONB, nullable=True)              # für Dropdown
    placeholder = Column(String(200), nullable=True)
    default_value = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TimeEntry(Base):
    """
    Ein einzelner Zeiteintrag.
    Kernfelder sind fix gespeichert (schnelle Abfragen),
    Custom-Felder liegen im JSONB-Feld 'data'.
    ended_at = NULL bedeutet der Timer läuft gerade.
    """
    __tablename__ = "time_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Benutzer
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Projekt (EntityRecord aus Stammdaten, denormalisiert)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    project_name = Column(String(300), nullable=True)

    # Kontakt (EntityRecord aus Stammdaten, denormalisiert)
    contact_id = Column(UUID(as_uuid=True), nullable=True)
    contact_name = Column(String(300), nullable=True)

    # Kernfelder Zeiterfassung
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)   # NULL = läuft noch
    pause_minutes = Column(Integer, default=0, nullable=False)
    note = Column(Text, nullable=True)
    billable = Column(Boolean, default=True, nullable=False)

    # Custom-Felder (erweiterbar)
    data = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    user = relationship("User", foreign_keys=[user_id], lazy="joined")

    @property
    def is_running(self) -> bool:
        return self.ended_at is None

    @property
    def duration_minutes(self) -> int:
        """Netto-Dauer in Minuten (ohne Pause). 0 wenn noch laufend."""
        if not self.ended_at:
            return 0
        delta = self.ended_at - self.started_at
        return max(0, int(delta.total_seconds() / 60) - self.pause_minutes)
