"""Dashboard: individuelle Konfiguration je Benutzer

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-04

Erweiterung users:
  - dashboard_config (JSONB): Widget-Anordnung, -Größen und -Sichtbarkeit
    des persönlichen Dashboards. NULL = Standard-Dashboard.
    Ersetzt die bisherige Speicherung im Browser-localStorage, damit das
    Dashboard auf allen Geräten gleich ist.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users',
                  sa.Column('dashboard_config', JSONB(), nullable=True))


def downgrade():
    op.drop_column('users', 'dashboard_config')
