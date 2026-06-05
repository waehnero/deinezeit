from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
import csv
import io
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from app.db.base import get_db
from app.api.deps import get_current_user, require_admin
from app.models.user import User
from app.models.masterdata import EntityType, FieldDefinition, EntityRecord
from app.schemas.masterdata import (
    EntityTypeCreate, EntityTypeUpdate, EntityTypeResponse,
    FieldDefinitionCreate, FieldDefinitionUpdate, FieldDefinitionResponse,
    EntityRecordCreate, EntityRecordUpdate, EntityRecordResponse,
    EntityRecordListResponse, UpdateFieldSortOrders
)
from app.services.masterdata_service import masterdata_service

router = APIRouter(prefix="/masterdata", tags=["Stammdaten"])


# ─── Stammdaten-Typen ─────────────────────────────────────────────────────────

@router.get("/types", response_model=List[EntityTypeResponse])
async def list_entity_types(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Stammdaten-Typen abrufen (z.B. Kunden, Lieferanten, Projekte)."""
    types = masterdata_service.list_entity_types(db)
    result = []
    for et in types:
        count = db.query(EntityRecord).filter(EntityRecord.entity_type_id == et.id).count()
        r = EntityTypeResponse.model_validate(et)
        r.record_count = count
        result.append(r)
    return result


@router.post("/types", response_model=EntityTypeResponse)
async def create_entity_type(
    body: EntityTypeCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Neuen Stammdaten-Typ anlegen (nur Admin)."""
    return masterdata_service.create_entity_type(
        db, body.name, body.icon, body.color, body.description, body.sort_order
    )


@router.get("/types/{slug}", response_model=EntityTypeResponse)
async def get_entity_type(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Einen Stammdaten-Typ abrufen (inkl. aller Felddefinitionen)."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    count = db.query(EntityRecord).filter(EntityRecord.entity_type_id == et.id).count()
    r = EntityTypeResponse.model_validate(et)
    r.record_count = count
    return r


@router.put("/types/{slug}", response_model=EntityTypeResponse)
async def update_entity_type(
    slug: str,
    body: EntityTypeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Stammdaten-Typ bearbeiten (nur Admin)."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    return masterdata_service.update_entity_type(db, et, body.model_dump(exclude_none=True))


@router.delete("/types/{slug}")
async def delete_entity_type(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Stammdaten-Typ deaktivieren (nur Admin)."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    masterdata_service.delete_entity_type(db, et)
    return {"message": f"'{et.name}' wurde deaktiviert"}


# ─── Felddefinitionen ─────────────────────────────────────────────────────────

@router.post("/types/{slug}/fields", response_model=FieldDefinitionResponse)
async def add_field(
    slug: str,
    body: FieldDefinitionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Neues Feld zum Stammdaten-Typ hinzufügen."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    valid_types = ['text', 'number', 'date', 'email', 'phone', 'dropdown',
                   'checkbox', 'textarea', 'url', 'relation']
    if body.field_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Ungültiger Feldtyp. Erlaubt: {valid_types}")

    if body.field_type == 'relation' and not body.linked_type_slug:
        raise HTTPException(status_code=400, detail="Verknüpfungs-Felder benötigen einen Ziel-Typ (linked_type_slug)")

    return masterdata_service.add_field(
        db, et, body.name, body.field_type,
        is_required=body.is_required,
        is_unique=body.is_unique,
        show_in_list=body.show_in_list,
        col_span=body.col_span,
        tab=body.tab,
        options=body.options,
        placeholder=body.placeholder,
        default_value=body.default_value,
        linked_type_slug=body.linked_type_slug,
    )


@router.put("/types/{slug}/fields/{field_id}", response_model=FieldDefinitionResponse)
async def update_field(
    slug: str,
    field_id: UUID,
    body: FieldDefinitionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Felddefinition bearbeiten."""
    field = masterdata_service.get_field(db, field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Feld nicht gefunden")
    return masterdata_service.update_field(db, field, body.model_dump())


@router.delete("/types/{slug}/fields/{field_id}")
async def delete_field(
    slug: str,
    field_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Feld entfernen."""
    field = masterdata_service.get_field(db, field_id)
    if not field:
        raise HTTPException(status_code=404, detail="Feld nicht gefunden")
    masterdata_service.delete_field(db, field)
    return {"message": f"Feld '{field.name}' wurde entfernt"}


@router.put("/types/{slug}/fields-order")
async def update_field_order(
    slug: str,
    body: UpdateFieldSortOrders,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Reihenfolge der Felder aktualisieren."""
    masterdata_service.update_field_order(
        db, [{"field_id": o.field_id, "sort_order": o.sort_order} for o in body.orders]
    )
    return {"message": "Reihenfolge gespeichert"}


@router.put("/types/{slug}/fields-layout")
async def update_fields_layout(
    slug: str,
    layout: List[dict],
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Reihenfolge, Breite UND Tab-Zuweisung aller Felder in einem Aufruf speichern."""
    from app.models.masterdata import FieldDefinition as FD
    for item in layout:
        update_data = {
            "sort_order": item["sort_order"],
            "col_span":   item.get("col_span", 12),
        }
        # Tab nur schreiben wenn explizit mitgegeben (auch None/null ist gültig)
        if "tab" in item:
            update_data["tab"] = item["tab"]
        db.query(FD).filter(FD.id == item["field_id"]).update(update_data)
    db.commit()
    return {"message": "Layout gespeichert"}


@router.put("/types/{slug}/tabs")
async def update_tabs(
    slug: str,
    body: dict,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """Tab-Liste des Stammdaten-Typs aktualisieren.
    Body: { "tabs": ["Allgemein", "Bankdaten", "Kontakt"] }
    """
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    tabs = body.get("tabs", [])
    if not isinstance(tabs, list):
        raise HTTPException(status_code=400, detail="tabs muss eine Liste sein")

    # Tabs bereinigen: leere Strings entfernen, Duplikate entfernen (Reihenfolge erhalten)
    seen = set()
    clean_tabs = []
    for t in tabs:
        t = str(t).strip()
        if t and t not in seen:
            seen.add(t)
            clean_tabs.append(t)

    et.tabs = clean_tabs
    db.commit()
    db.refresh(et)
    return {"tabs": et.tabs}


# ─── Datensätze ───────────────────────────────────────────────────────────────

@router.get("/types/{slug}/records", response_model=EntityRecordListResponse)
async def list_records(
    slug: str,
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    filter_field: Optional[str] = Query(None),
    filter_value: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Datensätze eines Stammdaten-Typs abrufen (mit Suche & Paginierung)."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    total, items = masterdata_service.list_records(
        db, et, search, page, page_size, filter_field, filter_value
    )
    return EntityRecordListResponse(total=total, page=page, page_size=page_size, items=items)


@router.post("/types/{slug}/records", response_model=EntityRecordResponse)
async def create_record(
    slug: str,
    body: EntityRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Neuen Datensatz anlegen."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")
    return masterdata_service.create_record(db, et, body.data, current_user.id)


@router.get("/types/{slug}/records/{record_id}", response_model=EntityRecordResponse)
async def get_record(
    slug: str,
    record_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Einen Datensatz abrufen."""
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")
    return record


@router.put("/types/{slug}/records/{record_id}", response_model=EntityRecordResponse)
async def update_record(
    slug: str,
    record_id: UUID,
    body: EntityRecordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Datensatz bearbeiten."""
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")
    return masterdata_service.update_record(db, record, body.data, current_user.id)


@router.get("/types/{slug}/records/export/csv")
async def export_records_csv(
    slug: str,
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Alle Datensätze als CSV exportieren."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    _, records = masterdata_service.list_records(db, et, search, page=1, page_size=10000)
    fields = sorted(et.fields, key=lambda f: f.sort_order)

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_ALL)

    # Header
    writer.writerow([f.name for f in fields])

    # Daten
    for record in records:
        writer.writerow([record.data.get(f.key, '') for f in fields])

    output.seek(0)
    filename = f"{slug}_export.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.post("/types/{slug}/records/import/csv")
async def import_records_csv(
    slug: str,
    rows: List[dict],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Datensätze aus CSV importieren (bereits geparste Zeilen als JSON)."""
    et = masterdata_service.get_entity_type(db, slug)
    if not et:
        raise HTTPException(status_code=404, detail="Stammdaten-Typ nicht gefunden")

    created = 0
    for row in rows:
        masterdata_service.create_record(db, et, row, current_user.id)
        created += 1

    return {"message": f"{created} Datensätze importiert", "count": created}


@router.delete("/types/{slug}/records/{record_id}")
async def delete_record(
    slug: str,
    record_id: UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Datensatz löschen."""
    record = masterdata_service.get_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden")
    masterdata_service.delete_record(db, record)
    return {"message": "Datensatz gelöscht"}
