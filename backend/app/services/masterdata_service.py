import re
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import or_, cast, String, func
from sqlalchemy.dialects.postgresql import JSONB
from app.models.masterdata import EntityType, FieldDefinition, EntityRecord


def slugify(text: str) -> str:
    """'Meine Kunden' → 'meine-kunden'"""
    text = text.lower().strip()
    text = re.sub(r'[äöüß]', lambda m: {'ä':'ae','ö':'oe','ü':'ue','ß':'ss'}[m.group()], text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')


def make_key(text: str) -> str:
    """'Firmen Name' → 'firmen_name'"""
    text = text.lower().strip()
    text = re.sub(r'[äöüß]', lambda m: {'ä':'ae','ö':'oe','ü':'ue','ß':'ss'}[m.group()], text)
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')


class MasterDataService:

    # ── Stammdaten-Typen ──────────────────────────────────────────────────────

    def list_entity_types(self, db: Session, include_inactive: bool = False) -> List[EntityType]:
        q = db.query(EntityType)
        if not include_inactive:
            q = q.filter(EntityType.is_active == True)
        return q.order_by(EntityType.sort_order, EntityType.name).all()

    def get_entity_type(self, db: Session, slug_or_id: str) -> Optional[EntityType]:
        try:
            uid = UUID(slug_or_id)
            return db.query(EntityType).filter(EntityType.id == uid).first()
        except ValueError:
            return db.query(EntityType).filter(EntityType.slug == slug_or_id).first()

    def create_entity_type(self, db: Session, name: str, icon: str = "Database",
                           color: str = "#6b7280", description: str = None,
                           sort_order: int = 0) -> EntityType:
        slug = slugify(name)
        # Slug eindeutig machen falls bereits vorhanden
        base_slug = slug
        counter = 1
        while db.query(EntityType).filter(EntityType.slug == slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        entity_type = EntityType(
            name=name, slug=slug, icon=icon, color=color,
            description=description, sort_order=sort_order,
            tabs=[],  # Leere Tab-Liste als Default
        )
        db.add(entity_type)
        db.commit()
        db.refresh(entity_type)
        return entity_type

    def update_entity_type(self, db: Session, entity_type: EntityType,
                           updates: dict) -> EntityType:
        for key, value in updates.items():
            if value is not None:
                setattr(entity_type, key, value)
        db.commit()
        db.refresh(entity_type)
        return entity_type

    def delete_entity_type(self, db: Session, entity_type: EntityType) -> None:
        entity_type.is_active = False
        db.commit()

    # ── Felddefinitionen ──────────────────────────────────────────────────────

    def add_field(self, db: Session, entity_type: EntityType,
                  name: str, field_type: str, **kwargs) -> FieldDefinition:
        key = make_key(name)
        # Key eindeutig innerhalb des Typs
        base_key = key
        counter = 1
        while db.query(FieldDefinition).filter(
            FieldDefinition.entity_type_id == entity_type.id,
            FieldDefinition.key == key
        ).first():
            key = f"{base_key}_{counter}"
            counter += 1

        # Höchste sort_order ermitteln
        max_order = db.query(func.max(FieldDefinition.sort_order))\
            .filter(FieldDefinition.entity_type_id == entity_type.id).scalar() or 0

        col_span = kwargs.pop('col_span', 12)
        field = FieldDefinition(
            entity_type_id=entity_type.id,
            name=name,
            key=key,
            field_type=field_type,
            sort_order=max_order + 10,
            col_span=col_span,
            **kwargs
        )
        db.add(field)
        db.commit()
        db.refresh(field)
        return field

    def update_field(self, db: Session, field: FieldDefinition,
                     updates: dict) -> FieldDefinition:
        for key, value in updates.items():
            if value is not None or key in ('options', 'default_value', 'placeholder'):
                setattr(field, key, value)
        db.commit()
        db.refresh(field)
        return field

    def delete_field(self, db: Session, field: FieldDefinition) -> None:
        db.delete(field)
        db.commit()

    def update_field_order(self, db: Session, orders: List[Dict]) -> None:
        for item in orders:
            db.query(FieldDefinition).filter(
                FieldDefinition.id == item['field_id']
            ).update({'sort_order': item['sort_order']})
        db.commit()

    def get_field(self, db: Session, field_id: UUID) -> Optional[FieldDefinition]:
        return db.query(FieldDefinition).filter(FieldDefinition.id == field_id).first()

    # ── Datensätze ────────────────────────────────────────────────────────────

    def list_records(self, db: Session, entity_type: EntityType,
                     search: str = None, page: int = 1,
                     page_size: int = 50,
                     filter_field: str = None,
                     filter_value: str = None) -> Tuple[int, List[EntityRecord]]:
        q = db.query(EntityRecord).filter(
            EntityRecord.entity_type_id == entity_type.id
        )

        if search:
            # Volltextsuche im JSONB-Feld und display_name
            search_term = f"%{search}%"
            q = q.filter(
                or_(
                    EntityRecord.display_name.ilike(search_term),
                    cast(EntityRecord.data, String).ilike(search_term)
                )
            )

        # Optionaler Feldwert-Filter (z.B. für Typ-Filter bei Kontakten)
        if filter_field and filter_value:
            q = q.filter(EntityRecord.data[filter_field].astext == filter_value)

        total = q.count()
        items = q.order_by(EntityRecord.updated_at.desc())\
                 .offset((page - 1) * page_size)\
                 .limit(page_size)\
                 .all()

        return total, items

    def get_record(self, db: Session, record_id: UUID) -> Optional[EntityRecord]:
        return db.query(EntityRecord).filter(EntityRecord.id == record_id).first()

    def create_record(self, db: Session, entity_type: EntityType,
                      data: Dict[str, Any], user_id: UUID = None) -> EntityRecord:
        display_name = self._extract_display_name(entity_type, data)

        record = EntityRecord(
            entity_type_id=entity_type.id,
            data=data,
            display_name=display_name,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def update_record(self, db: Session, record: EntityRecord,
                      data: Dict[str, Any], user_id: UUID = None) -> EntityRecord:
        record.data = data
        record.display_name = self._extract_display_name(record.entity_type, data)
        record.updated_by = user_id
        db.commit()
        db.refresh(record)
        return record

    def delete_record(self, db: Session, record: EntityRecord) -> None:
        db.delete(record)
        db.commit()

    def _extract_display_name(self, entity_type: EntityType,
                               data: Dict[str, Any]) -> str:
        """Ersten Text-Feldwert als Anzeigename verwenden."""
        for field in sorted(entity_type.fields, key=lambda f: f.sort_order):
            if field.field_type == 'text' and data.get(field.key):
                return str(data[field.key])[:300]
        return "Ohne Bezeichnung"


masterdata_service = MasterDataService()
