from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, String, func, and_
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.zeiterfassung import TimeEntry, TimeEntryField
from app.schemas.zeiterfassung import (
    TimeEntryFieldCreate, TimeEntryFieldUpdate, TimeEntryFieldResponse,
    UpdateTimeEntryFieldSortOrders,
    TimeEntryCreate, TimeEntryUpdate, TimeEntryStop,
    TimeEntryResponse, TimeEntryListResponse, TimeStats,
)

router = APIRouter(prefix="/zeiterfassung", tags=["Zeiterfassung"])


# ── Custom-Felder verwalten ───────────────────────────────────────────────────

@router.get("/fields", response_model=List[TimeEntryFieldResponse])
async def list_fields(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Custom-Felddefinitionen für Zeiteinträge."""
    return db.query(TimeEntryField).order_by(TimeEntryField.sort_order).all()


@router.post("/fields", response_model=TimeEntryFieldResponse)
async def create_field(
    body: TimeEntryFieldCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Neues Custom-Feld anlegen (nur Admin)."""
    # Key auf Eindeutigkeit prüfen
    existing = db.query(TimeEntryField).filter(TimeEntryField.key == body.key).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Feld mit Key '{body.key}' existiert bereits")

    valid_types = ['text', 'number', 'date', 'email', 'phone', 'url',
                   'dropdown', 'checkbox', 'textarea']
    if body.field_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Ungültiger Feldtyp: {body.field_type}")

    field = TimeEntryField(**body.model_dump())
    db.add(field)
    db.commit()
    db.refresh(field)
    return field


@router.put("/fields/{field_id}", response_model=TimeEntryFieldResponse)
async def update_field(
    field_id: UUID,
    body: TimeEntryFieldUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    field = db.query(TimeEntryField).filter(TimeEntryField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Feld nicht gefunden")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(field, k, v)
    db.commit()
    db.refresh(field)
    return field


@router.delete("/fields/{field_id}")
async def delete_field(
    field_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    field = db.query(TimeEntryField).filter(TimeEntryField.id == field_id).first()
    if not field:
        raise HTTPException(status_code=404, detail="Feld nicht gefunden")
    db.delete(field)
    db.commit()
    return {"message": "Feld gelöscht"}


@router.post("/fields/sort-orders")
async def update_sort_orders(
    body: UpdateTimeEntryFieldSortOrders,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Reihenfolge und col_span mehrerer Felder auf einmal aktualisieren."""
    for upd in body.updates:
        field = db.query(TimeEntryField).filter(
            TimeEntryField.id == upd['id']
        ).first()
        if field:
            if 'sort_order' in upd:
                field.sort_order = upd['sort_order']
            if 'col_span' in upd:
                field.col_span = upd['col_span']
    db.commit()
    return {"message": "Reihenfolge gespeichert"}


# ── Timer starten / stoppen ───────────────────────────────────────────────────

@router.get("/running", response_model=Optional[TimeEntryResponse])
async def get_running_timer(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Gibt den aktuell laufenden Timer des eingeloggten Benutzers zurück (oder null)."""
    entry = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.ended_at.is_(None),
    ).first()
    return entry


@router.post("/start", response_model=TimeEntryResponse)
async def start_timer(
    body: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Timer starten. Stoppt automatisch einen noch laufenden Timer."""
    # Laufenden Timer des Benutzers stoppen
    running = db.query(TimeEntry).filter(
        TimeEntry.user_id == current_user.id,
        TimeEntry.ended_at.is_(None),
    ).first()
    if running:
        running.ended_at = body.started_at
        running.updated_at = datetime.now(timezone.utc)

    entry = TimeEntry(
        user_id=current_user.id,
        project_id=body.project_id,
        project_name=body.project_name,
        contact_id=body.contact_id,
        contact_name=body.contact_name,
        started_at=body.started_at,
        ended_at=None,  # läuft
        pause_minutes=0,
        note=body.note,
        billable=body.billable,
        data=body.data,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/{entry_id}/stop", response_model=TimeEntryResponse)
async def stop_timer(
    entry_id: UUID,
    body: TimeEntryStop,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Laufenden Timer stoppen."""
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")
    if entry.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    if entry.ended_at:
        raise HTTPException(status_code=400, detail="Timer läuft nicht mehr")

    entry.ended_at = body.ended_at
    entry.pause_minutes = body.pause_minutes
    if body.note is not None:
        entry.note = body.note
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)
    return entry


# ── Zeiteinträge CRUD ─────────────────────────────────────────────────────────

@router.get("/entries", response_model=TimeEntryListResponse)
async def list_entries(
    user_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    project_id: Optional[UUID] = Query(None),
    contact_id: Optional[UUID] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Zeiteinträge abrufen – filterbar nach Benutzer, Datum, Projekt, Kontakt."""
    q = db.query(TimeEntry)

    if user_id:
        q = q.filter(TimeEntry.user_id == user_id)
    if date_from:
        q = q.filter(TimeEntry.started_at >= date_from)
    if date_to:
        q = q.filter(TimeEntry.started_at <= date_to)
    if project_id:
        q = q.filter(TimeEntry.project_id == project_id)
    if contact_id:
        q = q.filter(TimeEntry.contact_id == contact_id)
    if search:
        term = f"%{search}%"
        q = q.filter(or_(
            TimeEntry.note.ilike(term),
            TimeEntry.project_name.ilike(term),
            TimeEntry.contact_name.ilike(term),
        ))

    total = q.count()
    items = (
        q.order_by(TimeEntry.started_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return TimeEntryListResponse(total=total, page=page, page_size=page_size, items=items)


@router.post("/entries", response_model=TimeEntryResponse)
async def create_entry(
    body: TimeEntryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zeiteintrag manuell nachtragen."""
    entry = TimeEntry(
        user_id=current_user.id,
        **body.model_dump(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/entries/{entry_id}", response_model=TimeEntryResponse)
async def get_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")
    return entry


@router.put("/entries/{entry_id}", response_model=TimeEntryResponse)
async def update_entry(
    entry_id: UUID,
    body: TimeEntryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Zeiteintrag bearbeiten (inkl. Zeitwerte)."""
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")

    for k, v in body.model_dump(exclude_none=True).items():
        setattr(entry, k, v)
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/entries/{entry_id}")
async def delete_entry(
    entry_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    entry = db.query(TimeEntry).filter(TimeEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Zeiteintrag nicht gefunden")
    db.delete(entry)
    db.commit()
    return {"message": "Zeiteintrag gelöscht"}


# ── Statistik ─────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=TimeStats)
async def get_stats(
    user_id: Optional[UUID] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Heute / Woche / Monat Statistik für einen Benutzer."""
    target_user_id = user_id or current_user.id
    now = datetime.now(timezone.utc)

    # Heute: Mitternacht bis jetzt
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    # Woche: Montag dieser Woche
    week_start = today_start - timedelta(days=now.weekday())
    # Monat: 1. des Monats
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def sum_minutes(from_dt: datetime, to_dt: datetime, only_billable: bool = False) -> int:
        q = db.query(TimeEntry).filter(
            TimeEntry.user_id == target_user_id,
            TimeEntry.started_at >= from_dt,
            TimeEntry.started_at < to_dt,
            TimeEntry.ended_at.isnot(None),
        )
        if only_billable:
            q = q.filter(TimeEntry.billable == True)
        total = 0
        for e in q.all():
            delta = (e.ended_at - e.started_at).total_seconds() / 60
            total += max(0, int(delta) - e.pause_minutes)
        return total

    end = now + timedelta(hours=1)
    return TimeStats(
        today_minutes=sum_minutes(today_start, end),
        week_minutes=sum_minutes(week_start, end),
        month_minutes=sum_minutes(month_start, end),
        today_billable_minutes=sum_minutes(today_start, end, only_billable=True),
        week_billable_minutes=sum_minutes(week_start, end, only_billable=True),
        month_billable_minutes=sum_minutes(month_start, end, only_billable=True),
        today_target_minutes=8 * 60,
        week_target_minutes=40 * 60,
        month_target_minutes=160 * 60,
    )
