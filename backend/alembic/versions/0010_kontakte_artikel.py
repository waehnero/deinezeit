"""Stammdaten: Kunden+Lieferanten → Kontakte, neue Artikel-Typ

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-02

Migriert bestehende Installationen:
  - Kunden-Datensätze werden nach Kontakte übernommen (typ=Kunde)
  - Lieferanten-Datensätze werden nach Kontakte übernommen (typ=Lieferant)
  - Alte Kunden/Lieferanten entity_types werden gelöscht (CASCADE löscht
    field_definitions und entity_records automatisch)
  - Neuer Typ "Artikel" wird angelegt

Funktioniert sowohl auf bestehenden Installationen (die 0002-Seed haben)
als auch auf Neuinstallationen (wo 0002 bereits Kunden/Lieferanten anlegt).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # -------------------------------------------------------------------------
    # 1. Kontakte-Typ anlegen (nur wenn noch nicht vorhanden)
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO entity_types (id, name, slug, icon, color, description, sort_order)
        SELECT gen_random_uuid(), 'Kontakte', 'kontakte', 'Users', '#3b82f6',
               'Kunden, Lieferanten und Interessenten', 1
        WHERE NOT EXISTS (SELECT 1 FROM entity_types WHERE slug = 'kontakte')
    """))

    # -------------------------------------------------------------------------
    # 2. Felder für Kontakte anlegen (nur wenn Kontakte noch keine Felder hat)
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required, show_in_list,
             sort_order, placeholder, options)
        SELECT
            gen_random_uuid(),
            et.id,
            fd.name, fd.key, fd.field_type,
            fd.is_required::boolean,
            fd.show_in_list::boolean,
            fd.sort_order::integer,
            fd.placeholder,
            fd.options::jsonb
        FROM entity_types et,
        (VALUES
            ('Typ',             'typ',            'dropdown', 'true',  'true',  '1',  '',                            '["Kunde","Lieferant","Interessent"]'),
            ('Firmenname',      'firmenname',     'text',     'true',  'true',  '2',  'z.B. Muster GmbH',            'null'),
            ('Ansprechperson',  'ansprechperson', 'text',     'false', 'true',  '3',  'Vor- und Nachname',           'null'),
            ('E-Mail',          'email',          'email',    'false', 'true',  '4',  'info@firma.at',               'null'),
            ('Telefon',         'telefon',        'phone',    'false', 'false', '5',  '+43 1 234 567',               'null'),
            ('Mobil',           'mobil',          'phone',    'false', 'false', '6',  '+43 664 123 456',             'null'),
            ('Adresse',         'adresse',        'textarea', 'false', 'false', '7',  'Straße, PLZ Ort',             'null'),
            ('PLZ',             'plz',            'text',     'false', 'false', '8',  '1010',                        'null'),
            ('Ort',             'ort',            'text',     'false', 'true',  '9',  'Wien',                        'null'),
            ('Land',            'land',           'text',     'false', 'false', '10', 'Österreich',                  'null'),
            ('UID-Nummer',      'uid',            'text',     'false', 'false', '11', 'ATU12345678',                 'null'),
            ('Webseite',        'webseite',       'url',      'false', 'false', '12', 'https://',                    'null'),
            ('Zahlungsziel',    'zahlungsziel',   'number',   'false', 'false', '13', '30',                          'null'),
            ('Kategorie',       'kategorie',      'text',     'false', 'false', '14', 'z.B. Büromaterial',           'null'),
            ('Notizen',         'notizen',        'textarea', 'false', 'false', '15', '',                            'null')
        ) AS fd(name, key, field_type, is_required, show_in_list, sort_order, placeholder, options)
        WHERE et.slug = 'kontakte'
          AND NOT EXISTS (
              SELECT 1 FROM field_definitions fd2 WHERE fd2.entity_type_id = et.id
          )
    """))

    # -------------------------------------------------------------------------
    # 3. Kunden-Datensätze → Kontakte migrieren
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO entity_records (id, entity_type_id, data, display_name, created_by, updated_by, created_at, updated_at)
        SELECT
            er.id,
            (SELECT id FROM entity_types WHERE slug = 'kontakte'),
            er.data || '{"typ": "Kunde"}'::jsonb,
            er.display_name,
            er.created_by,
            er.updated_by,
            er.created_at,
            er.updated_at
        FROM entity_records er
        JOIN entity_types et ON er.entity_type_id = et.id
        WHERE et.slug = 'kunden'
          AND NOT EXISTS (
              SELECT 1 FROM entity_records er2
              WHERE er2.id = er.id
                AND er2.entity_type_id = (SELECT id FROM entity_types WHERE slug = 'kontakte')
          )
    """))

    # -------------------------------------------------------------------------
    # 4. Lieferanten-Datensätze → Kontakte migrieren
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO entity_records (id, entity_type_id, data, display_name, created_by, updated_by, created_at, updated_at)
        SELECT
            gen_random_uuid(),
            (SELECT id FROM entity_types WHERE slug = 'kontakte'),
            er.data || '{"typ": "Lieferant"}'::jsonb,
            er.display_name,
            er.created_by,
            er.updated_by,
            er.created_at,
            er.updated_at
        FROM entity_records er
        JOIN entity_types et ON er.entity_type_id = et.id
        WHERE et.slug = 'lieferanten'
    """))

    # -------------------------------------------------------------------------
    # 5. Alte Typen löschen (CASCADE entfernt field_definitions + entity_records)
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        DELETE FROM entity_types WHERE slug IN ('kunden', 'lieferanten')
    """))

    # -------------------------------------------------------------------------
    # 6. Artikel-Typ anlegen (nur wenn noch nicht vorhanden)
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO entity_types (id, name, slug, icon, color, description, sort_order)
        SELECT gen_random_uuid(), 'Artikel', 'artikel', 'Package', '#10b981',
               'Produkte und Dienstleistungen', 2
        WHERE NOT EXISTS (SELECT 1 FROM entity_types WHERE slug = 'artikel')
    """))

    # -------------------------------------------------------------------------
    # 7. Felder für Artikel anlegen
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required, show_in_list,
             sort_order, placeholder)
        SELECT
            gen_random_uuid(),
            et.id,
            fd.name, fd.key, fd.field_type,
            fd.is_required::boolean,
            fd.show_in_list::boolean,
            fd.sort_order::integer,
            fd.placeholder
        FROM entity_types et,
        (VALUES
            ('Bezeichnung',    'bezeichnung',    'text',     'true',  'true',  '1', 'z.B. Beratungsleistung'),
            ('Artikelnummer',  'artikelnummer',  'text',     'false', 'true',  '2', 'z.B. ART-001'),
            ('Preis',          'preis',          'number',   'false', 'true',  '3', '0.00'),
            ('Beschreibung',   'beschreibung',   'textarea', 'false', 'false', '4', '')
        ) AS fd(name, key, field_type, is_required, show_in_list, sort_order, placeholder)
        WHERE et.slug = 'artikel'
          AND NOT EXISTS (
              SELECT 1 FROM field_definitions fd2 WHERE fd2.entity_type_id = et.id
          )
    """))

    # -------------------------------------------------------------------------
    # 8. Projekte sort_order aktualisieren (falls vorhanden)
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE entity_types SET sort_order = 3 WHERE slug = 'projekte'
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Artikel löschen
    conn.execute(sa.text("DELETE FROM entity_types WHERE slug = 'artikel'"))

    # Kontakte löschen
    conn.execute(sa.text("DELETE FROM entity_types WHERE slug = 'kontakte'"))

    # Kunden und Lieferanten wiederherstellen (leer — Daten sind verloren)
    conn.execute(sa.text("""
        INSERT INTO entity_types (id, name, slug, icon, color, description, sort_order)
        VALUES
            (gen_random_uuid(), 'Kunden',     'kunden',     'Users',   '#3b82f6', 'Kundenstammdaten',      1),
            (gen_random_uuid(), 'Lieferanten','lieferanten','Package', '#10b981', 'Lieferantenstammdaten', 2)
    """))
