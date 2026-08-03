from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class PeriodResponse(BaseModel):
    jahr: int
    monat: int
    monatsname: str
    status: str                        # offen | abgeschlossen | wieder_geoeffnet
    closed_at: Optional[datetime] = None
    closed_by: Optional[str] = None
    reopened_at: Optional[datetime] = None
    reopened_by: Optional[str] = None
    reopen_reason: Optional[str] = None
    totals: Optional[dict] = None      # Kennzahlen beim Abschluss
    summen: Optional[dict] = None      # Kennzahlen jetzt

    class Config:
        from_attributes = True


class PeriodCheckPunkt(BaseModel):
    schluessel: str
    titel: str
    art: str                           # blockierend | hinweis
    erfuellt: bool
    anzahl: int
    text: str
    belege: List[dict] = []


class PeriodCheckResponse(BaseModel):
    jahr: int
    monat: int
    monatsname: str
    status: str
    abschluss_moeglich: bool
    punkte: List[PeriodCheckPunkt] = []
    summen: dict


class PeriodReopenRequest(BaseModel):
    grund: str


class HandoverResponse(BaseModel):
    id: UUID
    # Feldnamen wie im Modell — sonst greift from_attributes nicht
    year: int
    month: int
    created_at: datetime
    created_by: Optional[str] = None
    file_count: int
    byte_size: int
    checksum: Optional[str] = None
    note: Optional[str] = None

    class Config:
        from_attributes = True
