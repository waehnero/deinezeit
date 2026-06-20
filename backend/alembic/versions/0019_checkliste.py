"""Projektplan: Checklisten

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-19

Neue Tabelle:
  - planning_checklist_items  (Checklisten-Elemente an Projekt ODER Aufgabe)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'planning_checklist_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('parent_type', sa.String(length=20), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('text', sa.String(length=1000), nullable=False),
        sa.Column('is_done', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('assignee_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('assignee_contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('assignee_name', sa.String(length=300), nullable=True),
        sa.Column('linked_task_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_checklist_parent', 'planning_checklist_items', ['parent_type', 'parent_id'])


def downgrade():
    op.drop_index('ix_checklist_parent', table_name='planning_checklist_items')
    op.drop_table('planning_checklist_items')
