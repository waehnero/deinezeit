"""
Pydantic-Schemas für das Aufgabenmodul (zentrale To-do-Liste).
"""
from datetime import date, datetime, time
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.projektplan import StatusOption


# ── Aufgaben ──────────────────────────────────────────────────────────────────
class TodoBase(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: Optional[str] = None
    status: str = "offen"
    priority: str = "mittel"
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    assignee_id: Optional[UUID] = None
    # Lose Verknüpfungen
    planning_project_id: Optional[UUID] = None
    planning_task_id: Optional[UUID] = None
    time_entry_id: Optional[UUID] = None
    record_id: Optional[UUID] = None
    sort_order: int = 0
    data: dict = Field(default_factory=dict)


class TodoCreate(TodoBase):
    pass


class TodoUpdate(BaseModel):
    """Alle Felder optional — nur übermittelte Felder werden geändert."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    assignee_id: Optional[UUID] = None
    planning_project_id: Optional[UUID] = None
    planning_task_id: Optional[UUID] = None
    time_entry_id: Optional[UUID] = None
    record_id: Optional[UUID] = None
    sort_order: Optional[int] = None
    data: Optional[dict] = None
    is_archived: Optional[bool] = None


class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    due_time: Optional[time] = None
    completed_at: Optional[datetime] = None
    assignee_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    planning_project_id: Optional[UUID] = None
    planning_project_name: Optional[str] = None
    planning_task_id: Optional[UUID] = None
    planning_task_title: Optional[str] = None
    time_entry_id: Optional[UUID] = None
    record_id: Optional[UUID] = None
    record_name: Optional[str] = None
    record_type_slug: Optional[str] = None
    source: str
    source_meta: Optional[dict] = None
    sort_order: int
    data: dict
    is_archived: bool
    created_by: Optional[UUID] = None
    created_by_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Einstellungen (konfigurierbare Status/Prioritäten) ────────────────────────
class AufgabenSettings(BaseModel):
    """Frei konfigurierbare Listen für das Aufgabenmodul."""
    statuses: List[StatusOption] = Field(default_factory=list)
    priorities: List[StatusOption] = Field(default_factory=list)
    # Welcher Status-Wert gilt als "erledigt" (steuert completed_at + Filter)
    done_status: str = "erledigt"


# ── Dashboard-Statistik ───────────────────────────────────────────────────────
class AufgabenStatItem(BaseModel):
    """Kompakte Aufgabe für das Dashboard-Widget."""
    id: UUID
    title: str
    due_date: Optional[date] = None
    status: str
    priority: str
    ueberfaellig: bool = False


class AufgabenStats(BaseModel):
    """Zähler + nächste fällige Aufgaben für das Dashboard."""
    offen_gesamt: int
    heute_faellig: int
    ueberfaellig: int
    naechste: List[AufgabenStatItem] = Field(default_factory=list)
