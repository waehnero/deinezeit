"""Kontakte: Finanz-Tab mit IBAN, BIC und Bankname

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-03

Fügt zum Kontakte-Stammdatentyp drei neue Felder hinzu:
  - IBAN      (key: iban,     tab: Finanz, sort_order: 20)
  - BIC       (key: bic,      tab: Finanz, sort_order: 21)
  - Bankname  (key: bankname, tab: Finanz, sort_order: 22)

Und ergänzt den Tab "Finanz" im tabs-Array des Kontakte-Typs.

Sicherheitsprüfungen:
  - Felder werden NUR angelegt wenn der key noch nicht existiert
  - Tab wird NUR ergänzt wenn noch nicht vorhanden
  - Läuft sicher auf Neu- und Bestandsinstallationen
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # -------------------------------------------------------------------------
    # 1. Tab "Finanz" zum Kontakte-Typ hinzufügen (nur wenn noch nicht drin)
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        UPDATE entity_types
        SET tabs = CASE
            WHEN tabs IS NULL THEN '["Finanz"]'::jsonb
            WHEN NOT (tabs @> '["Finanz"]'::jsonb) THEN tabs || '["Finanz"]'::jsonb
            ELSE tabs
        END
        WHERE slug = 'kontakte'
    """))

    # -------------------------------------------------------------------------
    # 2. Neue Felder anlegen — je nur wenn key noch nicht vorhanden
    # -------------------------------------------------------------------------
    conn.execute(sa.text("""
        INSERT INTO field_definitions
            (id, entity_type_id, name, key, field_type, is_required,
             show_in_list, sort_order, placeholder, tab)
        SELECT
            gen_random_uuid(),
            et.id,
            fd.fname, fd.fkey, fd.ftype,
            false,
            false,
            fd.fsort::integer,
            fd.fplaceholder,
            'Finanz'
        FROM entity_types et,
        (VALUES
            ('IBAN',     'iban',     'text', '20', 'AT12 3456 7890 1234 5678'),
            ('BIC',      'bic',      'text', '21', 'BKAUATWW'),
            ('Bankname', 'bankname', 'text', '22', 'z.B. Bank Austria')
        ) AS fd(fname, fkey, ftype, fsort, fplaceholder)
        WHERE et.slug = 'kontakte'
          AND NOT EXISTS (
              SELECT 1 FROM field_definitions fd2
              WHERE fd2.entity_type_id = et.id
                AND fd2.key = fd.fkey
          )
    """))


def downgrade() -> None:
    conn = op.get_bind()

    # Felder entfernen
    conn.execute(sa.text("""
        DELETE FROM field_definitions
        WHERE key IN ('iban', 'bic', 'bankname')
          AND entity_type_id = (
              SELECT id FROM entity_types WHERE slug = 'kontakte'
          )
    """))

    # Tab "Finanz" aus dem Array entfernen
    conn.execute(sa.text("""
        UPDATE entity_types
        SET tabs = (
            SELECT jsonb_agg(elem)
            FROM jsonb_array_elements(tabs) AS elem
            WHERE elem::text != '"Finanz"'
        )
        WHERE slug = 'kontakte'
    """))
