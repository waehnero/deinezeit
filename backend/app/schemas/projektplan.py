"""
Pydantic-Schemas für das Projekt-Aufzeichnungstool.
"""
from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ── Meilensteine ──────────────────────────────────────────────────────────────
class MilestoneBase(BaseModel):
    title: str
    due_date: Optional[date] = None
    is_reached: bool = False
    color: Optional[str] = None
    sort_order: int = 0


class MilestoneCreate(MilestoneBase):
    pass


class MilestoneUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[date] = None
    is_reached: Optional[bool] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


class MilestoneResponse(MilestoneBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    created_at: Optional[datetime] = None


# ── Abhängigkeiten ────────────────────────────────────────────────────────────
class DependencyCreate(BaseModel):
    predecessor_id: UUID
    successor_id: UUID
    dep_type: str = Field(default="FS", pattern="^(FS|SS|FF|SF)$")
    lag_days: int = 0


class DependencyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    predecessor_id: UUID
    successor_id: UUID
    dep_type: str
    lag_days: int


# ── Checklisten ───────────────────────────────────────────────────────────────
class ChecklistItemCreate(BaseModel):
    text: str
    sort_order: int = 0


class ChecklistItemUpdate(BaseModel):
    text: Optional[str] = None
    is_done: Optional[bool] = None
    sort_order: Optional[int] = None


class ChecklistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    parent_type: str
    parent_id: UUID
    text: str
    is_done: bool
    sort_order: int
    assignee_user_id: Optional[UUID] = None
    assignee_contact_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    linked_task_id: Optional[UUID] = None


class ChecklistAssign(BaseModel):
    """Zuweisung eines Elements an Benutzer ODER Kontakt + E-Mail-Versand."""
    assignee_user_id: Optional[UUID] = None
    assignee_contact_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    email: Optional[str] = None          # Ziel-E-Mail (bei Kontakt ohne hinterlegte Mail)
    send_email: bool = True

    @field_validator("assignee_user_id", "assignee_contact_id", mode="before")
    @classmethod
    def _empty_to_none(cls, v):
        # Leerer String "" aus dem Frontend -> None (sonst UUID-Validierungsfehler/422)
        if v in ("", None):
            return None
        return v


# ── Aufgaben ──────────────────────────────────────────────────────────────────
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "offen"
    priority: str = "mittel"
    assignee_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    estimate_minutes: Optional[int] = None
    progress: int = 0
    is_milestone: bool = False
    sort_order: int = 0
    data: dict = Field(default_factory=dict)


class TaskCreate(TaskBase):
    parent_task_id: Optional[UUID] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[UUID] = None
    assignee_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    estimate_minutes: Optional[int] = None
    progress: Optional[int] = None
    is_milestone: Optional[bool] = None
    sort_order: Optional[int] = None
    parent_task_id: Optional[UUID] = None
    data: Optional[dict] = None


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    project_id: UUID
    parent_task_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    # Ist-Stunden (aus verknüpften TimeEntries summiert, vom Endpoint gefüllt)
    logged_minutes: int = 0
    # Liegt die Aufgabe auf dem kritischen Pfad? (vom Endpoint berechnet)
    is_critical: bool = False
    # Rekursive Kinder – beliebig tief.
    # Wird vom Endpoint (_build_tree) befüllt. Die SQLAlchemy-Relationship gleichen
    # Namens kann beim model_validate None liefern -> hier robust zu [] normalisieren.
    children: List["TaskResponse"] = Field(default_factory=list)
    # Checklisten-Elemente dieser Aufgabe (vom Endpoint befüllt)
    checklist: List["ChecklistItemResponse"] = Field(default_factory=list)

    @field_validator("children", mode="before")
    @classmethod
    def _children_default(cls, v):
        return v or []

    @field_validator("checklist", mode="before")
    @classmethod
    def _checklist_default(cls, v):
        return v or []


# ── Projekte ──────────────────────────────────────────────────────────────────
class PlanningProjectBase(BaseModel):
    name: str
    description: Optional[str] = None
    masterdata_project_id: Optional[UUID] = None
    masterdata_project_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    status: str = "offen"
    color: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class PlanningProjectCreate(PlanningProjectBase):
    pass


class PlanningProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    masterdata_project_id: Optional[UUID] = None
    masterdata_project_name: Optional[str] = None
    contact_id: Optional[UUID] = None
    contact_name: Optional[str] = None
    status: Optional[str] = None
    color: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_archived: Optional[bool] = None


class PlanningProjectListItem(PlanningProjectBase):
    """Schlanke Übersicht (ohne Aufgabenbaum) – für die Projektliste."""
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    is_archived: bool = False
    created_at: Optional[datetime] = None
    # Aggregierte Kennzahlen (vom Endpoint gefüllt)
    task_count: int = 0
    done_count: int = 0
    progress_percent: int = 0


class PlanningProjectDetail(PlanningProjectListItem):
    """Vollständiges Projekt inkl. Aufgabenbaum und Meilensteine."""
    origin_task_id: Optional[UUID] = None
    tasks: List[TaskResponse] = Field(default_factory=list)
    milestones: List[MilestoneResponse] = Field(default_factory=list)
    # Checkliste auf Projektebene
    checklist: List[ChecklistItemResponse] = Field(default_factory=list)
    # Abhängigkeiten (für Gantt-Verbindungslinien)
    dependencies: List[DependencyResponse] = Field(default_factory=list)


# ── Termin-Batch-Update (Gantt-Drag) ──────────────────────────────────────────
class TaskDateUpdate(BaseModel):
    id: UUID
    start_date: Optional[date] = None
    due_date: Optional[date] = None


class TaskDatesBatch(BaseModel):
    updates: List[TaskDateUpdate] = Field(default_factory=list)

# ── Konfigurierbare Aufgaben-Felder ───────────────────────────────────────────
class TaskFieldBase(BaseModel):
    name: str
    field_type: str
    is_required: bool = False
    show_in_list: bool = True
    sort_order: int = 0
    col_span: int = 12
    options: Optional[list] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None


class TaskFieldCreate(TaskFieldBase):
    pass


class TaskFieldUpdate(BaseModel):
    name: Optional[str] = None
    field_type: Optional[str] = None
    is_required: Optional[bool] = None
    show_in_list: Optional[bool] = None
    sort_order: Optional[int] = None
    col_span: Optional[int] = None
    options: Optional[list] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None


class TaskFieldResponse(TaskFieldBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    key: str


# ── Projekt-Einstellungen (Tags, Status, Prioritäten) ─────────────────────────
class StatusOption(BaseModel):
    value: str
    label: str
    color: Optional[str] = None


class ProjektplanSettings(BaseModel):
    """Frei konfigurierbare Listen für das Projektmodul."""
    statuses: List[StatusOption] = Field(default_factory=list)
    priorities: List[StatusOption] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


# ── Aktion: Aufgabe -> Detailprojekt ──────────────────────────────────────────
class PromoteTaskToProject(BaseModel):
    """Erzeugt aus einer Aufgabe ein neues Planungsprojekt (lose Kopplung)."""
    name: Optional[str] = None              # Default: Aufgaben-Titel
    move_subtasks: bool = True              # Teilaufgaben als Aufgaben übernehmen
    link_back: bool = True                  # origin_task_id setzen


# ── Aktion: Projekt duplizieren ───────────────────────────────────────────────
class DuplicateProject(BaseModel):
    """
    Dupliziert ein Projekt. Über die Flags steuerbar, wie viel an
    'verdichteter Information' mitkopiert wird.
    """
    name: Optional[str] = None              # Default: "<Name> (Kopie)"
    include_tasks: bool = True              # Aufgaben + Teilaufgaben mitkopieren
    include_milestones: bool = True         # Meilensteine mitkopieren
    include_field_values: bool = True       # eigene Feldwerte + Tags der Aufgaben
    include_assignees: bool = True          # Verantwortliche übernehmen
    include_dates: bool = True              # Termine (Start/Fällig) übernehmen
    reset_status: bool = False              # alle Aufgaben auf "offen"/0% zurücksetzen
