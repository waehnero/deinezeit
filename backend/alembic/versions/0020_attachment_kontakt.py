"""Datacenter: Kontakt je Anlage

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-25

Erweiterung attachments:
  - contact_id   (EntityRecord-ID aus Stammdaten, denormalisiert)
  - contact_name

Zweck: Jede Datei kann zusätzlich zu ihrem Ursprungs-Datensatz (entity_type/
entity_id) einem Kontakt zugeordnet werden. So lässt sich das Datacenter
wahlweise nach Modul ODER nach Kontakt anzeigen ("Kundenakte").

Befüllung des Kontakts erfolgt in der API beim Upload (Vererbung) bzw. über
ein einmaliges Backfill für bestehende Dateien.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('attachments', sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('attachments', sa.Column('contact_name', sa.String(length=300), nullable=True))
    op.create_index('ix_attachments_contact', 'attachments', ['contact_id'])

    # ── Backfill: bestehenden Dateien den Kontakt nachtragen (wo ermittelbar) ──
    conn = op.get_bind()

    # 1) Dateien an Zeiteinträgen -> Kontakt des Zeiteintrags
    conn.execute(sa.text("""
        UPDATE attachments a
        SET contact_id = t.contact_id, contact_name = t.contact_name
        FROM time_entries t
        WHERE a.entity_type = 'zeiterfassung'
          AND a.entity_id = t.id
          AND t.contact_id IS NOT NULL
          AND a.contact_id IS NULL
    """))

    # 2) Dateien an Projektaufgaben -> Kontakt der Aufgabe
    conn.execute(sa.text("""
        UPDATE attachments a
        SET contact_id = pt.contact_id, contact_name = pt.contact_name
        FROM planning_tasks pt
        WHERE a.entity_type = 'planning_task'
          AND a.entity_id = pt.id
          AND pt.contact_id IS NOT NULL
          AND a.contact_id IS NULL
    """))

    # 3) Dateien an Projektaufgaben ohne eigenen Kontakt -> Kontakt des Projekts
    conn.execute(sa.text("""
        UPDATE attachments a
        SET contact_id = pp.contact_id, contact_name = pp.contact_name
        FROM planning_tasks pt
        JOIN planning_projects pp ON pp.id = pt.project_id
        WHERE a.entity_type = 'planning_task'
          AND a.entity_id = pt.id
          AND pt.contact_id IS NULL
          AND pp.contact_id IS NOT NULL
          AND a.contact_id IS NULL
    """))

    # 4) Dateien direkt an Kontakt-Datensätzen -> der Kontakt selbst
    conn.execute(sa.text("""
        UPDATE attachments a
        SET contact_id = er.id, contact_name = er.display_name
        FROM entity_records er
        JOIN entity_types et ON et.id = er.entity_type_id
        WHERE et.slug IN ('kontakte', 'kontakt')
          AND a.entity_type = et.slug
          AND a.entity_id = er.id
          AND a.contact_id IS NULL
    """))


def downgrade():
    op.drop_index('ix_attachments_contact', table_name='attachments')
    op.drop_column('attachments', 'contact_name')
    op.drop_column('attachments', 'contact_id')
