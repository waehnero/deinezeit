"""Projektplan: konfigurierbare Aufgaben-Felder

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-19

Neue Tabelle:
  - planning_task_fields  (frei definierbare Custom-Felder für Aufgaben)

Tags/Status/Prioritäten werden im bestehenden settings-Key-Value-Store
unter dem Key 'projektplan_settings' als JSON abgelegt -> keine eigene Tabelle.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'planning_task_fields',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False, unique=True),
        sa.Column('field_type', sa.String(length=30), nullable=False),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('show_in_list', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('col_span', sa.Integer(), nullable=False, server_default='12'),
        sa.Column('options', postgresql.JSONB(), nullable=True),
        sa.Column('placeholder', sa.String(length=200), nullable=True),
        sa.Column('default_value', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table('planning_task_fields')
