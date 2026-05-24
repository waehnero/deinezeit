"""Add tab support to field_definitions and entity_types

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    # Jedes Feld bekommt einen Tab-Namen (z.B. "Allgemein", "Bankdaten")
    op.add_column('field_definitions',
        sa.Column('tab', sa.String(100), nullable=True, server_default=None)
    )

    # EntityType speichert die geordnete Tab-Liste als JSON-Array
    # z.B. ["Allgemein", "Bankdaten", "Kontakt"]
    op.add_column('entity_types',
        sa.Column('tabs', postgresql.JSONB(astext_type=sa.Text()), nullable=True,
                  server_default='[]')
    )


def downgrade():
    op.drop_column('field_definitions', 'tab')
    op.drop_column('entity_types', 'tabs')
