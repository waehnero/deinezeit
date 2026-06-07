from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from app.db.base import Base


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    doc_type   = Column(String(50), primary_key=True)
    subject    = Column(Text, nullable=False, default='')
    body_html  = Column(Text, nullable=False, default='')
    updated_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
