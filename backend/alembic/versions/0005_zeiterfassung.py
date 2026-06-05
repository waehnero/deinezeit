"""Zeiterfassung: time_entries und time_entry_fields Tabellen

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Felddefinitionen für Zeiteinträge (Custom-Felder) ─────────────────────
    op.create_table(
        'time_entry_fields',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key', sa.String(100), nullable=False),
        sa.Column('field_type', sa.String(30), nullable=False),
        sa.Column('is_required', sa.Boolean, default=False, nullable=False),
        sa.Column('show_in_list', sa.Boolean, default=True, nullable=False),
        sa.Column('sort_order', sa.Integer, default=0, nullable=False),
        sa.Column('col_span', sa.Integer, default=12, nullable=False),
        sa.Column('options', JSONB, nullable=True),
        sa.Column('placeholder', sa.String(200), nullable=True),
        sa.Column('default_value', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
    )

    # ── Zeiteinträge ──────────────────────────────────────────────────────────
    op.create_table(
        'time_entries',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Wer hat gebucht
        sa.Column('user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),

        # Verknüpfung zu Projekt (EntityRecord)
        sa.Column('project_id', UUID(as_uuid=True), nullable=True),
        sa.Column('project_name', sa.String(300), nullable=True),

        # Verknüpfung zu Kontakt (EntityRecord)
        sa.Column('contact_id', UUID(as_uuid=True), nullable=True),
        sa.Column('contact_name', sa.String(300), nullable=True),

        # Kernfelder
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),   # NULL = läuft
        sa.Column('pause_minutes', sa.Integer, default=0, nullable=False),
        sa.Column('note', sa.Text, nullable=True),
        sa.Column('billable', sa.Boolean, default=True, nullable=False),

        # Custom-Felder (erweiterbar wie bei Stammdaten)
        sa.Column('data', JSONB, nullable=False, server_default='{}'),

        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
    )

    # Index für schnelle Abfragen nach Benutzer und Zeitraum
    op.create_index('ix_time_entries_user_id', 'time_entries', ['user_id'])
    op.create_index('ix_time_entries_started_at', 'time_entries', ['started_at'])
    op.create_index('ix_time_entries_project_id', 'time_entries', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_time_entries_project_id', 'time_entries')
    op.drop_index('ix_time_entries_started_at', 'time_entries')
    op.drop_index('ix_time_entries_user_id', 'time_entries')
    op.drop_table('time_entries')
    op.drop_table('time_entry_fields')
