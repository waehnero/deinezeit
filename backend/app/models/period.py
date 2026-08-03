import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.db.base import Base


class AccountingPeriod(Base):
    """
    Ein abgeschlossener Kalendermonat.

    Solange kein Eintrag existiert, ist der Monat offen — es wird also nichts
    im Voraus angelegt, ein Monat entsteht erst durch seinen Abschluss.

    Nach dem Abschluss sind Belege mit Datum in diesem Monat gesperrt: weder
    neue Belege noch Änderungen an vorhandenen. Ohne diese Sperre stimmen die
    an die Steuerberatung übergebenen Zahlen schon am nächsten Tag nicht mehr
    mit dem System überein.

    Wiedereröffnen ist möglich, aber nur mit Begründung — und der Vorgang
    bleibt sichtbar erhalten statt spurlos rückgängig gemacht zu werden.
    """
    __tablename__ = "accounting_periods"
    __table_args__ = (UniqueConstraint("year", "month", name="uq_accounting_period"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)      # abgeschlossen | wieder_geoeffnet

    closed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(String(200), nullable=True)
    reopened_at = Column(DateTime(timezone=True), nullable=True)
    reopened_by = Column(String(200), nullable=True)
    reopen_reason = Column(String(500), nullable=True)

    # Kennzahlen zum Zeitpunkt des Abschlusses — so lässt sich später erkennen,
    # ob sich seither etwas verschoben hat.
    totals = Column(JSONB, nullable=True)

    @property
    def ist_gesperrt(self) -> bool:
        return self.status == "abgeschlossen"


class PeriodHandover(Base):
    """
    Ein erzeugtes Übergabepaket.

    Hält fest, wer wann welchen Monat übergeben hat, wie viele Dateien das
    Paket enthielt und welche Prüfsumme es hatte. Bei Rückfragen ist damit
    belegbar, was die Steuerberatung tatsächlich bekommen hat.
    """
    __tablename__ = "period_handovers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    year = Column(Integer, nullable=False, index=True)
    month = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    created_by = Column(String(200), nullable=True)
    file_count = Column(Integer, nullable=False, default=0)
    byte_size = Column(Integer, nullable=False, default=0)
    checksum = Column(String(64), nullable=True)      # SHA-256 über das ZIP
    note = Column(String(500), nullable=True)
