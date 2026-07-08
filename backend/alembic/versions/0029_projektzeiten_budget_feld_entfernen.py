"""Projektzeiten: manuelles Budget-Feld entfernen

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-07

Das Budget einer Projektzeit wird ab jetzt ausschließlich über
Stundenkonten (Tabelle stundenkonten, Migration 0028) geführt.
Ein früher manuell angelegtes Custom-Feld „Budget" am Stammdaten-Typ
'projektzeiten' ist damit überflüssig und wird entfernt — inklusive
der zugehörigen Werte im JSONB-Feld data der Datensätze.
"""
from alembic import op
import sqlalchemy as sa

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Keys der zu löschenden Budget-Felder ermitteln (Name ODER Key = "budget…")
    rows = conn.execute(sa.text("""
        SELECT fd.id, fd.key FROM field_definitions fd
        JOIN entity_types et ON et.id = fd.entity_type_id
        WHERE et.slug = 'projektzeiten'
          AND (lower(fd.name) LIKE 'budget%' OR lower(fd.key) LIKE 'budget%')
    """)).fetchall()

    for field_id, key in rows:
        # Wert aus allen Projektzeit-Datensätzen entfernen
        conn.execute(sa.text("""
            UPDATE entity_records er
            SET data = er.data - :key
            FROM entity_types et
            WHERE er.entity_type_id = et.id AND et.slug = 'projektzeiten'
        """), {"key": key})
        # Felddefinition löschen
        conn.execute(sa.text(
            "DELETE FROM field_definitions WHERE id = :id"
        ), {"id": field_id})


def downgrade():
    # Bewusst kein Downgrade: das gelöschte Custom-Feld und seine Werte
    # lassen sich nicht wiederherstellen. Bei Bedarf Feld manuell neu anlegen.
    pass
