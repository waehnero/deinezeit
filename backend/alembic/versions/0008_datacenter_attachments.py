"""Datacenter: Anhänge-Tabelle (Dateien + Links)

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'attachments',
        sa.Column('id',           UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('entity_type',  sa.String(50),  nullable=False),   # kontakt, projekt, zeiterfassung
        sa.Column('entity_id',    UUID(as_uuid=True), nullable=False),
        sa.Column('type',         sa.String(20),  nullable=False),   # file | link

        # Für type=file (MinIO)
        sa.Column('storage_key',  sa.String(500), nullable=True),    # Pfad in MinIO
        sa.Column('filename',     sa.String(255), nullable=True),
        sa.Column('filesize',     sa.BigInteger, nullable=True),     # Bytes
        sa.Column('mimetype',     sa.String(255), nullable=True),

        # Für type=link (externe Cloud-Links)
        sa.Column('link_url',     sa.Text,        nullable=True),
        sa.Column('link_provider',sa.String(50),  nullable=True),    # nextcloud, onedrive, googledrive, etc.

        # Gemeinsam
        sa.Column('display_name', sa.String(255), nullable=False),   # Anzeigename
        sa.Column('description',  sa.Text,        nullable=True),    # Optionale Beschreibung

        # Share-Link
        sa.Column('share_token',      sa.String(64),  nullable=True, unique=True),
        sa.Column('share_expires_at', sa.DateTime(timezone=True), nullable=True),

        # Metadaten
        sa.Column('uploaded_by',  UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at',   sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indizes für schnelle Abfragen
    op.create_index('ix_attachments_entity', 'attachments', ['entity_type', 'entity_id'])
    op.create_index('ix_attachments_share_token', 'attachments', ['share_token'])


def downgrade():
    op.drop_index('ix_attachments_share_token')
    op.drop_index('ix_attachments_entity')
    op.drop_table('attachments')
