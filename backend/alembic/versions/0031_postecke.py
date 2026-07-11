"""Postecke: Social-Media-Profile, Posts und Fotos (Etappe 1)

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-10

Neue Tabellen:
  - social_profile     Social-Media-Konten mit Stil-Prompt je Kanal
  - social_posts       vorbereitete Posts (Status-Workflow, Planungszeitpunkt)
  - social_post_fotos  Fotos je Post (Dateien im Objektspeicher)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'social_profile',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('owner_user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('kanal', sa.String(length=30), nullable=False),
        sa.Column('stil_prompt', sa.Text(), nullable=True),
        sa.Column('zugang_enc', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_social_profile_owner', 'social_profile', ['owner_user_id'])

    op.create_table(
        'social_posts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('owner_user_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('profil_id', UUID(as_uuid=True),
                  sa.ForeignKey('social_profile.id', ondelete='SET NULL'), nullable=True),
        sa.Column('titel', sa.String(length=300), nullable=True),
        sa.Column('beschreibung', sa.Text(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('hashtags', sa.Text(), nullable=True),
        sa.Column('ort', sa.String(length=300), nullable=True),
        sa.Column('gefuehl', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='entwurf'),
        sa.Column('geplant_am', sa.DateTime(timezone=True), nullable=True),
        sa.Column('veroeffentlicht_am', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ki_model', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_social_posts_owner', 'social_posts', ['owner_user_id'])
    op.create_index('ix_social_posts_status', 'social_posts', ['status'])
    op.create_index('ix_social_posts_geplant', 'social_posts', ['geplant_am'])

    op.create_table(
        'social_post_fotos',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('post_id', UUID(as_uuid=True),
                  sa.ForeignKey('social_posts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('storage_key', sa.String(length=500), nullable=False),
        sa.Column('filename', sa.String(length=300), nullable=False),
        sa.Column('mimetype', sa.String(length=100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_social_post_fotos_post', 'social_post_fotos', ['post_id'])


def downgrade():
    op.drop_index('ix_social_post_fotos_post', table_name='social_post_fotos')
    op.drop_table('social_post_fotos')
    op.drop_index('ix_social_posts_geplant', table_name='social_posts')
    op.drop_index('ix_social_posts_status', table_name='social_posts')
    op.drop_index('ix_social_posts_owner', table_name='social_posts')
    op.drop_table('social_posts')
    op.drop_index('ix_social_profile_owner', table_name='social_profile')
    op.drop_table('social_profile')
