"""
Migration: Kunden + Lieferanten → Kontakte
==========================================
Fuehrt die EntityTypes "kunden" und "lieferanten" in einen einzigen
EntityType "kontakte" zusammen. Ein neues Dropdown-Feld "Typ" unterscheidet
zwischen Kunde, Lieferant und Interessent.

Bestehende Datensaetze werden IN-PLACE migriert (gleiche UUIDs bleiben),
damit alle bestehenden Relation-Felder weiterhin funktionieren.

Aufruf im Container:
    python migrate_kontakte.py
"""

import sys
import uuid

sys.path.insert(0, '/app')

from app.db.base import SessionLocal
from app.models.masterdata import EntityType, FieldDefinition, EntityRecord


def log(msg):
    print(f"  {msg}")


def migrate():
    db = SessionLocal()
    try:
        # 1. Ausgangslage pruefen
        kunden      = db.query(EntityType).filter(EntityType.slug == 'kunden').first()
        lieferanten = db.query(EntityType).filter(EntityType.slug == 'lieferanten').first()
        kontakte    = db.query(EntityType).filter(EntityType.slug == 'kontakte').first()

        if kontakte:
            print("FEHLER: 'kontakte' existiert bereits - Migration schon durchgefuehrt?")
            return

        if not kunden and not lieferanten:
            print("HINWEIS: Weder 'kunden' noch 'lieferanten' gefunden - nichts zu tun.")
            return

        log(f"kunden={'ja' if kunden else 'nein'}, lieferanten={'ja' if lieferanten else 'nein'}")

        # 2. Neuen EntityType "Kontakte" anlegen
        kontakte = EntityType(
            id=uuid.uuid4(),
            name='Kontakte',
            slug='kontakte',
            icon='Users',
            color='#f97316',
            description='Kunden, Lieferanten und Interessenten',
            is_active=True,
            sort_order=0,
        )
        db.add(kontakte)
        db.flush()
        log(f"EntityType 'kontakte' angelegt")

        # 3. "Typ"-Feld als erstes Feld
        typ_field = FieldDefinition(
            id=uuid.uuid4(),
            entity_type_id=kontakte.id,
            name='Typ',
            key='typ',
            field_type='dropdown',
            options=['Kunde', 'Lieferant', 'Interessent'],
            is_required=True,
            show_in_list=True,
            sort_order=0,
            col_span=6,
            placeholder=None,
            default_value='Kunde',
            linked_type_slug=None,
        )
        db.add(typ_field)
        log("Feld 'Typ' angelegt")

        # 4. Felder von Kunden & Lieferanten uebernehmen (entity_type_id umhaengen)
        existing_keys = {'typ'}
        sort_order = 1

        for source_et, label in [(kunden, 'kunden'), (lieferanten, 'lieferanten')]:
            if not source_et:
                continue
            fields = (
                db.query(FieldDefinition)
                .filter(FieldDefinition.entity_type_id == source_et.id)
                .order_by(FieldDefinition.sort_order)
                .all()
            )
            log(f"Uebernehme {len(fields)} Felder aus '{label}'")
            for f in fields:
                if f.key in existing_keys:
                    log(f"  '{f.key}' uebersprungen (Duplikat)")
                    continue
                existing_keys.add(f.key)
                f.entity_type_id = kontakte.id
                f.sort_order = sort_order
                sort_order += 1
                log(f"  '{f.key}' umgehaengt")

        db.flush()

        # 5. Datensaetze in-place migrieren (IDs bleiben gleich!)
        if kunden:
            records = db.query(EntityRecord).filter(EntityRecord.entity_type_id == kunden.id).all()
            log(f"Migriere {len(records)} Kunden-Datensaetze")
            for r in records:
                data = dict(r.data)
                data['typ'] = 'Kunde'
                r.data = data
                r.entity_type_id = kontakte.id

        if lieferanten:
            records = db.query(EntityRecord).filter(EntityRecord.entity_type_id == lieferanten.id).all()
            log(f"Migriere {len(records)} Lieferanten-Datensaetze")
            for r in records:
                data = dict(r.data)
                data['typ'] = 'Lieferant'
                r.data = data
                r.entity_type_id = kontakte.id

        db.flush()

        # 6. Relation-Felder anderer Typen anpassen
        old_slugs = [s for s in ['kunden', 'lieferanten'] if s in (['kunden'] if kunden else []) + (['lieferanten'] if lieferanten else [])]
        if old_slugs:
            rel_fields = (
                db.query(FieldDefinition)
                .filter(FieldDefinition.field_type == 'relation')
                .filter(FieldDefinition.linked_type_slug.in_(old_slugs))
                .all()
            )
            log(f"Aktualisiere {len(rel_fields)} Relation-Felder -> 'kontakte'")
            for f in rel_fields:
                f.linked_type_slug = 'kontakte'
            db.flush()

        # 7. Alte EntityTypes loeschen (Felder & Records bereits umgehaengt)
        if kunden:
            db.delete(kunden)
            log("'kunden' geloescht")
        if lieferanten:
            db.delete(lieferanten)
            log("'lieferanten' geloescht")

        # 8. Commit
        db.commit()
        print()
        print("  Migration erfolgreich!")
        print("  Kontakte sind unter /masterdata/kontakte erreichbar.")
        print()

    except Exception as e:
        db.rollback()
        print(f"\n  FEHLER: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()


if __name__ == '__main__':
    print()
    print("  DeineZeit - Migration: Kunden + Lieferanten -> Kontakte")
    print("  " + "-" * 50)
    print()
    migrate()
