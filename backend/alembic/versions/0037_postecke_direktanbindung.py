"""Postecke: Direktanbindung Facebook-Seiten (Etappe 3)

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-20

Erweiterung social_posts:
  - extern_url    (String) — URL des direkt veröffentlichten Beitrags
  - publish_error (Text)   — letzter Fehler des Publish-Workers (Post bleibt
                             "geplant" und wird erneut versucht)

Die Zugangsdaten je Profil (Seiten-ID + Page-Access-Token) liegen
verschlüsselt im bereits vorhandenen Feld social_profile.zugang_enc —
dafür ist keine Schemaänderung nötig.
"""
from alembic import op
import sqlalchemy as sa

revision = '0037'
down_revision = '0036'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('social_posts', sa.Column('extern_url', sa.String(length=500), nullable=True))
    op.add_column('social_posts', sa.Column('publish_error', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('social_posts', 'publish_error')
    op.drop_column('social_posts', 'extern_url')
