"""Postecke: Video-Standbild (Poster) für die Vorschau

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-26

Erweiterung social_post_videos:
  - poster_key (String) — Objektspeicher-Schlüssel des beim Upload per ffmpeg
                          erzeugten Standbilds (erstes Frame, JPEG). Ermöglicht
                          eine Vorschau unabhängig vom Video-Format des Browsers.
"""
from alembic import op
import sqlalchemy as sa

revision = '0041'
down_revision = '0040'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_post_videos',
                  sa.Column('poster_key', sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column('social_post_videos', 'poster_key')
