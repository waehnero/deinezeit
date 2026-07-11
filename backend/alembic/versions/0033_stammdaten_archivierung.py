"""Stammdaten: Archivierung statt Löschung + Stundenkonten-FK entschärfen

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-11

Bugfix Datenzusammenhänge:

1. entity_records bekommt archived_at / archived_by:
   Datensätze mit Verweisen aus anderen Modulen (Zeiten, Belege,
   Projekte, Aufgaben, Dateien, …) dürfen nicht mehr hart gelöscht
   werden — sie werden archiviert und können vom Admin wiederhergestellt
   werden.

2. stundenkonten.project_id: ondelete CASCADE → RESTRICT.
   Bisher wurden beim Löschen einer Projektzeit alle vom Kunden
   erworbenen Stundenpakete kommentarlos mitgelöscht (Datenverlust!).
   Jetzt verhindert die Datenbank das Löschen, solange Stundenkonten
   existieren.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def _fk_name():
    """Namen der bestehenden FK-Constraint auf stundenkonten.project_id ermitteln."""
    conn = op.get_bind()
    row = conn.execute(sa.text("""
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'stundenkonten'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = 'project_id'
    """)).fetchone()
    return row[0] if row else None


def upgrade():
    # 1. Archivierungs-Felder
    op.add_column('entity_records',
                  sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('entity_records',
                  sa.Column('archived_by', postgresql.UUID(as_uuid=True),
                            sa.ForeignKey('users.id'), nullable=True))
    op.create_index('ix_entity_records_archived', 'entity_records', ['archived_at'])

    # 2. Stundenkonten-FK: CASCADE → RESTRICT
    name = _fk_name()
    if name:
        op.drop_constraint(name, 'stundenkonten', type_='foreignkey')
    op.create_foreign_key(
        'fk_stundenkonten_project_restrict',
        'stundenkonten', 'entity_records',
        ['project_id'], ['id'],
        ondelete='RESTRICT',
    )


def downgrade():
    op.drop_constraint('fk_stundenkonten_project_restrict',
                       'stundenkonten', type_='foreignkey')
    op.create_foreign_key(
        None, 'stundenkonten', 'entity_records',
        ['project_id'], ['id'],
        ondelete='CASCADE',
    )
    op.drop_index('ix_entity_records_archived', table_name='entity_records')
    op.drop_column('entity_records', 'archived_by')
    op.drop_column('entity_records', 'archived_at')
