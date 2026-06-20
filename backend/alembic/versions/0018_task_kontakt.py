"""Projektplan: Kontakt je Aufgabe

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-19

Erweiterung planning_tasks:
  - contact_id   (EntityRecord-ID aus Stammdaten, denormalisiert)
  - contact_name

Default-Verhalten (in der API): Eine neue Aufgabe erbt den Kontakt des
Projekts bzw. der Elternaufgabe, sofern keiner gezielt gesetzt wird.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('planning_tasks', sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('planning_tasks', sa.Column('contact_name', sa.String(length=300), nullable=True))
    op.create_index('ix_planning_tasks_contact', 'planning_tasks', ['contact_id'])


def downgrade():
    op.drop_index('ix_planning_tasks_contact', table_name='planning_tasks')
    op.drop_column('planning_tasks', 'contact_name')
    op.drop_column('planning_tasks', 'contact_id')
