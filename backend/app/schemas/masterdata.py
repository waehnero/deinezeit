from pydantic import BaseModel, field_validator
from typing import Optional, List, Any, Dict
from uuid import UUID
from datetime import datetime


# ── Felddefinitionen ──────────────────────────────────────────────────────────

class FieldDefinitionBase(BaseModel):
    name: str
    key: str
    field_type: str   # text, number, date, email, phone, dropdown, checkbox, textarea, url, relation
    is_required: bool = False
    is_unique: bool = False
    show_in_list: bool = True
    sort_order: int = 0
    col_span: int = 12   # 3=25%, 4=33%, 6=50%, 9=75%, 12=100%
    tab: Optional[str] = None  # Tab-Name, z.B. "Allgemein", "Bankdaten"
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    linked_type_slug: Optional[str] = None  # Für relation-Felder: Slug des Ziel-EntityType


class FieldDefinitionCreate(FieldDefinitionBase):
    pass


class FieldDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    field_type: Optional[str] = None
    is_required: Optional[bool] = None
    is_unique: Optional[bool] = None
    show_in_list: Optional[bool] = None
    sort_order: Optional[int] = None
    col_span: Optional[int] = None
    tab: Optional[str] = None
    options: Optional[List[str]] = None
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    linked_type_slug: Optional[str] = None


class FieldDefinitionResponse(FieldDefinitionBase):
    id: UUID
    entity_type_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ── Stammdaten-Typen ─────────────────────────────────────────────────────────

class EntityTypeBase(BaseModel):
    name: str
    slug: str
    icon: Optional[str] = "Database"
    color: Optional[str] = "#6b7280"
    description: Optional[str] = None
    sort_order: int = 0


class EntityTypeCreate(BaseModel):
    """Eingabe-Schema: slug wird vom Backend automatisch aus dem Namen generiert."""
    name: str
    icon: Optional[str] = "Database"
    color: Optional[str] = "#6b7280"
    description: Optional[str] = None
    sort_order: int = 0


class EntityTypeUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class EntityTypeResponse(EntityTypeBase):
    id: UUID
    is_active: bool
    record_count: int = 0
    tabs: List[str] = []           # Geordnete Tab-Liste, z.B. ["Allgemein", "Bankdaten"]
    fields: List[FieldDefinitionResponse] = []
    created_at: datetime

    # None aus DB → leere Liste (Spalte neu, Altdaten haben NULL)
    @field_validator('tabs', mode='before')
    @classmethod
    def tabs_none_to_list(cls, v):
        return v if v is not None else []

    class Config:
        from_attributes = True


# ── Datensätze ────────────────────────────────────────────────────────────────

class EntityRecordCreate(BaseModel):
    data: Dict[str, Any]


class EntityRecordUpdate(BaseModel):
    data: Dict[str, Any]


class EntityRecordResponse(BaseModel):
    id: UUID
    entity_type_id: UUID
    data: Dict[str, Any]
    display_name: Optional[str]
    created_by: Optional[UUID]
    updated_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EntityRecordListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[EntityRecordResponse]


# ── Feldreihenfolge ───────────────────────────────────────────────────────────

class FieldSortOrder(BaseModel):
    field_id: UUID
    sort_order: int


class UpdateFieldSortOrders(BaseModel):
    orders: List[FieldSortOrder]
