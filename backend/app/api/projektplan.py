"""
API-Router für das Projekt-Aufzeichnungstool (Projektplanung).

Endpunkte:
  Projekte:     GET/POST /projektplan/projects ...
  Aufgaben:     GET/POST/PUT/DELETE /projektplan/projects/{pid}/tasks ...
  Abhängigk.:   POST/DELETE /projektplan/dependencies ...
  Meilensteine: POST/PUT/DELETE /projektplan/projects/{pid}/milestones ...
  Aktion:       POST /projektplan/tasks/{tid}/promote  (Aufgabe -> Detailprojekt)
"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional, Dict
from uuid import UUID, uuid4
from datetime import datetime, timezone

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.projektplan import (
    PlanningProject, Task, TaskDependency, Milestone, ProjectTaskField, ChecklistItem,
    TASK_STATUS, TASK_PRIORITY, DEPENDENCY_TYPES,
)
from app.models.zeiterfassung import TimeEntry
from app.models.settings import Setting
from app.models.masterdata import EntityRecord
from app.schemas.projektplan import (
    PlanningProjectCreate, PlanningProjectUpdate,
    PlanningProjectListItem, PlanningProjectDetail,
    TaskCreate, TaskUpdate, TaskResponse,
    DependencyCreate, DependencyResponse,
    MilestoneCreate, MilestoneUpdate, MilestoneResponse,
    PromoteTaskToProject, DuplicateProject,
    TaskFieldCreate, TaskFieldUpdate, TaskFieldResponse,
    ProjektplanSettings, StatusOption,
    ChecklistItemCreate, ChecklistItemUpdate, ChecklistItemResponse, ChecklistAssign,
    TaskDatesBatch, AutomationRule,
)

router = APIRouter(prefix="/projektplan", tags=["Projektplanung"])

# Setting-Key für die konfigurierbaren Projekt-Listen (Tags/Status/Prioritäten)
SETTINGS_KEY = "projektplan_settings"

DEFAULT_SETTINGS = ProjektplanSettings(
    statuses=[
        StatusOption(value="offen", label="Offen", color="#6b7280"),
        StatusOption(value="in_arbeit", label="In Arbeit", color="#3b82f6"),
        StatusOption(value="blockiert", label="Blockiert", color="#ef4444"),
        StatusOption(value="erledigt", label="Erledigt", color="#22c55e"),
    ],
    priorities=[
        StatusOption(value="niedrig", label="Niedrig", color="#9ca3af"),
        StatusOption(value="mittel", label="Mittel", color="#6b7280"),
        StatusOption(value="hoch", label="Hoch", color="#f59e0b"),
        StatusOption(value="kritisch", label="Kritisch", color="#ef4444"),
    ],
    tags=[],
    task_types=[
        StatusOption(value="aufgabe", label="Aufgabe", color="#6b7280"),
        StatusOption(value="meilenstein", label="Meilenstein", color="#534AB7"),
        StatusOption(value="golive", label="GoLive", color="#1d9e75"),
    ],
)


def _make_key(text: str) -> str:
    repl = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
    s = "".join(repl.get(c, c) for c in text.lower())
    out = []
    for c in s:
        out.append(c if (c.isalnum() and c.isascii()) else "_")
    key = "".join(out).strip("_")
    while "__" in key:
        key = key.replace("__", "_")
    return key or "feld"


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def _logged_minutes_by_task(db: Session, task_ids: List[UUID]) -> Dict[UUID, int]:
    """Summiert die erfasste Netto-Zeit (Minuten) je Aufgabe aus TimeEntry."""
    if not task_ids:
        return {}
    rows = (
        db.query(TimeEntry.task_id, TimeEntry.started_at,
                 TimeEntry.ended_at, TimeEntry.pause_minutes)
        .filter(TimeEntry.task_id.in_(task_ids), TimeEntry.ended_at.isnot(None))
        .all()
    )
    result: Dict[UUID, int] = {}
    for task_id, started, ended, pause in rows:
        if not ended:
            continue
        minutes = max(0, int((ended - started).total_seconds() / 60) - (pause or 0))
        result[task_id] = result.get(task_id, 0) + minutes
    return result


def _checklist_by_parent(db: Session, parent_type: str, parent_ids: List[UUID]) -> Dict[UUID, list]:
    """Lädt Checklisten-Elemente gruppiert nach parent_id."""
    if not parent_ids:
        return {}
    rows = (
        db.query(ChecklistItem)
        .filter(ChecklistItem.parent_type == parent_type, ChecklistItem.parent_id.in_(parent_ids))
        .order_by(ChecklistItem.sort_order, ChecklistItem.created_at)
        .all()
    )
    out: Dict[UUID, list] = {}
    for r in rows:
        out.setdefault(r.parent_id, []).append(ChecklistItemResponse.model_validate(r))
    return out


def _critical_task_ids(tasks: List[Task], deps: List[TaskDependency]) -> set:
    """
    Berechnet den kritischen Pfad (vereinfachtes CPM auf Tagesbasis).

    Dauer je Aufgabe = (due_date - start_date) in Tagen (min. 1), sonst 1.
    Vorwärts-/Rückwärtsrechnung über die FS-Abhängigkeiten; Aufgaben mit
    Slack 0 liegen auf dem kritischen Pfad. Aufgaben ohne Datumsangaben
    werden über die reine Abhängigkeitskette (längster Pfad) berücksichtigt.
    """
    from datetime import date as _date

    dur: Dict[UUID, int] = {}
    for t in tasks:
        if t.start_date and t.due_date:
            d = (t.due_date - t.start_date).days
            dur[t.id] = max(1, d)
        else:
            dur[t.id] = 1

    # Adjazenz: predecessor -> [successors]
    succ: Dict[UUID, List[UUID]] = {}
    pred: Dict[UUID, List[UUID]] = {}
    ids = {t.id for t in tasks}
    for dp in deps:
        if dp.predecessor_id in ids and dp.successor_id in ids:
            succ.setdefault(dp.predecessor_id, []).append(dp.successor_id)
            pred.setdefault(dp.successor_id, []).append(dp.predecessor_id)

    if not succ and not pred:
        return set()

    # Topologische Reihenfolge (Kahn)
    indeg = {tid: 0 for tid in ids}
    for s_list in succ.values():
        for s in s_list:
            indeg[s] += 1
    queue = [tid for tid in ids if indeg[tid] == 0]
    topo = []
    while queue:
        n = queue.pop(0)
        topo.append(n)
        for s in succ.get(n, []):
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    if len(topo) != len(ids):
        return set()  # Zyklus -> kein kritischer Pfad

    # Vorwärts: frühester Start/Ende
    es: Dict[UUID, int] = {tid: 0 for tid in ids}
    ef: Dict[UUID, int] = {}
    for n in topo:
        es[n] = max([ef[p] for p in pred.get(n, [])], default=0)
        ef[n] = es[n] + dur[n]
    project_end = max(ef.values(), default=0)

    # Rückwärts: spätestes Ende/Start
    lf: Dict[UUID, int] = {tid: project_end for tid in ids}
    ls: Dict[UUID, int] = {}
    for n in reversed(topo):
        lf[n] = min([ls[s] for s in succ.get(n, [])], default=project_end)
        ls[n] = lf[n] - dur[n]

    # Slack 0 = kritisch (nur Aufgaben, die in einer Abhängigkeit vorkommen)
    in_dep = set(pred.keys()) | set(succ.keys())
    return {tid for tid in in_dep if (ls[tid] - es[tid]) == 0}


def _build_tree(tasks: List[Task], logged: Dict[UUID, int],
                checklists: Optional[Dict[UUID, list]] = None,
                critical: Optional[set] = None) -> List[TaskResponse]:
    """Baut aus einer flachen Aufgabenliste den rekursiven Baum (beliebig tief)."""
    checklists = checklists or {}
    critical = critical or set()
    nodes: Dict[UUID, TaskResponse] = {}
    for t in tasks:
        node = TaskResponse.model_validate(t)
        node.children = []
        node.logged_minutes = logged.get(t.id, 0)
        node.checklist = checklists.get(t.id, [])
        node.is_critical = t.id in critical
        nodes[t.id] = node

    roots: List[TaskResponse] = []
    for t in tasks:
        node = nodes[t.id]
        if t.parent_task_id and t.parent_task_id in nodes:
            nodes[t.parent_task_id].children.append(node)
        else:
            roots.append(node)

    def _sort(items: List[TaskResponse]):
        items.sort(key=lambda n: n.sort_order)
        for it in items:
            _sort(it.children)
    _sort(roots)
    return roots


def _project_stats(db: Session, project_id: UUID) -> Dict[str, int]:
    total = db.query(func.count(Task.id)).filter(Task.project_id == project_id).scalar() or 0
    done = (
        db.query(func.count(Task.id))
        .filter(Task.project_id == project_id, Task.status == "erledigt")
        .scalar() or 0
    )
    percent = int(round(done / total * 100)) if total else 0
    return {"task_count": total, "done_count": done, "progress_percent": percent}


def _get_project_or_404(db: Session, project_id: UUID) -> PlanningProject:
    proj = db.query(PlanningProject).filter(PlanningProject.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Planungsprojekt nicht gefunden")
    return proj


def _get_task_or_404(db: Session, task_id: UUID) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden")
    return task


# ── Projekte ──────────────────────────────────────────────────────────────────
@router.get("/projects", response_model=List[PlanningProjectListItem])
async def list_projects(
    include_archived: bool = Query(False),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = db.query(PlanningProject)
    if not include_archived:
        q = q.filter(PlanningProject.is_archived == False)  # noqa: E712
    projects = q.order_by(PlanningProject.created_at.desc()).all()

    # Kontakt-Typ (data.typ) gebündelt für alle verknüpften Kontakte nachschlagen
    contact_ids = {p.contact_id for p in projects if p.contact_id}
    contact_types: Dict[UUID, str] = {}
    if contact_ids:
        recs = db.query(EntityRecord).filter(EntityRecord.id.in_(contact_ids)).all()
        for r in recs:
            if isinstance(r.data, dict):
                t = r.data.get("typ") or r.data.get("kategorie")
                if t:
                    contact_types[r.id] = str(t)

    result = []
    for p in projects:
        item = PlanningProjectListItem.model_validate(p)
        stats = _project_stats(db, p.id)
        item.task_count = stats["task_count"]
        item.done_count = stats["done_count"]
        item.progress_percent = stats["progress_percent"]
        item.contact_type = contact_types.get(p.contact_id) if p.contact_id else None
        result.append(item)
    return result


@router.get("/projects/recent", response_model=List[PlanningProjectListItem])
async def recent_projects(
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Die zuletzt bearbeiteten (nicht archivierten) Projekte – fürs Dashboard."""
    projects = (
        db.query(PlanningProject)
        .filter(PlanningProject.is_archived == False)  # noqa: E712
        .order_by(PlanningProject.updated_at.desc().nullslast())
        .limit(limit)
        .all()
    )
    result = []
    for p in projects:
        item = PlanningProjectListItem.model_validate(p)
        stats = _project_stats(db, p.id)
        item.task_count = stats["task_count"]
        item.done_count = stats["done_count"]
        item.progress_percent = stats["progress_percent"]
        result.append(item)
    return result


@router.post("/projects", response_model=PlanningProjectDetail)
async def create_project(
    body: PlanningProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proj = PlanningProject(id=uuid4(), created_by=user.id, **body.model_dump())
    db.add(proj)
    db.commit()
    db.refresh(proj)
    return _project_detail(db, proj)


@router.get("/projects/{project_id}", response_model=PlanningProjectDetail)
async def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    proj = _get_project_or_404(db, project_id)
    return _project_detail(db, proj)


def _project_detail(db: Session, proj: PlanningProject) -> PlanningProjectDetail:
    # WICHTIG: NICHT model_validate(proj) verwenden – das würde die SQLAlchemy-
    # Relationships (tasks/children) aus dem ORM ziehen, wobei task.children ein
    # einzelnes Task-Objekt statt einer Liste sein kann -> ValidationError.
    # Stattdessen nur die Kopf-Felder des Projekts übernehmen; die Listen
    # (tasks, milestones, checklist, dependencies) setzen wir unten selbst.
    detail = PlanningProjectDetail(
        id=proj.id,
        name=proj.name,
        description=proj.description,
        masterdata_project_id=proj.masterdata_project_id,
        masterdata_project_name=proj.masterdata_project_name,
        contact_id=proj.contact_id,
        contact_name=proj.contact_name,
        status=proj.status,
        color=proj.color,
        start_date=proj.start_date,
        end_date=proj.end_date,
        is_archived=proj.is_archived,
        origin_task_id=proj.origin_task_id,
        created_at=proj.created_at,
    )
    tasks = db.query(Task).filter(Task.project_id == proj.id).all()
    task_ids = [t.id for t in tasks]
    logged = _logged_minutes_by_task(db, task_ids)
    task_checklists = _checklist_by_parent(db, "task", task_ids)
    # Abhängigkeiten dieses Projekts laden (beide Richtungen) + kritischen Pfad
    if task_ids:
        from sqlalchemy import or_
        deps = (
            db.query(TaskDependency)
            .filter(or_(
                TaskDependency.successor_id.in_(task_ids),
                TaskDependency.predecessor_id.in_(task_ids),
            ))
            .all()
        )
    else:
        deps = []
    critical = _critical_task_ids(tasks, deps)
    detail.tasks = _build_tree(tasks, logged, task_checklists, critical)
    detail.dependencies = [DependencyResponse.model_validate(d) for d in deps]
    # Robust sortieren: Meilensteine ohne Datum ans Ende; kein Vergleich date<->str.
    from datetime import date as _date
    _far = _date.max
    detail.milestones = [
        MilestoneResponse.model_validate(m)
        for m in sorted(proj.milestones, key=lambda m: (m.sort_order or 0, m.due_date or _far))
    ]
    detail.checklist = _checklist_by_parent(db, "project", [proj.id]).get(proj.id, [])
    stats = _project_stats(db, proj.id)
    detail.task_count = stats["task_count"]
    detail.done_count = stats["done_count"]
    detail.progress_percent = stats["progress_percent"]
    return detail


@router.put("/projects/{project_id}", response_model=PlanningProjectDetail)
async def update_project(
    project_id: UUID,
    body: PlanningProjectUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    proj = _get_project_or_404(db, project_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(proj, k, v)
    db.commit()
    db.refresh(proj)
    return _project_detail(db, proj)


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    proj = _get_project_or_404(db, project_id)
    db.delete(proj)
    db.commit()
    return {"status": "deleted"}


@router.post("/projects/{project_id}/duplicate", response_model=PlanningProjectDetail)
async def duplicate_project(
    project_id: UUID,
    body: DuplicateProject,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Dupliziert ein Projekt als eigenständige Kopie. Über die Flags steuerbar,
    wie viel mitkopiert wird (Aufgaben, Meilensteine, Feldwerte/Tags,
    Verantwortliche, Termine; optional Status-Reset für Vorlagen).
    Ist-Stunden und Anlagen werden NICHT kopiert.
    """
    src = _get_project_or_404(db, project_id)

    new_proj = PlanningProject(
        id=uuid4(),
        name=body.name or f"{src.name} (Kopie)",
        description=src.description,
        masterdata_project_id=src.masterdata_project_id,
        masterdata_project_name=src.masterdata_project_name,
        contact_id=src.contact_id,
        contact_name=src.contact_name,
        status="offen" if body.reset_status else src.status,
        color=src.color,
        start_date=src.start_date if body.include_dates else None,
        end_date=src.end_date if body.include_dates else None,
        created_by=user.id,
    )
    db.add(new_proj)
    db.flush()

    if body.include_tasks:
        src_tasks = db.query(Task).filter(Task.project_id == src.id).order_by(Task.sort_order).all()
        # Erst alle neuen Tasks anlegen, alte->neue ID merken, dann parent neu verdrahten
        id_map: Dict[UUID, UUID] = {}
        new_tasks: Dict[UUID, Task] = {}
        for t in src_tasks:
            new_id = uuid4()
            id_map[t.id] = new_id
            data = dict(t.data or {})
            if not body.include_field_values:
                data = {}  # entfernt auch Tags
            nt = Task(
                id=new_id,
                project_id=new_proj.id,
                parent_task_id=None,  # wird unten gesetzt
                title=t.title,
                description=t.description,
                status="offen" if body.reset_status else t.status,
                priority=t.priority,
                assignee_id=t.assignee_id if body.include_assignees else None,
                assignee_name=t.assignee_name if body.include_assignees else None,
                contact_id=t.contact_id,
                contact_name=t.contact_name,
                start_date=t.start_date if body.include_dates else None,
                due_date=t.due_date if body.include_dates else None,
                estimate_minutes=t.estimate_minutes,
                progress=0 if body.reset_status else t.progress,
                is_milestone=t.is_milestone,
                sort_order=t.sort_order,
                data=data,
                created_by=user.id,
            )
            db.add(nt)
            new_tasks[t.id] = nt
        db.flush()
        # Hierarchie (parent_task_id) über die ID-Map neu aufbauen
        for t in src_tasks:
            if t.parent_task_id and t.parent_task_id in id_map:
                new_tasks[t.id].parent_task_id = id_map[t.parent_task_id]

    if body.include_milestones:
        for m in src.milestones:
            db.add(Milestone(
                id=uuid4(),
                project_id=new_proj.id,
                title=m.title,
                due_date=m.due_date if body.include_dates else None,
                is_reached=False if body.reset_status else m.is_reached,
                color=m.color,
                sort_order=m.sort_order,
            ))

    db.commit()
    db.refresh(new_proj)
    return _project_detail(db, new_proj)


# ── Aufgaben ──────────────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/tasks", response_model=TaskResponse)
async def create_task(
    project_id: UUID,
    body: TaskCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proj = _get_project_or_404(db, project_id)

    # Status/Priorität sind frei konfigurierbar -> keine harte Validierung mehr.
    if body.parent_task_id:
        parent = _get_task_or_404(db, body.parent_task_id)
        if parent.project_id != project_id:
            raise HTTPException(status_code=400, detail="Übergeordnete Aufgabe gehört zu anderem Projekt")

    payload = body.model_dump()
    # Kontakt-Vererbung: Wird kein Kontakt mitgegeben, erbt die Aufgabe den
    # Kontakt des Projekts. Bei Teilaufgaben: bevorzugt den der Elternaufgabe.
    if not payload.get("contact_id"):
        if body.parent_task_id and parent.contact_id:
            payload["contact_id"] = parent.contact_id
            payload["contact_name"] = parent.contact_name
        elif proj.contact_id:
            payload["contact_id"] = proj.contact_id
            payload["contact_name"] = proj.contact_name

    task = Task(id=uuid4(), project_id=project_id, created_by=user.id, **payload)
    db.add(task)
    db.commit()
    db.refresh(task)
    resp = TaskResponse.model_validate(task)
    resp.children = []
    return resp


# WICHTIG: /tasks/dates muss VOR /tasks/{task_id} stehen, sonst matcht
# FastAPI "dates" als task_id (UUID-Fehler – wie zuvor bei der Checkliste).
@router.put("/tasks/dates", response_model=dict)
async def update_task_dates(
    body: TaskDatesBatch,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Aktualisiert Start-/Fälligkeitsdaten mehrerer Aufgaben (Drag im Gantt)."""
    updated = 0
    for u in body.updates:
        task = db.query(Task).filter(Task.id == u.id).first()
        if not task:
            continue
        if u.start_date is not None:
            task.start_date = u.start_date
        if u.due_date is not None:
            task.due_date = u.due_date
        updated += 1
    db.commit()
    return {"updated": updated}


def _load_settings(db: Session) -> ProjektplanSettings:
    """Lädt die Projekt-Einstellungen (inkl. Regeln) aus dem Setting-Store."""
    row = db.query(Setting).filter(Setting.key == SETTINGS_KEY).first()
    if not row or not row.value:
        return DEFAULT_SETTINGS
    try:
        return ProjektplanSettings(**json.loads(row.value))
    except Exception:
        return DEFAULT_SETTINGS


def _run_automation(db: Session, task: Task, settings: ProjektplanSettings, actor: User):
    """
    Wertet die Automatisierungsregeln für EINE Aufgabe aus, nachdem sie
    aktualisiert wurde. Führt erfüllte Regeln genau einmal aus (Dedup über
    task.data['_fired_rules']).
    """
    rules = settings.rules or []
    if not rules:
        return

    data = dict(task.data or {})
    fired = set(data.get("_fired_rules", []))
    task_type = (data.get("task_type") or "").lower()
    changed_fired = False

    for rule in rules:
        if not rule.enabled or not rule.id:
            continue
        # Typ-Filter
        if rule.applies_to_type and rule.applies_to_type.lower() != task_type:
            continue
        # Trigger prüfen (mind. eine Bedingung muss konfiguriert + erfüllt sein)
        trigger_ok = False
        if rule.trigger_progress_min is not None and (task.progress or 0) >= rule.trigger_progress_min:
            trigger_ok = True
        if rule.trigger_status and task.status == rule.trigger_status:
            trigger_ok = True
        if not trigger_ok:
            continue
        # Schon ausgelöst? (einmalig je Regel)
        if rule.id in fired:
            continue

        # ── Aktionen ausführen ──
        # 1) Status der Aufgabe ändern
        if rule.action_set_status:
            task.status = rule.action_set_status

        # 2) Nachfolger aktivieren (über Abhängigkeiten: diese Aufgabe = predecessor)
        if rule.action_activate_successors:
            succ_deps = db.query(TaskDependency).filter(
                TaskDependency.predecessor_id == task.id
            ).all()
            for dep in succ_deps:
                succ = db.query(Task).filter(Task.id == dep.successor_id).first()
                if succ and succ.status not in ("erledigt",):
                    succ.status = "in_arbeit"

        # 3) E-Mail an Verantwortlichen
        if rule.action_email_assignee and task.assignee_id:
            try:
                _send_automation_email(db, task, rule, actor)
            except Exception as exc:
                print(f"[Automation] E-Mail-Versand fehlgeschlagen: {exc}")

        fired.add(rule.id)
        changed_fired = True

    if changed_fired:
        data["_fired_rules"] = sorted(fired)
        task.data = data
        # SQLAlchemy braucht den Hinweis, dass das JSONB-Feld geändert wurde
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(task, "data")


def _send_automation_email(db: Session, task: Task, rule: AutomationRule, actor: User):
    """Benachrichtigt den Verantwortlichen der Aufgabe über die ausgelöste Regel."""
    from app.services.email_service import send_email

    u = db.query(User).filter(User.id == task.assignee_id).first()
    to_email = (u.email if u else "") or ""
    if not to_email:
        return

    settings_d = {r.key: r.value for r in db.query(Setting).all()}
    company = settings_d.get("company_name", "DeineZeit")

    proj = db.query(PlanningProject).filter(PlanningProject.id == task.project_id).first()
    project_name = proj.name if proj else ""

    rule_name = rule.name or "Automatische Benachrichtigung"
    subject = f"Aufgabe '{task.title}' - {rule_name}"
    body_text = (
        f"Hallo,\n\n"
        f"die Aufgabe '{task.title}' (Projekt: {project_name}) hat eine "
        f"Automatisierung ausgeloest: {rule_name}.\n\n"
        f"Aktueller Status: {task.status}\nFortschritt: {task.progress or 0}%\n\n"
        f"Mit freundlichen Gruessen\n{company}"
    )
    body_html = (
        f"<p>Hallo,</p>"
        f"<p>die Aufgabe <strong>{task.title}</strong> (Projekt: {project_name}) "
        f"hat eine Automatisierung ausgeloest: <strong>{rule_name}</strong>.</p>"
        f"<p>Aktueller Status: {task.status}<br>Fortschritt: {task.progress or 0}%</p>"
        f"<p>Mit freundlichen Gruessen<br>{company}</p>"
    )
    send_email(settings=settings_d, to_email=to_email, subject=subject,
               body_text=body_text, body_html=body_html)


@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    task = _get_task_or_404(db, task_id)
    payload = body.model_dump(exclude_unset=True)

    # Status/Priorität sind frei konfigurierbar -> keine harte Validierung mehr.
    if payload.get("parent_task_id") == task.id:
        raise HTTPException(status_code=400, detail="Aufgabe kann nicht sich selbst untergeordnet sein")

    for k, v in payload.items():
        setattr(task, k, v)

    # Aufgaben-Typ <-> Meilenstein synchronisieren: Typ "meilenstein" -> is_milestone.
    # data.task_type ist die Quelle der Wahrheit; is_milestone wird daraus abgeleitet.
    if isinstance(task.data, dict):
        ttype = task.data.get("task_type")
        if ttype is not None:
            task.is_milestone = (str(ttype).lower() == "meilenstein")

    # Automatisierungsregeln auswerten (nach dem Setzen der neuen Werte)
    try:
        _run_automation(db, task, _load_settings(db), user)
    except Exception as exc:
        print(f"[Automation] Auswertung fehlgeschlagen: {exc}")

    db.commit()
    db.refresh(task)
    # children explizit leeren, bevor validiert wird (ORM-Relationship kann ein
    # einzelnes Objekt statt Liste sein -> sonst ValidationError).
    resp = TaskResponse.model_validate(task, from_attributes=True)
    resp.logged_minutes = _logged_minutes_by_task(db, [task.id]).get(task.id, 0)
    resp.children = []
    resp.checklist = []
    return resp


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    task = _get_task_or_404(db, task_id)
    db.delete(task)  # Kinder via ondelete=CASCADE
    db.commit()
    return {"status": "deleted"}


# ── Abhängigkeiten ────────────────────────────────────────────────────────────
@router.post("/dependencies", response_model=DependencyResponse)
async def create_dependency(
    body: DependencyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if body.predecessor_id == body.successor_id:
        raise HTTPException(status_code=400, detail="Aufgabe kann nicht von sich selbst abhängen")
    pred = _get_task_or_404(db, body.predecessor_id)
    succ = _get_task_or_404(db, body.successor_id)

    # Beide Aufgaben müssen im selben Projekt sein
    if pred.project_id != succ.project_id:
        raise HTTPException(status_code=400, detail="Aufgaben gehören zu verschiedenen Projekten")

    # Duplikat verhindern (gleiche Richtung)
    existing = db.query(TaskDependency).filter(
        TaskDependency.predecessor_id == body.predecessor_id,
        TaskDependency.successor_id == body.successor_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Diese Verknüpfung besteht bereits")

    # Direkten Zyklus verhindern (B->A existiert schon, A->B würde Zyklus bilden)
    reverse = db.query(TaskDependency).filter(
        TaskDependency.predecessor_id == body.successor_id,
        TaskDependency.successor_id == body.predecessor_id,
    ).first()
    if reverse:
        raise HTTPException(status_code=400, detail="Das würde einen Zyklus erzeugen (umgekehrte Verknüpfung besteht bereits)")

    dep = TaskDependency(id=uuid4(), **body.model_dump())
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep


@router.delete("/dependencies/{dep_id}")
async def delete_dependency(
    dep_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    dep = db.query(TaskDependency).filter(TaskDependency.id == dep_id).first()
    if not dep:
        raise HTTPException(status_code=404, detail="Abhängigkeit nicht gefunden")
    db.delete(dep)
    db.commit()
    return {"status": "deleted"}


# ── Meilensteine ──────────────────────────────────────────────────────────────
@router.post("/projects/{project_id}/milestones", response_model=MilestoneResponse)
async def create_milestone(
    project_id: UUID,
    body: MilestoneCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_project_or_404(db, project_id)
    ms = Milestone(id=uuid4(), project_id=project_id, **body.model_dump())
    db.add(ms)
    db.commit()
    db.refresh(ms)
    return ms


@router.put("/milestones/{milestone_id}", response_model=MilestoneResponse)
async def update_milestone(
    milestone_id: UUID,
    body: MilestoneUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ms = db.query(Milestone).filter(Milestone.id == milestone_id).first()
    if not ms:
        raise HTTPException(status_code=404, detail="Meilenstein nicht gefunden")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(ms, k, v)
    db.commit()
    db.refresh(ms)
    return ms


@router.delete("/milestones/{milestone_id}")
async def delete_milestone(
    milestone_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    ms = db.query(Milestone).filter(Milestone.id == milestone_id).first()
    if not ms:
        raise HTTPException(status_code=404, detail="Meilenstein nicht gefunden")
    db.delete(ms)
    db.commit()
    return {"status": "deleted"}


# ── Aktion: Aufgabe -> Detailprojekt ──────────────────────────────────────────
@router.post("/tasks/{task_id}/promote", response_model=PlanningProjectDetail)
async def promote_task_to_project(
    task_id: UUID,
    body: PromoteTaskToProject,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Erzeugt aus einer Aufgabe ein neues Planungsprojekt (lose Kopplung).
    Optional werden die Teilaufgaben als Top-Level-Aufgaben übernommen.
    """
    task = _get_task_or_404(db, task_id)
    src = db.query(PlanningProject).filter(PlanningProject.id == task.project_id).first()

    new_proj = PlanningProject(
        id=uuid4(),
        name=body.name or task.title,
        description=task.description,
        masterdata_project_id=src.masterdata_project_id if src else None,
        masterdata_project_name=src.masterdata_project_name if src else None,
        contact_id=src.contact_id if src else None,
        contact_name=src.contact_name if src else None,
        start_date=task.start_date,
        end_date=task.due_date,
        origin_task_id=task.id if body.link_back else None,
        created_by=user.id,
    )
    db.add(new_proj)
    db.flush()

    if body.move_subtasks:
        children = db.query(Task).filter(Task.parent_task_id == task.id).all()
        for idx, child in enumerate(children):
            child.project_id = new_proj.id
            child.parent_task_id = None
            child.sort_order = idx

    db.commit()
    db.refresh(new_proj)
    return _project_detail(db, new_proj)


# ── Checklisten ───────────────────────────────────────────────────────────────
def _validate_parent(db: Session, parent_type: str, parent_id: UUID):
    if parent_type == "project":
        if not db.query(PlanningProject).filter(PlanningProject.id == parent_id).first():
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    elif parent_type == "task":
        if not db.query(Task).filter(Task.id == parent_id).first():
            raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden")
    else:
        raise HTTPException(status_code=400, detail="parent_type muss 'project' oder 'task' sein")


def _get_checklist_item_or_404(db: Session, item_id: UUID) -> ChecklistItem:
    it = db.query(ChecklistItem).filter(ChecklistItem.id == item_id).first()
    if not it:
        raise HTTPException(status_code=404, detail="Checklisten-Element nicht gefunden")
    return it


@router.get("/checklist/{parent_type}/{parent_id}", response_model=List[ChecklistItemResponse])
async def list_checklist(
    parent_type: str,
    parent_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _validate_parent(db, parent_type, parent_id)
    return (
        db.query(ChecklistItem)
        .filter(ChecklistItem.parent_type == parent_type, ChecklistItem.parent_id == parent_id)
        .order_by(ChecklistItem.sort_order, ChecklistItem.created_at)
        .all()
    )


@router.post("/checklist/{parent_type}/{parent_id}", response_model=ChecklistItemResponse)
async def create_checklist_item(
    parent_type: str,
    parent_id: UUID,
    body: ChecklistItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _validate_parent(db, parent_type, parent_id)
    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Text darf nicht leer sein")
    item = ChecklistItem(
        id=uuid4(), parent_type=parent_type, parent_id=parent_id,
        text=body.text.strip(), sort_order=body.sort_order, created_by=user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/checklist/item/{item_id}", response_model=ChecklistItemResponse)
async def update_checklist_item(
    item_id: UUID,
    body: ChecklistItemUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = _get_checklist_item_or_404(db, item_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/checklist/item/{item_id}")
async def delete_checklist_item(
    item_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    item = _get_checklist_item_or_404(db, item_id)
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@router.post("/checklist/item/{item_id}/promote", response_model=TaskResponse)
async def checklist_item_to_task(
    item_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Erzeugt aus einem Checklisten-Element eine Aufgabe im zugehörigen Projekt."""
    item = _get_checklist_item_or_404(db, item_id)

    # Ziel-Projekt bestimmen: bei project-Checkliste direkt, bei task-Checkliste das Projekt der Aufgabe
    if item.parent_type == "project":
        project_id = item.parent_id
        parent_task_id = None
    else:
        src_task = db.query(Task).filter(Task.id == item.parent_id).first()
        if not src_task:
            raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden")
        project_id = src_task.project_id
        parent_task_id = src_task.id  # als Teilaufgabe der Aufgabe anlegen

    new_task = Task(
        id=uuid4(), project_id=project_id, parent_task_id=parent_task_id,
        title=item.text,
        assignee_id=item.assignee_user_id,
        assignee_name=item.assignee_name if item.assignee_user_id else None,
        contact_id=item.assignee_contact_id,
        contact_name=item.assignee_name if item.assignee_contact_id else None,
        created_by=user.id,
    )
    db.add(new_task)
    db.flush()
    item.linked_task_id = new_task.id
    db.commit()
    db.refresh(new_task)
    resp = TaskResponse.model_validate(new_task)
    resp.children = []
    resp.checklist = []
    return resp


@router.post("/checklist/item/{item_id}/assign", response_model=ChecklistItemResponse)
async def assign_checklist_item(
    item_id: UUID,
    body: ChecklistAssign,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Weist ein Checklisten-Element einem Benutzer ODER Kontakt zu und versendet
    optional sofort eine E-Mail mit dem Element-Text und Projekt-/Aufgaben-Bezug.
    """
    item = _get_checklist_item_or_404(db, item_id)

    item.assignee_user_id = body.assignee_user_id
    item.assignee_contact_id = body.assignee_contact_id
    item.assignee_name = body.assignee_name

    # Ziel-E-Mail bestimmen
    to_email = (body.email or "").strip()
    if not to_email and body.assignee_user_id:
        u = db.query(User).filter(User.id == body.assignee_user_id).first()
        to_email = (u.email if u else "") or ""
    if not to_email and body.assignee_contact_id:
        rec = db.query(EntityRecord).filter(EntityRecord.id == body.assignee_contact_id).first()
        if rec and isinstance(rec.data, dict):
            to_email = (rec.data.get("email") or rec.data.get("e_mail") or rec.data.get("mail") or "")

    db.commit()
    db.refresh(item)

    # E-Mail versenden. Fehler werden NICHT hart durchgereicht – die Zuweisung
    # bleibt gespeichert, der E-Mail-Fehler wird nur geloggt.
    if body.send_email and to_email:
        try:
            _send_checklist_email(db, item, to_email, user)
        except Exception as exc:
            print(f"[Checkliste] E-Mail-Versand fehlgeschlagen: {exc}")

    return item


def _send_checklist_email(db: Session, item: ChecklistItem, to_email: str, sender: User):
    """Baut Kontext (Projekt/Aufgabe) und versendet die Benachrichtigung."""
    from app.services.email_service import send_email

    settings = {r.key: r.value for r in db.query(Setting).all()}
    company = settings.get("company_name", "DeineZeit")

    # Kontext: Projekt-/Aufgabenname ermitteln
    project_name, task_name = None, None
    if item.parent_type == "project":
        p = db.query(PlanningProject).filter(PlanningProject.id == item.parent_id).first()
        project_name = p.name if p else None
    else:
        t = db.query(Task).filter(Task.id == item.parent_id).first()
        if t:
            task_name = t.title
            p = db.query(PlanningProject).filter(PlanningProject.id == t.project_id).first()
            project_name = p.name if p else None

    bezug = []
    if project_name:
        bezug.append(f"Projekt: {project_name}")
    if task_name:
        bezug.append(f"Aufgabe: {task_name}")
    bezug_text = " · ".join(bezug) if bezug else "Projektplanung"

    subject = f"Neue Aufgabe für Sie: {item.text[:60]}"
    body_text = (
        f"Hallo {item.assignee_name or ''},\n\n"
        f"Ihnen wurde folgendes Element zugewiesen:\n\n"
        f"  • {item.text}\n\n"
        f"{bezug_text}\n\n"
        f"Zugewiesen von: {sender.full_name or sender.email}\n\n"
        f"(Ein Freigabe-Link folgt in einer späteren Version.)\n\n"
        f"Mit freundlichen Grüßen\n{company}"
    )
    body_html = (
        f"<p>Hallo {item.assignee_name or ''},</p>"
        f"<p>Ihnen wurde folgendes Element zugewiesen:</p>"
        f"<blockquote style='border-left:3px solid #3b82f6;padding-left:12px;margin:8px 0'>"
        f"<strong>{item.text}</strong></blockquote>"
        f"<p style='color:#555'>{bezug_text}</p>"
        f"<p style='color:#888;font-size:13px'>Zugewiesen von: {sender.full_name or sender.email}<br>"
        f"Ein Freigabe-Link folgt in einer späteren Version.</p>"
        f"<p>Mit freundlichen Grüßen<br>{company}</p>"
    )
    send_email(settings=settings, to_email=to_email, subject=subject,
               body_text=body_text, body_html=body_html)


# ── Konfigurierbare Aufgaben-Felder ───────────────────────────────────────────
VALID_FIELD_TYPES = ("text", "number", "date", "email", "phone", "url",
                     "dropdown", "checkbox", "textarea")


@router.get("/fields", response_model=List[TaskFieldResponse])
async def list_task_fields(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(ProjectTaskField).order_by(ProjectTaskField.sort_order).all()


@router.post("/fields", response_model=TaskFieldResponse)
async def create_task_field(
    body: TaskFieldCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if body.field_type not in VALID_FIELD_TYPES:
        raise HTTPException(status_code=400, detail=f"Ungültiger Feldtyp: {body.field_type}")
    key = _make_key(body.name)
    # Key eindeutig machen
    base, i = key, 2
    while db.query(ProjectTaskField).filter(ProjectTaskField.key == key).first():
        key = f"{base}_{i}"
        i += 1
    field = ProjectTaskField(id=uuid4(), key=key, **body.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


@router.put("/fields/{field_id}", response_model=TaskFieldResponse)
async def update_task_field(
    field_id: UUID,
    body: TaskFieldUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    field = db.query(ProjectTaskField).filter(ProjectTaskField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Feld nicht gefunden")
    payload = body.model_dump(exclude_unset=True)
    if "field_type" in payload and payload["field_type"] not in VALID_FIELD_TYPES:
        raise HTTPException(status_code=400, detail=f"Ungültiger Feldtyp: {payload['field_type']}")
    for k, v in payload.items():
        setattr(field, k, v)
    db.commit()
    db.refresh(field)
    return field


@router.delete("/fields/{field_id}")
async def delete_task_field(
    field_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    field = db.query(ProjectTaskField).filter(ProjectTaskField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Feld nicht gefunden")
    db.delete(field)
    db.commit()
    return {"status": "deleted"}


# ── Projekt-Einstellungen (Tags, Status, Prioritäten) ─────────────────────────
@router.get("/settings", response_model=ProjektplanSettings)
async def get_projektplan_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = db.query(Setting).filter(Setting.key == SETTINGS_KEY).first()
    if not row or not row.value:
        return DEFAULT_SETTINGS
    try:
        s = ProjektplanSettings(**json.loads(row.value))
        # Migration für Bestands-Einstellungen: Felder, die es früher noch nicht
        # gab, mit den Defaults auffüllen, statt leer zurückzugeben.
        if not s.task_types:
            s.task_types = DEFAULT_SETTINGS.task_types
        if not s.statuses:
            s.statuses = DEFAULT_SETTINGS.statuses
        if not s.priorities:
            s.priorities = DEFAULT_SETTINGS.priorities
        return s
    except Exception:
        return DEFAULT_SETTINGS


@router.put("/settings", response_model=ProjektplanSettings)
async def update_projektplan_settings(
    body: ProjektplanSettings,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    row = db.query(Setting).filter(Setting.key == SETTINGS_KEY).first()
    value = json.dumps(body.model_dump())
    if row:
        row.value = value
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Setting(key=SETTINGS_KEY, value=value, updated_at=datetime.now(timezone.utc)))
    db.commit()
    return body
