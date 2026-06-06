"""Verknüpfungs-Felder: linked_type_slug für Relation-Feldtyp

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-22

"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'field_definitions',
        sa.Column('linked_type_slug', sa.String(100), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('field_definitions', 'linked_type_slug')
