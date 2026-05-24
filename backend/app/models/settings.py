from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from app.db.base import Base


class Setting(Base):
    __tablename__ = "settings"

    key        = Column(String(100), primary_key=True)
    value      = Column(Text, nullable=False, default='')
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
