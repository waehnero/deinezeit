"""Grid-Layout: col_span für Feldbreite

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21

"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # col_span: Wie viele der 12 Rasterspalten belegt das Feld
    # 3 = 25%, 4 = 33%, 6 = 50%, 9 = 75%, 12 = 100%
    op.add_column('field_definitions',
        sa.Column('col_span', sa.Integer(), nullable=False, server_default='12')
    )

    # Standard-Felder auf sinnvolle Breiten setzen
    # Kunden
    op.execute("""
        UPDATE field_definitions SET col_span = 12 WHERE key = 'firmenname';
        UPDATE field_definitions SET col_span = 6  WHERE key = 'ansprechperson';
        UPDATE field_definitions SET col_span = 6  WHERE key = 'email';
        UPDATE field_definitions SET col_span = 6  WHERE key = 'telefon';
        UPDATE field_definitions SET col_span = 6  WHERE key = 'webseite';
        UPDATE field_definitions SET col_span = 12 WHERE key = 'adresse';
        UPDATE field_definitions SET col_span = 12 WHERE key = 'notizen';
        UPDATE field_definitions SET col_span = 12 WHERE key = 'beschreibung';
        UPDATE field_definitions SET col_span = 12 WHERE key = 'lieferkategorien';
        UPDATE field_definitions SET col_span = 12 WHERE key = 'projektname';
        UPDATE field_definitions SET col_span = 6  WHERE key = 'kunde';
        UPDATE field_definitions SET col_span = 6  WHERE key = 'status';
        UPDATE field_definitions SET col_span = 4  WHERE key = 'startdatum';
        UPDATE field_definitions SET col_span = 4  WHERE key = 'enddatum';
        UPDATE field_definitions SET col_span = 4  WHERE key = 'budget';
    """)


def downgrade() -> None:
    op.drop_column('field_definitions', 'col_span')
