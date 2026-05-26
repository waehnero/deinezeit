from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Any, Dict
from uuid import UUID
from datetime import datetime


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
    created_at: datetime
    updated_at: datetime


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
