import uuid
from datetime import datetime, timezone
from sqlalchemy import Index, Column, String, Boolean, DateTime, Date, Integer, Numeric, Text, ForeignKey
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
    is_required = Column(Boolean, nullable=False, default=False)
    show_in_list = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    col_span = Column(Integer, nullable=False, default=12)              # 3=25%, 4=33%, 6=50%, 9=75%, 12=100%
    options = Column(JSONB, nullable=True)              # für Dropdown
    placeholder = Column(String(200), nullable=True)
    default_value = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class TimeEntry(Base):
    """
    Ein einzelner Zeiteintrag.
    Kernfelder sind fix gespeichert (schnelle Abfragen),
    Custom-Felder liegen im JSONB-Feld 'data'.
    ended_at = NULL bedeutet der Timer läuft gerade.
    """
    __tablename__ = "time_entries"
    # Indizes/Constraints mit den Namen aus den Migrationen (Audit DATA-004):
    # Modelle und Produktionsschema müssen deckungsgleich sein, damit die
    # Tests dasselbe Schema prüfen wie der Betrieb (tests/test_migrationen.py).
    __table_args__ = (
        Index('ix_time_entries_project_id', 'project_id'),
        Index('ix_time_entries_started_at', 'started_at'),
        Index('ix_time_entries_task', 'task_id'),
        Index('ix_time_entries_user_id', 'user_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Benutzer. Bewusst OHNE Löschkaskade (bis Migration 0061 stand hier
    # ondelete="CASCADE"): Ein gelöschter Benutzer darf nicht seine
    # Zeiteinträge mitnehmen — das sind Arbeitszeitnachweise, teils bereits
    # abgerechnet. Benutzer mit Zeiteinträgen werden deaktiviert, nicht
    # gelöscht (api/users.py; Audit DATA-003).
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Projekt (EntityRecord aus Stammdaten, denormalisiert)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    project_name = Column(String(300), nullable=True)

    # Kontakt (EntityRecord aus Stammdaten, denormalisiert)
    contact_id = Column(UUID(as_uuid=True), nullable=True)
    contact_name = Column(String(300), nullable=True)

    # Optionale Verknüpfung zu einer Planungsaufgabe (Projekt-Aufzeichnungstool).
    # Erfasste Zeit fließt so ins Ist/Soll der Aufgabe. NULL = keine Aufgabe.
    task_id = Column(UUID(as_uuid=True), nullable=True)
    task_title = Column(String(500), nullable=True)

    # Kernfelder Zeiterfassung
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)   # NULL = läuft noch
    pause_minutes = Column(Integer, default=0, nullable=False)
    note = Column(Text, nullable=True)
    billable = Column(Boolean, default=True, nullable=False)

    # Abrechnungs-Workflow (Beschluss 2026-07-11):
    #   veraenderbar → gesperrt → freigegeben → abgerechnet
    # Bearbeiten/Löschen nur bei 'veraenderbar'. Mitarbeiter dürfen eigene
    # Einträge nur veraenderbar→freigegeben setzen, alle anderen Wechsel Admin.
    # Unabhängig davon sperrt eine Belegposition (invoice_positions.time_entry_id)
    # den Eintrag immer — zweite, nicht umgehbare Prüfung.
    status = Column(String(20), nullable=False, default="veraenderbar", index=True)

    # Custom-Felder (erweiterbar)
    data = Column(JSONB, nullable=False, default=dict)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
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


class Stundenkonto(Base):
    """
    Vom Kunden im Voraus erworbenes Stundenpaket für ein Zeitprojekt
    (EntityRecord vom Typ 'zeitprojekte').

    Das verfügbare Budget eines Zeitprojekts ergibt sich aus der Summe
    aller seiner Stundenkonten. Verbraucht wird das Budget durch
    verrechenbare Zeiteinträge auf diesem Projekt. Ist es aufgebraucht,
    soll dem Kunden ein neues Stundenkonto angeboten werden.
    """
    __tablename__ = "stundenkonten"
    # Indizes/Constraints mit den Namen aus den Migrationen (Audit DATA-004):
    # Modelle und Produktionsschema müssen deckungsgleich sein, damit die
    # Tests dasselbe Schema prüfen wie der Betrieb (tests/test_migrationen.py).
    __table_args__ = (
        Index('ix_stundenkonten_project', 'project_id'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zeitprojekt (EntityRecord vom Typ 'zeitprojekte')
    # RESTRICT: ein Zeitprojekt mit Stundenkonten darf nicht gelöscht werden —
    # sonst gingen vom Kunden erworbene Stundenpakete kommentarlos verloren.
    project_id = Column(UUID(as_uuid=True),
                        ForeignKey("entity_records.id", ondelete="RESTRICT"),
                        nullable=False)

    bezeichnung = Column(String(300), nullable=True)    # z.B. "Stundenpaket 10h"
    stunden = Column(Numeric(8, 2), nullable=False)     # erworbene Stunden
    preis = Column(Numeric(12, 2), nullable=True)       # optionaler Kaufpreis (netto)
    erworben_am = Column(Date, nullable=False)          # Kaufdatum
    notiz = Column(Text, nullable=True)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
