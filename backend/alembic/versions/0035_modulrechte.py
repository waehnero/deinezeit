"""Benutzer: Modulrechte (allowed_modules)

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-12

Der Admin kann pro Benutzer festlegen, welche Module er verwenden darf.
NULL = alle Module erlaubt (Standard) — Bestandsbenutzer behalten damit
ihr bisheriges Verhalten, es ändert sich beim Deploy nichts sichtbar.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0035'
down_revision = '0034'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('allowed_modules', JSONB, nullable=True))


def downgrade():
    op.drop_column('users', 'allowed_modules')
