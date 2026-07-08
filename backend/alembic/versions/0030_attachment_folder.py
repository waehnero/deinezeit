"""Datacenter: Unterordner je Anlage

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-08

Erweiterung attachments:
  - folder (String) — optionaler Unterordner-Name innerhalb des Kontakt-Ordners.

Zweck: Automatisch archivierte Verkaufsbelege werden je Belegart (z.B.
"Rechnungen", "Angebote") in einem eigenen Unterordner unter dem Kontakt
abgelegt, damit im Datacenter eine saubere Sortierung entsteht.
"""
from alembic import op
import sqlalchemy as sa

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('attachments', sa.Column('folder', sa.String(length=100), nullable=True))
    op.create_index('ix_attachments_folder', 'attachments', ['folder'])


def downgrade():
    op.drop_index('ix_attachments_folder', table_name='attachments')
    op.drop_column('attachments', 'folder')
