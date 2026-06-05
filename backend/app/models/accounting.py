import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class AccountingAccount(Base):
    """Kontenplan-Eintrag (EKR oder benutzerdefiniert)."""
    __tablename__ = "accounting_accounts"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nr          = Column(String(20), nullable=False, unique=True)   # z.B. "4000"
    name        = Column(String(200), nullable=False)
    typ         = Column(String(20), nullable=False)                # aktiv|passiv|ertrag|aufwand|neutral
    ust_code    = Column(String(10), nullable=True)                 # U20|U10|U00|UIG|URC
    beschreibung = Column(Text, nullable=True)
    is_active   = Column(Boolean, nullable=False, default=True)
    is_default_erloes = Column(Boolean, nullable=False, default=False)
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))
