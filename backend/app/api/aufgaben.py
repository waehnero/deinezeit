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

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.aufgaben import Todo
from app.models.projektplan import PlanningProject, Task
from app.models.masterdata import EntityRecord
from app.models.settings import Setting
from app.schemas.aufgaben import (
    TodoCreate, TodoUpdate, TodoResponse, AufgabenSettings,
    AufgabenStats, AufgabenStatItem,
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


# ── Projektplan-Aufgaben einblenden ───────────────────────────────────────────
# Aufgaben vom Typ "aufgabe" aus dem Projektmodul erscheinen automatisch mit
# in der To-do-Liste (source="projektplan") — OHNE Datenduplizierung: Quelle
# bleibt planning_tasks, Änderungen schreiben direkt dorthin zurück.

def _ist_normale_aufgabe(task: Task) -> bool:
    """Nur echte Aufgaben (kein Meilenstein, kein anderer Typ)."""
    if task.is_milestone:
        return False
    task_type = (task.data or {}).get("task_type") or "aufgabe"
    return task_type == "aufgabe"


def _task_to_response(task: Task, project_name: Optional[str]) -> TodoResponse:
    """Mappt eine Projektplan-Aufgabe auf das TodoResponse-Schema."""
    return TodoResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        start_date=task.start_date,
        due_date=task.due_date,
        due_time=None,
        completed_at=None,
        assignee_id=task.assignee_id,
        assignee_name=task.assignee_name,
        planning_project_id=task.project_id,
        planning_project_name=project_name,
        planning_task_id=None,
        planning_task_title=None,
        time_entry_id=None,
        record_id=task.contact_id,
        record_name=task.contact_name,
        record_type_slug=None,
        source="projektplan",
        source_meta=None,
        sort_order=task.sort_order or 0,
        data=task.data or {},
        is_archived=False,
        created_by=task.created_by,
        created_by_name=None,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _get_planning_task(db: Session, task_id: UUID) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id).first()


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
    include_projektplan: bool = Query(True, description="Projektplan-Aufgaben mit einblenden"),
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
    result = [TodoResponse.model_validate(r) for r in rows]

    # ── Projektplan-Aufgaben einmischen (nur Typ "aufgabe", Projekt aktiv) ────
    # Nicht sinnvoll bei Filtern, die es dort nicht gibt (Verknüpfung auf
    # eine Projektplan-Aufgabe oder einen Zeiterfassungs-/Stammdaten-Bezug
    # über planning_task_id).
    if include_projektplan and not planning_task_id:
        status_set = set(s.strip() for s in status.split(",") if s.strip()) if status else None
        prio_set = set(p.strip() for p in priority.split(",") if p.strip()) if priority else None
        s_lower = q.lower() if q else None

        ptasks = (
            db.query(Task, PlanningProject.name)
            .join(PlanningProject, Task.project_id == PlanningProject.id)
            .filter(PlanningProject.is_archived.is_(False))
            .all()
        )
        for task, proj_name in ptasks:
            if not _ist_normale_aufgabe(task):
                continue
            if status_set and task.status not in status_set:
                continue
            if prio_set and task.priority not in prio_set:
                continue
            if assignee_id and task.assignee_id != assignee_id:
                continue
            if mine and task.assignee_id != current_user.id and task.created_by != current_user.id:
                continue
            if due_from and (not task.due_date or task.due_date < due_from):
                continue
            if due_to and (not task.due_date or task.due_date > due_to):
                continue
            if s_lower and s_lower not in f"{task.title} {task.description or ''}".lower():
                continue
            if planning_project_id and task.project_id != planning_project_id:
                continue
            if record_id and task.contact_id != record_id:
                continue
            result.append(_task_to_response(task, proj_name))

    # Einheitliche Reihung: Fälligkeit (ohne Termin zuletzt), dann Titel
    result.sort(key=lambda r: (r.due_date is None, str(r.due_date or ""), (r.title or "").lower()))
    return result


@router.get("/stats", response_model=AufgabenStats)
def get_stats(
    mine: bool = Query(False, description="Nur mir zugewiesene oder von mir erstellte"),
    limit: int = Query(5, ge=1, le=20, description="Anzahl der nächsten Aufgaben"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard-Statistik: offene Aufgaben, heute fällig, überfällig + nächste Aufgaben.

    Zählt Todos und eingeblendete Projektplan-Aufgaben (Typ "aufgabe",
    Projekt aktiv) — konsistent zur Listenansicht.
    """
    done_status = _load_settings(db).done_status
    heute = date.today()

    # ── Todos ────────────────────────────────────────────────────────────────
    query = db.query(Todo).filter(
        Todo.is_archived.is_(False),
        Todo.status != done_status,
    )
    if mine:
        query = query.filter(or_(Todo.assignee_id == current_user.id,
                                 Todo.created_by == current_user.id))
    offene = [
        {"id": t.id, "title": t.title, "due_date": t.due_date,
         "status": t.status, "priority": t.priority}
        for t in query.all()
    ]

    # ── Projektplan-Aufgaben einmischen ──────────────────────────────────────
    ptasks = (
        db.query(Task)
        .join(PlanningProject, Task.project_id == PlanningProject.id)
        .filter(PlanningProject.is_archived.is_(False))
        .all()
    )
    for task in ptasks:
        if not _ist_normale_aufgabe(task):
            continue
        if task.status == done_status:
            continue
        if mine and task.assignee_id != current_user.id and task.created_by != current_user.id:
            continue
        offene.append({"id": task.id, "title": task.title, "due_date": task.due_date,
                       "status": task.status, "priority": task.priority or "mittel"})

    ueberfaellige = [a for a in offene if a["due_date"] and a["due_date"] < heute]
    heute_faellige = [a for a in offene if a["due_date"] == heute]

    # Nächste Aufgaben: überfällige zuerst, dann nach Fälligkeit (ohne Termin zuletzt)
    sortiert = sorted(offene, key=lambda a: (a["due_date"] is None, str(a["due_date"] or "")))
    naechste = [
        AufgabenStatItem(**a, ueberfaellig=bool(a["due_date"] and a["due_date"] < heute))
        for a in sortiert[:limit]
    ]

    return AufgabenStats(
        offen_gesamt=len(offene),
        heute_faellig=len(heute_faellige),
        ueberfaellig=len(ueberfaellige),
        naechste=naechste,
    )


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
    if todo:
        return todo
    # Fallback: eingeblendete Projektplan-Aufgabe
    task = _get_planning_task(db, todo_id)
    if task:
        proj = db.query(PlanningProject).filter(PlanningProject.id == task.project_id).first()
        return _task_to_response(task, proj.name if proj else None)
    raise HTTPException(404, "Aufgabe nicht gefunden")


@router.get("/{todo_id}/print")
def print_todo(
    todo_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Laufzettel-PDF (A4 hoch): obere Hälfte Aufgabeninfos + QR-Code,
    untere Hälfte 5-mm-Notizraster. Funktioniert auch für eingeblendete
    Projektplan-Aufgaben. Der QR-Code enthält die Aufgaben-URL (mit ID) —
    ein künftiges Belegmodul kann Scans darüber automatisch zuordnen.
    """
    from app.services.aufgaben_pdf import generate_todo_pdf
    from app.models.attachment import Attachment

    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if todo:
        data = TodoResponse.model_validate(todo)
        attachment_entity = "todo"
    else:
        task = _get_planning_task(db, todo_id)
        if not task:
            raise HTTPException(404, "Aufgabe nicht gefunden")
        proj = db.query(PlanningProject).filter(PlanningProject.id == task.project_id).first()
        data = _task_to_response(task, proj.name if proj else None)
        attachment_entity = "planning_task"

    # Firmenname aus Einstellungen -> Allgemein
    firma = db.query(Setting).filter(Setting.key == "company_name").first()
    company_name = (firma.value if firma and firma.value else "DeineZeit")

    # Anzahl der Anhänge (Datacenter, generisch über entity_type/entity_id)
    anhaenge = (db.query(Attachment)
                .filter(Attachment.entity_type == attachment_entity,
                        Attachment.entity_id == todo_id).count())

    einstellungen = _load_settings(db)
    qr_payload = f"{app_settings.FRONTEND_URL.rstrip('/')}/aufgaben?id={todo_id}"
    pdf = generate_todo_pdf(
        data.model_dump(),
        qr_payload,
        [s.model_dump() for s in einstellungen.statuses],
        [p.model_dump() for p in einstellungen.priorities],
        company_name=company_name,
        anhaenge=anhaenge,
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="aufgabe-{str(todo_id)[:8]}.pdf"'},
    )


@router.put("/{todo_id}", response_model=TodoResponse)
def update_todo(
    todo_id: UUID,
    body: TodoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    payload = body.model_dump(exclude_unset=True)

    if not todo:
        # Fallback: eingeblendete Projektplan-Aufgabe — erlaubte Felder
        # direkt auf planning_tasks zurückschreiben.
        task = _get_planning_task(db, todo_id)
        if not task:
            raise HTTPException(404, "Aufgabe nicht gefunden")
        erlaubt = {"title", "description", "status", "priority",
                   "start_date", "due_date", "assignee_id"}
        for key, value in payload.items():
            if key in erlaubt:
                setattr(task, key, value)
        if "assignee_id" in payload:
            if task.assignee_id:
                user = db.query(User).filter(User.id == task.assignee_id).first()
                if not user:
                    raise HTTPException(404, "Zugewiesener Benutzer nicht gefunden")
                task.assignee_name = user.full_name
            else:
                task.assignee_name = None
        if payload.get("status") == "erledigt":
            task.progress = 100
        task.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(task)
        proj = db.query(PlanningProject).filter(PlanningProject.id == task.project_id).first()
        return _task_to_response(task, proj.name if proj else None)

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
    """Aufgabe endgültig löschen.

    Regeln (Bugfix Datenzusammenhänge):
    - Nur Ersteller, Zugewiesener oder Admin.
    - Aufgaben mit verknüpftem Zeiteintrag sind unlöschbar (der Zeiteintrag
      verlöre seinen Aufgabenbezug) — stattdessen archivieren (is_archived).
    """
    todo = db.query(Todo).filter(Todo.id == todo_id).first()
    if not todo:
        if _get_planning_task(db, todo_id):
            raise HTTPException(
                400, "Projektplan-Aufgaben bitte im Modul Projekte löschen")
        raise HTTPException(404, "Aufgabe nicht gefunden")

    from app.models.user import UserRole
    if current_user.role != UserRole.admin and \
            current_user.id not in (todo.created_by, todo.assignee_id):
        raise HTTPException(
            403, "Nur der Ersteller, der Zugewiesene oder ein Admin "
                 "darf diese Aufgabe löschen")

    if todo.time_entry_id:
        raise HTTPException(
            409, "Löschen nicht möglich — die Aufgabe ist mit einem "
                 "Zeiteintrag verknüpft. Bitte stattdessen archivieren.")

    db.delete(todo)
    db.commit()
