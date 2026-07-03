"""
API-Router für das Aufgabenmodul (zentrale To-do-Liste).

Endpunkte:
  GET    /aufgaben/                 Liste mit Filtern (Status, Priorität, Zuweisung,
                                    Fälligkeit von/bis, Volltext, Verknüpfungen)
  POST   /aufgaben/                 Aufgabe anlegen
  GET    /aufgaben/{id}             Einzelne Aufgabe
  PUT    /aufgaben/{id}             Aufgabe ändern (Teil-Update)
  DELETE /aufgaben/{id}             Aufgabe löschen
  GET    /aufgaben/einstellungen    Konfigurierbare Status/Prioritäten lesen
  PUT    /aufgaben/einstellungen    … schreiben (nur Admin)

Verknüpfungs-IDs (Projektplan, Zeiterfassung, Stammdaten) werden beim
Schreiben aufgelöst und die Anzeigenamen denormalisiert gespeichert.
"""
import json
from datetime import date, datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.aufgaben import Todo
from app.models.projektplan import PlanningProject, Task
from app.models.masterdata import EntityRecord
from app.models.settings import Setting
from app.schemas.aufgaben import (
    TodoCreate, TodoUpdate, TodoResponse, AufgabenSettings,
)
from app.schemas.projektplan import StatusOption

router = APIRouter(prefix="/aufgaben", tags=["Aufgaben"])

# Setting-Key für die konfigurierbaren Listen (Status/Prioritäten)
SETTINGS_KEY = "aufgaben_settings"

DEFAULT_SETTINGS = AufgabenSettings(
    statuses=[
        StatusOption(value="offen", label="Offen", color="#6b7280"),
        StatusOption(value="in_arbeit", label="In Arbeit", color="#3b82f6"),
        StatusOption(value="wartet", label="Wartet", color="#f59e0b"),
        StatusOption(value="erledigt", label="Erledigt", color="#22c55e"),
    ],
    priorities=[
        StatusOption(value="niedrig", label="Niedrig", color="#9ca3af"),
        StatusOption(value="mittel", label="Mittel", color="#6b7280"),
        StatusOption(value="hoch", label="Hoch", color="#f59e0b"),
        StatusOption(value="kritisch", label="Kritisch", color="#ef4444"),
    ],
    done_status="erledigt",
)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def _load_settings(db: Session) -> AufgabenSettings:
    row = db.query(Setting).filter(Setting.key == SETTINGS_KEY).first()
    if not row or not row.value:
        return DEFAULT_SETTINGS
    try:
        s = AufgabenSettings(**json.loads(row.value))
        # Bestands-Einstellungen: leere Listen mit Defaults auffüllen
        if not s.statuses:
            s.statuses = DEFAULT_SETTINGS.statuses
        if not s.priorities:
            s.priorities = DEFAULT_SETTINGS.priorities
        return s
    except Exception:
        return DEFAULT_SETTINGS


def _resolve_links(db: Session, todo: Todo, fields: set):
    """
    Löst Verknüpfungs-IDs auf und pflegt die denormalisierten Namen.
    `fields` = Menge der im Request tatsächlich übermittelten Feldnamen.
    """
    if "assignee_id" in fields:
        if todo.assignee_id:
            user = db.query(User).filter(User.id == todo.assignee_id).first()
            if not user:
                raise HTTPException(404, "Zugewiesener Benutzer nicht gefunden")
            todo.assignee_name = user.full_name
        else:
            todo.assignee_name = None

    if "planning_project_id" in fields:
        if todo.planning_project_id:
            proj = db.query(PlanningProject).filter(
                PlanningProject.id == todo.planning_project_id).first()
            if not proj:
                raise HTTPException(404, "Planungsprojekt nicht gefunden")
            todo.planning_project_name = proj.name
        else:
            todo.planning_project_name = None

    if "planning_task_id" in fields:
        if todo.planning_task_id:
            task = db.query(Task).filter(Task.id == todo.planning_task_id).first()
            if not task:
                raise HTTPException(404, "Projektplan-Aufgabe nicht gefunden")
            todo.planning_task_title = task.title
            # Projekt der Aufgabe mitziehen, wenn keines explizit gesetzt wurde
            if not todo.planning_project_id:
                todo.planning_project_id = task.project_id
                proj = db.query(PlanningProject).filter(
                    PlanningProject.id == task.project_id).first()
                todo.planning_project_name = proj.name if proj else None
        else:
            todo.planning_task_title = None

    if "record_id" in fields:
        if todo.record_id:
            rec = db.query(EntityRecord).filter(EntityRecord.id == todo.record_id).first()
            if not rec:
                raise HTTPException(404, "Stammdaten-Datensatz nicht gefunden")
            todo.record_name = rec.display_name
            todo.record_type_slug = rec.entity_type.slug if rec.entity_type else None
        else:
            todo.record_name = None
            todo.record_type_slug = None


def _apply_done_status(db: Session, todo: Todo):
    """Setzt/entfernt completed_at je nach konfiguriertem Erledigt-Status."""
    done_status = _load_settings(db).done_status
    if todo.status == done_status:
        if not todo.completed_at:
            todo.completed_at = datetime.now(timezone.utc)
    else:
        todo.completed_at = None


# ── Aufgaben CRUD ─────────────────────────────────────────────────────────────
@router.get("/", response_model=List[TodoResponse])
def list_todos(
    status: Optional[str] = Query(None, description="Kommagetrennte Status-Werte"),
    priority: Optional[str] = Query(None, description="Kommagetrennte Prioritäten"),
    assignee_id: Optional[UUID] = None,
    mine: bool = Query(False, description="Nur mir zugewiesene oder von mir erstellte"),
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
    q: Optional[str] = Query(None, description="Volltext in Titel/Beschreibung"),
    planning_project_id: Optional[UUID] = None,
    planning_task_id: Optional[UUID] = None,
    record_id: Optional[UUID] = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Todo)
    if not include_archived:
        query = query.filter(Todo.is_archived.is_(False))
    if status:
        query = query.filter(Todo.status.in_([s.strip() for s in status.split(",") if s.strip()]))
    if priority:
        query = query.filter(Todo.priority.in_([p.strip() for p in priority.split(",") if p.strip()]))
    if assignee_id:
        query = query.filter(Todo.assignee_id == assignee_id)
    if mine:
        query = query.filter(or_(Todo.assignee_id == current_user.id,
                                 Todo.created_by == current_user.id))
    if due_from:
        query = query.filter(Todo.due_date >= due_from)
    if due_to:
        query = query.filter(Todo.due_date <= due_to)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Todo.title.ilike(like), Todo.description.ilike(like)))
    if planning_project_id:
        query = query.filter(Todo.planning_project_id == planning_project_id)
    if planning_task_id:
        query = query.filter(Todo.planning_task_id == planning_task_id)
    if record_id:
        query = query.filter(Todo.record_id == record_id)

    rows = query.order_by(Todo.sort_order, Todo.due_date.nullslast(),
                          Todo.created_at.desc()).all()
    return rows


@router.post("/", response_model=TodoResponse, status_code=201)
def create_todo(
    body: TodoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    todo = Todo(**body.model_dump())
    todo.created_by = current_user.id
    todo.created_by_name = current_user.full_name
    _resolve_links(db, todo, set(body.model_dump().keys()))
    _apply_done_status(db, todo)
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@router.get("/einstellungen", response_model=AufgabenSettings)
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _load_settings(db)


@router.put("/einstellungen", response_model=AufgabenSettings)
def update_settings(
    body: AufgabenSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = db.query(Setting).filter(Setting.key == SETTINGS_KEY).first()
    value = json.dumps(body.model_dump())
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Setting(key=SETTINGS_KEY, value=value,
                       updated_at=datetime.now(timezone.utc)))
    db.commit()
    return body


@router.get("/{todo_id}", response_model=TodoResponse)
def get_todo(
    todo_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    return todo


@router.put("/{todo_id}", response_model=TodoResponse)
def update_todo(
    todo_id: UUID,
    body: TodoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(404, "Aufgabe nicht gefunden")

    payload = body.model_dump(exclude_unset=True)
    for key, value in payload.items():
        setattr(todo, key, value)
    _resolve_links(db, todo, set(payload.keys()))
    if "status" in payload:
        _apply_done_status(db, todo)
    todo.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(todo)
    return todo


@router.delete("/{todo_id}", status_code=204)
def delete_todo(
    todo_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        raise HTTPException(404, "Aufgabe nicht gefunden")
    db.delete(todo)
    db.commit()
