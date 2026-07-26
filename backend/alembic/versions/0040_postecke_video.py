"""Postecke: Video-Post (Etappe „Video + Instagram", Teilschritt 1)

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-26

Neue Tabelle:
  - social_post_videos  Ein Video je Post (max. eines; kein Misch-Post
                        Foto+Video). Die 1:1-Beziehung ist über die
                        eindeutige post_id abgesichert.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0040'
down_revision = '0039'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'social_post_videos',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('post_id', UUID(as_uuid=True),
                  sa.ForeignKey('social_posts.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('filename', sa.String(length=300), nullable=False),
        sa.Column('mimetype', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    # unique = genau ein Video je Post (kein Misch-Post, keine Duplikate)
    op.create_index('ix_social_post_videos_post', 'social_post_videos',
                    ['post_id'], unique=True)


def downgrade():
    op.drop_index('ix_social_post_videos_post', table_name='social_post_videos')
    op.drop_table('social_post_videos')
