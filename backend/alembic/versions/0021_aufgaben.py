"""Aufgabenmodul (zentrale To-do-Liste)

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-03

Neue Tabelle:
  - todos   (Aufgaben mit losen Verknüpfungen zu Projektplan, Zeiterfassung
             und Stammdaten; source/source_meta für den späteren Mail-Ingest)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'todos',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='offen'),
        sa.Column('priority', sa.String(length=30), nullable=False, server_default='mittel'),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('due_time', sa.Time(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('assignee_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('assignee_name', sa.String(length=200), nullable=True),
        sa.Column('planning_project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('planning_project_name', sa.String(length=300), nullable=True),
        sa.Column('planning_task_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('planning_task_title', sa.String(length=500), nullable=True),
        sa.Column('time_entry_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('record_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('record_name', sa.String(length=300), nullable=True),
        sa.Column('record_type_slug', sa.String(length=100), nullable=True),
        sa.Column('source', sa.String(length=30), nullable=False, server_default='manuell'),
        sa.Column('source_meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('data', postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_by_name', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Indizes für die häufigsten Filter (Liste, Kanban, Kalender)
    op.create_index('ix_todos_status', 'todos', ['status'])
    op.create_index('ix_todos_assignee', 'todos', ['assignee_id'])
    op.create_index('ix_todos_due_date', 'todos', ['due_date'])
    op.create_index('ix_todos_planning_task', 'todos', ['planning_task_id'])
    op.create_index('ix_todos_record', 'todos', ['record_id'])


def downgrade():
    op.drop_index('ix_todos_record', table_name='todos')
    op.drop_index('ix_todos_planning_task', table_name='todos')
    op.drop_index('ix_todos_due_date', table_name='todos')
    op.drop_index('ix_todos_assignee', table_name='todos')
    op.drop_index('ix_todos_status', table_name='todos')
    op.drop_table('todos')
