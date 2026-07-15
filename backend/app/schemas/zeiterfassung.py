from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Any, Dict
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal


# ── Custom-Felder ─────────────────────────────────────────────────────────────

class TimeEntryFieldBase(BaseModel):
    name: str
    key: str
    field_type: str
    is_required: bool = False
    show_in_list: bool = True
    sort_order: int = 0
    col_span: int = 12
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None


class TimeEntryFieldCreate(TimeEntryFieldBase):
    pass


class TimeEntryFieldUpdate(BaseModel):
    name: Optional[str] = None
    field_type: Optional[str] = None
    is_required: Optional[bool] = None
    show_in_list: Optional[bool] = None
    sort_order: Optional[int] = None
    col_span: Optional[int] = None
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None


class TimeEntryFieldResponse(TimeEntryFieldBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime


class UpdateTimeEntryFieldSortOrders(BaseModel):
    updates: List[Dict[str, Any]]   # [{id, sort_order, col_span}, ...]


# ── Zeiteinträge ──────────────────────────────────────────────────────────────

class TimeEntryCreate(BaseModel):
    project_id: Optional[UUID] = None
    project_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    pause_minutes: int = 0
    note: Optional[str] = None
    billable: bool = True
    data: Dict[str, Any] = {}


class TimeEntryUpdate(BaseModel):
    project_id: Optional[UUID] = None
    project_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    pause_minutes: Optional[int] = None
    note: Optional[str] = None
    billable: Optional[bool] = None
    data: Optional[Dict[str, Any]] = None


class TimeEntryStop(BaseModel):
    ended_at: datetime
    pause_minutes: int = 0
    note: Optional[str] = None


class UserInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    full_name: str
    email: str


class TimeEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    user: Optional[UserInfo] = None
    project_id: Optional[UUID] = None
    project_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    pause_minutes: int
    note: Optional[str] = None
    billable: bool
    data: Dict[str, Any]
    is_running: bool
    duration_minutes: int
    status: str = "veraenderbar"
    created_at: datetime
    updated_at: datetime


class TimeEntryStatusUpdate(BaseModel):
    """Statuswechsel eines Zeiteintrags (veraenderbar/gesperrt/freigegeben/abgerechnet)."""
    status: str


class TimeEntryStatusBatch(BaseModel):
    """Statuswechsel für mehrere Zeiteinträge auf einmal."""
    entry_ids: List[UUID]
    status: str


class TimeEntryListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[TimeEntryResponse]


class TimeStats(BaseModel):
    today_minutes: int
    week_minutes: int
    month_minutes: int
    today_billable_minutes: int  # Davon verrechenbar
    week_billable_minutes: int
    month_billable_minutes: int
    today_target_minutes: int    # Soll-Stunden (Standard: 8h)
    week_target_minutes: int     # Soll-Stunden (Standard: 40h)
    month_target_minutes: int    # Soll-Stunden (Standard: 160h)


# ── Stundenkonten / Projekt-Budget ────────────────────────────────────────────

class StundenkontoCreate(BaseModel):
    bezeichnung: Optional[str] = None
    stunden: Decimal = Field(gt=0)          # erworbene Stunden
    preis: Optional[Decimal] = None         # optionaler Kaufpreis (netto)
    erworben_am: date
    notiz: Optional[str] = None


class StundenkontoUpdate(BaseModel):
    bezeichnung: Optional[str] = None
    stunden: Optional[Decimal] = Field(default=None, gt=0)
    preis: Optional[Decimal] = None
    erworben_am: Optional[date] = None
    notiz: Optional[str] = None


class StundenkontoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    bezeichnung: Optional[str] = None
    stunden: Decimal
    preis: Optional[Decimal] = None
    erworben_am: date
    notiz: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class KiNachtragenRequest(BaseModel):
    """Transkript einer Sprachaufnahme zum Nachtragen einer Projektzeit."""
    transcript: str = Field(min_length=3, max_length=5000)


class KiNachtragenResponse(BaseModel):
    """Von der KI extrahierter Vorschlag — wird im Dialog zur Kontrolle angezeigt."""
    transcript: str
    project_id: Optional[UUID] = None      # gesetzt, wenn Projektzeit gefunden
    project_name: Optional[str] = None     # Name aus den Stammdaten (oder gesprochener Name)
    contact_name: Optional[str] = None     # Kontakt der gefundenen Projektzeit
    date: Optional[str] = None             # YYYY-MM-DD
    end_date: Optional[str] = None         # YYYY-MM-DD (falls über Mitternacht)
    start_time: Optional[str] = None       # HH:MM
    end_time: Optional[str] = None         # HH:MM
    pause_minutes: int = 0
    note: Optional[str] = None
    billable: bool = True
    warnings: List[str] = []               # z.B. "Projektzeit 'X' nicht gefunden"


class ProjectBudget(BaseModel):
    """Budget-Stand einer Projektzeit (Budget = Summe der Stundenkonten,
    Verbrauch = verrechenbare Zeiteinträge)."""
    project_id: UUID
    has_budget: bool                 # False = keine Stundenkonten erfasst
    budget_minutes: int              # Summe erworbener Stunden in Minuten
    consumed_minutes: int            # verbraucht (nur verrechenbar, abgeschlossene Einträge)
    remaining_minutes: int           # Rest (kann negativ werden)
    exhausted: bool                  # True = Budget aufgebraucht → neues Stundenkonto anbieten
    konten_count: int
