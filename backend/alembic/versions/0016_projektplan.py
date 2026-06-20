"""Projekt-Aufzeichnungstool (Projektplanung)

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-19

Neue Tabellen:
  - planning_projects             (Planungsprojekt-Kopf, lose an Stammdaten gekoppelt)
  - planning_tasks                (Vorgänge, beliebig tief verschachtelbar via parent_task_id)
  - planning_task_dependencies    (Abhängigkeiten FS/SS/FF/SF für kritischen Pfad)
  - planning_milestones           (Meilensteine/Roadmap)

Erweiterung:
  - time_entries.task_id / task_title  (Zeit -> Aufgabe Kopplung)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    # ── planning_projects ─────────────────────────────────────────────────────
    op.create_table(
        'planning_projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('masterdata_project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('masterdata_project_name', sa.String(length=300), nullable=True),
        sa.Column('contact_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('contact_name', sa.String(length=300), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='offen'),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('origin_task_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_archived', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_planning_projects_masterdata', 'planning_projects', ['masterdata_project_id'])

    # ── planning_tasks ────────────────────────────────────────────────────────
    op.create_table(
        'planning_tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('planning_projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_task_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('planning_tasks.id', ondelete='CASCADE'), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='offen'),
        sa.Column('priority', sa.String(length=30), nullable=False, server_default='mittel'),
        sa.Column('assignee_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('assignee_name', sa.String(length=200), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('estimate_minutes', sa.Integer(), nullable=True),
        sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_milestone', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('data', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_planning_tasks_project', 'planning_tasks', ['project_id'])
    op.create_index('ix_planning_tasks_parent', 'planning_tasks', ['parent_task_id'])

    # ── planning_task_dependencies ────────────────────────────────────────────
    op.create_table(
        'planning_task_dependencies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('predecessor_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('planning_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('successor_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('planning_tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('dep_type', sa.String(length=2), nullable=False, server_default='FS'),
        sa.Column('lag_days', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_planning_deps_succ', 'planning_task_dependencies', ['successor_id'])
    op.create_index('ix_planning_deps_pred', 'planning_task_dependencies', ['predecessor_id'])

    # ── planning_milestones ───────────────────────────────────────────────────
    op.create_table(
        'planning_milestones',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('planning_projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('is_reached', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('color', sa.String(length=20), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_planning_milestones_project', 'planning_milestones', ['project_id'])

    # ── time_entries: Kopplung zur Aufgabe ────────────────────────────────────
    op.add_column('time_entries', sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('time_entries', sa.Column('task_title', sa.String(length=500), nullable=True))
    op.create_index('ix_time_entries_task', 'time_entries', ['task_id'])


def downgrade():
    op.drop_index('ix_time_entries_task', table_name='time_entries')
    op.drop_column('time_entries', 'task_title')
    op.drop_column('time_entries', 'task_id')

    op.drop_index('ix_planning_milestones_project', table_name='planning_milestones')
    op.drop_table('planning_milestones')

    op.drop_index('ix_planning_deps_pred', table_name='planning_task_dependencies')
    op.drop_index('ix_planning_deps_succ', table_name='planning_task_dependencies')
    op.drop_table('planning_task_dependencies')

    op.drop_index('ix_planning_tasks_parent', table_name='planning_tasks')
    op.drop_index('ix_planning_tasks_project', table_name='planning_tasks')
    op.drop_table('planning_tasks')

    op.drop_index('ix_planning_projects_masterdata', table_name='planning_projects')
    op.drop_table('planning_projects')
