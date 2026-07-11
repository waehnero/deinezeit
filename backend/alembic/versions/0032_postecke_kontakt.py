"""Postecke: Kontaktbezug je Post (für das Datacenter-Postsarchiv)

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-11

Erweiterung social_posts:
  - kontakt_id   (UUID)   — optionaler Stammdaten-Kontakt (denormalisiert)
  - kontakt_name (String) — Anzeigename des Kontakts

Zweck: Archivierte Posts werden im Datacenter unter dem Kontakt im
Unterordner "Postsarchiv" gespiegelt (ohne Kontakt: global), samt Fotos
und Content — analog zum Beleg-Archiv des Verkaufsmoduls.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0032'
down_revision = '0031'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_posts', sa.Column('kontakt_id', UUID(as_uuid=True), nullable=True))
    op.add_column('social_posts', sa.Column('kontakt_name', sa.String(length=300), nullable=True))
    op.create_index('ix_social_posts_kontakt', 'social_posts', ['kontakt_id'])


def downgrade():
    op.drop_index('ix_social_posts_kontakt', table_name='social_posts')
    op.drop_column('social_posts', 'kontakt_name')
    op.drop_column('social_posts', 'kontakt_id')
