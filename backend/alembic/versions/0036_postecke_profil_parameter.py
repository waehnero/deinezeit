"""Postecke: Bild-Parameter je Social-Media-Profil

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-20

Erweiterung social_profile:
  - bild_format (String) — Zielformat der Foto-Ausspielung ("original",
    "1:1", "4:5", "16:9", "9:16"); mittiger Zuschnitt beim Teilen/Download
  - bild_filter (String) — vordefinierter Foto-Filter ("kein", "brillant",
    "warm", "kuehl", "kontrast", "sw") für gleichbleibende Anzeigequalität

Die Originalfotos bleiben unverändert gespeichert; Zuschnitt und Filter
werden erst bei der Ausspielung angewendet. Neue Kanäle (TikTok, YouTube,
WhatsApp, X, Threads, Google Unternehmensprofil, Pinterest) brauchen keine
Migration — die Kanal-Spalte ist ein freier String.
"""
from alembic import op
import sqlalchemy as sa

revision = '0036'
down_revision = '0035'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_profile',
                  sa.Column('bild_format', sa.String(length=10),
                            nullable=False, server_default='original'))
    op.add_column('social_profile',
                  sa.Column('bild_filter', sa.String(length=30),
                            nullable=False, server_default='kein'))


def downgrade():
    op.drop_column('social_profile', 'bild_filter')
    op.drop_column('social_profile', 'bild_format')
