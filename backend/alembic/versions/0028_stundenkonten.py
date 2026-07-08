"""Stundenkonten für Projektzeit-Budgets

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-06

Neue Tabelle stundenkonten:
  Vom Kunden im Voraus erworbene Stundenpakete je Projektzeit
  (entity_records vom Typ 'projektzeiten'). Das Budget einer
  Projektzeit = Summe der Stundenkonten; verbraucht wird es durch
  verrechenbare Zeiteinträge. Der Restwert wird laufend berechnet
  und in Zeiterfassung + Stammdaten angezeigt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stundenkonten',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('entity_records.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('bezeichnung', sa.String(length=300), nullable=True),
        sa.Column('stunden', sa.Numeric(8, 2), nullable=False),
        sa.Column('preis', sa.Numeric(12, 2), nullable=True),
        sa.Column('erworben_am', sa.Date(), nullable=False),
        sa.Column('notiz', sa.Text(), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_stundenkonten_project', 'stundenkonten', ['project_id'])


def downgrade():
    op.drop_index('ix_stundenkonten_project', table_name='stundenkonten')
    op.drop_table('stundenkonten')
